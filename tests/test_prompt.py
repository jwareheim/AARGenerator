"""Unit tests for prompt building."""

import pytest


def make_snapshot(**kwargs):
    base = {
        "date": "2200.01.01",
        "empire_name": "Keth Dominion",
        "species_name": "Keth",
        "portrait_class": "humanoid",
        "species_traits": ["Intelligent", "Adaptive"],
        "ethics": ["Authoritarian", "Militarist"],
        "civics": ["Aristocratic Elite", "Distinguished Admiralty"],
        "authority": "Imperial",
        "origin": "Prosperous Unification",
        "home_planet": "Keth Prime",
        "home_system": "Keth",
        "planets": ["Keth Prime"],
        "pop_count": 12,
        "ruler": {"name": "Emperor Vorlan I", "traits": ["Charismatic"]},
        "leaders": [],
        "wars": [],
        "recent_techs": [],
        "perks": [],
        "federation": None,
        "subjects": [],
    }
    base.update(kwargs)
    return base


class TestBuildOriginPrompt:
    def test_contains_empire_name(self):
        import chronicle
        prompt = chronicle.build_origin_prompt(make_snapshot())
        assert "Keth Dominion" in prompt

    def test_contains_species(self):
        import chronicle
        prompt = chronicle.build_origin_prompt(make_snapshot())
        assert "Keth" in prompt

    def test_contains_ethics(self):
        import chronicle
        prompt = chronicle.build_origin_prompt(make_snapshot())
        assert "Authoritarian" in prompt

    def test_contains_home_planet(self):
        import chronicle
        prompt = chronicle.build_origin_prompt(make_snapshot())
        assert "Keth Prime" in prompt

    def test_contains_word_count_instruction(self):
        import chronicle
        prompt = chronicle.build_origin_prompt(make_snapshot())
        assert "400" in prompt or "600" in prompt


class TestBuildChapterPrompt:
    def _make_delta(self):
        return [
            {"type": "war_started", "weight": 1, "data": {"name": "War of Expansion"}},
            {"type": "date_delta", "weight": 99, "data": {"from": "2200.01.01", "to": "2230.06.15"}},
        ]

    def test_contains_chapter_number(self):
        import chronicle
        prompt = chronicle.build_chapter_prompt(3, self._make_delta(), make_snapshot(), {})
        assert "Chapter 3" in prompt

    def test_contains_date_range(self):
        import chronicle
        prompt = chronicle.build_chapter_prompt(3, self._make_delta(), make_snapshot(), {})
        assert "2200.01.01" in prompt
        assert "2230.06.15" in prompt

    def test_contains_war_event(self):
        import chronicle
        prompt = chronicle.build_chapter_prompt(3, self._make_delta(), make_snapshot(), {})
        assert "war_started" in prompt

    def test_includes_summary_when_present(self):
        import chronicle
        summary = {"text": "The Keth rose from dust."}
        prompt = chronicle.build_chapter_prompt(3, self._make_delta(), make_snapshot(), summary)
        assert "The Keth rose from dust." in prompt


class TestBuildSummaryUpdatePrompt:
    def test_contains_chapter_prose(self):
        import chronicle
        prompt = chronicle.build_summary_update_prompt("Chapter prose here.", {})
        assert "Chapter prose here." in prompt

    def test_contains_word_limit(self):
        import chronicle
        prompt = chronicle.build_summary_update_prompt("prose", {})
        assert "250" in prompt

    def test_includes_existing_summary(self):
        import chronicle
        existing = {"text": "Old summary text."}
        prompt = chronicle.build_summary_update_prompt("new prose", existing)
        assert "Old summary text." in prompt
