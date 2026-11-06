"""The theme choice (#359, #447): the color tokens in ``style.css``, their contrast, the
head script that applies a saved choice before first paint, the toggle's icons, and the
toggle and store in the shared layout.

What these tests read is the shipped source: the stylesheet, the installed Dash bundles
and the app. What the browser does with them (no flash, persistence, following the
device, the store triggering a chart's callback) is ``tests/e2e/test_dashboard_e2e_theme.py``'s.
"""

from __future__ import annotations

import html.parser
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

import dash
import pytest

from explore import api, components, labels
from explore import app as appmod
from tests.unit.test_dashboard_app import offline_client

STYLESHEET = Path(appmod.__file__).parent / "assets" / "style.css"
DCC_BUNDLE = Path(dash.__file__).parent / "dcc" / "dash_core_components.js"
RENDERER_BUNDLE = Path(dash.__file__).parent / "dash-renderer" / "build"

#: The closed list of color tokens, by role (``style.css``'s header comment). E14-S3
#: (#432) appends its chart tokens here; a token is never renamed once a chart reads it.
TOKENS: tuple[str, ...] = (
    "--page",
    "--text",
    "--text-secondary",
    "--text-faint",
    "--accent",
    "--on-accent",
    "--rule",
    "--callout",
    "--callout-edge",
    "--text-muted",
    "--surface",
    "--border",
    "--disabled",
    "--hover",
    "--active",
)

#: The one non-color custom property, declared in the light block.
NOT_COLORS = frozenset({"--measure"})

#: Each light control token, and the Dash variable whose light default it copies: in
#: light, Dash's own values paint the controls, so the tokens must equal them.
LIGHT_COPIES = {
    "--text-muted": "--Dash-Text-Weak",
    "--surface": "--Dash-Fill-Inverse-Strong",
    "--border": "--Dash-Stroke-Strong",
    "--disabled": "--Dash-Fill-Disabled",
    "--hover": "--Dash-Fill-Primary-Hover",
    "--active": "--Dash-Fill-Primary-Active",
}

DARK_MEDIA = "@media (prefers-color-scheme: dark)"
LIGHT = (None, ":root")
MEDIA_DARK = (DARK_MEDIA, ':root:not([data-theme="light"])')
EXPLICIT_DARK = (None, ':root[data-theme="dark"]')
PALETTE_BLOCKS = (LIGHT, MEDIA_DARK, EXPLICIT_DARK)


@pytest.fixture(autouse=True)
def _offline_process_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "CLIENT", offline_client())


# --- reading CSS -----------------------------------------------------------------------


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


Rule = tuple[str | None, str, str]


def rules(css: str) -> list[Rule]:
    """Every declaration block in ``css``: its enclosing at-rule's prelude (or
    ``None``), its selector, its body. ``css`` is comment-free."""
    found: list[Rule] = []
    stack: list[tuple[str, int]] = []
    start = 0
    for i, char in enumerate(css):
        if char == "{":
            stack.append((css[start:i].strip(), i + 1))
            start = i + 1
        elif char == "}":
            prelude, body_start = stack.pop()
            body = css[body_start:i]
            if "{" not in body:
                found.append((stack[-1][0] if stack else None, prelude, body))
            start = i + 1
    assert not stack, "unbalanced braces"
    return found


def declarations(body: str) -> list[tuple[str, str]]:
    pairs = []
    for part in body.split(";"):
        if part.strip():
            name, _, value = part.partition(":")
            pairs.append((name.strip(), " ".join(value.split())))
    return pairs


def shipped_rules() -> list[Rule]:
    return rules(strip_comments(STYLESHEET.read_text(encoding="utf-8")))


def block(key: tuple[str | None, str]) -> dict[str, str]:
    found = [
        body
        for context, selector, body in shipped_rules()
        if (context, selector) == key
    ]
    assert len(found) == 1, (key, len(found))
    return dict(declarations(found[0]))


def dash_light_defaults() -> dict[str, str]:
    """The installed dcc's bare ``:root`` declarations (its light defaults)."""
    # The bundle carries its CSS as JS strings, so a newline is the two characters \n.
    bundle = DCC_BUNDLE.read_text(encoding="utf-8")
    blocks = re.findall(r":root \{((?:\\n[^{}]*?)*)\}", bundle)
    assert blocks, "Dash no longer declares its variables on a bare :root"
    values: dict[str, str] = {}
    for text in blocks:
        for name, value in re.findall(r"(--Dash-[\w-]+):\s*([^;]+);", text):
            values[name] = " ".join(value.split())
    return values


# --- color literals --------------------------------------------------------------------

