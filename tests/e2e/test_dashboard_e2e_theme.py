"""The theme choice in a browser (#359): System, Light and Dark, remembered per browser,
applied before first paint, and the theme in effect exposed to Dash for charts (#432).

The store holding the theme in effect is read through ``serve.py``'s theme probe, a
hidden div a test-only clientside callback writes from the store, so these tests see
what a chart's callback would see. The device's setting is Playwright's emulated
``prefers-color-scheme``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

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
from tests.e2e.serve import THEME_PROBE_CALLS, THEME_PROBE_ID

pytestmark = pytest.mark.e2e

STYLESHEET = Path(appmod.__file__).parent / "assets" / "style.css"
KEY = appmod.THEME_STORAGE_KEY
PROBE = f"#{THEME_PROBE_ID}"
CONTROL = f"#{components.THEME_CONTROL_ID}"
CANDIDATE_SUCCESS = "#candidate"


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


def radio(page: Page, choice: str):  # type: ignore[no-untyped-def]
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
    expected = None if choice == "system" else choice
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
    """The page shows ``theme``'s palette, and the store holds it."""
    expect(page.locator(PROBE)).to_have_text(theme)
    assert (
        page.evaluate("getComputedStyle(document.documentElement).colorScheme") == theme
    )
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == rgb(
        PALETTES[theme]["--page"]
    )


@pytest.mark.parametrize("os_scheme", ["light", "dark"])
def test_with_no_saved_choice_the_page_follows_the_device(
    page: Page, os_scheme: str
) -> None:
    page.emulate_media(color_scheme=os_scheme)  # type: ignore[arg-type]
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    expect(radio(page, "system")).to_be_checked()
    assert theme_attribute(page) is None
    assert_painted(page, os_scheme)


def test_a_choice_persists_across_pages_and_reloads(page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    choose(page, "dark")
    expect(radio(page, "dark")).to_be_checked()
    assert theme_attribute(page) == "dark"
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
    choose(page, "system")
    expect(radio(page, "system")).to_be_checked()
    assert theme_attribute(page) is None
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
    expect(radio(page, "system")).to_be_checked()
    assert_painted(page, "dark")


#: The ``--Dash-*`` variables the controls paint with, and the token each maps to in
#: the dark palette; in the light palette they keep Dash's own values.
CONTROL_VARIABLES = {
    "--Dash-Text-Primary": "--text",
    "--Dash-Fill-Inverse-Strong": "--surface",
    "--Dash-Fill-Interactive-Strong": "--accent",
    "--Dash-Stroke-Strong": "--border",
}


def _variables(page: Page, selector: str) -> dict[str, str]:
    values: dict[str, str] = page.locator(selector).first.evaluate(
        "(element, names) => Object.fromEntries(names.map(name =>"
        " [name, getComputedStyle(element).getPropertyValue(name).trim()]))",
        list(CONTROL_VARIABLES),
    )
    return values


@pytest.mark.parametrize(
    ("os_scheme", "choice"), [("light", "dark"), ("dark", "light")]
)
def test_the_controls_follow_an_explicit_choice_against_the_device(
    page: Page, os_scheme: str, choice: str
) -> None:
    page.emulate_media(color_scheme=os_scheme)  # type: ignore[arg-type]
    # What the controls paint with under the choice: the device set the same way.
    page.goto("/elections")
    assert_rendered(page, ELECTIONS_SUCCESS)
    page.emulate_media(color_scheme=choice)  # type: ignore[arg-type]
    expected = {sel: _variables(page, sel) for sel in (YEARS, PV)}
    if choice == "dark":
        for name, token in CONTROL_VARIABLES.items():
            assert expected[YEARS][name] == DARK[token], name
    page.emulate_media(color_scheme=os_scheme)  # type: ignore[arg-type]
    assert {sel: _variables(page, sel) for sel in (YEARS, PV)} != expected

    choose(page, choice)
    assert_painted(page, choice)
    assert {sel: _variables(page, sel) for sel in (YEARS, PV)} == expected

    page.goto("/election/2016")
    assert_rendered(page, ELECTION_SUCCESS)
    assert _variables(page, "#election-state") == expected[YEARS]

    page.goto("/candidate/andrew-jackson")
    assert_rendered(page, CANDIDATE_SUCCESS)
    pill = page.locator(f"{CANDIDATE_SUCCESS} .year-buttons label").first
    accent = rgb(PALETTES[choice]["--accent"])
    assert pill.evaluate("e => getComputedStyle(e).borderTopColor") == accent
    checked = page.locator(
        f"{CANDIDATE_SUCCESS} .year-buttons label:has(input:checked)"
    )
    assert checked.evaluate("e => getComputedStyle(e).backgroundColor") == accent
    assert checked.evaluate("e => getComputedStyle(e).color") == rgb(
        PALETTES[choice]["--on-accent"]
    )


def test_the_control_is_a_named_radio_group_the_keyboard_operates(page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    group = page.get_by_role("group", name=labels.THEME_CONTROL)
    expect(group.get_by_role("radio")).to_have_count(len(labels.THEME_CHOICES))
    page.keyboard.press("Tab")  # the header comes first, so Tab lands on the group
    expect(radio(page, "system")).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(radio(page, "light")).to_be_checked()
    applied(page, "light")
    page.keyboard.press("ArrowRight")
    expect(radio(page, "dark")).to_be_checked()
    applied(page, "dark")
    assert_painted(page, "dark")


def test_the_store_follows_the_device_only_under_system(page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    assert_painted(page, "light")
    page.emulate_media(color_scheme="dark")
    assert_painted(page, "dark")

    choose(page, "light")
    assert_painted(page, "light")
    calls = probe_calls(page)
    page.emulate_media(color_scheme="light")
    page.emulate_media(color_scheme="dark")
    assert_painted(page, "light")
    assert probe_calls(page) == calls  # an explicit choice ignores the device

    # Back to System under a dark device: the theme in effect is re-resolved.
    choose(page, "system")
    assert_painted(page, "dark")


def test_returning_to_system_re_resolves_and_skips_an_unchanged_theme(
    page: Page,
) -> None:
    page.emulate_media(color_scheme="light")
    page.goto("/")
    assert_rendered(page, HOME_SUCCESS)
    choose(page, "dark")
    assert_painted(page, "dark")
    choose(page, "system")
    assert_painted(page, "light")
    # Light under a light device: the theme in effect is unchanged, so the store is
    # not written and a chart would not re-template.
    calls = probe_calls(page)
    choose(page, "light")
    expect(radio(page, "light")).to_be_checked()
    assert theme_attribute(page) == "light"
    assert probe_calls(page) == calls


#: A window whose storage refuses every access, as a private window can.
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
    expect(radio(page, "system")).to_be_checked()
    choose(page, "dark")
    assert_painted(page, "dark")
    page.locator('main a[href="/elections"]').click()
    assert_rendered(page, ELECTIONS_SUCCESS)
    assert_painted(page, "dark")
