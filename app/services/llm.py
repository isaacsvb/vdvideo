"""LLM service: generate a video script and stock-footage search terms.

Pluggable across providers (OpenAI, Gemini) behind a single `generate_script`
entry point selected by config.
"""
from __future__ import annotations

import json
import re

from loguru import logger

from app.config import get_settings
from app.models import ScriptResult, VideoParams

_SCRIPT_SYSTEM_PROMPT = """You are a professional short-form video scriptwriter.
Write a punchy, engaging voiceover script for a social-media short (TikTok / YouTube Shorts).
Rules:
- No markdown, no headings, no speaker labels, no scene directions, no emojis.
- Just the spoken narration as plain sentences.
- Hook the viewer in the first sentence.
"""


def _build_user_prompt(params: VideoParams) -> str:
    return (
        f"Topic: {params.topic}\n"
        f"Language: {params.language}\n"
        f"Write about {params.paragraphs} short sentences, suitable for a video "
        f"of at most {params.max_duration} seconds when read aloud.\n"
        "Return ONLY the narration text."
    )


def _terms_prompt(script: str, topic: str) -> str:
    return (
        "Based on the following video narration, produce 5 to 8 English search "
        "terms for finding relevant stock b-roll video clips. Each term should be "
        "1-3 words, concrete and visual.\n"
        'Return ONLY a JSON array of strings, e.g. ["city at night", "ocean waves"].\n\n'
        f"Topic: {topic}\n\nNarration:\n{script}"
    )


def _clean_script(text: str) -> str:
    text = re.sub(r"[*#`>]", "", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text


def _parse_terms(raw: str, fallback_topic: str) -> list[str]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            terms = json.loads(match.group(0))
            terms = [str(t).strip() for t in terms if str(t).strip()]
            if terms:
                return terms[:8]
        except json.JSONDecodeError:
            logger.warning("Could not parse search terms JSON; falling back")
    return [fallback_topic]


# --------------------------------------------------------------------------- #
# Provider back-ends
# --------------------------------------------------------------------------- #
def _openai_complete(prompt: str, system: str) -> str:
    from openai import OpenAI

    cfg = get_settings().llm.openai
    if not cfg.api_key:
        raise RuntimeError("OpenAI API key is not configured (set OPENAI_API_KEY or config.toml).")
    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url or None)
    resp = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.9,
    )
    return resp.choices[0].message.content or ""


def _gemini_complete(prompt: str, system: str) -> str:
    import google.generativeai as genai

    cfg = get_settings().llm.gemini
    if not cfg.api_key:
        raise RuntimeError("Gemini API key is not configured (set GEMINI_API_KEY or config.toml).")
    genai.configure(api_key=cfg.api_key)
    model = genai.GenerativeModel(cfg.model, system_instruction=system)
    resp = model.generate_content(prompt)
    return resp.text or ""


def _complete(prompt: str, system: str) -> str:
    provider = get_settings().llm.provider.lower()
    logger.debug(f"LLM provider = {provider}")
    if provider == "openai":
        return _openai_complete(prompt, system)
    if provider == "gemini":
        return _gemini_complete(prompt, system)
    raise ValueError(f"Unknown LLM provider: {provider!r}")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def generate_script(params: VideoParams) -> ScriptResult:
    """Generate the narration script and stock-footage search terms."""
    logger.info(f"Generating script for topic: {params.topic!r}")
    raw_script = _complete(_build_user_prompt(params), _SCRIPT_SYSTEM_PROMPT)
    script = _clean_script(raw_script)
    if not script:
        raise RuntimeError("LLM returned an empty script.")

    raw_terms = _complete(_terms_prompt(script, params.topic), "You output only JSON.")
    terms = _parse_terms(raw_terms, params.topic)
    logger.info(f"Script ok ({len(script)} chars); search terms: {terms}")
    return ScriptResult(script=script, search_terms=terms)