#: CSS Color 4's named colors.
NAMED_COLORS = frozenset(
    [
        "aliceblue",
        "antiquewhite",
        "aqua",
        "aquamarine",
        "azure",
        "beige",
        "bisque",
        "black",
        "blanchedalmond",
        "blue",
        "blueviolet",
        "brown",
        "burlywood",
        "cadetblue",
        "chartreuse",
        "chocolate",
        "coral",
        "cornflowerblue",
        "cornsilk",
        "crimson",
        "cyan",
        "darkblue",
        "darkcyan",
        "darkgoldenrod",
        "darkgray",
        "darkgreen",
        "darkgrey",
        "darkkhaki",
        "darkmagenta",
        "darkolivegreen",
        "darkorange",
        "darkorchid",
        "darkred",
        "darksalmon",
        "darkseagreen",
        "darkslateblue",
        "darkslategray",
        "darkslategrey",
        "darkturquoise",
        "darkviolet",
        "deeppink",
        "deepskyblue",
        "dimgray",
        "dimgrey",
        "dodgerblue",
        "firebrick",
        "floralwhite",
        "forestgreen",
        "fuchsia",
        "gainsboro",
        "ghostwhite",
        "gold",
        "goldenrod",
        "gray",
        "green",
        "greenyellow",
        "grey",
        "honeydew",
        "hotpink",
        "indianred",
        "indigo",
        "ivory",
        "khaki",
        "lavender",
        "lavenderblush",
        "lawngreen",
        "lemonchiffon",
        "lightblue",
        "lightcoral",
        "lightcyan",
        "lightgoldenrodyellow",
        "lightgray",
        "lightgreen",
        "lightgrey",
        "lightpink",
        "lightsalmon",
        "lightseagreen",
        "lightskyblue",
        "lightslategray",
        "lightslategrey",
        "lightsteelblue",
        "lightyellow",
        "lime",
        "limegreen",
        "linen",
        "magenta",
        "maroon",
        "mediumaquamarine",
        "mediumblue",
        "mediumorchid",
        "mediumpurple",
        "mediumseagreen",
        "mediumslateblue",
        "mediumspringgreen",
        "mediumturquoise",
        "mediumvioletred",
        "midnightblue",
        "mintcream",
        "mistyrose",
        "moccasin",
        "navajowhite",
        "navy",
        "oldlace",
        "olive",
        "olivedrab",
        "orange",
        "orangered",
        "orchid",
        "palegoldenrod",
        "palegreen",
        "paleturquoise",
        "palevioletred",
        "papayawhip",
        "peachpuff",
        "peru",
        "pink",
        "plum",
        "powderblue",
        "purple",
        "rebeccapurple",
        "red",
        "rosybrown",
        "royalblue",
        "saddlebrown",
        "salmon",
        "sandybrown",
        "seagreen",
        "seashell",
        "sienna",
        "silver",
        "skyblue",
        "slateblue",
        "slategray",
        "slategrey",
        "snow",
        "springgreen",
        "steelblue",
        "tan",
        "teal",
        "thistle",
        "tomato",
        "turquoise",
        "violet",
        "wheat",
        "white",
        "whitesmoke",
        "yellow",
        "yellowgreen",
    ]
)

#: CSS Color 4's system colors (and the deprecated ones browsers still honor).
SYSTEM_COLORS = frozenset(
    name.lower()
    for name in [
        "AccentColor",
        "AccentColorText",
        "ActiveText",
        "ButtonBorder",
        "ButtonFace",
        "ButtonText",
        "Canvas",
        "CanvasText",
        "Field",
        "FieldText",
        "GrayText",
        "Highlight",
        "HighlightText",
        "LinkText",
        "Mark",
        "MarkText",
        "SelectedItem",
        "SelectedItemText",
        "VisitedText",
        "ActiveBorder",
        "ActiveCaption",
        "AppWorkspace",
        "Background",
        "ButtonHighlight",
        "ButtonShadow",
        "CaptionText",
        "InactiveBorder",
        "InactiveCaption",
        "InactiveCaptionText",
        "InfoBackground",
        "InfoText",
        "Menu",
        "MenuText",
        "Scrollbar",
        "ThreeDDarkShadow",
        "ThreeDFace",
        "ThreeDHighlight",
        "ThreeDLightShadow",
        "ThreeDShadow",
        "Window",
        "WindowFrame",
        "WindowText",
    ]
)

#: Color keywords a rule may name: none is a palette value.
ALLOWED_KEYWORDS = frozenset({"currentcolor", "transparent", "inherit"})

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
COLOR_FUNCTION = re.compile(
    r"\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix)\(", re.IGNORECASE
)


