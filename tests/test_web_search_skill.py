"""
Tests for skills/web_search_skill.py.

Unit tests mock the provider SDKs and the network. No real API calls.
The "live" tests for Tavily/Serper/DDG are skipped without keys.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "web_search_skill.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "web_search_skill_under_test", str(SKILL_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["web_search_skill_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_skill()
search = mod.search
format_results = mod.format_results
WebSearchError = mod.WebSearchError
PROVIDERS = mod.PROVIDERS


# ----------------------------------------------------------------------
# Provider selection
# ----------------------------------------------------------------------
class TestProviderSelection:
    def test_providers_list(self):
        assert "tavily" in PROVIDERS
        assert "serper" in PROVIDERS
        assert "duckduckgo" in PROVIDERS

    def test_explicit_unknown_provider(self, monkeypatch):
        with pytest.raises(WebSearchError, match="Unknown provider"):
            search("hello", provider="bogus")

    def test_explicit_provider_honoured(self, monkeypatch):
        # Even with no env keys, "duckduckgo" should be tried.
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        with patch.object(mod, "_search_duckduckgo",
                          return_value={"query": "x", "provider": "duckduckgo",
                                        "results": [], "answer": None}) as m:
            search("hello", provider="duckduckgo")
        m.assert_called_once()

    def test_auto_prefers_tavily(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        with patch.object(mod, "_search_tavily",
                          return_value={"query": "x", "provider": "tavily",
                                        "results": [], "answer": None}) as m:
            search("x", provider="auto")
        m.assert_called_once()

    def test_auto_falls_back_to_serper(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.setenv("SERPER_API_KEY", "serper-test")
        with patch.object(mod, "_search_serper",
                          return_value={"query": "x", "provider": "serper",
                                        "results": [], "answer": None}) as m:
            search("x", provider="auto")
        m.assert_called_once()

    def test_auto_falls_back_to_ddg(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        with patch.object(mod, "_search_duckduckgo",
                          return_value={"query": "x", "provider": "duckduckgo",
                                        "results": [], "answer": None}) as m:
            search("x", provider="auto")
        m.assert_called_once()


# ----------------------------------------------------------------------
# Argument validation
# ----------------------------------------------------------------------
class TestArguments:
    def test_empty_query(self):
        with pytest.raises(WebSearchError, match="Empty query"):
            search("   ")

    def test_limit_too_low(self):
        with pytest.raises(WebSearchError, match="limit must be"):
            search("x", limit=0)

    def test_limit_too_high(self):
        with pytest.raises(WebSearchError, match="limit must be"):
            search("x", limit=999)


# ----------------------------------------------------------------------
# Tavily
# ----------------------------------------------------------------------
class TestTavily:
    def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with pytest.raises(WebSearchError, match="TAVILY_API_KEY not set"):
            mod._search_tavily("x", 5, 5.0)

    def test_unauthorized(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-bad")
        # Force ImportError path by ensuring `tavily` is not actually
        # available, then patch _search_tavily to raise.
        # Easier: directly call with a fake client.
        # We mock the SDK at the importlib level.
        fake_tavily = MagicMock()
        fake_tavily.TavilyClient.return_value.search.side_effect = Exception("401 Unauthorized")
        with patch.dict(sys.modules, {"tavily": fake_tavily}):
            with pytest.raises(WebSearchError, match="invalid or revoked"):
                mod._search_tavily("x", 5, 5.0)

    def test_success(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        fake_tavily = MagicMock()
        fake_tavily.TavilyClient.return_value.search.return_value = {
            "results": [
                {"title": "A", "url": "https://a", "content": "snippet A"},
                {"title": "B", "url": "https://b", "content": "snippet B"},
            ],
        }
        with patch.dict(sys.modules, {"tavily": fake_tavily}):
            out = mod._search_tavily("hello", 5, 5.0)
        assert out["provider"] == "tavily"
        assert len(out["results"]) == 2
        assert out["results"][0]["title"] == "A"


# ----------------------------------------------------------------------
# Serper
# ----------------------------------------------------------------------
class TestSerper:
    def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        with pytest.raises(WebSearchError, match="SERPER_API_KEY not set"):
            mod._search_serper("x", 5, 5.0)


# ----------------------------------------------------------------------
# DuckDuckGo (no key)
# ----------------------------------------------------------------------
class TestDuckDuckGo:
    def test_success(self, monkeypatch):
        # Stub urlopen to return canned HTML.
        sample_html = (
            '<html><body>'
            '<a class="result__a" href="https://example.com/?q=foo">Example Title</a>'
            '<a class="result__snippet">Example snippet text.</a>'
            '<a class="result__a" href="https://other.com/path">Other Title</a>'
            '<a class="result__snippet">Other snippet text.</a>'
            '</body></html>'
        )

        class FakeResp:
            def __init__(self, body):
                self.body = body.encode("utf-8")
            def read(self):
                return self.body
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with patch.object(mod.urllib.request, "urlopen",
                          return_value=FakeResp(sample_html)):
            out = mod._search_duckduckgo("test", 5, 5.0)
        assert out["provider"] == "duckduckgo"
        assert len(out["results"]) == 2
        assert "Example Title" in out["results"][0]["title"]
        assert "example.com" in out["results"][0]["url"]

    def test_no_results_raises(self, monkeypatch):
        class FakeResp:
            def read(self):
                return b"<html><body>no results</body></html>"
            def __enter__(self): return self
            def __exit__(self, *a): pass
        with patch.object(mod.urllib.request, "urlopen",
                          return_value=FakeResp()):
            with pytest.raises(WebSearchError, match="no results"):
                mod._search_duckduckgo("zzz", 5, 5.0)


# ----------------------------------------------------------------------
# Format helper
# ----------------------------------------------------------------------
class TestFormatResults:
    def test_empty_results(self):
        out = format_results({"provider": "tavily", "query": "x",
                              "results": [], "elapsed": 0.1})
        assert "No results" in out

    def test_with_results(self):
        out = format_results({
            "provider": "tavily",
            "query": "AI agents",
            "results": [
                {"title": "First", "url": "https://a", "snippet": "snip A"},
                {"title": "Second", "url": "https://b", "snippet": "snip B"},
            ],
            "elapsed": 0.4,
        })
        assert "AI agents" in out
        assert "First" in out
        assert "https://a" in out
        assert "tavily" in out
        assert "0.4s" in out

    def test_truncation(self):
        # 30 long results — should truncate.
        results = [
            {"title": f"Title {i}", "url": f"https://x{i}", "snippet": "x" * 50}
            for i in range(30)
        ]
        out = format_results(
            {"provider": "tavily", "query": "q", "results": results, "elapsed": 0.1},
            max_chars=400,
        )
        assert "more result" in out

    def test_escapes_markdown(self):
        out = format_results({
            "provider": "tavily",
            "query": "q",
            "results": [
                {"title": "Has *star* and _under_", "url": "https://x", "snippet": ""},
            ],
            "elapsed": 0.1,
        })
        # The Markdown-sensitive chars should be escaped.
        assert "\\*star\\*" in out
        assert "\\_under\\_" in out


# ----------------------------------------------------------------------
# Live integration (skipped without keys)
# ----------------------------------------------------------------------
@pytest.mark.skipif(
    not (os.getenv("TAVILY_API_KEY") or os.getenv("SERPER_API_KEY")),
    reason="No search API key set",
)
def test_live_search_real_call():
    """Smoke test: one real call against the configured provider."""
    out = search("Mavis AI agent", limit=2, timeout=15.0)
    assert out["provider"] in ("tavily", "serper")
    assert isinstance(out["results"], list)
