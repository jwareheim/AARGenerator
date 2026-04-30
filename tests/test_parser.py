"""Unit tests for save parsing and data extraction."""

import io
import json
import pathlib
import zipfile
from unittest.mock import patch, MagicMock

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def make_fake_save(meta_text: str, gamestate_text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta", meta_text)
        zf.writestr("gamestate", gamestate_text)
    return buf.getvalue()


class TestParseSave:
    def test_rejects_non_zip(self):
        import chronicle
        with pytest.raises(Exception):
            chronicle.parse_save(b"not a zip file")

    def test_rejects_missing_gamestate(self):
        import chronicle
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("meta", "date=2200.01.01")
        with pytest.raises(ValueError, match="gamestate"):
            chronicle.parse_save(buf.getvalue())

    def test_returns_snapshot_dict(self):
        import chronicle
        save_bytes = make_fake_save(
            meta_text='date="2200.01.01"\nversion="3.12.0"',
            gamestate_text='date="2200.01.01"',
        )
        with patch("ClauseWizard.cwparse", return_value=[]), \
             patch("ClauseWizard.cwformat", return_value={"date": "2200.01.01"}):
            snapshot = chronicle.parse_save(save_bytes)
        assert isinstance(snapshot, dict)
        assert "date" in snapshot


class TestExtractRelevantData:
    def test_returns_required_keys(self):
        import chronicle
        raw = {}
        meta = {"date": "2200.01.01", "version": "3.12.0"}
        snapshot = chronicle.extract_relevant_data(raw, meta)
        required = [
            "date", "empire_name", "species_name", "ethics", "civics",
            "planets", "wars", "leaders", "ruler", "recent_techs",
        ]
        for key in required:
            assert key in snapshot, f"Missing key: {key}"

    def test_date_comes_from_meta(self):
        import chronicle
        snapshot = chronicle.extract_relevant_data({}, {"date": "2287.06.15"})
        assert snapshot["date"] == "2287.06.15"