def color_literals(css: str) -> list[str]:
    """Every color literal in a declaration value outside the three palette blocks:
    ``selector: property: value`` for each offender. Comments and selectors are never
    scanned, nor quoted strings and the name a ``var()`` references; its fallback is."""
    offenders = []
    for context, selector, body in rules(strip_comments(css)):
        if (context, selector) in PALETTE_BLOCKS:
            continue
        for name, value in declarations(body):
            # Only the reference itself is dropped: a var() fallback is scanned.
            unquoted = re.sub(r"(['\"]).*?\1", "", value)
            scanned = re.sub(r"var\(\s*--[\w-]+\s*,?", "", unquoted)
            words = {w.lower() for w in re.findall(r"[A-Za-z][\w-]*", scanned)}
            named = (words & (NAMED_COLORS | SYSTEM_COLORS)) - ALLOWED_KEYWORDS
            if HEX.search(scanned) or COLOR_FUNCTION.search(scanned) or named:
                offenders.append(f"{selector}: {name}: {value}")
    return offenders


# --- contrast --------------------------------------------------------------------------

Color = tuple[float, float, float, float]


def parse_color(value: str) -> Color:
    value = value.strip()
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(d * 2 for d in digits)
        assert len(digits) == 6, value
        red, green, blue = (float(int(digits[i : i + 2], 16)) for i in (0, 2, 4))
        return (red, green, blue, 1.0)
    match = re.fullmatch(
        r"rgba?\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)", value
    )
    assert match, value
    r, g, b = (float(match.group(i)) for i in (1, 2, 3))
    return (r, g, b, float(match.group(4) or 1))


def over(top: Color, bottom: Color) -> Color:
    """``top`` composited over an opaque ``bottom``."""
    alpha = top[3]
    return (
        top[0] * alpha + bottom[0] * (1 - alpha),
        top[1] * alpha + bottom[1] * (1 - alpha),
        top[2] * alpha + bottom[2] * (1 - alpha),
        1.0,
    )


