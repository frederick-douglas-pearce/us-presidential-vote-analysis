"""The one label table: a plain-language header for each public API field (#306).

Every table labels its columns from :data:`LABELS`, keyed by the field name the public
``/v1`` API returns, never by a snapshot column name. Later tables add rows here rather
than labelling inline. The table is flat, so a key means one thing in every table that
shows it, and a field name the API uses with two meanings needs a qualified key for the
second. ``candidate_count`` already is one: here it is a ``/v1/elections`` row's count
of one year's candidates, while ``/v1/meta``'s counts the snapshot's distinct
candidates, so a table showing the latter needs its own key. ``coverage`` is another:
the plain key is a per-capita row's (#280), whether a census figure governs that
election, so a table showing the provenance block's year windows needs its own key.

The raw field name stays on hand because these tables double as the debugging view: as
each header's tooltip, and in a "Column names" glossary under the table, which works
where hovering does not. Like ``components``, this module reads no API.

The cells a null or a closed value can reach live here too (#307), so a later table
(S4's state and candidate histories) shows the same thing the one-election view does:
a null is never bare, and each closed value of ``pv_status`` and
``electoral_count_status`` has its plain label. The per-capita tables' cells and help
text (#280) follow the same rule: a null ratio or population is never bare: it says
why it is null where the row explains it, and names no cause where it does not. The
election panel's cells (#308) follow it too: a null popular-vote or hybrid field outside
the popular-vote window reads :data:`NOT_APPLICABLE`, never "No"; a value is shown
whatever the year, as :func:`popular_votes` shows one. The wording follows the project
glossary (``docs/glossary.md``) and its wording rules (#352): no underscore or raw field
name in a label, cell or note, and "counted" only for vote counts. No cell this module
words shows a raw value either (#355): a null or blank names no cause
(:data:`NOT_IN_DATASET`), and a value it has no wording for reads :data:`UNRECOGNIZED`,
with :data:`UNRECOGNIZED_NOTE` as its help text (:func:`cell`). Candidate and state
names in table rows are shown as served, an open vocabulary, not codes (#367): the API
types them as required text, so a served row never carries a null or non-text name,
though that type does not rule out a blank one. The panel's winners are nullable and
read through :func:`winner`.
The party is the nominating party (#389, D077): a closed vocabulary, each code read
from :data:`NOMINATING_PARTY`, never word-cased from the code.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, TypeGuard

from dash import html

#: Plain label for each public field name (approved by the owner, 2026-10-01; the
#: per-capita rows and the election panel's rows (#308), 2026-10-08; reworded to the
#: glossary's decisions, #352).
LABELS: dict[str, str] = {
    "year": "Election year",
    "candidate_count": "Candidates with electoral votes",
    "has_popular_vote": "Popular vote in this dataset",
    # The one-election view (#307). Series wording: appointed / cast / counted.
    "state": "State",
    "candidate": "Candidate",
    # The nominating party (#389, D077): the one party a table shows, in every year.
    "nominating_party": "Party",
    "nominating_party_note": "Party note",
    "state_electoral_votes": "Electors appointed (state)",
    "electoral_votes": "Electoral votes cast",
    "electoral_votes_counted": "Electoral votes counted",
    "electoral_count_status": "Count status",
    "electoral_count_status_reason": "Count status: the National Archives' reason",
    "pv_status": "Popular vote in this state",
    "popular_votes": "Popular votes",
    "national_electoral_votes": "Electoral votes cast (nation)",
    "national_electoral_votes_counted": "Electoral votes counted (nation)",
    "national_electoral_denominator": "Electors appointed (nation)",
    "electoral_rank": "Electoral rank (counted votes)",
    "took_office": "Took office",
    "national_pv_votes": "Popular votes (nation)",
    "ec_share_full": "Electoral share (counted ÷ appointed)",
    "pv_share": "Popular-vote share",
    # The per-capita tables (#280). ``state_electoral_votes`` above is the same
    # appointed allotment, so it keeps its label.
    "governing_census_year": "Census used",
    "population": "Population (from that census)",
    "boundary_basis": "Borders used",
    "coverage": "Census figure",
    "persons_per_electoral_vote": "People per electoral vote",
    # The election panel (#308), from a ``/v1/elections/{year}`` response's
    # ``election`` block. ``ec_winner`` is the largest counted share, not who took
    # office (1824: Jackson led and the House chose Adams), so its label follows
    # ``ec_determinative`` (#355, :func:`ec_winner_label`); this one claims neither a
    # majority nor its absence, for wherever no ``ec_determinative`` is in hand.
    "ec_winner": "Electoral College leader",
    "pv_winner": "Popular-vote winner",
    "hybrid_winner": "Hybrid winner",
    "pv_flip": "Popular-vote winner differs from the Electoral College result",
    "hybrid_flip": "Hybrid winner differs from the Electoral College result",
    "ec_margin": "Electoral margin (percentage points)",
    "pv_margin": "Popular-vote margin (percentage points)",
    "hybrid_margin": "Hybrid margin (percentage points)",
    "ec_determinative": "Electoral College majority",
    "pv_coverage": "Share of electors appointed by states that held a popular vote",
    # T3's hybrid column (#308). ``pv_coverage`` above means the same on a summary row.
    "hybrid_score": "Hybrid score",
    # Charts C4 and C5 and their companion table (#436): N1's ``elections`` item's
    # appointed allotment (the same national figure as
    # ``national_electoral_denominator``) and N1's per-year total popular vote.
    "electoral_denominator": "Electors appointed (nation)",
    "national_pv_denominator": "Total popular vote (nation)",
    # Chart C10 and its companion table (#582): a ``/v1/states/{usps}`` row's total
    # popular vote (restored; #436's wording, retired with C5's one-state mode, #562).
    "state_popular_total": "Total popular vote (state)",
    # T1's two N1 columns (#563, served by #570): "cast" because the sum is of votes
    # cast while the rank is by votes counted.
    "electoral_votes_outside_top_two": "Electoral votes cast outside the top two",
    "electors_without_a_counted_vote": "Electors without a counted vote",
}

#: Each closed ``pv_status`` value, as a filter option reads it.
PV_STATUS: dict[str, str] = {
    "popular_vote": "Popular vote held",
    "legislature_chosen": "State legislature chose the electors",
    "not_participating": "Took no part",
}

#: Each closed ``electoral_count_status`` value: its label, and for a value other than
#: ``counted``, what it means.
COUNT_STATUS: dict[str, tuple[str, str | None]] = {
    "counted": ("Counted", None),
    "not_counted": ("Not counted", "Congress decided not to count them"),
    "disputed": ("Disputed", "Congress never reached a decision"),
}

#: Each closed ``boundary_basis`` value of a per-capita row (#280).
BOUNDARY_BASIS: dict[str, str] = {
    "at_election": "Borders at the election",
    "present_day": "Present-day borders",
}

#: The per-capita ``coverage`` value that explains a null population and ratio.
NO_GOVERNING_FIGURE = "no_governing_figure"

#: Each closed ``coverage`` value of a per-capita row (#280).
PER_CAPITA_COVERAGE: dict[str, str] = {
    "covered": "Available",
    NO_GOVERNING_FIGURE: "No census figure for this state at this election",
}

#: A null ratio's cell when the state's allotment is zero (its votes were withheld).
NO_ELECTORAL_VOTES = "No electoral votes this election"

#: Why each election reads the census it does: one line under each per-capita table.
#: It follows the glossary's *Census used* and does not say the census set the
#: state's electoral votes, which is false for some rows (#423).
GOVERNING_CENSUS_NOTE = (
    "Population is from the census used for the latest redistribution of House "
    "seats made before the election, which is not always the nearest census: 2020 "
    "uses the 2010 census, and 1924 and 1928 use 1910, because Congress did not "
    "redistribute House seats after the 1920 census."
)

#: What each ``boundary_basis`` value describes. Neutral about the Census Bureau's
#: tabulation, which this dataset reports as published.
BOUNDARY_NOTE = (
    "At the election: the people inside the state's borders when the election was "
    "held. Present-day borders: the Census Bureau's figure for the state as its "
    "table reports it, which this dataset does not claim matches the state's borders "
    "at that election."
)

#: The popular-vote cells for a null figure (the null table in #307).
LEGISLATURE_CHOSE = "No popular vote: the state legislature chose the electors"
TOOK_NO_PART = "Took no part in this election"
BEFORE_WINDOW = "Popular vote held; not in this dataset before {pv_year_min}"
AFTER_WINDOW = "Popular vote held; not in this dataset yet"
NO_FIGURE = "No popular-vote figure in this dataset for this candidate in this state"
NO_NATIONAL_FIGURE = "No popular-vote figure in this dataset for this candidate"
#: A state's total popular vote with no figure inside the window: C10's table (#582;
#: #436's wording, retired with C5's one-state mode by #562 and restored).
NO_STATE_TOTAL = "No total popular vote in this dataset for this state"
#: The nation's total popular vote with no figure inside the window (#436), in the
#: C4/C5 table and C5.
NO_NATIONAL_TOTAL = "No total popular vote in this dataset for this election"

#: What the party column shows (#389): a table note under T2–T5 and in their
#: downloads. The second sentence keeps the rule-2 years true (D077).
PARTY_NOTE = (
    "The party column shows the party that nominated the candidate for President in "
    "that election. In 1824 and 1828, for a candidate no national convention or caucus "
    "nominated, and in 1836, for a Whig candidate, it shows the party this dataset's "
    "source names for them."
)

#: A null party's one cause (#389, D077): a null cell's help text and a table note.
#: Dataset-first, with no promise; it is not "without a nomination".
PARTY_NULL_NOTE = (
    'A party shown as "Not in this dataset" (an empty cell in the download) means this '
    "dataset records no party for that candidate in that election. It does not say "
    "whether a party nominated them."
)

#: The ``no_nomination`` cell (#389): distinct from the null, never "no party", and
#: never saying a withdrawn nominee was not nominated (D077).
NO_NOMINATION = "Without a party's nomination for President when the electors voted"

#: Help text on a ``no_nomination`` cell: it says what the ``nominating_party`` field
#: descriptions in ``src/usvote/api/models.py`` say, in the dashboard's wording (ba
#: spec, #389).
NO_NOMINATION_NOTE = (
    "Either no party nominated this candidate for President, or the nomination was "
    "withdrawn before the electors voted. It does not mean the candidate had no party."
)

#: The visible list of row notes under T2–T5 (#389): its heading, and one item per
#: candidate-year shown. Not written into a download, which carries the column.
PARTY_NOTES_HEADING = "Party notes"
PARTY_NOTE_ITEM = "{candidate}, {year}: {note}"

#: What ``has_popular_vote: false`` means: this dataset holds no popular vote for that
#: year, not that none was held. Never "No".
NOT_IN_DATASET = "Not in this dataset"

#: A value this module has no wording for (#355): an unknown closed-vocabulary code, a
#: value of the wrong type, a non-finite number, one too large to show as a share,
#: margin or ratio, or a winner's or Party notes name made only of format or control
#: characters that are not whitespace, with or without whitespace beside them, which
#: carries nothing to read (#532; a value of only whitespace, such as U+001F, is blank
#: instead). Never the raw value, and
#: never :data:`NOT_IN_DATASET`, which means the dataset holds nothing here. A download
#: writes the value as served.
UNRECOGNIZED = "Unrecognized value"

#: A cell this page could not read just now (#563, D116(e); #618): every cell of a
#: column whose source could not be read or checked in this render. A table note names
#: the column wherever the column is in the download; T1's page-only Recipients column
#: in its tier 2 has none (D116(e)). Not a value, and never :data:`NOT_IN_DATASET`:
#: the dataset may hold one. Moved from ``pages/elections.py``
#: (``T1_N1_UNAVAILABLE_CELL``) unchanged, so T1 and the state history's table share
#: one wording (ba spec, #618's plan gate).
UNAVAILABLE_CELL = "Not available right now"

#: The help text every :data:`UNRECOGNIZED` cell carries (#355). Wording approved by the
#: owner at #354's plan gate, 2026-10-15. One sentence, true on the panel too, which has
#: no download.
UNRECOGNIZED_NOTE = "This dataset holds a value that this page has no label for."

#: The accessible name of the theme toggle's group on every page (#359, #447; ba spec,
#: approved by the owner at #359's plan gate, 2026-11-05). Read by assistive
#: technology, not shown. Not a ``LABELS`` key.
THEME_CONTROL = "Theme"

#: The internal value of the Auto theme choice (#447, formerly System, #359): the
#: starting choice, which follows the device's light or dark setting. Never stored,
#: never shown and never set as ``data-theme``: Auto is the absence of both. It names
#: the Auto button's id (``components.THEME_BUTTON_IDS``).
THEME_AUTO = "auto"

#: Each theme choice, in display order (Dark, Auto, Light: owner decision, #447): the
#: internal value, never shown (for Dark and Light, the stored choice and
#: ``data-theme``; Auto is neither stored nor set), and the button's accessible name,
#: hidden text inside it (ba spec, approved at #447's plan gate, 2026-11-05).
THEME_CHOICES: dict[str, str] = {
    "dark": "Dark",
    THEME_AUTO: "Auto",
    "light": "Light",
}

#: Each theme button's tooltip, its ``title`` (#447; ba spec, approved at #447's plan
#: gate, 2026-11-05): the name for Dark and Light, whose icons are clear; for Auto,
#: what it does, since a sun-moon icon can read as switching by the time of day.
THEME_TITLES: dict[str, str] = {
    "dark": "Dark",
    THEME_AUTO: "Auto: follows your device's light or dark setting",
    "light": "Light",
}


#: The accessible name of the site navigation, the ``nav`` landmark at the top of every
#: page (#448; ba spec, approved at #448's plan gate, 2026-11-06). Read by assistive
#: technology, not shown: a screen reader adds "navigation", so it is heard as "Site
#: navigation", apart from the one-election view's earlier and later links. Not a
#: ``LABELS`` key.
SITE_NAV_LABEL = "Site"

#: The site name's short form, shown at every width, alone below 45rem (#448;
#: ba spec, approved at #448's plan gate, 2026-11-06; the owner may switch it to "Home"
#: once seen on the built page). The first word of ``config.SITE_TITLE``. Not a
#: ``LABELS`` key.
SITE_NAME_SHORT = "Explore"

#: The rest of the site name, after :data:`SITE_NAME_SHORT` (#448; ba spec, approved
#: at #448's plan gate, 2026-11-06): shown at wide widths and visually hidden at
#: narrow ones, so the link's accessible name is the full name, ``config.SITE_TITLE``'s
#: text, at every width and starts with what is shown (WCAG 2.5.3). Not a ``LABELS``
#: key.
SITE_NAME_REST = " — US Presidential Election Center"

#: The home page's heading (#277; a constant since #448, whose
#: ``test_the_full_name_is_the_site_title`` pins it as
#: the end of ``config.SITE_TITLE``): the full site name without "Explore —". The site
#: navigation sits above it, in the header. Not a ``LABELS`` key.
HOME_HEADING = "US Presidential Election Center"

#: The site navigation's three links, in order (#448; labels fixed by the owner in the
#: issue, confirmed by ba, approved at #448's plan gate, 2026-11-06). Not ``LABELS``
#: keys.
NAV_ELECTIONS = "Elections"
NAV_STATES = "States"
NAV_API_DOCS = "API docs"

#: The API docs link's tooltip, its ``title`` (#448; ba spec, approved at #448's plan
#: gate, 2026-11-06). It says "Opens", never "new tab": the link opens in the same tab.
#: Not a ``LABELS`` key.
NAV_API_DOCS_TITLE = (
    "How to read this dataset from your own software. Opens the API's documentation."
)

#: The election pages' shared wording (#465): each election has an overview and two
#: subpages (``explore.election_view``), and these strings are the same on all three,
#: so they live here rather than in one page module. None is a ``LABELS`` key.
#:
#: The not-found state's heading and sentence (#325), shared by the three pages since
#: #465 (ba spec, approved at #465's plan gate, 2026-11-10; the sentence reworded at
#: its code review, 2026-11-10): what is not found is the link, a year the dataset does
#: not serve or a section the site does not have, which reaches the overview
#: (``/election/1824/x``), so all three pages say the same. The heading also leads the
#: page's title on a not-found link (``api.NotFound.title``, D083). "Not found" is about
#: the link: a real election outside the dataset (1820) is not found too. The raw path
#: value is never echoed. The link under them leads back to the elections index.
ELECTION_NOT_FOUND_HEADING = "Election not found"
ELECTION_NOT_FOUND_SENTENCE = (
    "This link does not match any page for an election in this dataset."
)
ELECTION_NOT_FOUND_LINK = "Browse every election in the dataset"

#: The links to the nearest earlier and later year the index serves (#324), on every
#: election page since #465, and the accessible names of the landmark holding them:
#: :data:`ELECTION_NAV_LABEL` on the overview, and on a subpage
#: :data:`ELECTION_NAV_SECTION_LABEL` (filled with the subpage's section link text),
#: which says the links stay on the same table (ba spec, approved at #465's plan
#: gate, 2026-11-10). "Earlier" and "later" are about the years this dataset serves,
#: never a claim that no election fell between.
EARLIER_LINK = "Earlier: the {year} election"
LATER_LINK = "Later: the {year} election"
ELECTION_NAV_LABEL = "Earlier and later elections in this dataset"
ELECTION_NAV_SECTION_LABEL = "{section} for earlier and later elections in this dataset"

#: The links between an election's three pages (#465; ba spec, approved at #465's plan
#: gate, 2026-11-10), in page order, and their landmark's accessible name, read by
#: assistive technology and not shown. A screen reader adds "navigation", so the name
#: does not say it; it differs from :data:`SITE_NAV_LABEL` and the earlier and later
#: links' names. "Overview", never "Summary": the API serves T3's data as ``summary``.
ELECTION_SECTIONS_LABEL = "Pages for this election"
SECTION_OVERVIEW = "Overview"
SECTION_STATES = "Results by state"
SECTION_PER_CAPITA = "People per electoral vote"

#: The links between a state's three pages (#559, #619; ba specs, approved at their
#: plan gates, 2026-11-18 and 2026-11-23), in page order, and their landmark's
#: accessible name, on the election pages' pattern: the state history, its results by
#: election, then its people per electoral vote, whose link text is
#: :data:`SECTION_PER_CAPITA`, the same measure as on an election's pages. "State
#: history" is already the history page's heading on the degraded state and its title
#: before a code is checked (``title()`` in ``pages/state.py``). "Results by election"
#: is the state's form of an election's :data:`SECTION_STATES`, whose table has the
#: same columns with the year in place of the state; never "electoral votes" alone,
#: which on a state's pages also means its electors appointed (C7).
STATE_SECTIONS_LABEL = "Pages for this state"
SECTION_STATE_HISTORY = "State history"
SECTION_RESULTS_BY_ELECTION = "Results by election"

#: The links between the three elections pages (#562; ba spec, approved at #562's plan
#: gate, 2026-11-19), in page order, and their landmark's accessible name, on the
#: election and state pages' pattern: "all" where theirs say "this". "List of
#: elections", never "Overview", which names an election's first page.
ELECTIONS_SECTIONS_LABEL = "Pages for all elections"
SECTION_ELECTIONS_LIST = "List of elections"
SECTION_MAJORITY = "Electoral College majority"
SECTION_OVER_TIME = "Electors appointed and total popular vote"

#: The not-found state's heading, sentence and link, shared by a state's three pages
#: (#325; moved here and the sentence reworded by #559, ba spec, approved at its plan
#: gate, 2026-11-18; #619): what is not found is the link, a code the dataset does not
#: serve or a section the site does not have, which reaches the history page
#: (``/state/GA/x``), so every page says the same. "Not found" is about the link:
#: ``/state/ga`` is refused though Georgia is served. The heading also leads the page's
#: title on a not-found link (``api.NotFound.title``, D083). The raw path value is
#: never echoed. The link leads back to the state picker.
STATE_NOT_FOUND_HEADING = "State not found"
STATE_NOT_FOUND_SENTENCE = (
    "This link does not match any page for a state in this dataset."
)
STATE_NOT_FOUND_LINK = "Browse every state in the dataset"

#: The link that ends every chart's caption (#432; ba spec, approved at #432's plan
#: gate, 2026-11-06), to the chart's companion table on the same page.
#: ``components.chart`` writes the closing period as plain text after the link. It
#: never says "the same" or "all" (a filter can narrow the table and not the chart),
#: nor "above", "below" or "hover" (it must read right when the chart could not load).
#: Not a ``LABELS`` key.
CHART_TABLE_POINTER = "See this chart's numbers in a table on this page"
#: The summary that opens a chart's collapsed caption (#593, D109; ba spec, approved
#: by the owner at #593's plan gate, 2026-11-19): one label for every chart, true of
#: every caption, naming no position or shape. Not a ``LABELS`` key.
CHART_CAPTION_SUMMARY = "About this chart"

#: Chart C1 (#433; ba spec, approved by the owner at #433's plan gate, 2026-11-09):
#: each candidate's electoral share beside their popular-vote share on the one-election
#: view, with the majority line. Not ``LABELS`` keys. The series names are
#: ``LABELS["ec_share_full"]`` and ``LABELS["pv_share"]``, and each bar's text is T3's
#: cell for the same value, so the chart writes every number as T3 does.
C1_TITLE = "Each candidate's electoral share and popular-vote share in {year}"
#: The title in a year this dataset has no popular-vote figures for.
C1_TITLE_NO_PV = "Each candidate's electoral share in {year}"
#: The share axis's title. The candidate axis has none: the names are its ticks.
C1_X_AXIS = "Share"
#: The name of the marker series, kept off the legend and never shown.
C1_NO_FIGURE_SERIES = "No bar for this value"
#: The dashed line's label (``<br>`` is the one line break a chart string may carry).
C1_MAJORITY_LINE = "Majority line: half of<br>electors appointed"
#: The label of the marker drawn in place of a popular-vote bar the dataset has no
#: figure for, inside the popular-vote window. Never a zero-length bar.
C1_NO_FIGURE = "No figure in this dataset"
#: The label of the marker drawn in place of an electoral-share bar the dataset has no
#: value for (a null or blank; T3's cell reads ``NOT_IN_DATASET``). Never a zero-length
#: bar. It names the series, since the chart has no column header to say which share
#: is missing. Not from the plan-gate spec above: ba's addendum at #466's round-1 fix,
#: owner approval with #466.
C1_NO_SHARE = "No electoral share in this dataset"
#: Hover text, filled with T3's cell strings (never a number format in a template).
C1_EC_HOVER = (
    "{candidate}<br>Electoral share (counted ÷ appointed): {share}<br>"
    "Electoral votes counted: {counted}<br>Electors appointed: {appointed}"
)
C1_PV_HOVER = "{candidate}<br>Popular-vote share: {share}<br>Popular votes: {votes}"
#: A marker's hover: T3's cell for the value (``NO_NATIONAL_FIGURE``; for a null or
#: blank electoral share, ``LABELS["ec_share_full"]`` and ``NOT_IN_DATASET`` joined by
#: ``": "``, as T3 shows that cell under its header (ba's addendum at #466's round-1
#: fix, owner approval with #466); or ``UNRECOGNIZED`` followed by ``<br>`` and
#: ``UNRECOGNIZED_NOTE``).
C1_NO_FIGURE_HOVER = "{candidate}<br>{cell}"
#: The caption's sentences, joined in the order ``pages/election.py`` gives.
C1_BASES = (
    "Electoral share is electoral votes counted out of all electors appointed; "
    "popular-vote share is popular votes out of all votes cast for president "
    "nationally."
)
C1_EC_BASIS = (
    "Electoral share is electoral votes counted out of all electors appointed."
)
C1_MAJORITY_NOTE = (
    "The dashed line marks half of the electors appointed: a candidate whose electoral "
    "share is more than half has a majority of them."
)
C1_LINE_EC_ONLY = "The line applies to the electoral share only."
C1_ROW_ORDER = (
    "In each row, the upper bar is the electoral share and the lower bar the "
    "popular-vote share."
)
#: Shown only when a :data:`C1_NO_FIGURE` marker is drawn.
C1_NO_FIGURE_NOTE = (
    'A marker labeled "{label}" means this dataset has no popular-vote figure for '
    "that candidate. It is not a zero."
)
C1_NO_PV_CAPTION = (
    "No popular-vote share is drawn: this dataset's popular-vote figures cover "
    "{first}–{last}, not {year}."
)

#: Chart C2 (#434; ba spec, approved by the owner at #434's plan gate, 2026-11-11, with
#: its historical claims; extended by #564, ba spec v3, approved at #564's plan gate,
#: 2026-11-19, D108): each election's Electoral College leader's electoral share,
#: popular-vote share and hybrid score, against the majority line, beside its companion
#: table. Not ``LABELS`` keys. The circle series is named ``LABELS["ec_share_full"]``,
#: the triangle series ``LABELS["pv_share"]``, both in the chart's key; no mark carries
#: text, and each hover writes the companion table's cells (#558, D104). Its marker
#: series are named :data:`C2_NO_FIGURE` and :data:`UNRECOGNIZED`, each in the key.
C2_TITLE = (
    "The Electoral College leader's electoral share, popular-vote share and hybrid "
    "score in each election"
)
#: The value axis's title, up the side: the shares and the score share one axis.
C2_VALUE_AXIS = "Leader's shares<br>and hybrid score"
#: The dashed line's entry in C2's key, last, on every view (#596, D110: the owner's
#: choice at #596's plan gate, replacing the label below the line, which a filter set
#: among the marks): "each election's", since the number of electors appointed changes
#: with the year (never a fixed number such as 270); on two lines so the entry fits
#: 360 px.
C2_MAJORITY_KEY = "Majority line: half of each<br>election's electors appointed"
#: C2's title and value axis when no year shown has popular-vote figures (#596, D110;
#: ba spec for #596, option B, the owner's choice): only the electoral share is drawn,
#: as :data:`C1_TITLE_NO_PV` for one election.
C2_TITLE_NO_PV = "The Electoral College leader's electoral share in each election"
C2_VALUE_AXIS_NO_PV = "Leader's electoral share"
#: The circle's hover, filled with strings the page writes: the year as written, the
#: name as served, the companion table's cells, and the majority line every year.
C2_HOVER = (
    "{year}: {candidate}<br>Electoral share (counted ÷ appointed): {share}<br>"
    "Electoral votes counted: {counted}<br>Electors appointed: {appointed}<br>"
    "{majority}"
)
#: The hybrid series' name in the chart's key: the project's proposal (#564, D108).
C2_HYBRID_KEY = "Hybrid score (the project's proposal)"
#: The strip series' names in the key: a mark above a year in which a different
#: candidate came first under that method, from the served flag (#564, D108).
C2_PV_DIFFERENT_KEY = "Popular-vote winner: a different candidate"
C2_HYBRID_DIFFERENT_KEY = "Hybrid winner: a different candidate"
#: The marker series for a share or score this dataset has no figure for (#564's option
#: A): one open-circle series for any of the three marks; its hover says which.
C2_NO_FIGURE = "No share or score in this dataset"
#: The triangle's and the crossbar's hovers, and the strip marks' (#564): table cells
#: only.
C2_PV_HOVER = "{year}: {candidate}<br>Popular-vote share: {share}"
C2_HYBRID_HOVER = (
    "{year}: {candidate}<br>Hybrid score: {score}<br>"
    "The project's proposal, not an official measure"
)
C2_PV_DIFFERENT_HOVER = (
    "{year}: a different candidate won the popular vote<br>"
    "Popular-vote winner: {winner}"
)
C2_HYBRID_DIFFERENT_HOVER = (
    "{year}: a different candidate had the highest hybrid score<br>"
    "Hybrid winner: {winner}<br>The project's proposal, not an official measure"
)
#: The caption's sentences, in the order ``pages/elections_majority.py`` gives, with
#: :data:`C1_EC_BASIS` after :data:`C2_EC_MARK` and :data:`C1_LINE_EC_ONLY` after
#: :data:`C2_MAJORITY_NOTE`. The shape words are pinned to the traces' symbols.
C2_LEADER_POINT = (
    "Each year's marks are for that election's Electoral College leader: the candidate "
    "with the most electoral votes counted."
)
C2_EC_MARK = "The circle is the leader's electoral share."
C2_PV_MARK = (
    "The solid triangle is the leader's popular-vote share, their share of all votes "
    "cast for president nationally, and a thin line joins it to the circle."
)
#: "Crossbar", not "dash": the caption already says "the dashed line" for the
#: majority line (#593's ba spec).
C2_HYBRID_MARK = (
    "A short crossbar on the thin line is the leader's hybrid score: the average of "
    "their electoral share and popular-vote share, so it sits halfway between the "
    "circle and the triangle. The hybrid score is the project's own proposal, not an "
    "official measure."
)
C2_MAJORITY_NOTE = (
    "The dashed line marks half of each election's electors appointed: a leader whose "
    "electoral share is more than half had a majority of them. With half or less, no "
    "candidate had a majority, and the election went to the House of Representatives."
)
#: Its example is pinned to the served 1992 leader's ``pv_share`` (#564's plan gate).
C2_PLURALITY_NOTE = (
    "A popular-vote share under 50% is not unusual: a candidate can win the popular "
    "vote with less than half of all votes, as William J. Clinton did in 1992 with "
    "43.0%."
)
C2_TOOK_OFFICE = (
    "The leader did not always take office: in 1824 the leader, Andrew Jackson, had "
    "no majority, and the House of Representatives chose John Quincy Adams."
)
#: Only when the band before the popular-vote window is drawn; its bound from coverage.
C2_BEFORE_NOTE = (
    "The shaded years come before {pv_year_min}, when this dataset's popular-vote "
    "figures begin, so only the circle is drawn for them. Shading means this dataset "
    "has no popular-vote share or hybrid score for those years, not that no popular "
    "vote was held."
)
#: Only when that strip series is drawn.
C2_PV_DIFFERENT_NOTE = (
    "An asterisk along the top of the chart marks a year in which a different "
    "candidate won the popular vote; the table names them."
)
C2_HYBRID_DIFFERENT_NOTE = (
    "A pentagon along the top of the chart marks a year in which a different "
    "candidate had the highest hybrid score; the table names them."
)
#: The caption's last sentence, only when a marker is drawn (#558, D104; #564): the
#: marker sits at zero, and without a text label it would read as 0%.
C2_NO_SHARE_NOTE = (
    "A marker at the bottom of the chart in place of a circle, triangle or crossbar "
    "means this dataset has no figure to draw there for that election: its hover says "
    "which, and the chart's key says why. It is not a zero."
)
#: The companion table's notes, under the table and in its CSV's preamble, which has no
#: caption: with :data:`C2_TOOK_OFFICE` and :data:`HYBRID_NOTE` (#564).
C2_LEADER_ROW = (
    "Each row is that election's Electoral College leader: the candidate with the "
    "most electoral votes counted."
)
C2_TABLE_METHODS_NOTE = (
    "The popular-vote share and hybrid score are the leader's own. The popular-vote "
    "winner and hybrid winner columns name who came first under that method, who may "
    "be a different candidate."
)
C2_HYBRID_TABLE_NOTE = (
    "The hybrid score is the project's own proposal, not an official measure."
)

#: Chart C3 (#435; ba spec, revised after the architect's review and approved by the
#: owner at #435's plan gate, 2026-11-10): every state's people per electoral vote on
#: an election's People per electoral vote page, beside T6. Not ``LABELS`` keys. Each
#: bar's text and every hover value is T6's cell, so the chart writes every number as
#: T6 does. The bar series are named by :data:`BOUNDARY_BASIS`, or
#: :data:`C3_PLAIN_SERIES` (below).
C3_TITLE = (
    "People per electoral vote in each state in {year} (census used: {census_year})"
)
#: The title when the rows' census-year cells are not all one year (or one is
#: unrecognized).
C3_TITLE_NO_CENSUS = "People per electoral vote in each state in {year}"
#: The value axis's title (its tick labels are hidden: every bar carries its number).
C3_X_AXIS = LABELS["persons_per_electoral_vote"]
#: The plain bar series' name when any plain row's border cell is not "Borders at the
#: election" (a defensive case: a served body never carries one).
C3_PLAIN_SERIES = "Bars without stripes"
#: The selected state's series (the page's filter): one diamond, filled with the page
#: color and ringed in the text color, at the start of its row. "Selected", not "you
#: chose": a shared link carries the filter.
C3_SELECTED = "Selected state"
#: The marker series' name, kept off the legend and never shown: the figure rules need
#: every trace named.
C3_NO_FIGURE_SERIES = "No bar for this state"
#: The short labels drawn beside a marker, short enough for 390 px. T6's full cell is in
#: the marker's hover (:data:`C3_NO_FIGURE_HOVER`).
C3_NO_CENSUS_FIGURE = "No census figure"
C3_NO_ELECTORAL_VOTES = "No electoral votes"
#: A marker's drawn label, looked up by T6's cell; any cell not here draws
#: :data:`UNRECOGNIZED`.
C3_MARKER_LABELS: dict[str, str] = {
    PER_CAPITA_COVERAGE[NO_GOVERNING_FIGURE]: C3_NO_CENSUS_FIGURE,
    NO_ELECTORAL_VOTES: C3_NO_ELECTORAL_VOTES,
    NOT_IN_DATASET: NOT_IN_DATASET,
    UNRECOGNIZED: UNRECOGNIZED,
}
#: A bar's hover, filled with T6's cell strings.
C3_BAR_HOVER = (
    "{state}<br>People per electoral vote: {ratio}<br>Population: {population}<br>"
    "Electors appointed: {electoral_votes}<br>Census used: {census_year}<br>"
    "Borders used: {boundary}"
)
#: A marker's hover: T6's ratio cell in full (for ``UNRECOGNIZED``, followed by
#: ``<br>`` and :data:`UNRECOGNIZED_NOTE`).
C3_NO_FIGURE_HOVER = "{state}<br>People per electoral vote: {cell}"
#: The caption's sentences, in the order ``pages/election_per_capita.py`` gives.
C3_RATIO = (
    "Each bar is a state's population divided by its electors appointed: how many "
    "people each of its electoral votes stood for. States run from the most people per "
    "electoral vote at the top to the fewest."
)
#: With :data:`C3_TITLE`. It follows the glossary's *Census used* and does not say the
#: census set the state's electoral votes (#423).
C3_CENSUS = (
    "Population is from the census used for the latest redistribution of House seats "
    "made before this election, which is not always the nearest census."
)
#: With :data:`C3_TITLE_NO_CENSUS`.
C3_CENSUS_MIXED = (
    "Population is from each state's census used, which is not always the nearest "
    "census."
)
#: Shown whenever a striped bar is drawn, followed by :data:`BOUNDARY_NOTE`.
C3_STRIPES = "Striped bars use present-day borders."
#: Shown when no striped bar is drawn and every plain bar is at the election.
C3_ALL_AT_ELECTION = "Every bar uses the state's borders at the election."
#: Shown when the plain series is named :data:`C3_PLAIN_SERIES`.
C3_PLAIN_MIXED = (
    "For some bars without stripes, this page cannot say which borders the population "
    "describes."
)
#: Shown only when a marker is drawn.
C3_NO_FIGURE_NOTE = (
    "A labeled marker in place of a bar means there is no figure to draw for that "
    "state, and its label says why. It is not a zero. These states come last, in "
    "alphabetical order."
)
#: Shown only when the page's filter selects a state.
C3_SELECTED_NOTE = (
    "{state}, the selected state, is marked at the start of its row. The chart shows "
    "every state; only the table is narrowed to {state}."
)


#: What ``has_popular_vote``'s ``false`` means (#309): shown under T1, whose cells read
#: :data:`NOT_IN_DATASET`, and written into its downloaded file, where the cell is the
#: raw ``false``. It says nothing about whether a popular vote was held.
HAS_POPULAR_VOTE_NOTE = (
    'A false in the popular-vote column, shown as "Not in this dataset", means this '
    "dataset holds no popular-vote figure for that year. It does not say whether a "
    "popular vote was held."
)

#: A popular-vote or hybrid cell with no figure because the year lies outside the
#: popular-vote window (#308): the panel's null there, and T3's popular-vote columns
#: and hybrid score (``national_pv_votes``, ``pv_share``, ``hybrid_score``) in a year
#: with no popular vote. One wording for that cause in the panel and T3 (#352). A null
#: party has nothing to do with the window: in any year it reads :data:`NOT_IN_DATASET`
#: with :data:`PARTY_NULL_NOTE` (#389). T2 and T4 name the window's side
#: (:data:`BEFORE_WINDOW`, :data:`AFTER_WINDOW`).
NOT_APPLICABLE = "Not in this dataset: no popular-vote figures for this year"

#: A flip that happened; ``method`` is ``popular-vote`` or ``hybrid``, and ``role`` is
#: ``winner`` with an Electoral College majority, else ``leader`` (#355).
FLIP_YES = "Yes: the {method} winner is not the Electoral College {role}"

#: The panel's ``ec_winner`` label when ``ec_determinative`` is true, and when it is
#: false (#355); a null or unknown one reads ``LABELS["ec_winner"]``.
EC_WINNER = "Electoral College winner"
EC_LEADER_NO_MAJORITY = "Electoral College leader (no majority)"

#: Each ``ec_determinative`` value: a real outcome either way, never a missing value.
EC_MAJORITY = "A candidate won a majority of electors appointed"
NO_EC_MAJORITY = "No candidate reached a majority of electors appointed"

#: The hybrid's one line of help text: what it computes, and nothing about its merits.
HYBRID_NOTE = (
    "The hybrid score is the average of a candidate's electoral share and popular-vote "
    "share; the candidate with the highest score wins it."
)

#: What the panel's three margins measure (#352). Wording approved by the owner in
#: place on the #352 branch deploy, 2026-10-12.
MARGIN_NOTE = (
    "A margin is the gap, in percentage points, between the first- and second-place "
    "candidates under that method. Each method ranks the candidates on its own."
)

#: The metrics on ``/elections`` (#437, D097), keyed by metric key, never by a public
#: field name: ``LABELS`` stays keyed by field. The keys are ``explore.metrics``'
#: ``METRICS`` (ba spec, approved by the owner at #437's plan gate, 2026-11-11). The
#: count's label is the line above T1, formatted with the elections shown and served.
METRIC_LABELS: dict[str, str] = {
    "elections_shown": "Showing {shown} of {total} elections",
    "ec_margin_mean": "Average electoral margin",
    "pv_margin_mean": "Average popular-vote margin",
    # The counts on /elections/majority (#569, D112; ba spec, approved by the owner at
    # #569's plan gate, 2026-11-21).
    "ec_no_majority_count": (
        "Elections in which the Electoral College leader had no majority"
    ),
    "pv_flip_count": "Elections in which a different candidate won the popular vote",
    # The figures on /elections/over-time and a state's per-capita page (#600, D112(d);
    # ba spec, approved by the owner at #600's plan gate, 2026-11-22).
    "ec_appointed_first": "Electors appointed, earliest election",
    "ec_appointed_latest": "Electors appointed, latest election",
    "pv_total_first": "Total popular vote, earliest election with a total",
    "pv_total_latest": "Total popular vote, latest election with a total",
    "state_per_capita_lowest": "People per electoral vote, lowest",
    "state_per_capita_highest": "People per electoral vote, highest",
    # The figures on /state/<usps> and /candidate/<slug> (#601, D112(e), (f), D115; ba
    # spec, approved by the owner at #601's plan gate, 2026-11-22). "Appointed
    # electors", never "took part"; "the candidate who took office", never "the eventual
    # winner" (1824); the candidate count and totals say "cast" and "in all states".
    "state_elections_count": "Elections in which this state appointed electors",
    "state_took_office_count": (
        "Elections in which this state's electors cast at least one electoral vote "
        "for the candidate who took office"
    ),
    "candidate_elections_count": (
        "Elections in which electors cast at least one electoral vote for this "
        "candidate"
    ),
    "candidate_ev_cast_total": (
        "Total electoral votes cast for this candidate in all states"
    ),
    "candidate_ev_counted_total": (
        "Total electoral votes Congress counted for this candidate in all states"
    ),
}
#: An average or a total over two or more elections; ``{value}`` is :func:`margin`'s
#: cell for an average (:func:`metric_mean`) and :func:`number`'s for a total
#: (:func:`metric_total`, #601), the years the earliest and latest that entered it.
METRIC_OVER = "{value}, over {n} elections ({first}–{last})"
#: An average or a total over one election: the one year, never "2000–2000".
METRIC_OVER_ONE = "{value}, over 1 election ({year})"
#: No average, because no election matches the filters (T1 then shows its own empty
#: text, `empty=` in `pages/elections.py`, below the metrics).
METRIC_NO_AVERAGE_FILTERS = "No average: no elections match these filters"
#: No popular-vote average, because no year shown lies inside the popular-vote window;
#: the years come from ``coverage``, never a literal.
METRIC_NO_AVERAGE_PV_YEARS = (
    "No average: this dataset's popular-vote figures cover {first}–{last}, "
    "not the years shown"
)
#: No average, because every margin among the elections shown is null (no served year
#: reaches it; it keeps a null's dataset-first, no-cause reading).
METRIC_NO_AVERAGE_NULL = (
    "No average: this dataset has no margin for the elections shown"
)
#: After :data:`MARGIN_NOTE`, only when both averages are numbers, their N or years
#: differ, and a year in the electoral average lies outside the popular-vote window, so
#: the window is a cause of the difference (owner, #437's code review): two year sets
#: are never read as one comparison, and the note never names a reason that is not one.
METRIC_DIFFERENT_ELECTIONS = (
    "The two averages do not cover the same elections: this dataset's popular-vote "
    "figures cover {first}–{last}."
)
#: A count of elections over two or more elections (#569, D112; ba spec, approved at
#: #569's plan gate): two counts, never a percentage; the years are the earliest and
#: latest whose flag entered N, never the filter's bounds (:func:`metric_count`).
METRIC_COUNT_OF = "{count} of {n} elections ({first}–{last})"
#: A count of elections over one election: the one year, never "2000–2000".
METRIC_COUNT_OF_ONE = "{count} of 1 election ({year})"
#: Under the counts on ``/elections/majority``, whenever the popular-vote count shows a
#: number; the years come from ``coverage``, never a literal. True by construction: C2's
#: check makes a flip a value exactly when its year has a popular-vote winner, and the
#: note never says the counted years lie inside the window (#602's review, cr.3; ba).
METRIC_PV_WINDOW_NOTE = (
    "This dataset's popular-vote figures cover {first}–{last}. The number of "
    "elections in which a different candidate won the popular vote includes only "
    "elections with a popular-vote winner in this dataset."
)
#: No popular-vote figure (a count, or an earliest or latest total, #600), because no
#: year shown lies inside the popular-vote window.
METRIC_NO_FIGURE_PV_YEARS = (
    "No figure: this dataset's popular-vote figures cover {first}–{last}, "
    "not the years shown"
)
#: Each count's and select's wording when every value among the elections shown is
#: null, by metric key (#569, #600, D114); a mean words its own in
#: :func:`metric_mean`. The two counts' texts are #569's, unchanged.
METRIC_NO_FIGURE: dict[str, str] = {
    # No served year reaches it.
    "ec_no_majority_count": (
        "No figure: this dataset does not say whether any candidate had a majority in "
        "the elections shown"
    ),
    # No served year in the window reaches it.
    "pv_flip_count": (
        "No figure: this dataset has no popular-vote winner for the elections shown"
    ),
    # Never "has no electors appointed", which would read as zero electors (1864).
    "ec_appointed_first": (
        "No figure: this dataset has no number of electors appointed for the elections "
        "shown"
    ),
    "ec_appointed_latest": (
        "No figure: this dataset has no number of electors appointed for the elections "
        "shown"
    ),
    "pv_total_first": (
        "No figure: this dataset has no total popular vote for the elections shown"
    ),
    "pv_total_latest": (
        "No figure: this dataset has no total popular vote for the elections shown"
    ),
    # Names no cause: each T7 cell gives its own.
    "state_per_capita_lowest": (
        "No figure: none of the elections shown has a people-per-electoral-vote figure"
    ),
    "state_per_capita_highest": (
        "No figure: none of the elections shown has a people-per-electoral-vote figure"
    ),
    # A state's history (#601): the state appointed electors in some election, but the
    # took-office row's electoral votes are null in every one. Names no cause.
    "state_took_office_count": (
        "No figure: this dataset has no number of electoral votes this state's "
        "electors cast for the candidate who took office, in any election in which "
        "this state appointed electors"
    ),
    # A candidate's totals (#601): a sum with any null reads no figure (D097), so "one
    # or more" is true whether one year or every year is null.
    "candidate_ev_cast_total": (
        "No figure: this dataset has no number of electoral votes cast for this "
        "candidate in one or more of the elections shown"
    ),
    "candidate_ev_counted_total": (
        "No figure: this dataset has no number of electoral votes counted for this "
        "candidate in one or more of the elections shown"
    ),
}
#: A select with no figure because the years shown hold no election for the state (a
#: state's per-capita page, whose year range spans the dataset; #600). On the elections
#: pages no year shown shows *No elections match* and no figure instead.
METRIC_NO_FIGURE_NO_ELECTIONS = (
    "No figure: this dataset has no elections for this state in the years shown"
)
#: A count of elections with its years (#601; ba spec, approved at #601's plan gate):
#: a state's elections with electors appointed, a candidate's with electoral votes
#: cast for them (:func:`metric_elections`).
METRIC_COUNT_ELECTIONS = "{n} elections ({first}–{last})"
#: A count of one election: the one year, never "1828–1828".
METRIC_COUNT_ELECTIONS_ONE = "1 election ({year})"
#: Both state history figures when no year's allotment is above 0 (#601). It never
#: says "elections shown", since the history page reads no filter (D112(g), D118), and
#: never "0", which would read as a measurement.
METRIC_NO_FIGURE_NO_ELECTORS = (
    "No figure: this dataset has no election in which this state appointed electors"
)
#: A candidate's election count at 0 (#601): unreachable on a successful render, kept
#: so the count never reads "0 elections".
METRIC_NO_FIGURE_NO_CANDIDATE_ELECTIONS = (
    "No figure: this dataset has no election in which electors cast an electoral "
    "vote for this candidate"
)
#: Under the state history figures while the election count shows a number and some
#: year's allotment is exactly 0 (#601; owner, #601's plan gate): ``{years}`` is
#: :func:`metric_years` over those years, so GA's 50 beside C7's 51 years is explained.
METRIC_ZERO_ALLOTMENT_NOTE = (
    "These figures leave out {years}, when this state appointed no electors."
)
#: Under the candidate figures only while the State filter is applied (#601): the
#: figures are national (D112(g)); "State" is the filter's own label.
METRIC_ALL_STATES_NOTE = (
    "These figures cover every state. The State filter narrows only the rows below."
)
#: Under the state history figures while the Years filter applies a narrower range than
#: the state's span, the empty view included (#620, D119; ba spec, approved at #620's
#: plan gate): the figures read the whole history (D112(g), D115(g)).
METRIC_ALL_YEARS_NOTE = (
    "These figures cover this state's whole history in this dataset. The Years filter "
    "does not change them."
)
#: A select over two or more elections (#600, D112(d); ba spec, approved at #600's plan
#: gate): ``{value}`` is the companion table's own cell, ``{years}`` the year or tied
#: years (:func:`metric_years`), ``{first}``–``{last}`` the earliest and latest years
#: with a value, never the filter's bounds.
METRIC_SELECT = "{value} in {years}, among {n} elections with a figure ({first}–{last})"
#: A select over one election, on the first entry of its pair.
METRIC_SELECT_ONE = "{value} in {year}, the only election shown with a figure"
#: A select over one election, on the second entry of its pair: one value, not two
#: (D112(d)), so the entry and its id stay and name the other.
METRIC_SELECT_SAME = (
    "Same as the {other}: {year} is the only election shown with a figure"
)
#: The entry :data:`METRIC_SELECT_SAME` names, by pick.
METRIC_SELECT_OTHER = {"latest": "earliest", "highest": "lowest"}
#: Tied years: two as "{rest} and {last}"; three or more with a comma between each but
#: the last pair, as the owner wrote them (#600's issue body).
METRIC_YEARS_AND = "{rest} and {last}"
#: Under the over-time figures, while a total popular vote figure shows a number; the
#: years come from ``coverage``, never a literal. It never says the N years lie inside
#: the window (#602's review, cr.3, precedent).
METRIC_PV_TOTAL_WINDOW_NOTE = (
    "This dataset's popular-vote figures cover {first}–{last}. The earliest and "
    "latest total popular vote are taken only from elections with a total in this "
    "dataset."
)
#: Follows :data:`METRIC_DIFFERENT_ELECTIONS` while the popular-vote filter is off; it
#: names the elections page's checkbox by its own text.
METRIC_SAME_ELECTIONS = (
    'To compare the two over the same elections, select "Only years with a popular '
    'vote in this dataset".'
)


#: Each nominating-party code's display form (#389, D077; owner approval at #389's plan
#: gate). A closed table: a code outside it reads :data:`UNRECOGNIZED`, and
#: ``TestPartyDisplay.test_every_code_has_a_display_form`` (the one-election view's test
#: module) pins its keys to ``usvote.party.NOMINATING_PARTIES``, so a new code fails
#: until it has a form here. A joint nomination names its components in code order,
#: joined by "and", never a hyphen, which would read as one party's name.
NOMINATING_PARTY: dict[str, str] = {
    "democratic_republican": "Democratic-Republican",
    "national_republican": "National Republican",
    "democratic": "Democratic",
    "anti_masonic": "Anti-Masonic",
    "whig": "Whig",
    "american": "American (Know-Nothing)",
    "republican": "Republican",
    "southern_democratic": "Southern Democratic",
    "constitutional_union": "Constitutional Union",
    "liberal_republican": "Liberal Republican",
    "populist": "Populist",
    "progressive_1912": "Progressive (1912)",
    "progressive_1924": "Progressive (1924)",
    "states_rights_democratic": "States' Rights Democratic",
    "american_independent": "American Independent",
    "libertarian": "Libertarian",
    "liberal_republican_democratic": "Liberal Republican and Democratic",
    "democratic_populist": "Democratic and Populist",
    "american_whig": "American (Know-Nothing) and Whig",
    "no_nomination": NO_NOMINATION,
}


# --- Chart C9 (#563, D116): ba spec, approved at #563's plan gate, 2026-11-22 ---------

#: One recipient of electoral votes in a year, as T1's Recipients cell writes it (one
#: line each, in N1's served order) and C9's hover repeats it.
RECIPIENT_LINE = "{candidate}: {cast} cast, {counted} counted"
C9_TITLE = "Candidates with electoral votes in each election"
C9_VALUE_AXIS = "Candidates with electoral votes"
C9_HOVER = "{year}<br>Candidates with electoral votes: {count}<br>{recipients}"
C9_BASIS = (
    "Each bar is one election: the number of candidates who received at least one "
    "electoral vote cast that year."
)
C9_CAST_NOTE = (
    "A candidate is included even if Congress did not count their votes: in 1872, "
    "Horace Greeley received 3 electoral votes cast and none counted."
)
#: C9's finding over the years shown: two or more shown, at least one above two.
C9_FINDING = (
    "In {more} of the {n} elections shown, more than two candidates received "
    "electoral votes. The most in one election was {most}, in {years}."
)
C9_FINDING_NONE = (
    "In none of the {n} elections shown did more than two candidates receive "
    "electoral votes."
)
C9_FINDING_ONE = "Candidates with electoral votes in {year}: {count}."
C9_HOVER_NOTE = (
    "Hovering over or tapping a bar lists each candidate who received electoral votes "
    "that year, with their electoral votes cast and counted, as the list of elections "
    "on this page does."
)
C9_UNAVAILABLE = (
    "The chart of how many candidates received electoral votes in each election can't "
    "be shown right now. Please try again in a minute."
)

# --- Charts C4 and C5 (#436, D100): ba spec, approved at #436's plan gate -------------

#: C4's title, and the one-state form C7 shares (#560; C4 draws all states only since
#: #562, D107).
C4_TITLE = "Electors appointed in each election, all states"
C4_TITLE_STATE = "Electors appointed by {state} in each election"
C4_VALUE_AXIS = "Electors appointed"
C4_HOVER = "{year}, all states<br>Electors appointed: {appointed}"
C4_STATE_HOVER = (
    "{year}: {state}<br>Electors appointed: {appointed}<br>"
    "Popular vote in this state: {pv_status}"
)
#: C4's marker series, each named in the chart's key (#558, D104): a zero allotment,
#: by its cause; a null allotment is :data:`NOT_IN_DATASET`'s series and an unknown
#: value :data:`UNRECOGNIZED`'s.
C4_NO_ELECTORS_TOOK_NO_PART = "No electors: took no part"
C4_NO_ELECTORS = "No electors appointed"
C4_BASIS = (
    "Electors appointed is a state's allotment of electoral votes: how many electors "
    "it was entitled to choose. It is not the electoral votes cast or counted, which "
    "can be fewer."
)
#: Reworded at #562 (ba spec, approved at its plan gate, 2026-11-19): "With all
#: states," contrasted with the one-state mode that retired.
C4_ALL_STATES = (
    "Each bar is the whole Electoral College that year: every state's electors "
    "appointed, added up."
)
C4_ZERO_NOTE = (
    "A marker in place of a bar marks an election in which the state appointed no "
    "electors, and the chart's key says why. The table shows that allotment as 0."
)
C4_NO_FIGURE_NOTE = (
    "A marker in place of a bar means this dataset has no number of electors to draw "
    "for that election, and the chart's key says why. It is not a zero."
)
#: C7's and C10's start, on the state history (#620, D119; ba spec, approved at #620's
#: plan gate, 2026-11-23): shown only when the years shown start at the state's first
#: election and that is after the dataset's first year. It replaces the four
#: first-election notes (``FIRST_ELECTION_NOTE``, ``C10_FIRST_ELECTION_NOTE`` and their
#: ``_THIS_STATE`` forms), retired since the axis no longer starts before that election.
FIRST_ELECTION_START_NOTE = (
    "This chart starts at {year}, the first election in this dataset in which "
    "{state} appointed electors."
)
FIRST_ELECTION_START_NOTE_THIS_STATE = (
    "This chart starts at {year}, the first election in this dataset in which this "
    "state appointed electors."
)

#: Chart C7 (#560): one state's electors appointed, on its history page. Its title,
#: axis, hover, key and most of its caption are C4's one-state wording. The two below
#: are the forms for a state its page names by address, never by a choice (ba spec,
#: approved at #560's plan gate, 2026-11-18). A third, the note on what the page's
#: filters reached, ``C7_FILTERS_NOTE``, is retired with the filters (#619, D118).
C7_TITLE_THIS_STATE = "Electors appointed by this state in each election"

#: Chart C10 (#582): one state's total popular vote, on its history page, below C7. Its
#: axis, bands, key and most of its caption are C5's; its title and hover are C5's
#: one-state wording from #436 (retired by #562, restored), and the rest is the ba
#: spec approved at #582's plan gate, 2026-11-21. Its first-election sentence is C7's
#: since #620 (:data:`FIRST_ELECTION_START_NOTE`).
C10_TITLE_STATE = "Total popular vote in {state} in each election"
C10_TITLE_THIS_STATE = "Total popular vote in this state in each election"
C10_HOVER = (
    "{year}: {state}<br>Total popular vote: {total}<br>"
    "Popular vote in this state: {pv_status}"
)
C10_SHORT_TICKS_NOTE = (
    "The numbers up the side are written short: 500k is 500,000 and 2M is 2,000,000. "
    "Each bar's hover and the table give the total in full."
)

C5_TITLE = "Total popular vote in each election, all states"
C5_VALUE_AXIS = "Total popular vote"
C5_HOVER = "{year}, all states<br>Total popular vote: {total}"
#: The bands' labels (#558, D104; #593, D109): before the window, inside the band at
#: its top left, short enough for the band at 360 px on two lines (the year is in the
#: caption and the table; ``.format(pv_year_min=…)`` still applies, naming nothing);
#: after it, above the plot at the band's right edge, since that band can be one
#: election wide.
C5_BEFORE_BAND = "Shaded: no popular-vote<br>figures in this dataset"
C5_AFTER_BAND = (
    "Shaded: years after this dataset's<br>popular-vote figures run to {pv_year_max}"
)
#: C5's marker series, each named in the chart's key.
C5_LEGISLATURE = "Legislature chose the electors"
C5_TOOK_NO_PART = "Took no part"
C5_NO_TOTAL = "No total in this dataset"
C5_BASIS = (
    "The total popular vote is all the votes for President, for every candidate, "
    "including candidates who are not in this dataset, as the popular-vote source "
    "reports them."
)
#: Reworded at #562, as :data:`C4_ALL_STATES`.
C5_ALL_STATES = "Each bar is the national total: every state's total, added up."
#: C5's value axis writes its numbers short (#596, D110; C10's too, #582, D113: the two
#: exceptions to the chart rule); said in its caption only when a bar is drawn (ba spec
#: for #596).
C5_SHORT_TICKS_NOTE = (
    "The numbers up the side are written short: 50M is 50,000,000. Each bar's hover "
    "and the table give the total in full."
)
C5_BEFORE_NOTE = (
    "The shaded years come before {pv_year_min}, when this dataset's popular-vote "
    "figures begin. Shading means this dataset has no total for those years, not that "
    "no popular vote was held."
)
C5_AFTER_NOTE = (
    "Shaded years after {pv_year_max} have no popular-vote figures in this dataset yet."
)
C5_MARKER_NOTE = (
    "A marker in place of a bar means there is no total to draw for that election, "
    "and the chart's key says why. It is not a zero."
)
#: C5's marker label, looked up by the table's cell; a cell here with no label (the
#: band's) draws no marker, and any cell in neither draws :data:`UNRECOGNIZED`.
C5_MARKER_LABELS: dict[str, str] = {
    LEGISLATURE_CHOSE: C5_LEGISLATURE,
    TOOK_NO_PART: C5_TOOK_NO_PART,
    NO_NATIONAL_TOTAL: C5_NO_TOTAL,
    UNRECOGNIZED: UNRECOGNIZED,
}
#: C10's marker label, looked up by its table's cell (#582), as C5's is: the band's
#: cells (:data:`BEFORE_WINDOW`, :data:`AFTER_WINDOW`) have none and draw no marker,
#: and a null total with no status to explain it (:data:`NOT_IN_DATASET`) shares the
#: "no total" entry with one inside the window, so the open circle keeps one meaning on
#: the page (D113, amendment); the cell and the hover still say which it is.
C10_MARKER_LABELS: dict[str, str] = {
    LEGISLATURE_CHOSE: C5_LEGISLATURE,
    TOOK_NO_PART: C5_TOOK_NO_PART,
    NO_STATE_TOTAL: C5_NO_TOTAL,
    NOT_IN_DATASET: C5_NO_TOTAL,
    UNRECOGNIZED: UNRECOGNIZED,
}
#: The C4/C5 table's last note: the window, and that a missing total is never a zero.
OVER_TIME_WINDOW_NOTE = (
    "This dataset's popular-vote figures cover {pv_year_min}–{pv_year_max}. A total "
    "this dataset does not have is never shown as a zero; its cell says why."
)


def national_total(value: object, year: int, coverage: dict[str, Any]) -> str:
    """The nation's total popular vote cell (#436): the figure, or why there is none.

    A null (or a blank) outside the popular-vote window reads :data:`NOT_APPLICABLE`,
    inside it :data:`NO_NATIONAL_TOTAL`; it never takes a made-up ``pv_status``. Any
    other value no figure can show reads :data:`UNRECOGNIZED`. The window comes from
    ``coverage``, never a literal.
    """
    if not is_blank(value):
        return number(value)
    return NOT_APPLICABLE if not in_pv_window(year, coverage) else NO_NATIONAL_TOTAL


def _ec_role_is_winner(determinative: object) -> bool:
    """The one test of whether the Electoral College's top candidate is its winner:
    only a true ``ec_determinative`` (a majority of electors appointed); otherwise it
    is its leader."""
    return determinative is True


def ec_winner_label(determinative: object) -> str:
    """The panel's ``ec_winner`` label for the block's ``ec_determinative`` (#355)."""
    if _ec_role_is_winner(determinative):
        return EC_WINNER
    if determinative is False:
        return EC_LEADER_NO_MAJORITY
    return LABELS["ec_winner"]


def is_blank(value: object) -> bool:
    """A null or blank text: no value, so a cell names no cause for it, or the cause
    its row gives (#355). Every other value is a value.

    "Blank" means empty or only whitespace (``str.isspace``, which includes the ten
    control characters tab, line feed, U+000B, U+000C, carriage return, U+001C–U+001F
    and U+0085). Text made only of format or control characters that are not
    whitespace (U+200B, U+0001) is not blank (#532): it is a served value with nothing
    to read, so :func:`has_text` refuses it, and a cell that falls back through
    :func:`_unknown` reads it as :data:`UNRECOGNIZED`, never as the null wording. Kept
    apart on purpose (owner, #532's plan gate)."""
    return value is None or (isinstance(value, str) and not value.strip())


#: The Unicode general categories whose characters carry nothing to read (#532):
#: format (``Cf``: U+200B zero-width space, U+FEFF, the bidirectional marks, the tag
#: characters) and control (``Cc``, such as U+0001; ten of them, tab, the line breaks
#: and U+001C–U+001F among them, are also whitespace). Whitespace is ``str.isspace``,
#: exactly what ``str.strip`` removes.
NOTHING_TO_READ_CATEGORIES = frozenset({"Cc", "Cf"})


def _nothing_to_read(char: str) -> bool:
    """Whether one character carries nothing to read: whitespace, or a character of
    :data:`NOTHING_TO_READ_CATEGORIES`."""
    return char.isspace() or unicodedata.category(char) in NOTHING_TO_READ_CATEGORIES


def has_text(value: object) -> TypeGuard[str]:
    """Text with something in it (#367): the shared predicate wherever a page decides
    whether text is shown, such as a candidate link, a heading, a winner, a note or a
    reason. Never a bare ``not is_blank(value)``, which is true of a value that is not
    text, such as ``5``.

    Text has something in it when one character is neither whitespace nor a format or
    control character (:func:`_nothing_to_read`, #532), so a value of only zero-width
    spaces is no text, and a name carrying one beside its letters still is. A string can
    fail this and still not be blank (:func:`is_blank`): route its fallback through
    :func:`_unknown`, never straight to the null wording. Known residuals, which still
    count as text: Hangul fillers (U+3164 and its kin, category ``Lo``), the blank
    braille pattern U+2800 (``So``) and lone combining marks (``Mn``)."""
    return isinstance(value, str) and any(not _nothing_to_read(ch) for ch in value)


def finite(value: object) -> float | None:
    """A number as a finite float, or ``None`` for anything else: a bool, a value of no
    numeric type, an integer no float can hold, or a non-finite number. Each of those
    that is a value reads :data:`UNRECOGNIZED` (:func:`_unknown`), never a figure.

    Public since C1 (#433): a chart draws a value only where this accepts it and its
    cell is a figure, so the chart and its companion table agree on what is a number."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        number_ = float(value)
    except OverflowError:
        return None
    return number_ if math.isfinite(number_) else None


def _unknown(value: object, null: str = NOT_IN_DATASET) -> str:
    """A value a cell has no wording for: ``null`` for no value, else
    :data:`UNRECOGNIZED`. Never the raw value."""
    return null if is_blank(value) else UNRECOGNIZED


def cell(children: Any, tag: Any = html.Td, title: str | None = None) -> Any:
    """A cell (``tag``, a ``Td`` or a panel ``Dd``) holding ``children``; an
    :data:`UNRECOGNIZED` cell carries :data:`UNRECOGNIZED_NOTE` as its help text, else
    ``title`` where one is given."""
    if children == UNRECOGNIZED or children == [UNRECOGNIZED]:
        title = UNRECOGNIZED_NOTE
    return tag(children) if title is None else tag(children, title=title)


def header(field: str) -> html.Th:
    """A column header: the plain label, with the raw field name as its tooltip."""
    return html.Th(LABELS[field], title=field, scope="col")


def glossary(
    fields: Iterable[str],
    summary: str = "Column names",
    chosen: Mapping[str, str] | None = None,
    ident: str | None = None,
    page_only: Iterable[tuple[str, str]] = (),
) -> html.Details:
    """Each column's plain label beside the API field name it shows. A list that is no
    table (the election panel) names its ``summary`` otherwise, and a label that
    depends on the data (``ec_winner``'s, #355) comes from ``chosen``. ``ident`` is the
    list's DOM id, where a page has several (#436). ``page_only`` lists, after the
    fields, each page-only column (#563, D116) as its header and the served fields it
    is built from."""
    shown = {**LABELS, **(chosen or {})}
    kwargs: dict[str, Any] = {} if ident is None else {"id": ident}
    return html.Details(
        [
            html.Summary(summary),
            html.Dl(
                [
                    item
                    for field in fields
                    for item in (html.Dt(shown[field]), html.Dd(html.Code(field)))
                ]
                + [
                    item
                    for header_text, sources in page_only
                    for item in (html.Dt(header_text), html.Dd(html.Code(sources)))
                ]
            ),
        ],
        className="glossary",
        **kwargs,
    )


def has_popular_vote(value: object) -> str:
    """The cell for ``has_popular_vote``.

    ``True`` reads "Yes" and ``False`` :data:`NOT_IN_DATASET`. A null or a blank names
    no cause, so it reads :data:`NOT_IN_DATASET` too (:data:`HAS_POPULAR_VOTE_NOTE`
    explains only ``False``); any other value reads :data:`UNRECOGNIZED`.
    """
    if value is True:
        return "Yes"
    if value is False:
        return NOT_IN_DATASET
    return _unknown(value)


def number(value: object) -> str:
    """An integer with thousands separators, however large; a null or a blank names no
    cause, and anything else (a float, a bool, a string) reads :data:`UNRECOGNIZED`."""
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return _unknown(value)


def share(value: object) -> str:
    """A share as a percentage to one decimal place.

    Total: a null or a blank names no cause; any other value no percentage can show
    reads :data:`UNRECOGNIZED` (see :func:`finite`), including a finite one whose
    percentage overflows, rather than raising ``OverflowError`` past the page's degraded
    state (``json`` parses integers of any size).
    """
    number_ = finite(value)
    if number_ is None or not math.isfinite(number_ * 100):
        return _unknown(value)
    return f"{number_ * 100:.1f}%"


def yes_no(value: object) -> str:
    """A known boolean fact (``took_office``): "Yes" or "No"; a null or a blank names
    no cause, and anything else reads :data:`UNRECOGNIZED`."""
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return _unknown(value)


def nominating_party(value: object) -> str:
    """A nominating party's display form (#389); see :func:`_closed_value`. Exact
    match: a code is never stripped or re-cased."""
    return _closed_value(value, NOMINATING_PARTY)


def _note_text(value: object) -> str | None:
    """A row note as served, or ``None`` when it is not text with something in it."""
    return value if has_text(value) else None


def nominating_party_cell(row: Mapping[str, Any]) -> html.Td:
    """A row's party cell (#389): :func:`nominating_party`, with the one help text that
    explains it. An unrecognized value carries :data:`UNRECOGNIZED_NOTE`
    (:func:`cell`); a row with a note carries the note as served, after
    :data:`NO_NOMINATION_NOTE` on a ``no_nomination`` row and after
    :data:`PARTY_NULL_NOTE` on a null or blank party (defensive: the API serves no such
    row); a ``no_nomination`` row without one carries :data:`NO_NOMINATION_NOTE`; a
    null or blank party carries :data:`PARTY_NULL_NOTE`; a party with no note carries
    none."""
    value = row.get("nominating_party")
    shown = nominating_party(value)
    note = _note_text(row.get("nominating_party_note"))
    # The rule keys on the code and the null, never on a display label.
    lead = (
        NO_NOMINATION_NOTE
        if value == "no_nomination"
        else PARTY_NULL_NOTE
        if is_blank(value)
        else None
    )
    title = note if lead is None else lead if note is None else f"{lead} {note}"
    td: html.Td = cell(shown, title=title)
    return td


def party_notes(rows: Iterable[Mapping[str, Any]]) -> list[html.Div]:
    """The visible Party notes list under a table (#389): one item per candidate-year
    among ``rows`` whose note is text with something in it, in first-seen order, each
    candidate-year once however many state rows repeat it (keyed on the year, the slug
    and the name, so two candidates whose slug is missing never merge). A list, empty
    when there is none, so a page splices it in place (``*party_notes(rows)``).
    The candidate's name is shown as served; a null or blank one reads
    :data:`NOT_IN_DATASET`, and one that is not text, or is made only of format or
    control characters that are not whitespace, with or without whitespace beside them
    (#532), reads :data:`UNRECOGNIZED`
    (:func:`_unknown`), never the raw value."""
    items: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        note = _note_text(row.get("nominating_party_note"))
        name = row.get("candidate")
        key = (repr(row.get("year")), repr(row.get("candidate_slug")), repr(name))
        if note is None or key in seen:
            continue
        seen.add(key)
        items.append(
            PARTY_NOTE_ITEM.format(
                candidate=name if has_text(name) else _unknown(name),
                year=row.get("year"),
                note=note,
            )
        )
    if not items:
        return []
    return [
        html.Div(
            [
                html.P(html.Strong(PARTY_NOTES_HEADING), className="note"),
                html.Ul([html.Li(item) for item in items]),
            ],
            className="party-notes",
        )
    ]


def popular_votes(
    value: object,
    pv_status: object,
    year: int,
    coverage: dict[str, Any],
    no_figure: str = NO_FIGURE,
) -> str:
    """A state's popular-vote cell: the figure, or why there is none.

    A null (or a blank, #355) is never bare: a legislature's choice and a state taking
    no part say so whatever the year; a held popular vote with no figure says whether
    the year lies before the dataset's popular-vote window, after it (a snapshot whose
    Electoral College data runs ahead of its popular vote), or inside it. An unknown
    status names no cause it cannot vouch for: see :func:`_unknown`. The window comes
    from ``coverage``, never a literal. ``no_figure`` is the cell inside the window:
    a candidate's by default, :data:`NO_STATE_TOTAL` for a state's total (C10, #582).
    """
    if not is_blank(value):
        return number(value)
    if pv_status == "legislature_chosen":
        return LEGISLATURE_CHOSE
    if pv_status == "not_participating":
        return TOOK_NO_PART
    if pv_status != "popular_vote":
        return _unknown(pv_status)
    if year < coverage["pv_year_min"]:
        return BEFORE_WINDOW.format(pv_year_min=coverage["pv_year_min"])
    if year > coverage["pv_year_max"]:
        return AFTER_WINDOW
    return no_figure


def pv_status(value: object) -> str:
    """A ``pv_status`` value's label; see :func:`_closed_value`."""
    return _closed_value(value, PV_STATUS)


def count_status(status: object, reason: object) -> list[Any]:
    """A count-status cell: the label, and for a vote not counted, its meaning and the
    National Archives' reason sentence verbatim, shown only when it is text with
    something in it (the download keeps it as served). Any other status: see
    :func:`_unknown`."""
    if not isinstance(status, str) or status not in COUNT_STATUS:
        return [_unknown(status)]
    label, meaning = COUNT_STATUS[status]
    if meaning is None:
        return [label]
    parts: list[Any] = [html.Strong(label), f" ({meaning})"]
    if has_text(reason):
        parts += [html.Br(), html.Span(reason, className="reason")]
    return parts


def _closed_value(value: object, table: dict[str, str]) -> str:
    """A closed value's label. A null or a blank is no value the row explains, so it
    names none (:data:`NOT_IN_DATASET`, never a bare cell); any other value outside
    ``table`` reads :data:`UNRECOGNIZED`, never the raw value (#355)."""
    if isinstance(value, str) and value in table:
        return table[value]
    return _unknown(value)


def boundary_basis(value: object) -> str:
    """A ``boundary_basis`` value's label (#280); see :func:`_closed_value`."""
    return _closed_value(value, BOUNDARY_BASIS)


def per_capita_coverage(value: object) -> str:
    """A per-capita ``coverage`` value's label (#280); see :func:`_closed_value`."""
    return _closed_value(value, PER_CAPITA_COVERAGE)


def _null_per_capita(coverage: object) -> str:
    """Why a per-capita figure is null, as far as ``coverage`` says.

    No governing census figure reads as such; ``covered``, a null or a blank gives no
    cause, so the cell names none (:data:`NOT_IN_DATASET`); any other value reads
    :data:`UNRECOGNIZED` (see :func:`_closed_value`).
    """
    if coverage == "covered":
        return NOT_IN_DATASET
    return per_capita_coverage(coverage)


def population(value: object, coverage: object) -> str:
    """A per-capita population cell: the figure, or why there is none (#280); a blank
    is no figure (#355)."""
    return _null_per_capita(coverage) if is_blank(value) else number(value)


def persons_per_electoral_vote(
    value: object, coverage: object, allotment: object
) -> str:
    """A persons-per-electoral-vote cell: the figure to a whole person, or why there is
    none (#280). Never bare, and never an infinity: a null ratio over a zero allotment
    reads as such.

    The single statement of which cause explains a null (or blank, #355) ratio. A
    missing census figure comes first, so a row carrying both causes reads as that;
    then a zero allotment (the state's votes were withheld), which wins over an
    unrecognized ``coverage``; then ``coverage`` as :func:`_null_per_capita` reads it.
    Total, as :func:`share` is: any other value no figure can show (a non-finite
    number, an integer no float can hold, a bool, a string) reads
    :data:`UNRECOGNIZED`, and so does a figure that rounds to zero or less, which no
    state's population divided by its electors appointed can be (#435's review).
    """
    if is_blank(value):
        if coverage == NO_GOVERNING_FIGURE:
            return PER_CAPITA_COVERAGE[NO_GOVERNING_FIGURE]
        if allotment == 0 and not isinstance(allotment, bool):
            return NO_ELECTORAL_VOTES
        return _null_per_capita(coverage)
    number_ = finite(value)
    if number_ is None:
        return _unknown(value)
    shown = round(number_)
    return UNRECOGNIZED if shown <= 0 else f"{shown:,}"


def census_year(value: object) -> str:
    """A census year (#280): the year, with no thousands separator; otherwise see
    :func:`_unknown`."""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return _unknown(value)


#: The per-capita columns both tables share, in display order, after each table's own
#: first column (T6 the state, T7 the year).
PER_CAPITA_FIELDS = (
    "governing_census_year",
    "state_electoral_votes",
    "population",
    "boundary_basis",
    "coverage",
    "persons_per_electoral_vote",
)


def per_capita_strings(row: dict[str, Any]) -> dict[str, str]:
    """A per-capita row's worded cells for :data:`PER_CAPITA_FIELDS`, by field (#280,
    #435): the one source of the strings T6 and T7 show and chart C3 draws, so the
    chart writes each figure as the table does."""
    coverage = row["coverage"]
    allotment = row["state_electoral_votes"]
    return {
        "governing_census_year": census_year(row["governing_census_year"]),
        "state_electoral_votes": number(allotment),
        "population": population(row["population"], coverage),
        "boundary_basis": boundary_basis(row["boundary_basis"]),
        "coverage": per_capita_coverage(coverage),
        "persons_per_electoral_vote": persons_per_electoral_vote(
            row["persons_per_electoral_vote"], coverage, allotment
        ),
    }


def per_capita_cells(
    row: dict[str, Any], strings: dict[str, str] | None = None
) -> list[html.Td]:
    """A per-capita row's cells for :data:`PER_CAPITA_FIELDS` (#280), from
    :func:`per_capita_strings` (passed in when the page already computed them).

    The boundary-basis cell carries :data:`BOUNDARY_NOTE` as its help text, as a null
    party cell carries its note; an unrecognized cell carries :data:`UNRECOGNIZED_NOTE`.
    """
    worded = per_capita_strings(row) if strings is None else strings
    return [
        cell(worded[field], title=BOUNDARY_NOTE if field == "boundary_basis" else None)
        for field in PER_CAPITA_FIELDS
    ]


def in_pv_window(year: int, coverage: dict[str, Any]) -> bool:
    """Whether ``year`` lies inside the popular-vote window ``coverage`` names (#308).

    The window comes from ``coverage``, never a literal. This module reads no
    :mod:`explore.query`, so it does not check the window: the page does, once, with
    ``query.year_span`` before any cell reads it (a bool, a float, a reversed window or
    a missing bound would otherwise decide the answer silently). Unchecked, this raises
    only on a missing key or an incomparable type.
    """
    return bool(coverage["pv_year_min"] <= year <= coverage["pv_year_max"])


def _null(applicable: bool) -> str:
    """A null panel figure: :data:`NOT_APPLICABLE` outside the window; inside it, no
    cause."""
    return NOT_IN_DATASET if applicable else NOT_APPLICABLE


def winner(value: object, applicable: bool) -> str:
    """A winner cell (#308): the name, or why there is none.

    ``applicable`` is whether the method has a winner this year: always for the
    Electoral College, inside the popular-vote window for the other two. A name is
    shown whatever the year, as :func:`popular_votes` shows a figure; a blank is no
    name, and a value that is not text, or is made only of format or control
    characters that are not whitespace, with or without whitespace beside them (#532),
    reads :data:`UNRECOGNIZED`.
    """
    if has_text(value):
        return value
    return _unknown(value, _null(applicable))


def flip(value: object, method: str, applicable: bool, *, determinative: object) -> str:
    """A flip cell (#308): only ``True`` and ``False`` read Yes and No; a null or a
    blank is never "No" (see :func:`winner`); anything else reads
    :data:`UNRECOGNIZED`. A flip names the Electoral College's winner only with a
    majority (``determinative``), else its leader (#355)."""
    if value is True:
        role = "winner" if _ec_role_is_winner(determinative) else "leader"
        return FLIP_YES.format(method=method, role=role)
    if value is False:
        return "No"
    return _unknown(value, _null(applicable))


def margin(value: object, applicable: bool) -> str:
    """A margin cell (#308), already in percentage points in the API, to one decimal.

    A null or a blank reads as :func:`winner`'s does. Total, as :func:`share` is: any
    other value no figure can show (a non-finite number, an integer no float can hold,
    a value of no numeric type) reads :data:`UNRECOGNIZED`.
    """
    points = finite(value)
    if points is None:
        return _unknown(value, _null(applicable))
    return f"{points:.1f} percentage points"


def metric_mean(
    mean: Any, years: Sequence[int], pv_window: tuple[int, int] | None = None
) -> tuple[str, str | None]:
    """An average margin's value on ``/elections`` (#437), as ``(value, over)``: the
    value text, and the text after it naming its N and years, or ``None`` where there is
    none to name. ``mean`` is an ``explore.metrics.Mean`` (this module imports no
    ``metrics``, which imports it); ``years`` the distinct years shown; ``pv_window``
    the popular-vote window, given for the popular-vote average only.

    Checked in order: an unrecognized mean (:data:`UNRECOGNIZED`, with no N or years);
    no contributing election, worded by its cause (no year shown, then a popular-vote
    average with no year shown inside the window, then every margin null); else the
    number, through :func:`margin`, so the average over one election reads exactly as
    that year's panel cell.
    """
    if mean.unrecognized:
        return UNRECOGNIZED, None
    if mean.n == 0:
        if not years:
            return METRIC_NO_AVERAGE_FILTERS, None
        if pv_window is not None and not any(
            pv_window[0] <= year <= pv_window[1] for year in years
        ):
            first, last = pv_window
            return METRIC_NO_AVERAGE_PV_YEARS.format(first=first, last=last), None
        return METRIC_NO_AVERAGE_NULL, None
    text = margin(mean.value, True)
    if mean.n == 1:
        whole = METRIC_OVER_ONE.format(value=text, year=mean.first)
    else:
        whole = METRIC_OVER.format(
            value=text, n=mean.n, first=mean.first, last=mean.last
        )
    return text, whole.removeprefix(text)


def metric_count(
    result: Any,
    years: Sequence[int],
    no_figure: str,
    pv_window: tuple[int, int] | None = None,
) -> tuple[str, str | None]:
    """A count of elections, as ``(value, rest)``, on ``/elections/majority`` (#569,
    D112) and ``/state/<usps>`` (the took-office count, #601, D115, whose ``no_figure``
    the page chooses and whose N may be smaller than the elections count beside it): the
    value text, and the text after it naming its N and years, or ``None`` where there is
    none to name. ``result`` is an ``explore.metrics.FlagCount`` (this module imports no
    ``metrics``, which imports it); ``years`` the distinct years shown; ``no_figure``
    the count's own wording for every flag null; ``pv_window`` the popular-vote window,
    given for the popular-vote count only.

    Checked in order: an unrecognized count (:data:`UNRECOGNIZED`, with no N or years);
    no contributing election, worded by its cause (a popular-vote count with no year
    shown inside the window, then every flag null); else the count, with N and years.
    """
    if result.unrecognized:
        return UNRECOGNIZED, None
    if result.n == 0:
        if pv_window is not None and not any(
            pv_window[0] <= year <= pv_window[1] for year in years
        ):
            first, last = pv_window
            return METRIC_NO_FIGURE_PV_YEARS.format(first=first, last=last), None
        return no_figure, None
    text = str(result.count)
    if result.n == 1:
        whole = METRIC_COUNT_OF_ONE.format(count=text, year=result.first)
    else:
        whole = METRIC_COUNT_OF.format(
            count=text, n=result.n, first=result.first, last=result.last
        )
    return text, whole.removeprefix(text)


def metric_elections(
    n: int, years: Sequence[int], no_figure: str
) -> tuple[str, str | None]:
    """A count of elections with its years (#601, D115), as ``(value, rest)``: ``n``,
    the count ``explore.metrics.count`` computed (this module only words it, D097), from
    the earliest to the latest of ``years``, or ``no_figure`` (with no rest) when ``n``
    is 0, never "0 elections"."""
    if n == 0:
        return no_figure, None
    text = str(n)
    if n == 1:
        whole = METRIC_COUNT_ELECTIONS_ONE.format(year=min(years))
    else:
        whole = METRIC_COUNT_ELECTIONS.format(
            n=text, first=min(years), last=max(years)
        )
    return text, whole.removeprefix(text)


def metric_total(result: Any, no_figure: str) -> tuple[str, str | None]:
    """A total of electoral votes (#601, D115), as ``(value, rest)``. ``result`` is an
    ``explore.metrics.Total`` (this module imports no ``metrics``). Checked in order:
    unrecognized (:data:`UNRECOGNIZED`, no N or years); no figure (``no_figure``, a null
    among the years, D097); else the total through :func:`number`, as T5's cells write
    a number, over its N and years (:data:`METRIC_OVER`, the averages' wording)."""
    if result.unrecognized:
        return UNRECOGNIZED, None
    if result.n == 0:
        return no_figure, None
    text = number(result.value)
    if result.n == 1:
        whole = METRIC_OVER_ONE.format(value=text, year=result.first)
    else:
        whole = METRIC_OVER.format(
            value=text, n=result.n, first=result.first, last=result.last
        )
    return text, whole.removeprefix(text)


def metric_years(years: Sequence[int]) -> str:
    """One year, or tied years joined by :data:`METRIC_YEARS_AND` (#600): "1824 and
    1828", "1852, 1856 and 1860"."""
    text = [str(year) for year in years]
    if len(text) == 1:
        return text[0]
    return METRIC_YEARS_AND.format(rest=", ".join(text[:-1]), last=text[-1])


def metric_select(
    result: Any,
    pick: str,
    years: Sequence[int],
    no_figure: str,
    pv_window: tuple[int, int] | None = None,
) -> tuple[str, str | None]:
    """A select figure (#600, D112(d)), as ``(value, rest)``: the value text, and the
    text after it naming the year or years and N, or ``None`` where there is none.
    ``result`` is an ``explore.metrics.Selection`` (this module imports no
    ``metrics``, which imports it), whose picks carry the companion table's cells;
    ``pick`` one of its picks; ``years`` the distinct years shown; ``no_figure`` the
    figure's own wording for every value null; ``pv_window`` the popular-vote window,
    given for a figure read against it only.

    Checked in order: an unrecognized selection (:data:`UNRECOGNIZED`, with no N or
    years); no value, worded by its cause (no year shown, then a popular-vote figure
    with no year shown inside the window, then every value null); one election (the
    second of a pair names the first, :data:`METRIC_SELECT_SAME`); else the value
    with its year or tied years, N and the years with a value.
    """
    if result.unrecognized:
        return UNRECOGNIZED, None
    if result.n == 0:
        if not years:
            return METRIC_NO_FIGURE_NO_ELECTIONS, None
        if pv_window is not None and not any(
            pv_window[0] <= year <= pv_window[1] for year in years
        ):
            first, last = pv_window
            return METRIC_NO_FIGURE_PV_YEARS.format(first=first, last=last), None
        return no_figure, None
    first_year, last_year = result.first[0], result.latest[0]
    if pick in ("first", "latest"):
        year, value = getattr(result, pick)
        picked: Sequence[int] = (year,)
    else:
        value, picked = getattr(result, pick)
    if result.n == 1:
        if pick in METRIC_SELECT_OTHER:
            return (
                METRIC_SELECT_SAME.format(
                    other=METRIC_SELECT_OTHER[pick], year=first_year
                ),
                None,
            )
        whole = METRIC_SELECT_ONE.format(value=value, year=first_year)
    else:
        whole = METRIC_SELECT.format(
            value=value,
            years=metric_years(picked),
            n=result.n,
            first=first_year,
            last=last_year,
        )
    return value, whole.removeprefix(value)


def ec_majority(value: object) -> str:
    """An ``ec_determinative`` cell (#308): ``False`` is a real outcome, never a gap;
    a null or a blank names no cause; anything else reads :data:`UNRECOGNIZED`."""
    if value is True:
        return EC_MAJORITY
    if value is False:
        return NO_EC_MAJORITY
    return _unknown(value)


def national_pv(value: Any, has_popular_vote: bool, as_share: bool) -> str:
    """A national cell that needs the popular vote, on T3's year rule (#352; shared by
    T3 and C2's table since #564): :data:`NOT_APPLICABLE` in a year with no popular
    vote (the index row's ``has_popular_vote``), and inside it a null (or a blank,
    #355) is a candidate with no popular-vote figure."""
    if not has_popular_vote:
        return NOT_APPLICABLE
    if is_blank(value):
        return NO_NATIONAL_FIGURE
    return share(value) if as_share else number(value)


def share_cell(value: object) -> str:
    """A share the schema makes nullable though the API fills it for every year
    (``ec_share_full``, ``pv_coverage``): a null names no cause, as :func:`share` reads
    one."""
    return share(value)


#: The year filters on the three elections pages (#596, D110; ba spec for #596): the
#: slider's label, the popular-vote checkbox's text (which
#: :data:`METRIC_SAME_ELECTIONS` names by its text; the control adds a leading space),
#: and what each page shows when the filters leave no election.
YEARS_FILTER = "Years"
PV_ONLY_FILTER = "Only years with a popular vote in this dataset"
NO_ELECTIONS_MATCH = "No elections match these filters."
#: The state history's form, in place of C7, C10 and their table when its one filter,
#: the Years slider, leaves no election (#620, D119; ba spec, approved at #620's plan
#: gate).
STATE_NO_ELECTIONS_IN_RANGE = "No election for this state falls in the years chosen."
