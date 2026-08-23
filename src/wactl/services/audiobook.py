"""Multi-step PDF → audio pipeline for :class:`wactl.commands.pdf_audio.PdfAudioCommand`.

The pipeline:
1. Extract text from the PDF (page by page).
2. Split text into Gemini-TTS-sized chunks.
3. Synthesize each chunk to WAV via Gemini TTS in parallel.
4. Concatenate the WAV chunks into a single audio clip.

The function returns the final ``bytes`` (audio) — the caller (the worker)
uploads to S3 and replies to the user via Telegram.

TTS is slow (2-10 s per chunk), so we fan out with :mod:`asyncio.gather`
to keep wall-clock latency roughly equal to one chunk's runtime.
"""

from __future__ import annotations

import asyncio
import io
import wave

from wactl.exceptions import ConverterError
from wactl.integrations.converters import pdf_text
from wactl.integrations.gemini import tts

#: Default chunk size (~2000 chars ≈ 30s of speech). Tuned to keep
#: individual TTS calls under ~10s. Override via ``chunk_chars`` if needed.
DEFAULT_CHUNK_CHARS = 2000


async def synthesize(
    pdf_bytes: bytes,
    *,
    api_key: str,
    voice: str = "en-US-Journey-D",
    model: str = "gemini-2.0-flash",
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    max_chunks: int = 80,
) -> bytes:
    """Run the PDF→text→chunks→audio→merge pipeline. Returns MP3 bytes.

    Raises :class:`wactl.exceptions.UserInputError` for empty / unreadable
    PDFs and :class:`ConverterError` for downstream pipeline failures.
    """
    text = pdf_text.extract_text(pdf_bytes)
    if not text:
        raise ConverterError("PDF contains no extractable text")

    chunks = tts.split_into_chunks(text, max_chars=chunk_chars)
    if not chunks:
        raise ConverterError("Text could not be chunked for TTS")
    if len(chunks) > max_chunks:
        # Pathological case — refuse rather than burn API budget.
        raise ConverterError(
            f"Audiobook would require {len(chunks)} chunks (max {max_chunks}); try a shorter document",
        )

    # Fan out TTS calls in parallel; limit concurrency so a long book
    # doesn't open dozens of sockets at once.
    semaphore = asyncio.Semaphore(4)

    async def _one(chunk: str) -> bytes:
        async with semaphore:
            return await tts.synthesize(
                chunk,
                voice=voice,
                api_key=api_key,
                model=model,
            )

    audios = await asyncio.gather(*(_one(c) for c in chunks))

    return _concat_wavs_to_mp3(audios)


def _concat_wavs_to_mp3(wav_blobs: list[bytes]) -> bytes:
    """Concatenate a list of WAV files into a single MP3.

    MP3 because WAVs produced by TTS are typically 16-bit PCM mono at the
    model-default sample rate; MP3 keeps the upload under Telegram's
    50 MB outbound limit for most document lengths.
    """
    try:
        # Stitch raw PCM frames without re-decoding whenever possible.
        nchannels, sampwidth, framerate, _nframes, _comptype, _compname = _wav_params(
            wav_blobs[0],
        )
        combined = bytearray()
        for blob in wav_blobs:
            n_ch, s_w, fr, _nf, _ct, _cn = _wav_params(blob)
            if n_ch != nchannels or s_w != sampwidth or fr != framerate:
                # Fall back to pydub decode if streams disagree.
                return _concat_via_pydub(wav_blobs)
            with wave.open(io.BytesIO(blob), "rb") as r:
                combined.extend(r.readframes(r.getnframes()))
        stitched_wav = io.BytesIO()
        with wave.open(stitched_wav, "wb") as w:
            w.setnchannels(nchannels)
            w.setsampwidth(sampwidth)
            w.setframerate(framerate)
            w.writeframes(bytes(combined))
        stitched_wav.seek(0)
        # Lazy import: pydub fails to import on Python 3.12 due to an
        # upstream regex issue. Defer until actually needed.
        from pydub import AudioSegment  # type: ignore[import-untyped]  # noqa: PLC0415

        audio = AudioSegment.from_wav(stitched_wav)
        out = io.BytesIO()
        audio.export(out, format="mp3", bitrate="128k")
        return out.getvalue()
    except ConverterError:
        raise
    except Exception as exc:
        raise ConverterError(f"Audiobook merge failed: {exc}") from exc


def _wav_params(blob: bytes) -> tuple[int, int, int, int, str, str]:
    """Return ``(nchannels, sampwidth, framerate, nframes, comptype, compname)``.

    Reads the params inside a ``with`` block so the underlying file is
    closed before we hand the values back to the caller.
    """
    try:
        with wave.open(io.BytesIO(blob), "rb") as r:
            p = r.getparams()
            return (p.nchannels, p.sampwidth, p.framerate, p.nframes, p.comptype, p.compname)
    except (wave.Error, EOFError) as exc:
        raise ConverterError(f"Invalid WAV from TTS: {exc}") from exc


def _concat_via_pydub(wav_blobs: list[bytes]) -> bytes:
    """Slow path: decode each WAV with pydub, concatenate, export MP3."""
    # Lazy import — pydub has a Python 3.12 incompatibility at module load.
    from pydub import AudioSegment  # noqa: PLC0415  # type: ignore[import-untyped]

    segments = [AudioSegment.from_wav(io.BytesIO(b)) for b in wav_blobs]
    combined = segments[0]
    for s in segments[1:]:
        combined += s
    out = io.BytesIO()
    combined.export(out, format="mp3", bitrate="128k")
    return out.getvalue()


__all__ = ["DEFAULT_CHUNK_CHARS", "synthesize"]
