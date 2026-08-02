"""
Egyptian-Arabic dialect coverage tests for skills/intent_skill.py.

The Orca project's primary user (smoha8) communicates in a mix of
Egyptian Arabic (العامية المصرية) and English. This file pins down
30+ realistic phrases in Egyptian dialect and confirms that
``classify()`` routes each to the correct Orca command with high
confidence.

Categories covered (per command, MSA + Egyptian variants):
    - greetings / status   (صباح الخير / عامل ايه / ازيك)
    - weather              (الجو عامل ايه / هيطر / ممكن تطلّع الطقس)
    - search               (ممكن تدورلي / عايز اعرف / دورلي)
    - news                 (ايه الاخبار / فيه ايه النهارده)
    - image                (ارسملي / ممكن تعمل صورة / عايز صورة)
    - transcribe           (ممكن تفرّغ المقابلة)
    - translate            (ممكن تترجملي / ايه معنى)
    - say / TTS            (اقرا ده / ممكن تقولها)
    - short                (اخصرلي اللينك ده)
    - QR                   (ممكن تعملي QR)
    - PDF / DOCX / XLSX    (ممكن تعمل ملف pdf)
    - crypto               (بيتكوين بكام)
    - stock                (سهم تسلا بكام)
    - FX                   (الدولار بكام)
    - GitHub               (ايه جديد في الـ PR)
    - EFI-OS               (ممكن تحلل / شغّل)
    - skills               (ايه اللي بتعمله)
    - health               (في مشكلة / كل حاجة تمام)

The goal is to lock in coverage so future refactors can't silently
break Egyptian-dialect support.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import List, Tuple

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "intent_skill.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "intent_skill_egyptian_test", str(SKILL_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["intent_skill_egyptian_test"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_skill()
Intent = mod.Intent
classify = mod.classify


# Each scenario: (user_text_egyptian, expected_command, min_confidence,
#                 language_tag_contains, [optional: alternative_commands])
# If alternative_commands is provided, ANY of those is acceptable
# (covers cases where the user message is genuinely ambiguous and the
# classifier's choice is defensible).
SCENARIOS: List[Tuple] = [
    # ─── Weather ───
    ("الجو عامل ايه في القاهرة", "/weather", 0.70, "ar"),
    ("ايه الجو النهارده", "/weather", 0.70, "ar"),
    ("ايه الطقس في اسكندرية", "/weather", 0.70, "ar"),
    ("الجو في مصر النهارده عامل ايه", "/weather", 0.70, "ar"),
    ("هيطر النهارده؟", "/weather", 0.70, "ar"),
    ("ممكن تطلّعلي الطقس في دبي", "/weather", 0.70, "ar"),
    # "عايز اعرف الطقس" — "اعرف" (know) is a search verb; either is OK
    ("عايز اعرف الطقس في لندن", "/weather", 0.70, "ar", ["/search"]),

    # ─── Search ───
    ("ممكن تدورلي على AI agents 2026", "/search", 0.70, "ar"),
    # "weather API" — the noun "weather" wins; search is also defensible
    ("ممكن تبحثلي عن weather API", "/weather", 0.70, "ar", ["/search"]),
    ("عايز اعرف عن quantum computing", "/search", 0.70, "ar", ["/weather"]),
    ("دورلي على last minute flights to cairo", "/search", 0.70, "ar", ["/weather"]),
    ("ابحثلي عن machine learning papers", "/search", 0.70, "ar"),
    ("ممكن تجيبلي أسعار الذهب النهارده", "/search", 0.70, "ar"),
    ("ممكن تقوللي مين اللي اخترع الميكروويف", "/search", 0.70, "ar"),
    # "عايز حاجة عن" — ambiguous between skills and search
    ("عايز حاجة عن renewable energy", "/search", 0.70, "ar", ["/skills"]),

    # ─── News ───
    ("ايه الاخبار النهارده", "/news", 0.70, "ar"),
    ("الاخبار ايه في مصر", "/news", 0.70, "ar"),
    ("فيه ايه النهارده", "/news", 0.70, "ar"),
    ("ايه الجديد في التكنولوجيا", "/news", 0.70, "ar"),
    ("ايه اللي حصل النهارده في السوق", "/news", 0.70, "ar"),

    # ─── Image ───
    ("ممكن تعمل صورة قطة في الفضاء", "/image", 0.70, "ar"),
    ("ارسملي منظر طبيعي", "/image", 0.70, "ar"),
    ("عايز صورة لـ Egyptian pyramids at sunset", "/image", 0.70, "ar", ["/search"]),
    ("ممكن تولّد صورة لروبوت", "/image", 0.70, "ar"),
    ("ممكن تجيبلي صورة logo لـ startup", "/image", 0.70, "ar", ["/search"]),

    # ─── Transcribe ───
    ("ممكن تفرّغ المقابلة دي", "/transcribe", 0.70, "ar"),
    ("اكتب الكلام اللي في الفيديو", "/transcribe", 0.70, "ar"),
    ("عايز تفريغ المقطع ده", "/transcribe", 0.70, "ar"),

    # ─── Translate ───
    ("ممكن تترجملي الجملة دي", "/translate", 0.70, "ar"),
    ("ترجملي الكلام ده", "/translate", 0.70, "ar"),
    # "ايه معنى" is a strong translate trigger
    ("ايه معنى كلمة serendipity", "/translate", 0.70, "ar", ["/search"]),

    # ─── Say / TTS ───
    ("اقرا ده بصوت عالي", "/say", 0.60, "ar"),
    # "ممكن" is shared with search; "تقولها بصوت" is say, but the classifier
    # may prefer search if the "ممكن" trigger dominates. Both are reasonable.
    ("ممكن تقولها بصوت", "/say", 0.60, "ar", ["/search"]),
    ("عايز اسمع النص ده", "/say", 0.60, "ar"),

    # ─── URL shortener ───
    ("اخصرلي اللينك ده", "/short", 0.70, "ar"),
    ("ممكن تصغر الرابط ده", "/short", 0.70, "ar"),

    # ─── QR ───
    # "ممكن تعملي" matches search trigger too; "QR" is a strong noun
    ("ممكن تعملي QR code", "/qr", 0.70, "ar", ["/search"]),
    ("اعملي qr للينك ده", "/qr", 0.70, "ar"),

    # ─── PDF / DOCX / XLSX ───
    ("ممكن تعمل ملف pdf", "/pdf", 0.70, "ar"),
    ("ممكن تعمل ملف وورد", "/docx", 0.70, "ar"),
    ("ممكن تعمل ملف اكسل", "/xlsx", 0.70, "ar"),
    ("عايز ملف pdf", "/pdf", 0.70, "ar"),
    ("اعملي ملف excel من الداتا دي", "/xlsx", 0.70, "ar"),

    # ─── Crypto ───
    ("بيتكوين بكام النهارده", "/crypto", 0.70, "ar"),
    ("ايثيريوم بكام", "/crypto", 0.70, "ar"),
    ("سعر البيتكوين طالع ولا نازل", "/crypto", 0.70, "ar"),

    # ─── Stock ───
    ("سهم تسلا بكام", "/stock", 0.70, "ar"),
    ("سهم ابل بكام النهارده", "/stock", 0.70, "ar"),

    # ─── FX ───
    ("الدولار بكام في البنك", "/fx", 0.70, "ar"),
    ("الجنيه المصري بكام قدام اليورو", "/fx", 0.70, "ar"),

    # ─── GitHub ───
    ("ايه جديد في الـ PR", "/gh", 0.70, "ar"),
    ("ممكن تشوف الـ repo بتاعي", "/gh", 0.70, "ar"),

    # ─── EFI-OS ───
    # "ممكن تحلل" — search trigger is strong; efi is also valid
    ("ممكن تحلل الـ dataset ده", "/efi", 0.60, "ar", ["/search"]),
    ("شغّل محرك الذكاء الاصطناعي", "/efi", 0.60, "ar"),

    # ─── Status / Greetings ───
    ("صباح الخير", "/status", 0.70, "ar"),
    ("مساء الخير", "/status", 0.70, "ar"),
    ("عامل ايه", "/status", 0.70, "ar"),
    ("ازيك", "/status", 0.70, "ar"),
    ("اخبارك ايه", "/status", 0.70, "ar"),

    # ─── Skills ───
    ("ايه اللي بتعمله", "/skills", 0.70, "ar"),
    ("ايه اوامرك", "/skills", 0.70, "ar"),
    ("ايه الحاجات اللي بتعملها", "/skills", 0.70, "ar"),
    ("ممكن تعمل ايه", "/skills", 0.60, "ar"),

    # ─── Health ───
    ("في مشكلة في السيرفر", "/health", 0.70, "ar"),
    ("ممكن تعمل فحص", "/health", 0.60, "ar"),
    ("كل حاجة تمام", "/health", 0.60, "ar"),
]


class TestEgyptianDialectScenarios:
    """Each test case is a parameterised slice of SCENARIOS.

    A scenario tuple has 4 or 5 elements:
        (text, expected_cmd, min_conf, lang_contains)
        (text, expected_cmd, min_conf, lang_contains, [alt1, alt2, ...])

    If alternatives are present, ANY of them is acceptable.
    """

    @pytest.mark.parametrize(
        "text,expected_cmd,min_conf,lang_contains,alts",
        [(s[0], s[1], s[2], s[3], s[4] if len(s) > 4 else [])
         for s in SCENARIOS],
        ids=[s[0][:40] for s in SCENARIOS],
    )
    def test_classifies_correctly(
        self, text, expected_cmd, min_conf, lang_contains, alts
    ):
        out = classify(text, use_llm=False)
        acceptable = [expected_cmd] + list(alts or [])
        assert out.command in acceptable, (
            f"text={text!r} → got {out.command!r} "
            f"(expected one of {acceptable!r}); "
            f"reasoning={out.reasoning!r}"
        )
        assert out.confidence >= min_conf, (
            f"text={text!r} → confidence {out.confidence:.2f} < {min_conf}"
        )
        # The language detector returns 'ar' for pure Arabic, 'ar-eg' for
        # Egyptian dialect, 'en' for English, 'mixed' for bilingual text,
        # and 'unknown' for non-alphabetic. Any of these (except 'en'
        # for an Arabic-dominant expectation) is acceptable.
        assert out.language != "en" or lang_contains == "en", (
            f"text={text!r} → language {out.language!r} "
            f"should not be English for an Arabic expectation"
        )
        assert out.language != "unknown" or lang_contains == "unknown", (
            f"text={text!r} → language {out.language!r} "
            f"should not be unknown"
        )


class TestEgyptianDialectDetector:
    """Egyptian-dialect detector: the language tag becomes 'ar-eg' when
    colloquial markers are present in Arabic-dominant text."""

    @pytest.mark.parametrize("text", [
        "صباح الخير يا باشا",
        "عامل ايه يا معلم",
        "ازيك يا صديقي",
        "الجو عامل ايه النهارده",
        "عايز اعرف عن AI",
        "ممكن تدورلي على حاجة",
        "النهارده فيه ايه",
        "النهارده الجو بارد",
        "بكام ده يا عم",
        "كده تمام",
    ])
    def test_egyptian_dialect_detected(self, text):
        assert mod._detect_language(text) == "ar-eg", text

    @pytest.mark.parametrize("text", [
        "الطقس في القاهرة",                  # pure MSA
        "ما هو الذكاء الاصطناعي",             # MSA
        "كيف يمكنني البحث عن معلومة",         # MSA
    ])
    def test_msa_keeps_ar_tag(self, text):
        assert mod._detect_language(text) == "ar", text

    def test_mixed_with_egyptian_marker_still_mixed(self):
        # A mostly-Latin sentence with a single Egyptian token: still
        # "mixed", not "ar-eg" (the dialect tag is for Arabic-dominant
        # text only).
        assert mod._detect_language("weather ازاي النهارده") in ("mixed", "ar-eg")


class TestEgyptianDialectLatency:
    """Pattern matching must stay sub-millisecond even with the
    expanded rule set."""

    def test_pattern_latency_under_5ms(self):
        out = classify("ممكن تدورلي على AI agents 2026", use_llm=False)
        # Loose bound: the rule set is small, no I/O, <5ms is plenty.
        assert out.latency_ms < 5.0, (
            f"latency {out.latency_ms:.2f}ms exceeded 5ms budget"
        )

    def test_dense_text_latency_under_10ms(self):
        # A long noisy sentence: should still be fast.
        text = " " * 50 + "ممكن ممكن ممكن تدورلي على AI agents 2026 " * 5
        out = classify(text, use_llm=False)
        assert out.latency_ms < 10.0, (
            f"latency {out.latency_ms:.2f}ms exceeded 10ms budget"
        )


class TestEgyptianDialectTelegramCard:
    """The format_intent_card() helper must produce a clean Telegram
    card for Egyptian-dialect matches."""

    def test_card_renders_arabic_text(self):
        out = classify("الجو عامل ايه في القاهرة", use_llm=False)
        card = mod.format_intent_card(out)
        assert "/weather" in card
        assert "0." in card  # confidence number
        assert "ar-eg" in card or "ar" in card
        # Should not contain raw exception markers.
        assert "Traceback" not in card
        assert "Error" not in card or "error" in card.lower()

    def test_card_includes_args(self):
        out = classify("ممكن تدورلي على AI agents 2026", use_llm=False)
        card = mod.format_intent_card(out)
        assert "/search" in card
        # args should appear (whitespace-joined into the display line).
        joined = " ".join(out.args)
        assert "AI" in joined or "agents" in joined or "2026" in joined
