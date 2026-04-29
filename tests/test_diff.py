"""Unit tests for snapshot diffing."""

import pytest


def make_snapshot(**kwargs):
    base = {
        "date": "2200.01.01",
        "planets": [],
        "wars": [],
        "leaders": [],
        "ruler": {"name": "Emperor I", "traits": []},
        "perks": [],
        "recent_techs": [],
        "federation": None,
        "subjects": [],
    }
    base.update(kwargs)
    return base


class TestDiffSnapshots:
    def test_empty_baseline_returns_empty(self):
        import chronicle
        assert chronicle.diff_snapshots({}, make_snapshot()) == []

    def test_always_includes_date_delta(self):
        import chronicle
        baseline = make_snapshot(date="2200.01.01")
        current = make_snapshot(date="2210.06.15")
        deltas = chronicle.diff_snapshots(baseline, current)
        types = [d["type"] for d in deltas]
        assert "date_delta" in types

    def test_detects_new_war(self):
        import chronicle
        baseline = make_snapshot(wars=[])
        current = make_snapshot(wars=[{"id": "war_001", "name": "War of Aggression"}])
        deltas = chronicle.diff_snapshots(baseline, current)
        types = [d["type"] for d in deltas]
        assert "war_started" in types

    def test_detects_ended_war(self):
        import chronicle
        baseline = make_snapshot(wars=[{"id": "war_001", "name": "Old War"}])
        current = make_snapshot(wars=[])
        deltas = chronicle.diff_snapshots(baseline, current)
        types = [d["type"] for d in deltas]
        assert "war_ended" in types

    def test_detects_colonized_planet(self):
        import chronicle
        baseline = make_snapshot(planets=["Keth Prime"])
        current = make_snapshot(planets=["Keth Prime", "New Keth"])
        deltas = chronicle.diff_snapshots(baseline, current)
        types = [d["type"] for d in deltas]
        assert "planet_colonized" in types

    def test_detects_lost_planet(self):
        import chronicle
        baseline = make_snapshot(planets=["Keth Prime", "Outer World"])
        current = make_snapshot(planets=["Keth Prime"])
        deltas = chronicle.diff_snapshots(baseline, current)
        types = [d["type"] for d in deltas]
        assert "planet_lost" in types

    def test_detects_leader_death(self):
        import chronicle
        baseline = make_snapshot(leaders=[{"id": "l001", "name": "Admiral Renn"}])
        current = make_snapshot(leaders=[])
        deltas = chronicle.diff_snapshots(baseline, current)
        types = [d["type"] for d in deltas]
        assert "leader_died" in types

    def test_detects_ruler_change(self):
        import chronicle
        baseline = make_snapshot(ruler={"name": "Emperor I"})
        current = make_snapshot(ruler={"name": "Empress II"})
        deltas = chronicle.diff_snapshots(baseline, current)
        types = [d["type"] for d in deltas]
        assert "ruler_changed" in types

    def test_deltas_sorted_by_weight(self):
        import chronicle
        baseline = make_snapshot(
            wars=[],
            planets=["Keth Prime"],
            recent_techs=[],
        )
        current = make_snapshot(
            wars=[{"id": "w1", "name": "War"}],
            planets=["Keth Prime", "Colony"],
            recent_techs=["tech_shields_3"],
        )
        deltas = chronicle.diff_snapshots(baseline, current)
        weights = [d["weight"] for d in deltas]
        assert weights == sorted(weights)
