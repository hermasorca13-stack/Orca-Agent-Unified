"""
Tests for skills/intent_skill.py.

Unit tests cover:
- Pattern-based classification (Arabic + English + mixed)
- Language detection
- Entity extraction
- User profile (record + recent)
- Intent dataclass properties (is_actionable, is_suggestion)
- Format helper
- LLM refinement (mocked — never hits the real API)
- Empty / whitespace inputs
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "intent_skill.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "intent_skill_under_test", str(SKILL_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["intent_skill_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_skill()
Intent = mod.Intent
IntentSkillError = mod.IntentSkillError
UserProfile = mod.UserProfile
classify = mod.classify
format_intent_card = mod.format_intent_card


# ----------------------------------------------------------------------
# Language detection
# ----------------------------------------------------------------------
class TestLanguage:
    def test_pure_arabic(self):
        assert mod._detect_language("الطقس في القاهرة") == "ar"

    def test_pure_english(self):
        assert mod._detect_language("weather in cairo") == "en"

    def test_mixed(self):
        assert mod._detect_language("ابحث عن weather in Tokyo") == "mixed"

    def test_unknown(self):
        assert mod._detect_language("1234 ?!@#") == "unknown"

    def test_empty(self):
        assert mod._detect_language("") == "unknown"


# ----------------------------------------------------------------------
# Entity extraction
# ----------------------------------------------------------------------
class TestEntities:
    def test_url(self):
        e = mod._extract_entities("visit https://example.com/x?y=1 now")
        assert e["urls"] == ["https://example.com/x?y=1"]

    def test_windows_path(self):
        e = mod._extract_entities("open C:\\Users\\me\\file.txt")
        assert "C:\\Users\\me\\file.txt" in e["paths"]

    def test_unix_path(self):
        e = mod._extract_entities("cat /etc/passwd")
        assert "/etc/passwd" in e["paths"]

    def test_quoted(self):
        e = mod._extract_entities('send "hello world" to me')
        assert "hello world" in e["quoted"]

    def test_numbers(self):
        e = mod._extract_entities("translate 42 items")
        assert "42" in e["numbers"]

    def test_no_entities(self):
        e = mod._extract_entities("just some text")
        assert e == {}


# ----------------------------------------------------------------------
# Pattern-based classification
# ----------------------------------------------------------------------
class TestPattern:
    def test_english_weather(self):
        out = classify("weather in Cairo", use_llm=False)
        assert out.command == "/weather"
        assert out.confidence >= 0.7
        assert "Cairo" in (out.args + [" ".join(out.args)])

    def test_english_search(self):
        out = classify("search for AI agents", use_llm=False)
        assert out.command == "/search"
        assert out.confidence >= 0.7

    def test_english_image(self):
        out = classify("generate an image of a cat", use_llm=False)
        assert out.command == "/image"
        assert out.confidence >= 0.7

    def test_english_translate(self):
        out = classify("translate this to Arabic", use_llm=False)
        assert out.command == "/translate"
        assert out.confidence >= 0.7

    def test_english_news(self):
        out = classify("today's news please", use_llm=False)
        assert out.command == "/news"

    def test_english_stock(self):
        out = classify("stock AAPL", use_llm=False)
        assert out.command == "/stock"

    def test_arabic_status(self):
        out = classify("ايه حالة السيرفر؟", use_llm=False)
        assert out.command == "/status"
        assert out.language == "ar"

    def test_arabic_image(self):
        out = classify("اعمل صورة قطة في الفضاء", use_llm=False)
        assert out.command == "/image"
        assert out.language == "ar"

    def test_mixed(self):
        out = classify("ابحث عن weather in Tokyo", use_llm=False)
        # Either /search or /weather is acceptable; the test only
        # checks that a plausible command is picked.
        assert out.command in ("/search", "/weather")
        assert out.language == "mixed"

    def test_empty(self):
        out = classify("", use_llm=False)
        assert out.command is None
        assert out.confidence == 0.0

    def test_whitespace(self):
        out = classify("   \t  ", use_llm=False)
        assert out.command is None
        assert out.confidence == 0.0

    def test_unknown_no_match(self):
        out = classify("xqzpfoobarbaz nonsense", use_llm=False)
        # No rule matches; command is None.
        assert out.command is None

    def test_entities_extracted(self):
        out = classify("search for https://example.com article", use_llm=False)
        assert "urls" in out.entities
        assert out.entities["urls"] == ["https://example.com"]

    def test_latency_reported(self):
        out = classify("weather Tokyo", use_llm=False)
        assert out.latency_ms >= 0


# ----------------------------------------------------------------------
# Intent properties
# ----------------------------------------------------------------------
class TestIntent:
    def test_actionable_high_confidence(self):
        i = Intent(command="/weather", args=["Cairo"], confidence=0.85)
        assert i.is_actionable is True
        assert i.is_suggestion is False

    def test_suggestion_medium_confidence(self):
        i = Intent(command="/weather", args=["Cairo"], confidence=0.5)
        assert i.is_actionable is False
        assert i.is_suggestion is True

    def test_not_actionable_low_confidence(self):
        i = Intent(command="/weather", args=["Cairo"], confidence=0.2)
        assert i.is_actionable is False
        assert i.is_suggestion is False

    def test_actionable_requires_command(self):
        i = Intent(command=None, confidence=0.99)
        assert i.is_actionable is False


# ----------------------------------------------------------------------
# UserProfile
# ----------------------------------------------------------------------
class TestUserProfile:
    def test_record_and_recent(self):
        p = UserProfile(max_history=5)
        p.record("u1", "weather", ["Cairo"])
        p.record("u1", "search", ["AI agents"])
        recent = p.recent("u1")
        assert len(recent) == 2
        assert recent[0]["command"] == "weather"
        assert recent[1]["command"] == "search"

    def test_max_history_capped(self):
        p = UserProfile(max_history=3)
        for i in range(10):
            p.record("u1", f"cmd{i}", [str(i)])
        recent = p.recent("u1")
        assert len(recent) == 3
        assert recent[-1]["command"] == "cmd9"

    def test_per_user_isolation(self):
        p = UserProfile()
        p.record("alice", "weather", ["Cairo"])
        p.record("bob", "search", ["x"])
        assert p.recent("alice")[0]["command"] == "weather"
        assert p.recent("bob")[0]["command"] == "search"

    def test_empty_user_id_ignored(self):
        p = UserProfile()
        p.record("", "weather", ["x"])
        p.record(None, "weather", ["x"])  # type: ignore
        assert p.recent("") == []

    def test_empty_command_ignored(self):
        p = UserProfile()
        p.record("u1", "", ["x"])
        assert p.recent("u1") == []

    def test_thread_safety(self):
        # Smoke test: spawn 20 threads, each records 100 commands.
        import threading as _t
        p = UserProfile(max_history=2000)
        def work():
            for i in range(100):
                p.record("u", "weather", ["x"])
        threads = [_t.Thread(target=work) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(p.recent("u")) == 2000


# ----------------------------------------------------------------------
# LLM refinement (mocked — never hits the real API)
# ----------------------------------------------------------------------
class TestLLMRefinement:
    def test_llm_not_called_when_pattern_high_confidence(self):
        # High-confidence pattern matches should bypass the LLM
        # entirely (saves a round-trip + cost).
        out = classify("search for AI agents", use_llm=True)
        assert out.source == "pattern"  # not "hybrid"

    def test_llm_not_called_without_key(self, monkeypatch):
        # No key + low confidence → return pattern match (no error).
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        out = classify("xqzfoobar", use_llm=True)
        # Low confidence, no fallback possible.
        assert out.confidence < 0.7

    def test_llm_failure_falls_back_to_pattern(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        # Force the SDK import to fail.
        with patch.dict(sys.modules, {"openai": None}):
            out = classify("abracadabra", use_llm=True)
        # Pattern returned (whatever it is); no exception.
        assert isinstance(out, Intent)

    def test_llm_refines_low_confidence(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        # Build a fake openai module with the chat.completions interface.
        fake_openai = MagicMock()
        fake_resp = MagicMock()
        fake_resp.choices = [MagicMock()]
        fake_resp.choices[0].message.content = (
            '{"command": "weather", "args": ["Tokyo"], '
            '"confidence": 0.92, "language": "en", '
            '"reasoning": "user asked for weather in Tokyo"}'
        )
        fake_openai.OpenAI.return_value.chat.completions.create.return_value = fake_resp
        with patch.dict(sys.modules, {"openai": fake_openai}):
            out = classify("abracadabra nocity", use_llm=True)
        # The LLM refinement should have kicked in.
        assert out.source == "hybrid"
        assert out.command == "/weather"
        assert out.confidence == 0.92

    def test_llm_response_malformed_json_keeps_pattern(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        fake_openai = MagicMock()
        fake_resp = MagicMock()
        fake_resp.choices = [MagicMock()]
        fake_resp.choices[0].message.content = "not json at all"
        fake_openai.OpenAI.return_value.chat.completions.create.return_value = fake_resp
        with patch.dict(sys.modules, {"openai": fake_openai}):
            out = classify("abracadabra", use_llm=True)
        # No JSON found; fall back to pattern (whatever it produced).
        assert isinstance(out, Intent)


# ----------------------------------------------------------------------
# Format helper
# ----------------------------------------------------------------------
class TestFormat:
    def test_no_command(self):
        i = Intent(confidence=0.1, language="en", source="pattern",
                   latency_ms=5, reasoning="nothing matched")
        out = format_intent_card(i)
        assert "Couldn't classify" in out

    def test_with_command(self):
        i = Intent(command="/weather", args=["Cairo"], confidence=0.9,
                   language="en", source="pattern", latency_ms=4,
                   reasoning="matched /weather pattern")
        out = format_intent_card(i)
        assert "/weather" in out
        assert "Cairo" in out
        assert "0.90" in out

    def test_with_secondary(self):
        primary = Intent(command="/weather", args=["Cairo"], confidence=0.9)
        primary.secondary = [
            Intent(command="/search", args=["weather Cairo"], confidence=0.4),
        ]
        out = format_intent_card(primary)
        assert "Also considered" in out
        assert "/search" in out
