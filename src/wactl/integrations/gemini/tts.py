"""Text-to-speech via Gemini TTS.

Returns raw audio bytes (WAV). Callers decide what to do with them —
typically upload to S3 and send via WhatsApp audio message.
"""

from __future__ import annotations

import asyncio

from google import genai
from google.genai import types as genai_types

from wactl.exceptions import ExternalAPIError


async def synthesize(
    text: str,
    *,
    voice: str = "en-US-Journey-D",
    api_key: str,
    model: str = "gemini-2.0-flash",
) -> bytes:
    """Synthesize ``text`` with the given voice and return WAV bytes."""
    if not text.strip():
        raise ValueError("text must be non-empty")

    client = genai.Client(api_key=api_key)

    def _call() -> bytes:
        resp = client.models.generate_content(
            model=model,
            contents=text,
            config=genai_types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=genai_types.SpeechConfig(
                    voice_config=genai_types.VoiceConfig(
                        prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                            voice_name=voice,
                        )
                    )
                ),
            ),
        )
        # resp.candidates[0].content.parts[0].inline_data.data is the bytes
        candidates = getattr(resp, "candidates", None)
        if not candidates:
            raise ExternalAPIError("Gemini TTS returned no candidates")
        parts = getattr(candidates[0].content, "parts", None)
        if not parts:
            raise ExternalAPIError("Gemini TTS returned no parts")
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return bytes(inline.data)
        raise ExternalAPIError("Gemini TTS response had no audio data")

    try:
        return await asyncio.to_thread(_call)
    except ExternalAPIError:
        raise
    except Exception as exc:
        raise ExternalAPIError(
            f"Gemini TTS failed: {exc}",
            retryable=True,
        ) from exc


__all__ = ["synthesize"]


# Helper used by the audiobook service — splits text into chunks small
# enough to feed to Gemini TTS without exceeding its input limit.
def split_into_chunks(text: str, *, max_chars: int) -> list[str]:
    """Split ``text`` into chunks of at most ``max_chars`` characters.

    Splits prefer paragraph, then sentence, then word boundaries. If a
    single word exceeds ``max_chars``, it is included as its own chunk
    (better to over-send than to lose content).
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    for paragraph in text.split("\n\n"):
        if not paragraph.strip():
            continue
        if len(paragraph) <= max_chars:
            chunks.append(paragraph.strip())
            continue
        # Split by sentences.
        current = ""
        for sentence in paragraph.replace("\n", " ").split(". "):
            piece = sentence.strip()
            if not piece:
                continue
            if not piece.endswith("."):
                piece += "."
            if len(current) + len(piece) + 1 > max_chars:
                if current:
                    chunks.append(current.strip())
                current = piece
            else:
                current = f"{current} {piece}".strip()
        if current:
            chunks.append(current.strip())
    return chunks
