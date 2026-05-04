"""Parser tests — calls the real stellaris-parser binary against the fixture."""

import json
import pathlib
import subprocess
import sys

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
REPO_ROOT = pathlib.Path(__file__).parent.parent
_BIN_NAME = "stellaris-parser.exe" if sys.platform == "win32" else "stellaris-parser"
BINARY = REPO_ROOT / "bin" / _BIN_NAME

REQUIRED_SNAPSHOT_KEYS = [
    "date", "empire_name", "species_name", "portrait_class", "species_traits",
    "ethics", "civics", "authority", "origin", "home_planet", "home_system",
    "patch_version", "planets", "pop_count", "fleet_power", "income",
    "traditions", "perks", "ruler", "leaders", "wars", "federation",
    "subjects", "rivals", "allies", "recent_techs",
]

REQUIRED_INCOME_KEYS = ["energy", "minerals", "alloys"]


def _run(sav_path):
    return subprocess.run(
        [str(BINARY), "extract", str(sav_path)],
        capture_output=True,
        timeout=60,
    )


@pytest.fixture(scope="module")
def raw_snapshot():
    """Raw JSON from the binary — the Snapshot schema."""
    result = _run(FIXTURES / "sample.sav")
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def snapshot(raw_snapshot):
    """Normalised snapshot dict produced by extract_relevant_data()."""
    import chronicle
    return chronicle.extract_relevant_data(raw_snapshot)


# ── Player country ID ─────────────────────────────────────────────────────────

class TestPlayerCountryId:
    def test_is_zero_for_fixture(self, raw_snapshot):
        assert raw_snapshot["player_country_id"] == 0

    def test_is_integer(self, raw_snapshot):
        assert isinstance(raw_snapshot["player_country_id"], int)


# ── Owned planets ─────────────────────────────────────────────────────────────

class TestOwnedPlanets:
    # Non-habitable planet class prefixes that should never appear as owned planets
    _STELLAR_PREFIXES = (
        "pc_a_star", "pc_f_star", "pc_g_star", "pc_k_star", "pc_m_star",
        "pc_t_star", "pc_asteroid", "pc_gas_giant", "pc_neutron_star",
        "pc_black_hole", "pc_rare_crystal",
    )

    def test_owned_planets_is_list(self, snapshot):
        assert isinstance(snapshot["planets"], list)

    def test_owned_planet_count_is_positive(self, raw_snapshot):
        assert raw_snapshot["state"]["owned_planet_count"] > 0

    def test_no_stellar_bodies_by_name(self, snapshot):
        for name in snapshot["planets"]:
            for prefix in self._STELLAR_PREFIXES:
                assert not name.startswith(prefix), (
                    f"Non-habitable body '{name}' found in owned planets"
                )


# ── Required snapshot keys and types ─────────────────────────────────────────

class TestSnapshotShape:
    def test_all_required_keys_present(self, snapshot):
        for key in REQUIRED_SNAPSHOT_KEYS:
            assert key in snapshot, f"Missing required snapshot key: {key}"

    def test_income_sub_keys(self, snapshot):
        for key in REQUIRED_INCOME_KEYS:
            assert key in snapshot["income"], f"Missing income key: {key}"

    def test_string_fields(self, snapshot):
        for field in ("date", "empire_name", "patch_version", "authority"):
            assert isinstance(snapshot[field], str), f"{field} should be str"

    def test_list_fields(self, snapshot):
        for field in ("planets", "ethics", "civics", "traditions", "perks",
                      "leaders", "wars", "subjects", "rivals", "allies",
                      "recent_techs", "species_traits"):
            assert isinstance(snapshot[field], list), f"{field} should be list"

    def test_numeric_fields(self, snapshot):
        assert isinstance(snapshot["pop_count"], int)
        assert isinstance(snapshot["fleet_power"], int)
        assert isinstance(snapshot["income"]["energy"], float)
        assert isinstance(snapshot["income"]["minerals"], float)
        assert isinstance(snapshot["income"]["alloys"], float)

    def test_ruler_is_dict(self, snapshot):
        assert isinstance(snapshot["ruler"], dict)

    def test_federation_is_none_or_dict(self, snapshot):
        assert snapshot["federation"] is None or isinstance(snapshot["federation"], dict)

    def test_fixture_ethics_match_expected(self, snapshot):
        assert "ethic_militarist" in snapshot["ethics"]
        assert "ethic_fanatic_spiritualist" in snapshot["ethics"]

    def test_fixture_has_traditions(self, snapshot):
        assert len(snapshot["traditions"]) > 0

    def test_fixture_has_recent_techs(self, snapshot):
        assert len(snapshot["recent_techs"]) == 10
