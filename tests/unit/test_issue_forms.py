"""The UX-review issue form (#514): ``.github/ISSUE_TEMPLATE/ux-review.yml``.

The form is for the owner's review of the live dashboard. The repo is public, so anyone
can read and file it, but it is not a product surface (neither the dashboard nor the
API's published text), so its wording takes no ``ba`` label spec (root ``CLAUDE.md``,
*Who writes wording*). What these tests pin is that it stays in step with the
dashboard: its page dropdown lists exactly the pages the app registers, and its theme
dropdown the names the theme toggle uses. A page added to the dashboard fails here
until the form lists it.

GitHub's issue-form schema is not validated offline: these tests parse the YAML and
compare it with the app's page registry and theme names.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import dash
import pytest
import yaml

from explore import app, labels

FORM = Path(__file__).resolve().parents[2] / ".github" / "ISSUE_TEMPLATE" / "ux-review.yml"

#: The option the form gives Dash's custom-404 page, and its catch-all.
NOT_FOUND_OPTION = "Page not found (the link matches no page)"
OTHER_OPTION = "other"

#: A Dash path variable, ``<year>``; the form writes it ``{year}``, because GitHub
#: strips ``<...>`` from the issue it files.
PATH_VARIABLE = re.compile(r"<(\w+)>")

#: The WCAG 2.2 success criteria the checklist names, with their official titles (all
#: Level A or AA, the #501 target), checked against https://www.w3.org/TR/WCAG22/.
WCAG22_TITLES = {
    "1.1.1": "Non-text Content",
    "1.3.1": "Info and Relationships",
    "1.4.1": "Use of Color",
    "1.4.3": "Contrast (Minimum)",
    "1.4.4": "Resize Text",
    "1.4.10": "Reflow",
    "1.4.11": "Non-text Contrast",
    "2.1.1": "Keyboard",
    "2.1.2": "No Keyboard Trap",
    "2.2.2": "Pause, Stop, Hide",
    "2.4.3": "Focus Order",
    "2.4.6": "Headings and Labels",
    "2.4.7": "Focus Visible",
    "2.4.11": "Focus Not Obscured (Minimum)",
    "2.5.3": "Label in Name",
    "3.3.2": "Labels or Instructions",
    "4.1.2": "Name, Role, Value",
}

#: The checklist's eight items in order (#514 AC2), each with exactly the criteria it
#: names, in the order it names them.
CHECKLIST = {
    "Contrast": ("1.4.3", "1.4.11"),
    "Color as the only cue": ("1.4.1",),
    "Keyboard reach and order": ("2.1.1", "2.1.2", "2.4.3"),
    "Visible focus": ("2.4.7", "2.4.11"),
    "Text resize and reflow at 320 px": ("1.4.4", "1.4.10"),
    "Labels and names": ("1.3.1", "2.4.6", "2.5.3", "3.3.2", "4.1.2"),
    "Motion": ("2.2.2",),
    "Chart alternative": ("1.1.1",),
}

CRITERION = re.compile(r"\b\d\.\d\.\d+\b")


@pytest.fixture(scope="module")
def form() -> dict[str, Any]:
    loaded = yaml.safe_load(FORM.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def field(form: dict[str, Any], field_id: str) -> dict[str, Any]:
    matches = [item for item in form["body"] if item.get("id") == field_id]
    assert len(matches) == 1, field_id
    found: dict[str, Any] = matches[0]
    return found


def help_text(form: dict[str, Any]) -> str:
    return "\n".join(
        item["attributes"]["value"]
        for item in form["body"]
        if item["type"] == "markdown"
    )


def option(page: dict[str, Any]) -> str:
    """The form's option for a registered page."""
    if app.is_not_found_page(page):
        return NOT_FOUND_OPTION
    path = str(page.get("path_template") or page["path"])
    return PATH_VARIABLE.sub(r"{\1}", path)


class TestPages:
    def test_options_are_every_registered_page_plus_other(
        self, form: dict[str, Any]
    ) -> None:
        registered = {option(page) for page in dash.page_registry.values()}
        options = field(form, "page")["attributes"]["options"]
        assert len(options) == len(set(options))
        assert set(options) == registered | {OTHER_OPTION}, (
            "The dashboard's pages changed: update the page dropdown in "
            f"{FORM.relative_to(FORM.parents[2])} to match"
        )

    def test_no_option_carries_an_angle_bracket(self, form: dict[str, Any]) -> None:
        options = field(form, "page")["attributes"]["options"]
        assert not [o for o in options if "<" in o or ">" in o]


class TestTheme:
    def options(self, form: dict[str, Any]) -> list[str]:
        found: list[str] = field(form, "theme")["attributes"]["options"]
        return found

    def test_options_are_the_toggles_names_in_its_order(
        self, form: dict[str, Any]
    ) -> None:
        assert self.options(form) == list(labels.THEME_CHOICES.values())

    def test_each_option_is_its_tooltips_name(self, form: dict[str, Any]) -> None:
        # The field's description sends the reviewer to the toggle's tooltips.
        for value, shown in zip(labels.THEME_CHOICES, self.options(form), strict=True):
            assert labels.THEME_TITLES[value].split(":", 1)[0] == shown


class TestLabels:
    def test_applies_dashboard_ui_by_default(self, form: dict[str, Any]) -> None:
        assert form["labels"] == ["epic:dashboard-ui"]

    def test_help_text_names_the_labels_and_the_routing_test(
        self, form: dict[str, Any]
    ) -> None:
        text = help_text(form)
        assert "owner's page-by-page UX review" in text
        assert "`a11y`" in text
        assert "`epic:dashboard`" in text
        assert "#361" in text
        assert "look the same whatever the data" in text
        assert "reader-facing words goes to `epic:dashboard`" in text
        assert "`/docs`" in text
        assert "`epic:internal-api`" in text


class TestChecklist:
    def items(self, form: dict[str, Any]) -> list[str]:
        attributes = field(form, "accessibility")["attributes"]
        assert attributes["multiple"] is True
        found: list[str] = attributes["options"]
        return found

    def test_the_eight_options_in_order(self, form: dict[str, Any]) -> None:
        names = [item.split(":", 1)[0] for item in self.items(form)]
        assert names == list(CHECKLIST)

    def test_each_item_names_exactly_its_criteria_with_titles(
        self, form: dict[str, Any]
    ) -> None:
        for item, (name, criteria) in zip(
            self.items(form), CHECKLIST.items(), strict=True
        ):
            assert tuple(CRITERION.findall(item)) == criteria, name
            for number in criteria:
                assert f"{number} {WCAG22_TITLES[number]}" in item, (name, number)

    def test_every_listed_criterion_is_used(self) -> None:
        used = {number for criteria in CHECKLIST.values() for number in criteria}
        assert used == set(WCAG22_TITLES)


class TestShape:
    def test_the_fields_the_issue_names_in_order_with_their_types(
        self, form: dict[str, Any]
    ) -> None:
        fields = [(item["id"], item["type"]) for item in form["body"] if "id" in item]
        assert fields == [
            ("page", "dropdown"),
            ("url", "input"),
            ("theme", "dropdown"),
            ("viewport-width", "input"),
            ("seen", "textarea"),
            ("expected", "textarea"),
            ("screenshot", "textarea"),
            ("accessibility", "dropdown"),
        ]

    def test_required_fields(self, form: dict[str, Any]) -> None:
        required = {
            item["id"]
            for item in form["body"]
            if item.get("validations", {}).get("required")
        }
        assert required == {"page", "url", "theme", "seen", "expected"}
