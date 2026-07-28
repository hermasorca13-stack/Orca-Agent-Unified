# AUTOORCA MASTER INTELLIGENCE HUB v2.0 - Python Integration
# Integrated from AutoOrca_Master_Hub-1.jsx

AUTOORCA_CONFIG = {
    "CLAUDE": {
        "models": ["Haiku 4.5", "Sonnet 4.6", "Opus 4.6", "Opus 4.7"],
        "values": ["Broadly safe", "Broadly ethical", "Anthropic principles", "Genuinely helpful"]
    },
    "MINIMAX_MAVIS": {
        "persona": "Energetic, warm Gen-Z coworker",
        "skills": ["deep-research", "docx", "lark-tools", "pdf", "plan-mode", "pptx", "skill-creator", "team", "visual-page", "worktree-management", "xlsx"]
    },
    "KIMI_K2": {
        "models": ["kimi-k2.5", "kimi-k2.6", "kimi-k2.7", "kimi-k2.7-code", "Kimi-K2-Instruct"],
        "api_base": "https://api.moonshot.ai/v1"
    },
    "AUTOORCA_SYSTEM": {
        "total_bots": 23,
        "master_ledger": "86capke4g",
        "binding_directive": "No hard-coding to single provider. Support Anthropic/OpenAI/Gemini/local/custom."
    }
}

SYSTEM_INSTRUCTION = """
You are the AutoOrca Master Intelligence System.
Operational brain for Mohamed's 23-bot civil engineering AI office.
Ground truth rule: Always check ClickUp task content + attachment metadata.
Zero% repetition — every skill/pattern passes cleanly to the next.
"""
