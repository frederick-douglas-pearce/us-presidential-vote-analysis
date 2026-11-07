"""The theme choice (#359, #447): the color tokens in ``style.css``, their contrast, the
head script that applies a saved choice before first paint, the toggle's icons, and the
toggle and store in the shared layout.

What these tests read is the shipped source: the stylesheet, the installed Dash bundles
and the app. What the browser does with them (no flash, persistence, following the
device, the store triggering a chart's callback) is ``tests/e2e/test_dashboard_e2e_theme.py``'s.
"""

from __future__ import annotations

import html.parser
import itertools
import json
import math
import re
import urllib.parse
import xml.etree.ElementTree as ET
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
    "--chart-1",
    "--chart-2",
    "--chart-3",
    "--chart-axis",
    "--chart-grid",
    "--chart-reference",
)

#: The non-color custom properties, declared in the light block: the readable measure
#: (#360) and the font stack the page and the charts share (#432).
NOT_COLORS = frozenset({"--measure", "--font-body"})

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

#: The one at-rule whose rules may name system colors (#447's review): forced-colors
#: mode, where the browser replaces author colors and only system colors hold. Not a
#: palette block: it declares no token, and a token there is the author color it fixes.
FORCED_COLORS = "@media (forced-colors: active)"


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


def color_words(text: str, allowed: frozenset[str]) -> list[str]:
    """The color literals in ``text``: hex values, color functions, and named or system
    colors outside ``allowed``. The one scan the stylesheet lint and the icon scan
    share."""
    found = HEX.findall(text) + [m.group(0) for m in COLOR_FUNCTION.finditer(text)]
    words = {w.lower() for w in re.findall(r"[A-Za-z][\w-]*", text)}
    return found + sorted((words & (NAMED_COLORS | SYSTEM_COLORS)) - allowed)


def color_literals(css: str) -> list[str]:
    """Every color literal in a declaration value outside the three palette blocks:
    ``selector: property: value`` for each offender. Comments and selectors are never
    scanned, nor quoted strings and the name a ``var()`` references; its fallback is.
    Inside :data:`FORCED_COLORS` a system color is allowed, and a ``var()`` is not."""
    offenders = []
    for context, selector, body in rules(strip_comments(css)):
        if (context, selector) in PALETTE_BLOCKS:
            continue
        forced = context == FORCED_COLORS
        allowed = ALLOWED_KEYWORDS | SYSTEM_COLORS if forced else ALLOWED_KEYWORDS
        for name, value in declarations(body):
            unquoted = re.sub(r"(['\"]).*?\1", "", value)
            if forced and "var(" in unquoted:
                offenders.append(f"{selector}: {name}: {value}")
                continue
            # Only the reference itself is dropped: a var() fallback is scanned.
            scanned = re.sub(r"var\(\s*--[\w-]+\s*,?", "", unquoted)
            if color_words(scanned, allowed):
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


#: The site navigation's marker rule (#448): the current page's link, or its section's.
MARKED = '.site-nav a[aria-current="page"], .site-nav a[aria-current="true"]'

#: What the site navigation paints (#448), read from its own rules, as TOGGLE_PAINT is:
#: (selector, the property naming the foreground token, the minimum ratio). Every one
#: sits on the page: the bar has no fill. Link text is text (AA); the marker's underline
#: and the focus ring are graphics (3:1).
NAV_PAINT = (
    ("a", "color", 4.5),
    (".site-nav .site-name", "color", 4.5),
    (MARKED, "text-decoration-color", 3.0),
    (".site-nav a:focus-visible", "outline", 3.0),
)


