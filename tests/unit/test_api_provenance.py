"""The presentation-layer provenance lookups (``usvote.api.provenance``, E8-S4 #98).

Guards the two properties that keep the code→display map honest: it resolves the codes the
snapshot actually emits, and it **fails loud** on an unmapped code rather than silently
blanking (D005). The redistributable note is asserted to name the source/license (so it
can't drift from the maps) and to state the UCSB exclusion (D030).
"""

from __future__ import annotations

import pytest

from usvote.api import provenance


def test_mit_and_cc0_resolve() -> None:
    src = provenance.source_display("MIT")
    lic = provenance.license_display("CC0-1.0")
    assert src.name == "MIT Election Lab"
    assert lic.name.startswith("CC0")
    assert lic.url.startswith("http")


def test_unknown_source_fails_loud() -> None:
    with pytest.raises(provenance.UnknownProvenanceCode, match="source"):
        provenance.source_display("UCSB")


def test_unknown_license_fails_loud() -> None:
    with pytest.raises(provenance.UnknownProvenanceCode, match="license"):
        provenance.license_display("CC-BY-4.0")


def test_redistributable_note_names_source_license_and_excludes_ucsb() -> None:
    src = provenance.source_display("MIT")
    lic = provenance.license_display("CC0-1.0")
    note = provenance.redistributable_note(src, lic)
    assert src.name in note
    assert lic.name in note
    assert "UCSB" in note


def test_maps_cover_every_code_the_snapshot_can_emit() -> None:
    """The public API is redistributable-only (D016/D030): MIT / CC0-1.0 must be mapped.

    A future PV source cleared for public redistribution must add its display row here (and
    would trip this test until it does), so the map can never fall behind the snapshot.
    """
    assert "MIT" in provenance._SOURCES
    assert "CC0-1.0" in provenance._LICENSES
