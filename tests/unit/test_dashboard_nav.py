"""The site navigation (#448): the bar in the shared layout's header, its links and
wording, the current-page table each page's ``nav=`` declares, and the inline callback
that writes ``aria-current``.

These tests read the layout, the registry and the callback's source. What the browser
does with them (one row at 390 px, the marker after a navigation, Tab order, no full
reload) is ``tests/e2e/test_dashboard_e2e_nav.py``'s.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import dash
import pytest
from dash._pages import _path_to_page

from explore import api, components, config, labels
from explore import app as appmod
from tests.nav_marks import MARKS
from tests.unit.test_dashboard_app import offline_client, route


@pytest.fixture(autouse=True)
def _offline_process_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "CLIENT", offline_client())


def nodes(node: Any) -> list[Any]:
    found = [node]
    children = getattr(node, "children", None)
    if isinstance(children, list | tuple):
        for child in children:
            found.extend(nodes(child))
    elif children is not None and not isinstance(children, str):
        found.extend(nodes(children))
    return found


def text(node: Any) -> str:
    """The text a component tree shows, joined as a browser joins inline content."""
    if isinstance(node, str):
        return node
    children = getattr(node, "children", None)
    if isinstance(children, list | tuple):
        return "".join(text(child) for child in children)
    return "" if children is None else text(children)


def header() -> Any:
    return appmod.app.layout.children[0]


def site_nav() -> Any:
    return header().children[0]


def page_global(module: str, name: str) -> Any:
    """A page module's global, through its layout: Dash executes a page before it is
    in ``sys.modules``, so a test never imports a second copy."""
    return dash.page_registry[module]["layout"].__globals__[name]


class TestStructure:
    def test_one_site_nav_inside_the_header_before_main(self) -> None:
        layout = appmod.app.layout
        head, main, _store = layout.children
        assert type(head).__name__ == "Header" and head.className == "site-header"
        assert type(main).__name__ == "Main" and main.children is dash.page_container
        navs = [n for n in nodes(layout) if type(n).__name__ == "Nav"]
        assert navs == [site_nav()]
        nav = site_nav()
        assert nav.id == components.SITE_NAV_ID
        assert nav.className == "site-nav"
        # No data-current until the callback's first run writes one, so its presence
        # shows the callback ran (an e2e "no mark" check waits on it).
        assert "data-current" not in nav.to_plotly_json()["props"]

    def test_the_landmark_is_named_apart_from_the_election_views_nav(self) -> None:
        name = getattr(site_nav(), "aria-label")
        assert name == labels.SITE_NAV_LABEL
        assert name not in {
            labels.ELECTION_NAV_LABEL,
            labels.ELECTION_SECTIONS_LABEL,
            *(
                labels.ELECTION_NAV_SECTION_LABEL.format(section=text)
                for text in (labels.SECTION_STATES, labels.SECTION_PER_CAPITA)
            ),
        }

    def test_site_name_three_links_then_the_toggle_four_on_the_right(self) -> None:
        head = header()
        nav, toggle = head.children
        # The toggle follows the nav in the header, outside the landmark, exactly once.
        assert toggle.id == components.THEME_CONTROL_ID
        assert [
            n
            for n in nodes(appmod.app.layout)
            if getattr(n, "id", None) == components.THEME_CONTROL_ID
        ] == [toggle]
        assert components.THEME_CONTROL_ID not in {
            getattr(n, "id", None) for n in nodes(nav)
        }
        name, *right = nav.children
        assert [type(n).__name__ for n in nav.children] == ["Link"] * 3 + ["A"]
        # The cap: three links and the toggle at the right, four entries.
        assert len([*right, toggle]) == 4
        assert name.className == "site-name"
        assert [n.id for n in nav.children] == [
            *components.NAV_LINK_IDS.values(),
            components.NAV_API_DOCS_ID,
        ]
        assert [text(n) for n in right] == [
            labels.NAV_ELECTIONS,
            labels.NAV_STATES,
            labels.NAV_API_DOCS,
        ]

    def test_in_app_links_are_dcc_links_to_their_paths(self) -> None:
        nav = site_nav()
        assert list(components.NAV_LINKS) == ["home", "elections", "states"]
        for link, (link_id, path) in zip(
            nav.children[:3], components.NAV_LINKS.values(), strict=True
        ):
            assert type(link).__name__ == "Link"
            assert (link.id, link.href) == (link_id, path)
            assert getattr(link, "target", None) is None
            assert getattr(link, "refresh", False) is False

    def test_api_docs_is_a_same_tab_link_built_from_the_api_base(self) -> None:
        docs = site_nav().children[3]
        assert type(docs).__name__ == "A"
        assert docs.href == config.API_BASE + "/docs" == appmod.API_DOCS_URL
        assert docs.href == "https://api.us-presidential-election-center.org/docs"
        assert getattr(docs, "target", None) is None
        assert docs.title == labels.NAV_API_DOCS_TITLE

    def test_no_page_marks_success_with_a_header_element(self) -> None:
        # The bar renders from no data, so it is never a page's success marker. That it
        # reads none is held elsewhere: site_nav takes only a URL string, components
        # imports no api (TestSharedPieces.test_the_shared_modules_read_no_api, in
        # test_dashboard_elections.py), and the e2e degraded template, /state/TX, still
        # shows the bar.
        ids = {getattr(n, "id", None) for n in nodes(header())} - {None}
        assert ids
        successes = {page.get("success") for page in dash.page_registry.values()} - {
            None
        }
        assert successes
        assert not ids & successes


class TestWording:
    def test_the_full_name_is_the_site_title(self) -> None:
        # The link's name is short + rest, so it starts with what is shown (WCAG 2.5.3);
        # it must also be the site title, which a short form like "Home" would break.
        assert labels.SITE_NAME_SHORT + labels.SITE_NAME_REST == config.SITE_TITLE
        assert config.SITE_TITLE.endswith(labels.HOME_HEADING)

    def test_the_site_name_link_shows_the_short_form_and_names_the_full(self) -> None:
        name = site_nav().children[0]
        (inner,) = [name.children]
        assert type(inner).__name__ == "Span"
        short, rest = inner.children
        assert short == labels.SITE_NAME_SHORT
        assert rest.className == "site-name-rest"
        assert rest.children == labels.SITE_NAME_REST
        assert text(name) == config.SITE_TITLE

    def test_the_home_heading_is_the_one_constant(self) -> None:
        source = page_global("pages.home", "labels")
        assert source is labels
        tree = dash.page_registry["pages.home"]["layout"]()
        assert tree.children[0].children == labels.HOME_HEADING

    def test_no_raw_value_or_underscore_in_the_bar(self) -> None:
        shown = text(site_nav())
        assert "_" not in shown
        assert "dashboard" not in shown.lower()


# --- the current-page table ------------------------------------------------------------


def js_decode(pathname: str) -> str:
    """NAV_CALLBACK's decode, run in Python: each maximal run of ``%XX`` escapes as
    UTF-8 with replacement, every other character as it is."""
    return re.sub(
        r"(?:%[0-9A-Fa-f]{2})+",
        lambda run: bytes.fromhex(run.group(0).replace("%", "")).decode(
            "utf-8", "replace"
        ),
        pathname,
    )


def js_match(pathname: str) -> appmod.NavEntry | None:
    """The rule NAV_CALLBACK implements, run in Python on the embedded table: decode
    each run of escapes, strip leading and trailing slashes, first pattern or path
    match wins. The JS itself runs on the same corpus in the browser
    (``test_the_registered_callback_marks_every_path``, ``test_dashboard_e2e_nav.py``);
    ``TestNavCallback`` pins its decode, strip and match lines."""
    path = re.sub(r"^/+|/+$", "", js_decode(pathname))
    for entry in appmod.NAV_TABLE:
        if (entry.pattern is not None and re.search(entry.pattern, path)) or (
            path == entry.path
        ):
            return entry
    return None


def router_choice(pathname: str, monkeypatch: pytest.MonkeyPatch) -> str | None:
    """The module of the page Dash's router picks for ``pathname``, or ``None``, read
    off ``dash.dash._path_to_page`` while a real routing request runs."""
    chosen: list[str | None] = []

    def spy(key: str) -> Any:
        page, path_vars = _path_to_page(key)
        chosen.append(page.get("module") if page else None)
        return page, path_vars

    monkeypatch.setattr(dash.dash, "_path_to_page", spy)
    route(pathname)
    assert len(chosen) == 1, (pathname, chosen)
    return chosen[0]


class TestCurrentPage:
    def test_every_registered_page_declares_its_link(self) -> None:
        for page in dash.page_registry.values():
            assert "nav" in page, page["module"]
            assert page["nav"] is None or page["nav"] in components.NAV_LINKS
        declared = {p["module"]: p["nav"] for p in dash.page_registry.values()}
        assert declared == {
            "pages.home": "home",
            "pages.elections": "elections",
            "pages.election": "elections",
            "pages.election_states": "elections",
            "pages.election_per_capita": "elections",
            "pages.states": "states",
            "pages.state": "states",
            "pages.candidate": None,
            "pages.not_found_404": None,
        }

    def test_the_table_is_the_registry_in_order(self) -> None:
        pages = list(dash.page_registry.values())
        assert [appmod.nav_entry(p) for p in pages] == list(appmod.NAV_TABLE)

    @pytest.mark.parametrize("path", sorted(MARKS))
    def test_the_matcher_agrees_with_dashs_router(
        self, path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry = js_match(path)
        # The router's own decision, observed in a real routing request, so the oracle
        # never re-implements the router's rule (#456: a re-implemented oracle kept
        # agreeing with a rule Dash 4.5.0 had changed).
        module = router_choice(path, monkeypatch)
        chosen = (
            next(
                p["module"]
                for p in dash.page_registry.values()
                if appmod.nav_entry(p) == entry
            )
            if entry is not None
            else None
        )
        assert chosen == module, path
        mark = (
            None
            if entry is None or entry.link is None
            else (
                entry.link,
                entry.current,
            )
        )
        assert mark == MARKS[path], path

    def test_a_page_without_nav_or_with_an_unknown_one_fails(self) -> None:
        base = {"module": "pages.fake", "path": "/fake", "path_template": None}
        with pytest.raises(RuntimeError, match="registers no nav="):
            appmod.nav_entry(base)
        with pytest.raises(RuntimeError, match="unknown nav="):
            appmod.nav_entry({**base, "nav": "candidates"})

    def test_a_template_needing_an_escape_fails(self) -> None:
        page = {
            "module": "pages.fake",
            "path": "/fake.page/none",
            "path_template": "/fake.page/<x>",
            "nav": None,
        }
        with pytest.raises(RuntimeError, match="template to escape"):
            appmod.nav_entry(page)

    def test_current_is_page_for_the_links_own_page_and_true_for_a_detail(
        self,
    ) -> None:
        def entry(path: str, template: str | None, nav: str) -> appmod.NavEntry:
            page = {"module": "m", "path": path, "path_template": template, "nav": nav}
            return appmod.nav_entry(page)

        assert entry("/elections", None, "elections").current == "page"
        assert entry("/election/none", "/election/<year>", "elections").current == (
            "true"
        )
        assert entry("/states", None, "elections").current == "true"
        assert entry("/", None, "home").current == "page"
        # A templated page is a detail page even where its path equals its link's
        # target: it marks "true", never "page" (no registered page is one today).
        assert entry("/elections", "/elections/<x>", "elections").current == "true"


class TestNavCallback:
    def test_the_script_embeds_the_table_and_the_link_ids(self) -> None:
        script = appmod.NAV_CALLBACK
        table = [entry.__dict__ for entry in appmod.NAV_TABLE]
        assert f"var table = {json.dumps(table)};" in script
        assert f"var ids = {json.dumps(components.NAV_LINK_IDS)};" in script
        # The router's strip, both ends, and the fallback before the Location reports.
        assert r'path = path.replace(/^\/+|\/+$/g, "");' in script
        # The match line, literally: the rule js_match models, and no flags.
        assert (
            "if ((entry.pattern !== null && new RegExp(entry.pattern).test(path))"
            " || path === entry.path) { hit = entry; } }"
        ) in script
        assert script.count("new RegExp(") == 1
        # First match wins, as in the router: the loop stops at the first hit. Today
        # no path matches two pages, so only this pin notices a last-match loop.
        assert (
            "for (var i = 0; i < table.length && hit === null; i++) {" in script
        )
        assert "window.location.pathname" in script
        # Decoded once, before the strip, as the router decodes (D089): each run of
        # escapes as UTF-8 with replacement, the rule js_decode models. Never
        # decodeURIComponent, which throws on a malformed escape the router decodes.
        decode = (
            " path = path.replace(/(?:%[0-9A-Fa-f]{2})+/g, function (run) {"
            " var bytes = new Uint8Array(run.length / 3);"
            " for (var b = 0; b < bytes.length; b++) {"
            " bytes[b] = parseInt(run.substr(b * 3 + 1, 2), 16); }"
            " return new TextDecoder().decode(bytes); });"
        )
        assert decode in script
        assert script.index(decode) < script.index(r"path = path.replace(/^\/+")
        assert script.count("TextDecoder(") == 1
        assert "decodeURI" not in script and "unescape(" not in script

    def test_the_app_is_served_at_the_root_as_the_matcher_assumes(self) -> None:
        # The JS strips only slashes, which is all the router strips at the root; app.py
        # refuses any other prefix at import, so a prefixed deployment fails loudly
        # rather than losing the marker.
        assert appmod.app.config.requests_pathname_prefix == "/"
        assert appmod.app.strip_relative_path("//election/1824/") == "election/1824"
        source = Path(appmod.__file__).read_text(encoding="utf-8")
        assert 'if app.config.requests_pathname_prefix != "/":' in source

    def test_it_writes_aria_current_and_never_false(self) -> None:
        script = appmod.NAV_CALLBACK
        assert 'link.setAttribute("aria-current", hit.current)' in script
        assert 'link.removeAttribute("aria-current")' in script
        assert '"false"' not in script
        values = {e.current for e in appmod.NAV_TABLE} - {None}
        assert values == {"page", "true"}

    def test_one_clientside_callback_on_the_routers_location(self) -> None:
        assert appmod.server.test_client().get("/").status_code == 200
        key = f"{components.SITE_NAV_ID}.data-current"
        spec = appmod.app.callback_map[key]
        assert spec["inputs"] == [{"id": "_pages_location", "property": "pathname"}]
        assert spec["state"] == []
        assert "callback" not in spec  # clientside: no Python function runs
        # No other callback reads or writes the bar: it makes no server call.
        nav_ids = {
            components.SITE_NAV_ID,
            components.NAV_API_DOCS_ID,
            *components.NAV_LINK_IDS.values(),
        }
        for other, other_spec in appmod.app.callback_map.items():
            if other == key:
                continue
            assert not nav_ids & {i["id"] for i in other_spec["inputs"]}, other
            assert not any(
                other.startswith(f"{i}.") or f"..{i}." in other for i in nav_ids
            ), other