def luminance(color: Color) -> float:
    def channel(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in color[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(foreground: Color, background: Color) -> float:
    """WCAG 2's contrast ratio, the foreground composited over the background."""
    assert background[3] == 1.0, "composite the background over the page first"
    lighter, darker = sorted(
        (luminance(over(foreground, background)), luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def resolve(value: str, palette: dict[str, str]) -> str:
    match = re.fullmatch(r"var\((--[\w-]+)\)", value)
    return palette[match.group(1)] if match else value


def painted(theme: str, variable: str) -> str:
    """The value a ``--Dash-*`` variable paints with in ``theme``: Dash's own default
    in light, the dark blocks' mapping onto a token in dark."""
    if theme == "light":
        return dash_light_defaults()[variable]
    dark = block(EXPLICIT_DARK)
    return resolve(dark[variable], dark)


#: Text the page paints, on what it paints it on: (foreground token, background token).
PAGE_PAIRS = (
    ("--text", "--page"),
    ("--text-secondary", "--page"),
    ("--text-faint", "--page"),
    ("--accent", "--page"),
    ("--on-accent", "--accent"),
    ("--text", "--callout"),
)

#: Control text Dash paints, on the control's background and on the page (slider marks
#: and checklist labels sit on the page).
CONTROL_PAIRS = (
    ("--Dash-Text-Primary", "--Dash-Fill-Inverse-Strong"),
    ("--Dash-Text-Weak", "--Dash-Fill-Inverse-Strong"),
    ("--Dash-Text-Primary", None),
    ("--Dash-Text-Weak", None),
)

AA = 4.5

#: WCAG 1.4.11's ratio for a graphic or a focus indicator against what is next to it.
NON_TEXT = 3.0

#: The theme toggle's selected-position rule (#447), as its selector reads in
#: ``style.css``: one rule for the three positions, each under its ``data-theme``.
SELECTED = (
    ':root[data-theme="dark"] #theme-dark, :root:not([data-theme]) #theme-auto, '
    ':root[data-theme="light"] #theme-light'
)

#: What the theme toggle paints (#447), read from its own rules so the pairs cannot
#: drift from the stylesheet: (selector, the property naming the foreground token, the
#: property naming the background token, or None for the page). The unselected
#: button's background is transparent, so its icon sits on the page.
TOGGLE_PAINT = (
    (".theme-control button", "color", None),
    (".theme-control button:hover", "color", None),
    (SELECTED, "color", "background"),
    (SELECTED, "background", None),
    (".theme-control button:focus-visible", "outline", None),
)


def toggle_rule(selector: str) -> dict[str, str]:
    """The declarations of the one shipped rule whose selector reads ``selector``."""
    found = [
        body
        for _, prelude, body in shipped_rules()
        if " ".join(prelude.split()) == selector
    ]
    assert len(found) == 1, (selector, len(found))
    return dict(declarations(found[0]))


def token_in(value: str) -> str:
    """The one token a declaration value names through ``var()``."""
    (token,) = re.findall(r"var\((--[\w-]+)\)", value)
    return str(token)


# --- the tokens ------------------------------------------------------------------------


class TestThemeTokens:
    def test_each_palette_block_declares_exactly_the_closed_list(self) -> None:
        assert len(set(TOKENS)) == len(TOKENS)
        for key in PALETTE_BLOCKS:
            declared = {
                name
                for name in block(key)
                if name.startswith("--") and not name.startswith("--Dash-")
            }
            # --measure, the one non-color, is the light block's alone.
            expected = set(TOKENS) | (NOT_COLORS if key == LIGHT else set())
            assert declared == expected, key

    def test_the_light_block_is_the_one_bare_root_and_sets_color_scheme(self) -> None:
        assert block(LIGHT)["color-scheme"] == "light"
        assert block(MEDIA_DARK)["color-scheme"] == "dark"
        assert block(EXPLICIT_DARK)["color-scheme"] == "dark"
        # The light block maps none of Dash's variables: in light, Dash's own paint.
        assert not any(name.startswith("--Dash-") for name in block(LIGHT))

    def test_the_header_comment_lists_exactly_the_closed_list(self) -> None:
        css = STYLESHEET.read_text(encoding="utf-8")
        header = css[: css.index("*/")]
        listed = re.findall(r"^ {5}(--[\w-]+) {2,}\S", header, flags=re.M)
        assert len(listed) == len(set(listed))
        assert set(listed) == set(TOKENS)

    def test_the_checked_pill_outranks_dashs_hover_and_focus_color(self) -> None:
        # Dash's rule (0,3,1), a private of the installed dcc, injected after our
        # sheet: it would color a hovered or focused option's text with the accent.
        # The bundle carries its CSS as JS strings: a newline is the two characters \n.
        raw = DCC_BUNDLE.read_text(encoding="utf-8").replace("\\n", " ")
        bundle = " ".join(raw.split())
        option = ".dash-options-list-option:not(:has(input[disabled]))"
        assert f"{option}:hover, {option}:focus-within {{" in bundle
        assert "color: var(--Dash-Fill-Interactive-Strong);" in bundle
        # Ours, (0,3,2), keeps the checked pill's text on --on-accent in both states.
        rule = {
            selector.strip(): body
            for _, selectors, body in shipped_rules()
            for selector in selectors.split(",")
        }
        for state in ("hover", "focus-within"):
            body = rule[f".year-buttons label:has(input:checked):{state}"]
            assert dict(declarations(body)) == {"color": "var(--on-accent)"}

    def test_the_two_dark_blocks_are_identical(self) -> None:
        assert block(MEDIA_DARK) == block(EXPLICIT_DARK)

    def test_every_var_reference_names_a_known_token(self) -> None:
        css = strip_comments(STYLESHEET.read_text(encoding="utf-8"))
        referenced = set(re.findall(r"var\(\s*(--[\w-]+)", css))
        assert referenced
        assert referenced <= set(TOKENS) | NOT_COLORS

    def test_each_light_control_token_copies_the_dash_default_it_names(self) -> None:
        defaults = dash_light_defaults()
        light = block(LIGHT)
        assert set(LIGHT_COPIES) <= set(TOKENS)
        for token, variable in LIGHT_COPIES.items():
            assert light[token] == defaults[variable], token

    def test_no_rule_outside_the_palette_blocks_names_a_color(self) -> None:
        assert color_literals(STYLESHEET.read_text(encoding="utf-8")) == []

    @pytest.mark.parametrize(
        "css",
        [
            "a { color: red; }",
            "a { color: #abc; }",
            "a { border: 1px solid #a1b2c3; }",
            "a { background: rgb(1, 2, 3); }",
            "a { color: RGBA(1, 2, 3, 0.5); }",
            "a { color: hsl(10 20% 30%); }",
            "a { color: oklch(0.5 0.1 200); }",
            "a { color: color-mix(in srgb, white, black); }",
            "a { color: CanvasText; }",
            "a { border: 1px solid Tomato; }",
            "@media (min-width: 1px) { a { color: #fff; } }",
            "a { color: var(--text, #f00); }",
            "a { color: var(--text, red); }",
            "a { border-color: var(--rule, rgb(1, 2, 3)); }",
            ":root { --page: #fff; } a { outline-color: navy; }",
        ],
    )
    def test_the_color_lint_flags_a_literal(self, css: str) -> None:
        assert color_literals(css) != []

    @pytest.mark.parametrize(
        "css",
        [
            "#bad, #elections-table { min-width: 0; }",
            "a { color: currentColor; border-color: transparent; }",
            "a { color: inherit; }",
            "a { color: var(--text); }",
            'a { font-family: "Tomato Sans", system-ui; }',
            "/* color: red */ a { color: var(--accent); }",
            ":root { --page: #fff; }",
        ],
    )
    def test_the_color_lint_passes_what_is_no_literal(self, css: str) -> None:
        assert color_literals(css) == []


class TestDarkThemeVariables:
    """#409, now under #359's two dark blocks: each sets every Dash color variable.

    A Dash upgrade that renames, adds or moves one would leave the controls on their
    light defaults in dark mode with nothing else failing, so the installed Dash's
    declarations are read here and compared with what each dark block sets.
    """

    #: Not a color: the dark blocks leave it alone.
    NOT_COLOR_VARIABLES = frozenset({"--Dash-Spacing"})

    @pytest.mark.parametrize(
        "key", [MEDIA_DARK, EXPLICIT_DARK], ids=["media", "explicit"]
    )
    def test_each_dark_block_sets_every_dash_color_variable(
        self, key: tuple[str | None, str]
    ) -> None:
        declared = set(dash_light_defaults()) - self.NOT_COLOR_VARIABLES
        assert {name for name in block(key) if name.startswith("--Dash-")} == declared


class TestThemeContrast:
    """WCAG AA (4.5:1) for text and links in both palettes, over the colors that paint:
    the tokens on the page, and Dash's own values or the dark mapping on the controls.
    An ``rgba`` color is composited over its background first."""

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize(("foreground", "background"), PAGE_PAIRS)
    def test_page_text_meets_aa(
        self, theme: str, foreground: str, background: str
    ) -> None:
        palette = block(LIGHT if theme == "light" else EXPLICIT_DARK)
        page = parse_color(palette["--page"])
        ground = over(parse_color(palette[background]), page)
        ratio = contrast(parse_color(palette[foreground]), ground)
        assert ratio >= AA, (theme, foreground, background, round(ratio, 2))

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize(("foreground", "background"), CONTROL_PAIRS)
    def test_control_text_meets_aa(
        self, theme: str, foreground: str, background: str | None
    ) -> None:
        palette = block(LIGHT if theme == "light" else EXPLICIT_DARK)
        page = parse_color(palette["--page"])
        ground = (
            page
            if background is None
            else over(parse_color(painted(theme, background)), page)
        )
        ratio = contrast(parse_color(painted(theme, foreground)), ground)
        assert ratio >= AA, (theme, foreground, background, round(ratio, 2))

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize(("selector", "foreground", "background"), TOGGLE_PAINT)
    def test_the_theme_toggle_meets_non_text_contrast(
        self, theme: str, selector: str, foreground: str, background: str | None
    ) -> None:
        # Icons and the focus ring are graphics: 3:1 (WCAG 1.4.11), in each state.
        rule = toggle_rule(selector)
        palette = block(LIGHT if theme == "light" else EXPLICIT_DARK)
        page = parse_color(palette["--page"])
        ground = (
            page
            if background is None
            else over(parse_color(palette[token_in(rule[background])]), page)
        )
        ratio = contrast(parse_color(palette[token_in(rule[foreground])]), ground)
        assert ratio >= NON_TEXT, (theme, selector, foreground, round(ratio, 2))

    def test_the_unselected_button_paints_on_the_page(self) -> None:
        # What makes the "on the page" pairs above true: no fill and no UA button look.
        rule = toggle_rule(".theme-control button")
        assert rule["background"] == "transparent"
        assert rule["appearance"] == "none"
        assert rule["border"] == "0"

    def test_the_contrast_helper_fails_low_contrast_and_composites_alpha(self) -> None:
        white = (255.0, 255.0, 255.0, 1.0)
        assert contrast(parse_color("#000"), white) == pytest.approx(21)
        assert contrast(parse_color("#ccc"), white) < AA
        # Black at 10% alpha on white is nearly white, not black.
        assert contrast(parse_color("rgba(0, 0, 0, 0.1)"), white) < 1.5


# --- the head script -------------------------------------------------------------------


class HeadScripts(html.parser.HTMLParser):
    """The scripts and stylesheet links of a page, in document order, with whether each
    sits inside ``<head>``."""

    def __init__(self, body: str) -> None:
        super().__init__()
        self.items: list[tuple[str, bool, str]] = []
        self._in_head = False
        self._script: list[str] | None = None
        self.feed(body)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "head":
            self._in_head = True
        elif tag == "script" and not dict(attrs).get("src"):
            self._script = []
        elif tag == "link" and dict(attrs).get("rel") == "stylesheet":
            self.items.append(("stylesheet", self._in_head, ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self._in_head = False
        elif tag == "script" and self._script is not None:
            self.items.append(("script", self._in_head, "".join(self._script)))
            self._script = None

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script.append(data)


def inner(script: str) -> str:
    return script.removeprefix("<script>").removesuffix("</script>")


class TestThemeHeadScript:
    @pytest.mark.parametrize(
        "path", ["/", "/elections", "/election/1824", "/no-such-view", "/state/ZZ"]
    )
    def test_every_index_response_runs_the_theme_script_before_any_stylesheet(
        self, path: str
    ) -> None:
        body = appmod.server.test_client().get(path).get_data(as_text=True)
        items = HeadScripts(body).items
        themed = [
            i
            for i, item in enumerate(items)
            if item[2] == inner(appmod.THEME_HEAD_SCRIPT)
        ]
        assert len(themed) == 1, path
        (at,) = themed
        assert items[at][1], "the theme script is not in <head>"
        stylesheets = [i for i, item in enumerate(items) if item[0] == "stylesheet"]
        assert stylesheets and at < min(stylesheets)

    @pytest.mark.parametrize(
        ("path", "own"),
        [
            ("/", '<link rel="canonical"'),
            ("/elections", '<link rel="canonical"'),
            ("/no-such-view", '<meta name="robots"'),
        ],
    )
    def test_the_head_runs_dash_metas_then_the_theme_script_then_the_cards(
        self, path: str, own: str
    ) -> None:
        # The order interpolate_index states and dashboard/CLAUDE.md records: Dash's
        # own metas (charset first), the theme script, the card tags, then ours.
        body = appmod.server.test_client().get(path).get_data(as_text=True)
        positions = [
            body.find('<meta charset="UTF-8">'),
            body.find(appmod.THEME_HEAD_SCRIPT),
            body.find('<meta name="description"'),  # the first card tag
            body.find(own),
        ]
        assert -1 not in positions, (path, positions)
        assert positions == sorted(positions), (path, positions)

    def test_the_head_script_applies_only_an_explicit_choice_and_survives_storage(
        self,
    ) -> None:
        script = appmod.THEME_HEAD_SCRIPT
        assert script.startswith("<script>") and script.endswith("</script>")
        # In the toggle's order since #447 (Dark, Auto, Light): the same behavior.
        assert appmod.THEME_EXPLICIT == ("dark", "light")
        assert '["dark", "light"]' in script
        assert f'"{appmod.THEME_STORAGE_KEY}"' in script
        assert re.search(r"try \{.*localStorage.*\} catch", script)
        assert script.count("setAttribute") == 1

    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/elections",
            "/election/1824",
            "/states",
            "/candidate/andrew-jackson",
            "/no-such-view",
        ],
    )
    def test_meta_charset_sits_in_the_first_1024_bytes(self, path: str) -> None:
        # The HTML encoding prescan reads only the first 1024 bytes; the theme script
        # follows Dash's own metas, so it never pushes <meta charset> past them.
        body = appmod.server.test_client().get(path).get_data()
        start = body.find(b'<meta charset="UTF-8">')
        assert start >= 0
        assert start + len(b'<meta charset="UTF-8">') <= 1024, start

    def test_no_inline_script_can_close_its_own_tag(self) -> None:
        # json.dumps does not escape "</", and Dash writes an inline clientside
        # callback into an inline <script> too.
        assert "</" not in inner(appmod.THEME_HEAD_SCRIPT)
        assert "</" not in appmod.THEME_CALLBACK


# --- the control and the store ---------------------------------------------------------


def nodes(node: Any) -> list[Any]:
    found = [node]
    children = getattr(node, "children", None)
    if isinstance(children, list | tuple):
        for child in children:
            found.extend(nodes(child))
    elif children is not None and not isinstance(children, str):
        found.extend(nodes(children))
    return found


def texts(node: Any) -> list[str]:
    found: list[str] = []
    for item in nodes(node):
        if isinstance(item, str):
            found.append(item)
        elif isinstance(getattr(item, "children", None), str):
            found.append(item.children)
        for option in getattr(item, "options", None) or []:
            found.append(str(option["label"]))
    return found


class TestThemeControl:
    def test_the_layout_holds_the_toggle_above_main_and_the_store(self) -> None:
        layout = appmod.app.layout
        header, main, store = layout.children
        assert type(header).__name__ == "Header"
        assert type(main).__name__ == "Main" and main.className == "explore"
        assert main.children is dash.page_container
        assert type(store).__name__ == "Store"
        assert store.id == components.THEME_STORE_ID
        assert store.storage_type == "memory"
        (group,) = [
            n
            for n in nodes(header)
            if getattr(n, "id", None) == components.THEME_CONTROL_ID
        ]
        assert type(group).__name__ == "Div"
        assert group.role == "group"
        assert getattr(group, "aria-label") == labels.THEME_CONTROL
        # #444's markup is not inherited: no dcc choice control anywhere in the header.
        assert not [
            n for n in nodes(header) if type(n).__name__ in ("RadioItems", "Checklist")
        ]

    def test_the_toggle_is_three_named_buttons_dark_auto_light(self) -> None:
        group = appmod.app.layout.children[0].children
        assert list(labels.THEME_CHOICES) == ["dark", labels.THEME_AUTO, "light"]
        assert [type(b).__name__ for b in group.children] == ["Button"] * 3
        assert [b.id for b in group.children] == list(
            components.THEME_BUTTON_IDS.values()
        )
        for value, button in zip(labels.THEME_CHOICES, group.children, strict=True):
            assert button.id == f"theme-{value}"
            assert button.type == "button"
            assert button.title == labels.THEME_TITLES[value]
            # Strings, Dash's prop type: Auto pressed until the first call corrects it.
            pressed = "true" if value == labels.THEME_AUTO else "false"
            assert getattr(button, "aria-pressed") == pressed
            icon, name = button.children
            assert icon.className == f"theme-icon theme-icon-{value}"
            assert getattr(icon, "aria-hidden") == "true"
            assert icon.children is None
            assert name.className == "visually-hidden"
            assert name.children == labels.THEME_CHOICES[value]
        assert getattr(group, "persistence", None) in (None, False)

    def test_the_toggle_shows_only_its_names_and_no_raw_value(self) -> None:
        header = appmod.app.layout.children[0]
        shown = texts(header)
        assert shown == list(labels.THEME_CHOICES.values())
        assert not any("_" in text for text in shown)
        assert not set(shown) & set(labels.THEME_CHOICES)  # never the internal value

    def test_the_titles_name_each_position_and_auto_says_what_it_does(self) -> None:
        assert list(labels.THEME_TITLES) == list(labels.THEME_CHOICES)
        for value in ("dark", "light"):
            assert labels.THEME_TITLES[value] == labels.THEME_CHOICES[value]
        auto = labels.THEME_TITLES[labels.THEME_AUTO]
        assert auto.startswith(labels.THEME_CHOICES[labels.THEME_AUTO] + ":")

    def test_one_clientside_callback_drives_the_store_and_never_the_url(self) -> None:
        assert appmod.server.test_client().get("/").status_code == 200
        buttons = list(components.THEME_BUTTON_IDS.values())
        theme = [
            key
            for key, spec in appmod.app.callback_map.items()
            if components.THEME_STORE_ID in key
            or any(i["id"] == components.THEME_STORE_ID for i in spec["inputs"])
        ]
        assert theme == [
            f"..{components.THEME_STORE_ID}.data..."
            + "...".join(f"{b}.aria-pressed" for b in buttons)
            + ".."
        ]
        spec = appmod.app.callback_map[theme[0]]
        # The three buttons in the toggle's order, then the store as the last state:
        # THEME_CALLBACK reads the store as its last argument.
        assert spec["inputs"] == [{"id": b, "property": "n_clicks"} for b in buttons]
        assert spec["state"] == [{"id": components.THEME_STORE_ID, "property": "data"}]
        assert "callback" not in spec  # clientside: no Python function runs
        # Nothing the theme feeds writes a URL: the theme never enters it or og:url.
        for key, other in appmod.app.callback_map.items():
            fed = {i["id"] for i in other["inputs"]} & {
                components.THEME_STORE_ID,
                components.THEME_CONTROL_ID,
                *buttons,
            }
            if fed:
                assert ".search" not in key and ".pathname" not in key, key

    def test_the_callback_maps_each_button_and_sets_no_attribute_on_one(self) -> None:
        script = appmod.THEME_CALLBACK
        # React owns aria-pressed: the one attribute the callback sets is data-theme.
        assert script.count("setAttribute") == 1
        assert 'root.setAttribute("data-theme", choice)' in script
        assert "getElementById" not in script and "querySelector" not in script
        # The choice is the triggered button, through the one id map.
        mapping = {b: v for v, b in components.THEME_BUTTON_IDS.items()}
        assert f"var byButton = {json.dumps(mapping)};" in script
        assert "callback_context.triggered_id" in script
        # aria-pressed follows <html data-theme>, never the theme in effect.
        assert re.search(r'var applied = root\.getAttribute\("data-theme"\);', script)
        assert f"var choices = {json.dumps(list(labels.THEME_CHOICES))};" in script

    def test_the_served_renderer_defines_dash_clientside_set_props(self) -> None:
        # The listener pushes the theme in effect with dash_clientside.set_props. The
        # string "set_props" also names a worker message type in the bundle, so the
        # assignment itself is matched, in the minified bundle production serves.
        bundle = (RENDERER_BUNDLE / "dash_renderer.min.js").read_text(encoding="utf-8")
        assert re.search(
            r"(\w+)=window\.dash_clientside=window\.dash_clientside\|\|\{\};"
            r"\1\.set_props=function",
            bundle,
        )


# --- the toggle's icons and selected position --------------------------------------------


def icon_uris() -> dict[str, str]:
    """Each icon class's mask data URI, decoded, from both of its declarations."""
    found = {}
    for value in labels.THEME_CHOICES:
        rule = toggle_rule(f".theme-icon-{value}")
        assert rule["-webkit-mask-image"] == rule["mask-image"], value
        match = re.fullmatch(r'url\("data:image/svg\+xml,([^"]*)"\)', rule["mask-image"])
        assert match, value
        found[value] = urllib.parse.unquote(match.group(1))
    return found


class TestThemeIcons:
    def test_each_icon_is_a_prefixed_and_unprefixed_mask_of_the_text_color(self) -> None:
        icon = toggle_rule(".theme-icon")
        assert icon["background-color"] == "currentColor"
        assert icon["forced-color-adjust"] == "none"
        # Chrome and Edge before 120 support only the -webkit- mask.
        for part in ("repeat", "position", "size"):
            assert icon[f"-webkit-mask-{part}"] == icon[f"mask-{part}"], part
        for value in labels.THEME_CHOICES:
            rule = toggle_rule(f".theme-icon-{value}")
            assert set(rule) == {"-webkit-mask-image", "mask-image"}, value
        assert set(icon_uris()) == set(labels.THEME_CHOICES)

    def test_no_icon_names_a_color(self) -> None:
        # The color lint skips quoted strings, so it cannot see inside a data URI.
        for value, svg in icon_uris().items():
            assert svg.startswith("<svg ") and svg.endswith("</svg>"), value
            words = {w.lower() for w in re.findall(r"[A-Za-z][\w-]*", svg)}
            named = (words & (NAMED_COLORS | SYSTEM_COLORS)) - ALLOWED_KEYWORDS
            assert not HEX.search(svg) and not COLOR_FUNCTION.search(svg), value
            assert not named, (value, named)
            # The mask reads alpha: every paint is currentColor or none.
            paints = re.findall(r"(?:fill|stroke)='([^']*)'", svg)
            assert paints and set(paints) <= {"currentColor", "none"}, (value, paints)

    def test_the_icon_scan_flags_a_color(self) -> None:
        for svg in ("<svg fill='#000'/>", "<svg fill='red'/>", "<svg fill='rgb(1,2,3)'/>"):
            words = {w.lower() for w in re.findall(r"[A-Za-z][\w-]*", svg)}
            assert (
                HEX.search(svg)
                or COLOR_FUNCTION.search(svg)
                or (words & NAMED_COLORS) - ALLOWED_KEYWORDS
            ), svg

    def test_tablers_license_ships_beside_the_icons(self) -> None:
        css = STYLESHEET.read_text(encoding="utf-8")
        notice = css.index("Copyright (c) 2020-2024 Paweł Kuna")
        assert "@tabler/icons 3.24.0" in css
        for line in (
            "Permission is hereby granted, free of charge,",
            "The above copyright notice and this permission notice shall be included",
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND',
        ):
            assert css.index(line) > notice, line
        # In the comment just before the icon rules, never in the header comment.
        assert notice > css.index("*/")
        between = css[notice : css.index(".theme-icon {")]
        assert between.count("*/") == 1 and "{" not in between


class TestThemeSelected:
    def test_the_selected_rules_name_exactly_the_button_ids(self) -> None:
        (prelude,) = [
            p
            for _, p, _ in shipped_rules()
            if " ".join(p.split()) == SELECTED
        ]
        conditions = {
            "dark": ':root[data-theme="dark"]',
            labels.THEME_AUTO: ":root:not([data-theme])",
            "light": ':root[data-theme="light"]',
        }
        assert set(conditions) == set(labels.THEME_CHOICES)
        selectors = [" ".join(p.split()) for p in prelude.split(",")]
        assert selectors == [
            f"{conditions[v]} #{components.THEME_BUTTON_IDS[v]}"
            for v in labels.THEME_CHOICES
        ]

    def test_the_selected_position_has_a_cue_that_is_not_a_color(self) -> None:
        # Forced colors drop the fill; the border survives, painted in a system color.
        assert toggle_rule(SELECTED)["border"] == "2px solid transparent"
        assert toggle_rule(".theme-control button")["border"] == "0"

    def test_no_toggle_rule_is_scoped_to_the_site_header(self) -> None:
        # #448 moves the toggle into a navigation bar: its rules name .theme-control.
        for _, prelude, _ in shipped_rules():
            assert not re.search(r"\.site-header\s+\.theme-", prelude), prelude
