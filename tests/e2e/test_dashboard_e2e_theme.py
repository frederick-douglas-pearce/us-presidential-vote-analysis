"""The theme choice in a browser (#359, #447): the Dark, Auto and Light toggle,
remembered per browser, applied before first paint, and the theme in effect exposed to
Dash for charts (#432).

The store holding the theme in effect is read through ``serve.py``'s theme probe, a
hidden div a test-only clientside callback writes from the store, so these tests see
what a chart's callback would see, and the probe records the palette ``<html>`` showed
at each call. The device's setting is Playwright's emulated ``prefers-color-scheme``.

A test that asserts something did *not* happen waits for the event that could have
caused it (the choice's callback, or a real ``change`` event from the device's setting),
then makes a change whose effect it can count, so a spurious write that landed late
still shows in the count.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Locator, Page, expect

from explore import app as appmod
from explore import components, labels
from tests.e2e.dashboard_pages import (
    ELECTION_SUCCESS,
    ELECTIONS_SUCCESS,
    HOME_SUCCESS,
    PV,
    YEARS,
    assert_rendered,
)
from tests.e2e.serve import THEME_PROBE_CALLS, THEME_PROBE_ID, THEME_PROBE_SEEN

pytestmark = pytest.mark.e2e

STYLESHEET = Path(appmod.__file__).parent / "assets" / "style.css"
KEY = appmod.THEME_STORAGE_KEY
PROBE = f"#{THEME_PROBE_ID}"
CONTROL = f"#{components.THEME_CONTROL_ID}"
AUTO = labels.THEME_AUTO
CANDIDATE_SUCCESS = "#candidate"
DARK_QUERY = "(prefers-color-scheme: dark)"


def _block(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start : css.index("}", start)]


def _palette(selector: str) -> dict[str, str]:
    """A palette block's token values, from the shipped stylesheet."""
    css = re.sub(r"/\*.*?\*/", "", STYLESHEET.read_text(encoding="utf-8"), flags=re.S)
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", _block(css, selector)))


LIGHT = _palette(":root")
DARK = _palette(':root[data-theme="dark"]')
PALETTES = {"light": LIGHT, "dark": DARK}


def rgb(value: str) -> str:
    """A ``#rgb``/``#rrggbb`` token value as ``getComputedStyle`` reports it."""
    digits = value.strip().lstrip("#")
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


def button(page: Page, choice: str) -> Locator:
    return page.locator(f"#{components.THEME_BUTTON_IDS[choice]}")


def choose(page: Page, choice: str) -> None:
    """Press ``choice``'s button and wait for the theme callback to apply it."""
    button(page, choice).click()
    applied(page, choice)


def applied(page: Page, choice: str) -> None:
    """Wait until the theme callback has applied ``choice`` to ``<html data-theme>``."""
    expected = None if choice == AUTO else choice
    page.wait_for_function(
        f"document.documentElement.getAttribute('data-theme') === {json.dumps(expected)}"
    )


#: Each theme button's computed background, and the page's own ``--accent``.
FILLS = f"""() => ({{
  accent: getComputedStyle(document.documentElement).getPropertyValue("--accent"),
  fills: {json.dumps(list(components.THEME_BUTTON_IDS.values()))}.map(
    function (id) {{
      return getComputedStyle(document.getElementById(id)).backgroundColor; }}),
}})"""


def assert_selected(page: Page, choice: str) -> None:
    """``choice`` is the one pressed position, to assistive technology and to the eye:
    ``aria-pressed`` (which the theme callback sets) and the accent fill (which the
    stylesheet draws from ``<html data-theme>``) agree."""
    for value in labels.THEME_CHOICES:
        expect(button(page, value)).to_have_attribute(
            "aria-pressed", "true" if value == choice else "false"
        )
    seen: dict[str, Any] = page.evaluate(FILLS)
    accent = rgb(seen["accent"])
    pairs = zip(labels.THEME_CHOICES, seen["fills"], strict=True)
    filled = [value for value, fill in pairs if fill == accent]
    assert filled == [choice], seen


