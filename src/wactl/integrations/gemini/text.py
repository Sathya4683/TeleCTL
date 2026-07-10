"""High-level text helpers built on top of :class:`GeminiClient`."""

from __future__ import annotations

from wactl.integrations.gemini.client import GeminiClient

SYSTEM_SUMMARIZER = (
    "You are a concise summarizer. Produce a clear, bullet-pointed summary "
    "of the user's content. No preamble, no apologies, no closing remarks. "
    "Keep it short — under 400 words."
)

SYSTEM_TRANSLATOR = (
    "You are a professional translator. Translate the user's content into "
    "the target language. Preserve tone, names, and technical terms. Output "
    "only the translation — no commentary."
)

LANGUAGE_NAME = {
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese (Simplified)",
    "hi": "Hindi",
    "ta": "Tamil",
    "ar": "Arabic",
    "ru": "Russian",
}


async def summarize(client: GeminiClient, text: str, *, max_words: int = 400) -> str:
    """Summarize ``text`` using Gemini. Returns markdown bullet points."""
    prompt = (
        f"Summarize the following content in under {max_words} words. "
        "Use bullet points. Preserve links and key facts.\n\n"
        f"---\n{text}\n---"
    )
    return await client.generate_text(
        prompt,
        system_instruction=SYSTEM_SUMMARIZER,
        temperature=0.2,
        max_output_tokens=min(2048, max_words * 3),
    )


async def translate(
    client: GeminiClient,
    text: str,
    *,
    target_language: str,
) -> str:
    """Translate ``text`` to ``target_language`` (ISO code or name)."""
    if not target_language:
        raise ValueError("target_language is required")
    pretty = LANGUAGE_NAME.get(target_language.lower(), target_language)
    prompt = (
        f"Translate the following content into {pretty}. Preserve Markdown "
        "formatting if present.\n\n"
        f"---\n{text}\n---"
    )
    return await client.generate_text(
        prompt,
        system_instruction=SYSTEM_TRANSLATOR,
        temperature=0.2,
    )


async def summarize_github_pr(
    client: GeminiClient,
    *,
    title: str,
    body: str,
    diff: str,
    additions: int,
    deletions: int,
    changed_files: int,
    max_words: int = 350,
) -> str:
    """Summarize a GitHub PR — title, description, and a (truncated) diff."""
    diff_excerpt = diff if len(diff) <= 6000 else diff[:6000] + "\n... (truncated)"
    prompt = (
        f"PR Title: {title}\n"
        f"Description:\n{body or '(none)'}\n\n"
        f"Stats: +{additions}/-{deletions} across {changed_files} files\n\n"
        "Unified diff (may be truncated):\n"
        f"```\n{diff_excerpt}\n```\n\n"
        f"Summarize this PR in under {max_words} words. "
        "Highlight: what the PR does, key implementation choices, and any "
        "obvious risks or test gaps."
    )
    return await client.generate_text(
        prompt,
        system_instruction=SYSTEM_SUMMARIZER,
        temperature=0.2,
        max_output_tokens=min(2048, max_words * 3),
    )


__all__ = [
    "LANGUAGE_NAME",
    "summarize",
    "summarize_github_pr",
    "translate",
]


# Whitespace stripper used after Gemini calls to clean up.
def _clean(text: str) -> str:  # pragma: no cover
    return text.strip()
