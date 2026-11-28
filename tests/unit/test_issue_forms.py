"""The UX-review issue form (#514): ``.github/ISSUE_TEMPLATE/ux-review.yml``.

The form is read by the repo owner and the loop, never by a dashboard reader, so its
wording is not a ``ba`` label spec. What these tests pin is that it stays in step with the
dashboard: its page dropdown lists exactly the pages the app registers, and its theme
dropdown the theme names the toggle uses. A page added to the dashboard fails here until
the form lists it.

GitHub's issue-form schema is not validated offline; these tests read the YAML only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import dash
import pytest
import yaml

import explore.app  # noqa: F401  (registers every page in dash.page_registry)
from explore import labels

FORM = Path(__file__).resolve().parents[2] / ".github" / "ISSUE_TEMPLATE" / "ux-review.yml"

#: The 404 page's module and the option the form gives it.
NOT_FOUND_MODULE = "pages.not_found_404"
NOT_FOUND_OPTION = "Page not found (the link matches no page)"
OTHER_OPTION = "other"

#: The checklist's eight items, by the text before each item's colon (#514 AC2).
CHECKLIST_ITEMS = (
    "Contrast",
    "Color as the only cue",
    "Keyboard reach and order",
    "Visible focus",
    "Text resize and reflow at 320 px",
    "Labels and names",
    "Motion",
    "Chart alternative",
)

#: The WCAG 2.2 success criteria the checklist may name, with their official titles
#: (all Level A or AA, the #501 target), checked against https://www.w3.org/TR/WCAG22/.
WCAG22_A_AA = {
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
    "2.4.7": "Focus Visible",
    "2.4.11": "Focus Not Obscured (Minimum)",
    "2.5.3": "Label in Name",
    "3.3.2": "Labels or Instructions",
    "4.1.2": "Name, Role, Value",
}

CRITERION = re.compile(r"\b(\d\.\d\.\d+) ")


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


class TestPages:
    def test_options_are_every_registered_page_plus_other(
        self, form: dict[str, Any]
    ) -> None:
        registered = {
            NOT_FOUND_OPTION
            if module == NOT_FOUND_MODULE
            else page.get("path_template") or page["path"]
            for module, page in dash.page_registry.items()
        }
        options = field(form, "page")["attributes"]["options"]
        assert len(options) == len(set(options))
        assert set(options) == registered | {OTHER_OPTION}

    def test_the_registry_has_the_404_page(self) -> None:
        # The mapping above relies on this module name; a rename must fail loudly here.
        assert NOT_FOUND_MODULE in dash.page_registry


class TestTheme:
    def test_options_are_the_toggles_names_in_its_order(
        self, form: dict[str, Any]
    ) -> None:
        options = field(form, "theme")["attributes"]["options"]
        assert options == list(labels.THEME_CHOICES.values())


class TestLabels:
    def test_applies_dashboard_ui_by_default(self, form: dict[str, Any]) -> None:
        assert form["labels"] == ["epic:dashboard-ui"]

    def test_help_text_names_a11y_and_the_routing_test(
        self, form: dict[str, Any]
    ) -> None:
        text = help_text(form)
        assert "`a11y`" in text
        assert "`epic:dashboard`" in text
        assert "#361" in text
        assert "look the same whatever the data" in text


class TestChecklist:
    def items(self, form: dict[str, Any]) -> list[str]:
        checklist = field(form, "accessibility")
        assert checklist["type"] == "checkboxes"
        return [option["label"] for option in checklist["attributes"]["options"]]

    def test_the_eight_items_in_order(self, form: dict[str, Any]) -> None:
        names = tuple(item.split(":", 1)[0] for item in self.items(form))
        assert names == CHECKLIST_ITEMS

    def test_each_item_names_wcag22_criteria_by_number_and_title(
        self, form: dict[str, Any]
    ) -> None:
        for item in self.items(form):
            named = CRITERION.findall(item)
            assert named, item
            for number in named:
                assert number in WCAG22_A_AA, (item, number)
                assert f"{number} {WCAG22_A_AA[number]}" in item, (item, number)

    def test_no_item_is_required(self, form: dict[str, Any]) -> None:
        options = field(form, "accessibility")["attributes"]["options"]
        assert not any(option.get("required") for option in options)


class TestShape:
    def test_field_ids_are_unique(self, form: dict[str, Any]) -> None:
        ids = [item["id"] for item in form["body"] if "id" in item]
        assert len(ids) == len(set(ids))

    def test_required_fields(self, form: dict[str, Any]) -> None:
        required = {
            item["id"]
            for item in form["body"]
            if item.get("validations", {}).get("required")
        }
        assert required == {"page", "url", "theme", "seen", "expected"}

    def test_the_fields_the_issue_names(self, form: dict[str, Any]) -> None:
        ids = [item["id"] for item in form["body"] if "id" in item]
        assert ids == [
            "page",
            "url",
            "theme",
            "viewport-width",
            "seen",
            "expected",
            "screenshot",
            "accessibility",
        ]