def theme_attribute(page: Page) -> str | None:
    value: str | None = page.evaluate(
        "document.documentElement.getAttribute('data-theme')"
    )
    return value


def stored(page: Page) -> str | None:
    value: str | None = page.evaluate(f"localStorage.getItem({json.dumps(KEY)})")
    return value


def probe_calls(page: Page) -> int:
    calls: int = page.evaluate(f"window.{THEME_PROBE_CALLS} || 0")
    return calls


def assert_painted(page: Page, theme: str) -> None:
    """The page shows ``theme``'s palette, and the store holds it. Every value the
    store ever gave a dependent callback came after the palette it names: the store's
    contract that it changes only after the palette has."""
    expect(page.locator(PROBE)).to_have_text(theme)
    root = "getComputedStyle(document.documentElement).colorScheme"
    assert page.evaluate(root) == theme
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == rgb(
        PALETTES[theme]["--page"]
    )
    seen: list[list[str]] = page.evaluate(f"window.{THEME_PROBE_SEEN} || []")
    assert seen and all(value == shown for value, shown in seen), seen


#: Counts real ``change`` events of the device's dark setting. Our listener is
#: registered after the page's own, so when it has run, the page's has too.
DEVICE_COUNTER = f"""() => {{
  if (window.exploreDeviceChanges === undefined) {{
    window.exploreDeviceChanges = 0;
    var count = function () {{ window.exploreDeviceChanges += 1; }};
    count.exploreTest = true;
    window.matchMedia({json.dumps(DARK_QUERY)}).addEventListener("change", count);
  }}
}}"""


def switch_device(page: Page, scheme: str) -> None:
    """Set the device's setting to ``scheme`` (a change) and wait for the browser to
    deliver its ``change`` event: two emulations with no rendering step between them
    merge into none."""
    page.evaluate(DEVICE_COUNTER)
    before: int = page.evaluate("window.exploreDeviceChanges")
    page.emulate_media(color_scheme=scheme)  # type: ignore[arg-type]
    page.wait_for_function(f"window.exploreDeviceChanges > {before}")


@pytest.mark.parametrize("os_scheme", ["light", "dark"])
def test_with_no_saved_choice_the_page_follows_the_device(
    page: Page, os_scheme: str
) -> None:
    page.emulate_media(color_scheme=os_scheme)  # type: ignore[arg-type]
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    assert_selected(page, AUTO)
    assert theme_attribute(page) is None
    assert_painted(page, os_scheme)