def toggle_rule(selector: str, context: str | None = None) -> dict[str, str]:
    """The declarations of the one shipped rule whose selector reads ``selector``,
    inside the at-rule ``context`` (``None``: at the top level)."""
    found = [
        body
        for at, prelude, body in shipped_rules()
        if at == context and " ".join(prelude.split()) == selector
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
            # The non-colors are the light block's alone.
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
            "a { background-color: ButtonFace; }",
            "@media (forced-colors: active) { a { color: #fff; } }",
            "@media (forced-colors: active) { a { color: red; } }",
            "@media (forced-colors: active) { a { color: var(--text); } }",
            "@media (forced-colors: active) { a { color: var(--text, ButtonText); } }",
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
            "@media (forced-colors: active) { a { color: ButtonText; } }",
            "@media (forced-colors: active) { a { background-color: ButtonFace; } }",
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

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize(("selector", "foreground", "minimum"), NAV_PAINT)
    def test_the_site_navigation_meets_its_contrast(
        self, theme: str, selector: str, foreground: str, minimum: float
    ) -> None:
        rule = toggle_rule(selector)
        palette = block(LIGHT if theme == "light" else EXPLICIT_DARK)
        page = parse_color(palette["--page"])
        ratio = contrast(parse_color(palette[token_in(rule[foreground])]), page)
        assert ratio >= minimum, (theme, selector, foreground, round(ratio, 2))

    def test_the_site_navigation_paints_what_nav_paint_measures(self) -> None:
        # NAV_PAINT's premises (#448's review): the global `a` rule is what colors the
        # nav's links, and nothing behind the bar is filled, so every pair sits on
        # --page. A nav rule that set a color or a fill would paint a pair no test reads.
        # Every context counts, media queries included; the forced-colors block, where
        # system colors repaint everything, names no nav rule at all.
        named = r"\.site-(?:header|nav|name)\b"
        nav_rules = [
            (at, " ".join(prelude.split()), dict(declarations(body)))
            for at, prelude, body in shipped_rules()
            if re.search(named, prelude)
        ]
        assert nav_rules
        assert any(at is not None for at, _, _ in nav_rules)  # the media rules are read
        for at, prelude, rule in nav_rules:
            assert at != FORCED_COLORS, prelude
            assert not {"background", "background-color"} & set(rule), (at, prelude)
            # The site name alone sets a color, NAV_PAINT's second pair.
            if prelude != ".site-nav .site-name":
                assert "color" not in rule, (at, prelude)
        assert toggle_rule(".site-nav .site-name")["color"] == "var(--text)"

    def test_the_bar_layout_declarations_are_pinned(self) -> None:
        # The declarations the e2e fit checks cannot see in every font or at every
        # width (#448's acceptance gate): the full name's breakpoint, the wrap that
        # keeps the toggle on screen when the row is too narrow, and the toggle's
        # 24 px buttons, which keep 16 px of slack at 390 px in CI's DejaVu Sans.
        shown = toggle_rule(".site-name-rest", "@media (min-width: 45rem)")
        assert shown["position"] == "static" and shown["clip-path"] == "none"
        assert [
            at for at, p, _ in shipped_rules() if " ".join(p.split()) == ".site-name-rest"
        ] == [None, "@media (min-width: 45rem)"]
        assert toggle_rule(".site-header")["flex-wrap"] == "wrap"
        assert toggle_rule(".site-nav")["flex-wrap"] == "wrap"
        button = toggle_rule(".theme-control button")
        assert (button["width"], button["height"]) == ("1.5rem", "1.5rem")

    def test_the_rest_of_the_site_name_keeps_its_space(self) -> None:
        # The rest opens with a space, which an absolutely positioned (blockified) box
        # may collapse, so the name would read "Explore— US…" (#448's review). The e2e
        # name check does not discriminate in Chromium, so the declaration is pinned
        # here.
        assert toggle_rule(".site-name-rest")["white-space"] == "pre"
        assert labels.SITE_NAME_REST.startswith(" ")

    def test_the_marker_is_an_underline_not_color_alone(self) -> None:
        # WCAG 1.4.1: the current link differs by a decoration, which forced colors
        # keep, and the other links carry none.
        marked = toggle_rule(MARKED)
        assert marked["text-decoration-line"] == "underline"
        assert marked["text-decoration-thickness"] == "2px"
        assert toggle_rule(".site-nav a")["text-decoration"] == "none"

    @pytest.mark.parametrize(
        ("gap_selector", "focus_selector"),
        [
            (".theme-control", ".theme-control button:focus-visible"),
            (".site-nav", ".site-nav a:focus-visible"),
            (".site-header", ".site-nav a:focus-visible"),
            (".site-header", ".theme-control button:focus-visible"),
        ],
    )
    def test_each_gap_clears_the_focus_ring(
        self, gap_selector: str, focus_selector: str
    ) -> None:
        # A ring reaches offset plus width past its control. Only one control is
        # focused at a time, so the risk is one ring landing on a neighbor, such as a
        # selected toggle position's accent fill, accent on accent (1:1): the gap must
        # exceed one ring's reach (API docs then Dark sit across the header's gap, #448).
        gap = toggle_rule(gap_selector)["gap"]
        focus = toggle_rule(focus_selector)
        width = re.fullmatch(r"(\d+)px solid var\(--[\w-]+\)", focus["outline"])
        offset = re.fullmatch(r"(\d+)px", focus["outline-offset"])
        rem = re.fullmatch(r"([\d.]+)rem", gap)
        assert width and offset and rem, (gap, focus)
        reach = int(width.group(1)) + int(offset.group(1))
        assert float(rem.group(1)) * 16 > reach, (gap_selector, gap, reach)

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


# --- chart colors (#432) ---------------------------------------------------------------

#: The categorical series tokens, in the order a chart takes them.
CHART_SERIES = ("--chart-1", "--chart-2", "--chart-3")

#: Chart text, on the plot's background (the page): WCAG 1.4.3.
CHART_TEXT = ("--text", "--text-secondary")

#: What a chart draws that a reader needs to see, on the page: WCAG 1.4.11's 3:1. The
#: gridlines (``--chart-grid``) are decoration under the marks, so they are exempt.
CHART_MARKS = (*CHART_SERIES, "--chart-axis", "--chart-reference")

#: The color-vision floor: every pair of series tokens at a CIEDE2000 difference of at
#: least this, unsimulated and under each simulation, in both palettes.
CVD_FLOOR = 10.0

#: Machado, Oliveira and Fernandes (2009), severity 1.0, applied to linear sRGB: the
#: three common dichromacies. The same matrices as the ``dataviz`` skill's validator.
MACHADO: dict[str, tuple[tuple[float, float, float], ...]] = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritanopia": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}

Lab = tuple[float, float, float]


def linear_rgb(color: Color) -> tuple[float, float, float]:
    def channel(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in color[:3])
    return (r, g, b)


def simulate(
    rgb: tuple[float, float, float], kind: str | None
) -> tuple[float, float, float]:
    """``rgb`` (linear) as a reader with ``kind`` sees it, clamped; ``None`` is
    unsimulated."""
    if kind is None:
        return rgb
    r, g, b = (
        min(1.0, max(0.0, row[0] * rgb[0] + row[1] * rgb[1] + row[2] * rgb[2]))
        for row in MACHADO[kind]
    )
    return (r, g, b)


def cielab(rgb: tuple[float, float, float]) -> Lab:
    """Linear sRGB to CIELAB (D65)."""
    r, g, b = rgb
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        delta = 6 / 29
        return t ** (1 / 3) if t > delta**3 else t / (3 * delta**2) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def ciede2000(first: Lab, second: Lab) -> float:
    """The CIEDE2000 color difference (Sharma, Wu and Dalal 2005), kL = kC = kH = 1."""
    (l1, a1, b1), (l2, a2, b2) = first, second
    mean_c = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(mean_c**7 / (mean_c**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def hue(a: float, b: float) -> float:
        return 0.0 if a == 0 and b == 0 else math.degrees(math.atan2(b, a)) % 360

    h1p, h2p = hue(a1p, b1), hue(a2p, b2)
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    d_l, d_c = l2 - l1, c2p - c1p
    d_h = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))
    mean_l, mean_cp = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        mean_h = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        mean_h = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        mean_h = (h1p + h2p + 360) / 2
    else:
        mean_h = (h1p + h2p - 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(mean_h - 30))
        + 0.24 * math.cos(math.radians(2 * mean_h))
        + 0.32 * math.cos(math.radians(3 * mean_h + 6))
        - 0.20 * math.cos(math.radians(4 * mean_h - 63))
    )
    rotation = 30 * math.exp(-(((mean_h - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(mean_cp**7 / (mean_cp**7 + 25**7))
    s_l = 1 + 0.015 * (mean_l - 50) ** 2 / math.sqrt(20 + (mean_l - 50) ** 2)
    s_c = 1 + 0.045 * mean_cp
    s_h = 1 + 0.015 * mean_cp * t
    r_t = -math.sin(math.radians(2 * rotation)) * r_c
    return math.sqrt(
        (d_l / s_l) ** 2
        + (d_c / s_c) ** 2
        + (d_h / s_h) ** 2
        + r_t * (d_c / s_c) * (d_h / s_h)
    )


def separation(first: str, second: str, kind: str | None) -> float:
    """How far apart two hex colors are, as a reader with ``kind`` sees them."""
    return ciede2000(
        cielab(simulate(linear_rgb(parse_color(first)), kind)),
        cielab(simulate(linear_rgb(parse_color(second)), kind)),
    )


class TestChartColors:
    """The chart tokens (#432): chart text at 4.5:1 and every mark at 3:1 on the page,
    and the categorical series apart for common color-vision deficiencies, in both
    palettes. The method: Machado, Oliveira and Fernandes (2009) at severity 1.0 in
    linear sRGB, then CIEDE2000 between every pair, at least :data:`CVD_FLOOR`."""

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize("token", CHART_TEXT)
    def test_chart_text_meets_aa_on_the_page(self, theme: str, token: str) -> None:
        palette = block(LIGHT if theme == "light" else EXPLICIT_DARK)
        ratio = contrast(parse_color(palette[token]), parse_color(palette["--page"]))
        assert ratio >= AA, (theme, token, round(ratio, 2))

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize("token", CHART_MARKS)
    def test_each_mark_meets_3_to_1_on_the_page(self, theme: str, token: str) -> None:
        palette = block(LIGHT if theme == "light" else EXPLICIT_DARK)
        ratio = contrast(parse_color(palette[token]), parse_color(palette["--page"]))
        assert ratio >= NON_TEXT, (theme, token, round(ratio, 2))

    def test_what_the_template_paints_is_what_these_tests_measure(self) -> None:
        """Closure over ``charts.TEMPLATE`` (#432's review): each color it paints is a
        token one of these tests holds to its ratio, so a template that moves text or a
        line onto an unmeasured token, or a plot onto another background, fails."""
        from explore import charts

        layout = charts.TEMPLATE["layout"]
        assert {layout["paper_bgcolor"], layout["plot_bgcolor"]} == {"var(--page)"}
        backgrounds = {"var(--page)", layout["hoverlabel"]["bgcolor"]}
        assert backgrounds == {"var(--page)", "var(--surface)"}
        seen: set[str] = set()
        for path, key, value in charts._walk(charts.TEMPLATE):
            if not isinstance(value, str) or not value.startswith("var(--"):
                continue
            token = value.removeprefix("var(").removesuffix(")")
            seen.add(path)
            if path.endswith(".font.color") or path.endswith("tickfont.color"):
                assert token in CHART_TEXT, path
            elif key in ("linecolor", "tickcolor", "zerolinecolor"):
                assert token in CHART_MARKS, path
            elif key == "gridcolor":
                assert token == "--chart-grid", path
            elif key == "colorway" or path.startswith("layout.colorway"):
                assert token in CHART_SERIES, path
            elif key in ("paper_bgcolor", "plot_bgcolor", "bgcolor", "family"):
                pass  # the backgrounds, checked above, and the font stack
            elif key == "bordercolor":
                assert token == "--border", path  # a control's stroke, as Dash's
            else:
                raise AssertionError(f"{path}: a painted color no test measures")
        assert "layout.hoverlabel.font.color" in seen

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_the_hover_label_s_text_meets_aa_on_its_background(self, theme: str) -> None:
        from explore import charts

        palette = block(LIGHT if theme == "light" else EXPLICIT_DARK)
        label = charts.TEMPLATE["layout"]["hoverlabel"]
        text = resolve(label["font"]["color"], palette)
        ground = resolve(label["bgcolor"], palette)
        ratio = contrast(parse_color(text), parse_color(ground))
        assert ratio >= AA, (theme, round(ratio, 2))

    def test_every_chart_token_but_the_grid_is_checked(self) -> None:
        charted = {t for t in TOKENS if t.startswith("--chart-")}
        assert charted == set(CHART_MARKS) | {"--chart-grid"}

    def test_the_series_tokens_are_hex(self) -> None:
        # The contrast and CIEDE2000 math here composites no alpha over the page, so a
        # chart token is a plain hex color, never rgba (plotly.js itself reads both).
        for key in PALETTE_BLOCKS:
            palette = block(key)
            for token in TOKENS:
                if token.startswith("--chart-"):
                    assert re.fullmatch(r"#[0-9a-f]{6}", palette[token]), (key, token)

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize("kind", [None, *MACHADO])
    def test_the_series_stay_apart(self, theme: str, kind: str | None) -> None:
        palette = block(LIGHT if theme == "light" else EXPLICIT_DARK)
        for first, second in itertools.combinations(CHART_SERIES, 2):
            gap = separation(palette[first], palette[second], kind)
            assert gap >= CVD_FLOOR, (theme, kind, first, second, round(gap, 2))

    @pytest.mark.parametrize(
        ("first", "second", "expected"),
        [
            # Sharma, Wu and Dalal (2005), Table 1, pairs 1, 7, 17 and 25.
            ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
            ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
            ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
            ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
        ],
    )
    def test_ciede2000_matches_sharmas_reference_pairs(
        self, first: Lab, second: Lab, expected: float
    ) -> None:
        assert ciede2000(first, second) == pytest.approx(expected, abs=1e-4)
        assert ciede2000(second, first) == pytest.approx(expected, abs=1e-4)

    def test_the_simulation_separates_what_it_should_not(self) -> None:
        """Non-vacuity: an orange and a green that a protanope and a deuteranope
        confuse, and a teal and a blue that a tritanope confuses, pass unsimulated and
        fail the floor under their simulations."""
        orange, green = "#e8a33d", "#6fbf40"
        assert separation(orange, green, None) >= CVD_FLOOR
        assert separation(orange, green, "protanopia") < CVD_FLOOR
        assert separation(orange, green, "deuteranopia") < CVD_FLOOR
        teal, blue = "#1f9e89", "#4c8cd8"
        assert separation(teal, blue, None) >= CVD_FLOOR
        assert separation(teal, blue, "tritanopia") < CVD_FLOOR


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


def toggle_group() -> Any:
    """The theme toggle's group in the shared layout's header: the header's last child,
    after the site navigation (#448)."""
    header = appmod.app.layout.children[0]
    group = header.children[-1]
    assert getattr(group, "id", None) == components.THEME_CONTROL_ID
    return group


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
        group = toggle_group()
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

    def test_the_toggle_names_are_its_choices_and_no_raw_value(self) -> None:
        shown = texts(toggle_group())
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
            for key in appmod.app.callback_map
            if components.THEME_STORE_ID in key
        ]
        # The store's one reader is the chart callback (#432), which redraws charts.
        readers = [
            key
            for key, spec in appmod.app.callback_map.items()
            if any(i["id"] == components.THEME_STORE_ID for i in spec["inputs"])
        ]
        assert readers == [
            '..{"chart":["MATCH"],"type":"explore-chart-graph"}.figure'
            '...{"chart":["MATCH"],"type":"explore-chart-graph"}.style..'
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
        # Ids are compared as JSON: a pattern-matching id (a chart's) is a dict.
        sources = {
            json.dumps(name)
            for name in (components.THEME_STORE_ID, components.THEME_CONTROL_ID, *buttons)
        }
        fed_keys = []
        for key, other in appmod.app.callback_map.items():
            if {json.dumps(i["id"]) for i in other["inputs"]} & sources:
                fed_keys.append(key)
                assert ".search" not in key and ".pathname" not in key, key
        assert set(readers) <= set(fed_keys)  # non-vacuity: the chart callback is fed

    def test_the_callback_maps_each_button_and_sets_no_attribute_on_one(self) -> None:
        script = appmod.THEME_CALLBACK
        # React owns aria-pressed: the one attribute the callback sets is data-theme,
        # the one element it touches is <html>, and it names no aria property at all.
        assert script.count("setAttribute") == 1
        assert 'root.setAttribute("data-theme", choice)' in script
        assert set(re.findall(r"document\.(\w+)", script)) == {"documentElement"}
        assert "aria" not in script.lower()
        # The choice is the triggered button, through the one id map.
        mapping = {b: v for v, b in components.THEME_BUTTON_IDS.items()}
        assert f"var byButton = {json.dumps(mapping)};" in script
        assert "callback_context.triggered_id" in script
        # The selection is read from <html data-theme>; that it, and never the theme in
        # effect, decides aria-pressed is the e2e suite's to show (under Auto on a dark
        # device, Auto is pressed).
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


def icon_data() -> dict[str, str]:
    """Each icon class's mask data URI payload, still percent-encoded, read from both
    of its declarations."""
    found = {}
    for value in labels.THEME_CHOICES:
        rule = toggle_rule(f".theme-icon-{value}")
        assert rule["-webkit-mask-image"] == rule["mask-image"], value
        match = re.fullmatch(r'url\("data:image/svg\+xml,([^"]*)"\)', rule["mask-image"])
        assert match, value
        found[value] = match.group(1)
    return found


def svg_colors(encoded: str) -> list[str]:
    """The color literals in a percent-encoded SVG, decoded as a browser reads it."""
    return color_words(urllib.parse.unquote(encoded), ALLOWED_KEYWORDS)


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
        assert set(icon_data()) == set(labels.THEME_CHOICES)

    def test_each_icon_is_a_well_formed_svg_image(self) -> None:
        # A mask image that fails to load masks the whole icon away, silently.
        for value, encoded in icon_data().items():
            # A raw '#' would end the data URL there, as a fragment.
            assert "#" not in encoded, value
            root = ET.fromstring(urllib.parse.unquote(encoded))
            assert root.tag == "{http://www.w3.org/2000/svg}svg", value
            assert root.get("viewBox") == "0 0 24 24", value
            assert len(root), value  # it draws something

    def test_no_icon_names_a_color(self) -> None:
        # The color lint skips quoted strings, so it cannot see inside a data URI.
        for value, encoded in icon_data().items():
            assert svg_colors(encoded) == [], value
            # The mask reads alpha: every paint is currentColor or none.
            svg = urllib.parse.unquote(encoded)
            paints = re.findall(r"(?:fill|stroke)='([^']*)'", svg)
            assert paints and set(paints) <= {"currentColor", "none"}, (value, paints)

    @pytest.mark.parametrize(
        "encoded",
        [
            "%3Csvg fill='%23000'/%3E",
            "%3Csvg fill='red'/%3E",
            "%3Csvg fill='rgb(1,2,3)'/%3E",
            "%3Csvg fill='AccentColor'/%3E",
        ],
    )
    def test_the_icon_scan_flags_a_color(self, encoded: str) -> None:
        assert svg_colors(encoded) != []

    def test_the_icon_scan_passes_current_color(self) -> None:
        assert svg_colors("%3Csvg fill='currentColor' stroke='none'/%3E") == []

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

    def test_forced_colors_paint_every_icon_in_system_colors(self) -> None:
        # forced-color-adjust: none leaves the icon's currentColor on the author's token,
        # so the forced-colors block sets it, on the icon itself, to a system color on
        # the system button face: no hover or selected rule can leak a token there.
        icon = toggle_rule(".theme-icon", FORCED_COLORS)
        button = toggle_rule(".theme-control button", FORCED_COLORS)
        assert icon == {"background-color": "ButtonText"}
        assert button == {"background-color": "ButtonFace"}
        assert {"buttontext", "buttonface"} <= SYSTEM_COLORS


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

    def test_the_selected_position_keeps_a_border_under_forced_colors(self) -> None:
        # Outside forced colors the fill is the cue and this border is transparent;
        # forced colors drop the fill and paint the border in a system color.
        assert toggle_rule(SELECTED)["border"] == "2px solid transparent"
        assert toggle_rule(".theme-control button")["border"] == "0"

    def test_no_toggle_rule_names_the_site_header(self) -> None:
        # #448 moves the toggle into a navigation bar: no rule for it names the header,
        # by class or by element, under any combinator.
        # Nor the site navigation, the bar beside it (#448).
        toggle = [p for _, p, _ in shipped_rules() if re.search(r"[.#]theme-", p)]
        assert toggle
        for prelude in toggle:
            assert ".site-header" not in prelude, prelude
            assert ".site-nav" not in prelude, prelude
            assert not re.search(r"(^|[\s>+~,])header\b", prelude), prelude
            assert not re.search(r"(^|[\s>+~,])nav\b", prelude), prelude
