import pytest

from app.exceptions import SopNotFoundError
from app.rag import SopIndex


def test_sop_index_loads_documents():
    index = SopIndex()
    assert len(index.chunks) > 0
    doc_names = {c.doc for c in index.chunks}
    assert len(doc_names) >= 3


def test_sop_search_finds_temperature_deviation_procedure():
    index = SopIndex()
    matches = index.search("cargo temperature deviation exceeds setpoint severe refrigeration failure")
    assert len(matches) > 0
    assert any("temperature_deviation" in m.doc for m in matches)


def test_sop_search_finds_diversion_facility_procedure():
    index = SopIndex()
    matches = index.search("divert refrigerated facility approved region")
    assert len(matches) > 0
    assert any("diversion_facilities" in m.doc for m in matches)


def test_sop_search_returns_empty_for_irrelevant_query_below_threshold():
    index = SopIndex()
    matches = index.search("quarterly marketing budget spreadsheet unrelated topic xyz123")
    assert matches == []


def test_sop_not_found_raises_for_missing_directory(tmp_path):
    empty_dir = tmp_path / "does_not_exist"
    with pytest.raises(SopNotFoundError):
        SopIndex(docs_dir=str(empty_dir))


def test_sop_not_found_raises_for_empty_directory(tmp_path):
    with pytest.raises(SopNotFoundError):
        SopIndex(docs_dir=str(tmp_path))