def test_a_choice_persists_across_pages_and_reloads(page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    choose(page, "dark")
    assert_selected(page, "dark")
    assert stored(page) == "dark"
    assert_painted(page, "dark")

    page.locator('main a[href="/elections"]').click()  # a client-side navigation
    assert_rendered(page, ELECTIONS_SUCCESS)
    assert_selected(page, "dark")
    assert_painted(page, "dark")

    page.reload()
    assert_rendered(page, ELECTIONS_SUCCESS)
    assert_selected(page, "dark")
    assert_painted(page, "dark")

    # Back to Auto: the stored choice is cleared and the device's setting applies.
    choose(page, AUTO)
    assert_selected(page, AUTO)
    assert stored(page) is None
    assert_painted(page, "light")


#: Records, at the moment ``<body>`` is first inserted, ``<html data-theme>``; and in
#: a frame queued then, which runs before the first paint the stylesheet blocks, the
#: body's background and the root's ``color-scheme``.
FIRST_PAINT = """
window.exploreFirstPaint = null;
new MutationObserver(function (records, observer) {
  if (!document.body) { return; }
  observer.disconnect();
  var root = document.documentElement;
  var seen = {theme: root.getAttribute("data-theme")};
  requestAnimationFrame(function () {
    seen.background = getComputedStyle(document.body).backgroundColor;
    seen.scheme = getComputedStyle(root).colorScheme;
    window.exploreFirstPaint = seen;
  });
}).observe(document, {childList: true, subtree: true});
"""


@pytest.mark.parametrize(("os_scheme", "saved"), [("dark", "light"), ("light", "dark")])
def test_a_saved_choice_paints_first_with_no_flash(
    page: Page, os_scheme: str, saved: str
) -> None:
    page.emulate_media(color_scheme=os_scheme)  # type: ignore[arg-type]
    page.add_init_script(
        f"localStorage.setItem({json.dumps(KEY)}, {json.dumps(saved)});" + FIRST_PAINT
    )
    page.goto("/")
    page.wait_for_function("window.exploreFirstPaint !== null")
    first = page.evaluate("window.exploreFirstPaint")
    assert first == {
        "theme": saved,
        "background": rgb(PALETTES[saved]["--page"]),
        "scheme": saved,
    }
    assert_rendered(page, HOME_SUCCESS)
    assert_selected(page, saved)
    assert_painted(page, saved)


@pytest.mark.parametrize("saved", ["blue", "<img src=x>", "system", "auto", ""])
def test_a_saved_value_that_is_no_explicit_choice_is_auto(
    page: Page, saved: str
) -> None:
    page.emulate_media(color_scheme="dark")
    page.add_init_script(
        f"localStorage.setItem({json.dumps(KEY)}, {json.dumps(saved)});"
    )
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    assert theme_attribute(page) is None
    assert_selected(page, AUTO)
    assert_painted(page, "dark")


#: What each kind of dcc control paints, as a computed style: (page, selector,
#: property), and in the dark palette the token it paints with. In light the controls
#: keep Dash's own colors, so there the explicit choice is compared with the device
#: set the same way.
PAINTED: tuple[tuple[str, str, str, str], ...] = (
    ("/elections", f"{YEARS} .dash-slider-thumb", "backgroundColor", "--accent"),
    ("/elections", f"{YEARS} .dash-slider-track", "backgroundColor", "--disabled"),
    ("/elections", f"{YEARS} .dash-slider-mark", "color", "--text"),
    ("/elections", f"{PV} label", "color", "--text"),
    ("/election/2016", "#election-state", "backgroundColor", "--surface"),
    ("/election/2016", "#election-state", "color", "--text"),
    ("/election/2016", "#election-state", "borderTopColor", "--border"),
    (
        "/candidate/andrew-jackson",
        f"{CANDIDATE_SUCCESS} .year-buttons label",
        "borderTopColor",
        "--accent",
    ),
    (
        "/candidate/andrew-jackson",
        f"{CANDIDATE_SUCCESS} .year-buttons label:has(input:checked)",
        "backgroundColor",
        "--accent",
    ),
    (
        "/candidate/andrew-jackson",
        f"{CANDIDATE_SUCCESS} .year-buttons label:has(input:checked)",
        "color",
        "--on-accent",
    ),
)

SUCCESS = {
    "/elections": ELECTIONS_SUCCESS,
    "/election/2016": ELECTION_SUCCESS,
    "/candidate/andrew-jackson": CANDIDATE_SUCCESS,
}


NO_TRANSITIONS = "*, *::before, *::after { transition: none !important; }"


def painted(page: Page, path: str) -> dict[tuple[str, str], str]:
    values: dict[tuple[str, str], str] = {}
    for at, selector, prop, _ in PAINTED:
        if at == path:
            values[(selector, prop)] = page.locator(selector).first.evaluate(
                f"e => getComputedStyle(e).{prop}"
            )
    return values


@pytest.mark.parametrize(
    ("os_scheme", "choice"), [("light", "dark"), ("dark", "light")]
)
def test_the_controls_follow_an_explicit_choice_against_the_device(
    page: Page, os_scheme: str, choice: str
) -> None:
    for path, success in SUCCESS.items():
        # What the controls paint with under the choice: the device set the same way,
        # with no saved choice.
        page.emulate_media(color_scheme=choice)  # type: ignore[arg-type]
        page.goto(path)
        assert_rendered(page, success)
        # Dash animates some control colors; this test compares settled ones.
        page.add_style_tag(content=NO_TRANSITIONS)
        if theme_attribute(page) is not None:
            choose(page, AUTO)
        expected = painted(page, path)
        if choice == "dark":
            for at, selector, prop, token in PAINTED:
                if at == path:
                    assert expected[(selector, prop)] == rgb(DARK[token]), selector
        page.emulate_media(color_scheme=os_scheme)  # type: ignore[arg-type]
        expect(page.locator(PROBE)).to_have_text(os_scheme)
        assert painted(page, path) != expected, path

        choose(page, choice)
        assert_painted(page, choice)
        assert painted(page, path) == expected, path


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("state", ["focus", "hover"])
def test_the_checked_year_pill_keeps_its_colors_when_focused_or_hovered(
    page: Page, theme: str, state: str
) -> None:
    """The browser proof that the (0,3,2) pill rule outranks Dash's injected one, on
    the candidate page's year buttons (the theme control left the shared rule, #447)."""
    page.emulate_media(color_scheme="light" if theme == "dark" else "dark")
    page.goto("/candidate/andrew-jackson")
    assert_rendered(page, CANDIDATE_SUCCESS)
    choose(page, theme)
    pill = page.locator(f"{CANDIDATE_SUCCESS} .year-buttons label:has(input:checked)")
    if state == "focus":
        pill.locator("input").focus()
        expect(pill.locator("input")).to_be_focused()
    else:
        pill.hover()
    colors: dict[str, Any] = pill.evaluate(
        "e => ({color: getComputedStyle(e).color,"
        " background: getComputedStyle(e).backgroundColor})"
    )
    assert colors == {
        "color": rgb(PALETTES[theme]["--on-accent"]),
        "background": rgb(PALETTES[theme]["--accent"]),
    }


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("state", ["focus", "hover"])
def test_the_selected_position_keeps_its_colors_when_focused_or_hovered(
    page: Page, theme: str, state: str
) -> None:
    page.emulate_media(color_scheme="light" if theme == "dark" else "dark")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    choose(page, theme)
    selected = button(page, theme)
    if state == "focus":
        # By keyboard, so the ring shows (:focus-visible): back one stop and forward.
        selected.focus()
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Tab")
        expect(selected).to_be_focused()
    else:
        selected.hover()
    colors: dict[str, Any] = selected.evaluate(
        "e => ({color: getComputedStyle(e).color,"
        " background: getComputedStyle(e).backgroundColor,"
        " outline: getComputedStyle(e).outlineColor})"
    )
    assert colors["color"] == rgb(PALETTES[theme]["--on-accent"])
    assert colors["background"] == rgb(PALETTES[theme]["--accent"])
    if state == "focus":
        assert colors["outline"] == rgb(PALETTES[theme]["--accent"])
    # An unselected position under the pointer turns the accent, on the page.
    other = button(page, AUTO)
    other.hover()
    assert other.evaluate("e => getComputedStyle(e).color") == rgb(
        PALETTES[theme]["--accent"]
    )


@pytest.mark.parametrize("key", ["Enter", " "], ids=["enter", "space"])
def test_each_position_is_a_named_pressed_button_chosen_from_the_keyboard(
    page: Page, key: str
) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    group = page.get_by_role("group", name=labels.THEME_CONTROL)
    expect(group.get_by_role("button")).to_have_count(len(labels.THEME_CHOICES))
    expect(page.locator("header [role=listbox], header [role=option]")).to_have_count(0)
    # The header comes first: Tab reaches Dark, then Auto, then Light.
    for choice in labels.THEME_CHOICES:
        page.keyboard.press("Tab")
        focused = page.locator(":focus")
        expect(focused).to_have_id(components.THEME_BUTTON_IDS[choice])
        expect(focused).to_have_role("button")
        expect(focused).to_have_accessible_name(labels.THEME_CHOICES[choice])
        pressed = "true" if choice == AUTO else "false"
        expect(focused).to_have_attribute("aria-pressed", pressed)
    # Light is focused: the key chooses it, and focus stays on it after the callback.
    page.keyboard.press(key)
    applied(page, "light")
    assert_selected(page, "light")
    expect(button(page, "light")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Shift+Tab")
    page.keyboard.press(key)
    applied(page, "dark")
    assert_selected(page, "dark")
    expect(button(page, "dark")).to_be_focused()
    assert_painted(page, "dark")


def test_the_toggle_keeps_one_row_at_a_phones_width(page: Page) -> None:
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    boxes: list[dict[str, float]] = page.locator(f"{CONTROL} button").evaluate_all(
        "buttons => buttons.map(b => {"
        " var r = b.getBoundingClientRect();"
        " return {top: r.top, width: r.width, height: r.height}; })"
    )
    assert len(boxes) == len(labels.THEME_CHOICES)
    assert len({round(b["top"]) for b in boxes}) == 1, boxes
    # WCAG 2.5.8: each target at least 24 x 24 CSS px.
    assert all(b["width"] >= 24 and b["height"] >= 24 for b in boxes), boxes
    assert page.evaluate("document.documentElement.scrollWidth") == 390
    # The toggle's measured width, which #448's one-row navigation bar budgets for.
    width = page.locator(CONTROL).evaluate("e => e.getBoundingClientRect().width")
    print(f"theme toggle width at 390 px: {width:.1f} px")
    assert width <= 120, width


#: Records, the first time the saved position's button is in the document and in the
#: next frame, which buttons look selected (carry the accent fill).
FIRST_TOGGLE_FRAME = f"""
window.exploreToggleFrames = null;
new MutationObserver(function (records, observer) {{
  var ids = {json.dumps(list(components.THEME_BUTTON_IDS.values()))};
  if (!document.getElementById(ids[0])) {{ return; }}
  observer.disconnect();
  function look() {{
    var accent = getComputedStyle(document.documentElement)
      .getPropertyValue("--accent").trim();
    var probe = document.createElement("i");
    probe.style.color = accent;
    document.body.appendChild(probe);
    var want = getComputedStyle(probe).color;
    probe.remove();
    return ids.filter(function (id) {{
      return getComputedStyle(document.getElementById(id)).backgroundColor === want;
    }});
  }}
  var frames = [look()];
  requestAnimationFrame(function () {{
    frames.push(look());
    window.exploreToggleFrames = frames;
  }});
}}).observe(document, {{childList: true, subtree: true}});
"""


@pytest.mark.parametrize(("os_scheme", "saved"), [("light", "dark"), ("dark", "light")])
def test_the_saved_position_looks_selected_from_its_first_frame(
    page: Page, os_scheme: str, saved: str
) -> None:
    page.emulate_media(color_scheme=os_scheme)  # type: ignore[arg-type]
    page.add_init_script(
        f"localStorage.setItem({json.dumps(KEY)}, {json.dumps(saved)});"
        + FIRST_TOGGLE_FRAME
    )
    page.goto("/")
    page.wait_for_function("window.exploreToggleFrames !== null")
    frames = page.evaluate("window.exploreToggleFrames")
    expected = [components.THEME_BUTTON_IDS[saved]]
    assert frames == [expected, expected]
    assert_rendered(page, HOME_SUCCESS)
    assert_selected(page, saved)


def test_choosing_the_pressed_position_again_changes_nothing(page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    choose(page, "dark")
    assert_painted(page, "dark")
    calls = probe_calls(page)
    button(page, "dark").click()
    assert_selected(page, "dark")
    assert stored(page) == "dark"
    # The barrier, Light, is one write: a write from the repeated Dark would be two.
    choose(page, "light")
    assert_painted(page, "light")
    assert probe_calls(page) == calls + 1
    assert_selected(page, "light")


def _channels(color: str) -> tuple[float, float, float, float]:
    match = re.fullmatch(
        r"rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)", color.strip()
    )
    assert match, color
    r, g, b = (float(match.group(i)) for i in (1, 2, 3))
    return (r, g, b, float(match.group(4) or 1))


def _contrast(foreground: str, background: str) -> float:
    """WCAG 2's ratio of two opaque computed colors."""

    def luminance(color: str) -> float:
        def channel(c: float) -> float:
            c /= 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        r, g, b, alpha = _channels(color)
        assert alpha == 1, color
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


#: Each theme button's painted background (the page's where it is transparent), its
#: icon's painted color, and its top border's width and color.
FORCED_PAINT = f"""() => {{
  var page = getComputedStyle(document.body).backgroundColor;
  return {json.dumps(list(components.THEME_BUTTON_IDS.values()))}.map(function (id) {{
    var button = document.getElementById(id);
    var style = getComputedStyle(button);
    var ground = style.backgroundColor;
    if (ground === "rgba(0, 0, 0, 0)" || ground === "transparent") {{ ground = page; }}
    return {{
      ground: ground,
      icon: getComputedStyle(button.querySelector(".theme-icon")).backgroundColor,
      adjust: getComputedStyle(button.querySelector(".theme-icon")).forcedColorAdjust,
      borderWidth: style.borderTopWidth,
      borderColor: style.borderTopColor,
    }};
  }});
}}"""


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_forced_colors_paint_every_icon_and_the_selection_border(
    page: Page, scheme: str
) -> None:
    """In each forced palette, with each position selected: every icon paints at 3:1
    or more against its button, and the selected position's border is visible (its
    color differs from its button's), the cue that survives the dropped fill. Checked
    in Chromium's forced-colors emulation, which the e2e tier runs (advisory, D082)."""
    page.emulate_media(color_scheme=scheme, forced_colors="active")  # type: ignore[arg-type]
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    for choice in labels.THEME_CHOICES:
        choose(page, choice)
        page.mouse.move(0, 0)  # no hover on any button
        seen: list[dict[str, str]] = page.evaluate(FORCED_PAINT)
        for value, paint in zip(labels.THEME_CHOICES, seen, strict=True):
            assert paint["adjust"] == "none", (choice, value, paint)
            ratio = _contrast(paint["icon"], paint["ground"])
            assert ratio >= 3, (scheme, choice, value, paint, round(ratio, 2))
            if value == choice:
                assert paint["borderWidth"] == "2px", (choice, paint)
                assert paint["borderColor"] != paint["ground"], (choice, paint)
            else:
                assert paint["borderWidth"] == "0px", (choice, value, paint)


@pytest.mark.parametrize("os_scheme", ["light", "dark"])
def test_the_stylesheet_draws_the_selection_from_the_theme_attribute(
    page: Page, os_scheme: str
) -> None:
    """Setting ``<html data-theme>`` by hand, with no callback, moves the visible
    selection and leaves ``aria-pressed`` where it was: the stylesheet, not the
    pressed state, draws the selected position."""
    page.emulate_media(color_scheme=os_scheme)  # type: ignore[arg-type]
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    assert_selected(page, AUTO)
    for attribute, drawn in [("dark", "dark"), ("light", "light"), (None, AUTO)]:
        if attribute is None:
            page.evaluate("document.documentElement.removeAttribute('data-theme')")
        else:
            page.evaluate(
                "document.documentElement.setAttribute('data-theme',"
                f" {json.dumps(attribute)})"
            )
        seen: dict[str, Any] = page.evaluate(FILLS)
        accent = rgb(seen["accent"])
        pairs = zip(labels.THEME_CHOICES, seen["fills"], strict=True)
        assert [value for value, fill in pairs if fill == accent] == [drawn], seen
        for value in labels.THEME_CHOICES:
            expect(button(page, value)).to_have_attribute(
                "aria-pressed", "true" if value == AUTO else "false"
            )


def test_the_store_follows_the_device_only_under_auto(page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    assert_painted(page, "light")
    switch_device(page, "dark")
    assert_painted(page, "dark")

    choose(page, "light")
    assert_painted(page, "light")
    calls = probe_calls(page)
    # Two real device changes under an explicit choice: neither may write the store.
    switch_device(page, "light")
    switch_device(page, "dark")
    # A barrier whose effect is countable: one write. A late spurious write from
    # either device change would make it more, or record a value the palette did not
    # show (assert_painted).
    choose(page, "dark")
    assert_painted(page, "dark")
    assert probe_calls(page) == calls + 1

    # Back to Auto under a dark device, from the choice that matches it: dark is
    # already in effect, so no write, the saved choice is cleared and Auto is pressed;
    # then the device's change is followed again, and Auto stays pressed.
    calls = probe_calls(page)
    choose(page, AUTO)
    assert stored(page) is None
    assert_selected(page, AUTO)
    switch_device(page, "light")
    assert_painted(page, "light")
    assert probe_calls(page) == calls + 1
    assert_selected(page, AUTO)


def test_returning_to_auto_re_resolves_and_skips_an_unchanged_theme(
    page: Page,
) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    choose(page, "dark")
    assert_painted(page, "dark")
    choose(page, AUTO)
    assert_painted(page, "light")
    # Light under a light device: the theme in effect is unchanged, so the store is
    # not written and a chart would not re-template. The barrier, a change to Dark,
    # is one write; a write of the unchanged theme would make it two.
    calls = probe_calls(page)
    choose(page, "light")
    assert_selected(page, "light")
    choose(page, "dark")
    assert_painted(page, "dark")
    assert probe_calls(page) == calls + 1


#: Counts the page's registrations of a listener for the device's dark setting,
#: leaving out the tests' own counter (``DEVICE_COUNTER``).
LISTENER_COUNTER = f"""
window.exploreThemeListeners = 0;
var original = MediaQueryList.prototype.addEventListener;
MediaQueryList.prototype.addEventListener = function (type, listener, options) {{
  if (type === "change" && this.media === {json.dumps(DARK_QUERY)}
      && !(listener && listener.exploreTest)) {{
    window.exploreThemeListeners += 1;
  }}
  return original.call(this, type, listener, options);
}};
"""


def test_the_theme_callback_registers_one_device_listener_per_document(
    page: Page,
) -> None:
    page.emulate_media(color_scheme="light")
    page.add_init_script(LISTENER_COUNTER)
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    assert_painted(page, "light")
    for choice in ["dark", "light", AUTO]:
        choose(page, choice)
    page.locator('main a[href="/elections"]').click()  # a client-side navigation
    assert_rendered(page, ELECTIONS_SUCCESS)
    choose(page, "dark")
    assert_painted(page, "dark")
    assert page.evaluate("window.exploreThemeListeners") == 1


#: A window whose storage refuses every access. The head script's ``try`` is what
#: keeps this from a page error, which the suite's browser guard fails every test on
#: (``tests/e2e/conftest.py``).
REFUSED_STORAGE = """
Object.defineProperty(window, "localStorage", {
  configurable: true,
  get: function () { throw new DOMException("refused", "SecurityError"); },
});
"""


def test_refused_storage_keeps_the_choice_for_the_document(page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.add_init_script(REFUSED_STORAGE)
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    assert_selected(page, AUTO)
    choose(page, "dark")
    assert_painted(page, "dark")
    assert_selected(page, "dark")
    page.locator('main a[href="/elections"]').click()
    assert_rendered(page, ELECTIONS_SUCCESS)
    assert_painted(page, "dark")
    assert_selected(page, "dark")
