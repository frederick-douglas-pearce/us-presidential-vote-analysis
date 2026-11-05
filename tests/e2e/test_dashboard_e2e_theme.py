"""The theme choice in a browser (#359): System, Light and Dark, remembered per browser,
applied before first paint, and the theme in effect exposed to Dash for charts (#432).

The store holding the theme in effect is read through ``serve.py``'s theme probe, a
hidden div a test-only clientside callback writes from the store, so these tests see
what a chart's callback would see, and the probe records the palette ``<html>`` showed
at each call. The device's setting is Playwright's emulated ``prefers-color-scheme``.

A test that asserts something did *not* happen waits for the event that could have
caused it (a real ``change`` event from the device's setting), then makes a change whose
effect it can count, so a spurious write that landed late still shows in the count.
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


def radio(page: Page, choice: str) -> Locator:
    return page.locator(CONTROL).get_by_role(
        "radio", name=labels.THEME_CHOICES[choice], exact=True
    )


def choose(page: Page, choice: str) -> None:
    """Pick ``choice`` and wait for the theme callback to apply it: the browser checks
    the radio at once, the callback sets ``data-theme`` after."""
    page.locator(CONTROL).get_by_text(labels.THEME_CHOICES[choice], exact=True).click()
    applied(page, choice)


def applied(page: Page, choice: str) -> None:
    """Wait until the theme callback has applied ``choice`` to ``<html data-theme>``."""
    expected = None if choice == labels.THEME_SYSTEM else choice
    page.wait_for_function(
        f"document.documentElement.getAttribute('data-theme') === {json.dumps(expected)}"
    )


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
    expect(radio(page, labels.THEME_SYSTEM)).to_be_checked()
    assert theme_attribute(page) is None
    assert_painted(page, os_scheme)


def test_a_choice_persists_across_pages_and_reloads(page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    choose(page, "dark")
    expect(radio(page, "dark")).to_be_checked()
    assert stored(page) == "dark"
    assert_painted(page, "dark")

    page.locator('main a[href="/elections"]').click()  # a client-side navigation
    assert_rendered(page, ELECTIONS_SUCCESS)
    expect(radio(page, "dark")).to_be_checked()
    assert_painted(page, "dark")

    page.reload()
    assert_rendered(page, ELECTIONS_SUCCESS)
    expect(radio(page, "dark")).to_be_checked()
    assert_painted(page, "dark")

    # Back to System: the stored choice is cleared and the device's setting applies.
    choose(page, labels.THEME_SYSTEM)
    expect(radio(page, labels.THEME_SYSTEM)).to_be_checked()
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
    expect(radio(page, saved)).to_be_checked()
    assert_painted(page, saved)


@pytest.mark.parametrize("saved", ["blue", "<img src=x>", "system", ""])
def test_a_saved_value_that_is_no_explicit_choice_is_system(
    page: Page, saved: str
) -> None:
    page.emulate_media(color_scheme="dark")
    page.add_init_script(
        f"localStorage.setItem({json.dumps(KEY)}, {json.dumps(saved)});"
    )
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    assert theme_attribute(page) is None
    expect(radio(page, labels.THEME_SYSTEM)).to_be_checked()
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
            choose(page, labels.THEME_SYSTEM)
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
def test_the_checked_pill_keeps_its_colors_when_focused_or_hovered(
    page: Page, theme: str, state: str
) -> None:
    page.emulate_media(color_scheme="light" if theme == "dark" else "dark")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    choose(page, theme)
    if state == "focus":
        radio(page, theme).focus()
        expect(radio(page, theme)).to_be_focused()
    else:
        page.locator(CONTROL).get_by_text(
            labels.THEME_CHOICES[theme], exact=True
        ).hover()
    pill = page.locator(f"{CONTROL} label:has(input:checked)")
    colors: dict[str, Any] = pill.evaluate(
        "e => ({color: getComputedStyle(e).color,"
        " background: getComputedStyle(e).backgroundColor})"
    )
    assert colors == {
        "color": rgb(PALETTES[theme]["--on-accent"]),
        "background": rgb(PALETTES[theme]["--accent"]),
    }


def test_the_focused_choice_is_a_named_checked_radio(page: Page) -> None:
    """What the control relies on for its state (an accepted residual: Dash wraps the
    radios in an unnamed listbox of options, see components.theme_control)."""
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    group = page.get_by_role("group", name=labels.THEME_CONTROL)
    expect(group.get_by_role("radio")).to_have_count(len(labels.THEME_CHOICES))
    page.keyboard.press("Tab")  # the header comes first, so Tab lands on the group
    for choice in [labels.THEME_SYSTEM, "light", "dark"]:
        if choice != labels.THEME_SYSTEM:
            page.keyboard.press("ArrowRight")
            applied(page, choice)
        focused = page.locator(":focus")
        expect(focused).to_have_role("radio")
        expect(focused).to_have_accessible_name(labels.THEME_CHOICES[choice])
        expect(focused).to_be_checked()
        checked = [
            r.is_checked() for r in page.locator(f"{CONTROL} input[type=radio]").all()
        ]
        assert checked.count(True) == 1
    names = page.locator(f"{CONTROL} input[type=radio]").evaluate_all(
        "inputs => inputs.map(i => i.name)"
    )
    assert len(set(names)) == 1 and names[0]
    assert_painted(page, "dark")


def test_the_three_choices_keep_one_row_at_a_phones_width(page: Page) -> None:
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    tops = page.locator(f"{CONTROL} label").evaluate_all(
        "labels => labels.map(l => Math.round(l.getBoundingClientRect().top))"
    )
    assert len(tops) == len(labels.THEME_CHOICES) and len(set(tops)) == 1, tops
    assert page.evaluate("document.documentElement.scrollWidth") == 390


def test_the_store_follows_the_device_only_under_system(page: Page) -> None:
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

    # Back to System under a dark device: dark is already in effect, so no write;
    # then the device's change is followed again.
    calls = probe_calls(page)
    choose(page, labels.THEME_SYSTEM)
    switch_device(page, "light")
    assert_painted(page, "light")
    assert probe_calls(page) == calls + 1


def test_returning_to_system_re_resolves_and_skips_an_unchanged_theme(
    page: Page,
) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    choose(page, "dark")
    assert_painted(page, "dark")
    choose(page, labels.THEME_SYSTEM)
    assert_painted(page, "light")
    # Light under a light device: the theme in effect is unchanged, so the store is
    # not written and a chart would not re-template. The barrier, a change to Dark,
    # is one write; a write of the unchanged theme would make it two.
    calls = probe_calls(page)
    choose(page, "light")
    expect(radio(page, "light")).to_be_checked()
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
    for choice in ["dark", "light", labels.THEME_SYSTEM]:
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


def test_refused_storage_keeps_the_choice_for_the_page(page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.add_init_script(REFUSED_STORAGE)
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    expect(radio(page, labels.THEME_SYSTEM)).to_be_checked()
    choose(page, "dark")
    assert_painted(page, "dark")
    page.locator('main a[href="/elections"]').click()
    assert_rendered(page, ELECTIONS_SUCCESS)
    assert_painted(page, "dark")
