"""Tests for the LLM service helpers and provider routing (mocked)."""
from __future__ import annotations

import pytest

from app.models import ScriptResult, VideoParams
from app.services import llm
from app.services.llm import _clean_script, _parse_terms


class TestCleanScript:
    def test_strips_markdown_chars(self):
        assert _clean_script("# Title\n**bold** `code` > quote") == "Title\nbold code  quote"

    def test_collapses_blank_lines(self):
        assert _clean_script("line one\n\n\nline two") == "line one\nline two"

    def test_trims_whitespace(self):
        assert _clean_script("   hello   ") == "hello"


class TestParseTerms:
    def test_parses_json_array(self):
        assert _parse_terms('["ocean waves", "city night"]', "x") == ["ocean waves", "city night"]

    def test_extracts_array_from_noise(self):
        raw = 'Sure! Here you go: ["reading", "library", "books"] hope that helps'
        assert _parse_terms(raw, "x") == ["reading", "library", "books"]

    def test_caps_at_eight(self):
        raw = "[" + ",".join(f'"t{i}"' for i in range(20)) + "]"
        assert len(_parse_terms(raw, "x")) == 8

    def test_fallback_on_bad_json(self):
        assert _parse_terms("not json at all", "my topic") == ["my topic"]

    def test_fallback_on_empty_array(self):
        assert _parse_terms("[]", "my topic") == ["my topic"]


class TestProviderRouting:
    def test_unknown_provider_raises(self, monkeypatch):
        class FakeSettings:
            class llm:
                provider = "mystery"

        monkeypatch.setattr(llm, "get_settings", lambda: FakeSettings())
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            llm._complete("prompt", "system")

    def test_generate_script_composes_results(self, monkeypatch):
        # Mock the low-level completion so no network/keys are needed.
        calls = {"n": 0}

        def fake_complete(prompt: str, system: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return "**Reading** is great.\n\n\nIt helps you grow."
            return '["reading", "books", "library"]'

        monkeypatch.setattr(llm, "_complete", fake_complete)
        result = llm.generate_script(VideoParams(topic="the benefits of reading"))
        assert isinstance(result, ScriptResult)
        assert result.script == "Reading is great.\nIt helps you grow."
        assert result.search_terms == ["reading", "books", "library"]

    def test_generate_script_errors_on_empty(self, monkeypatch):
        monkeypatch.setattr(llm, "_complete", lambda p, s: "   ")
        with pytest.raises(RuntimeError, match="empty script"):
            llm.generate_script(VideoParams(topic="reading"))
