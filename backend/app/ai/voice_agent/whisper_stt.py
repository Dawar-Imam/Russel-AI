"""
OpenRouter Whisper STT adapter for livekit-agents 1.x.

Architecture:
  OpenRouterWhisperSTT implements STT._recognize_impl (batch/non-streaming).
  Wrap with livekit.agents.stt.StreamAdapter(stt=..., vad=silero_vad) to make it
  compatible with AgentSession's streaming STT slot.

  StreamAdapter uses Silero VAD to detect end-of-speech, buffers the full utterance,
  then calls _recognize_impl with the merged AudioFrame. No rolling windows or
  overlap dedup needed — VAD gives us clean, complete utterances.
"""

import asyncio
import io
import logging
import uuid
import wave

import httpx
import numpy as np
from livekit import rtc
from livekit.agents import stt, utils

_logger = logging.getLogger("russel.whisper_stt")

OPENROUTER_TRANSCRIPTIONS_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
TARGET_SAMPLE_RATE = 16_000
DEFAULT_MODEL = "openai/whisper-large-v3-turbo"


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def to_single_frame(buffer: rtc.AudioFrame | list[rtc.AudioFrame]) -> rtc.AudioFrame:
    """Normalize AudioBuffer (single frame or list) to one merged AudioFrame."""
    if isinstance(buffer, list):
        return utils.combine_frames(buffer)
    return buffer


def frame_to_wav(frame: rtc.AudioFrame) -> bytes:
    """
    Convert an AudioFrame (PCM 16-bit LE) to 16 kHz mono WAV bytes.

    Steps:
      1. Interpret raw bytes as int16 samples.
      2. Mix down to mono if multi-channel.
      3. Resample to 16 kHz via linear interpolation.
      4. Encode as WAV.
    """
    pcm = bytes(frame.data)
    sr = frame.sample_rate
    ch = frame.num_channels

    samples = np.frombuffer(pcm, dtype=np.int16).copy()

    # --- mono mix ---
    if ch > 1:
        samples = samples.reshape(-1, ch).mean(axis=1).astype(np.int16)

    # --- resample ---
    if sr != TARGET_SAMPLE_RATE:
        src_len = len(samples)
        dst_len = int(src_len * TARGET_SAMPLE_RATE / sr)
        if dst_len < 1:
            dst_len = 1
        indices = np.linspace(0, src_len - 1, dst_len)
        samples = np.interp(indices, np.arange(src_len), samples.astype(np.float32)).astype(np.int16)

    # --- WAV encode ---
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_SAMPLE_RATE)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def strip_overlap(prev: str, current: str, max_words: int = 15) -> str:
    """
    Remove leading words from `current` that duplicate trailing words of `prev`.

    Used when rolling-window overlap causes the start of a new transcript to
    repeat the end of the previous one. Not needed in VAD-triggered mode (where
    utterances are clean), but kept as a utility for tests.
    """
    if not prev or not current:
        return current
    prev_words = prev.split()
    curr_words = current.split()
    check = min(len(prev_words), len(curr_words), max_words)
    for n in range(check, 0, -1):
        if prev_words[-n:] == curr_words[:n]:
            trimmed = " ".join(curr_words[n:]).strip()
            return trimmed
    return current


# ---------------------------------------------------------------------------
# OpenRouter Whisper STT implementation
# ---------------------------------------------------------------------------

class OpenRouterWhisperSTT(stt.STT):
    """
    Non-streaming (batch) STT that sends a complete AudioFrame to OpenRouter Whisper.

    Use with livekit.agents.stt.StreamAdapter to make it streaming-capable:
        whisper = OpenRouterWhisperSTT(api_key=...)
        stream_stt = stt.StreamAdapter(stt=whisper, vad=silero_vad)
        AgentSession(stt=stream_stt, ...)
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_MODEL,
        fallback_deepgram_key: str | None = None,
    ) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=False,
                interim_results=False,
            )
        )
        self._api_key = api_key
        self._model = model
        self._fallback_deepgram_key = fallback_deepgram_key

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "openrouter"

    async def _recognize_impl(
        self,
        buffer: rtc.AudioFrame | list[rtc.AudioFrame],
        *,
        language=None,
        conn_options=None,
    ) -> stt.SpeechEvent:
        frame = to_single_frame(buffer)
        wav_data = frame_to_wav(frame)

        transcript = await self._call_openrouter(wav_data)

        if transcript is None:
            try:
                transcript = await self._fallback_deepgram(frame)
            except Exception as exc:
                _logger.error("Fallback deepgram raised: %s", exc)
                transcript = ""

        text = transcript.strip() if transcript else ""
        _logger.info("Whisper transcript (%d chars): %r", len(text), text[:80])

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            request_id=str(uuid.uuid4()),
            alternatives=(
                [stt.SpeechData(language="en", text=text, confidence=1.0)]
                if text
                else []
            ),
        )

    async def _call_openrouter(self, wav_data: bytes) -> str | None:
        """POST wav_data to OpenRouter Whisper. Retries once on failure."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(2):
                try:
                    resp = await client.post(
                        OPENROUTER_TRANSCRIPTIONS_URL,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        files={"file": ("audio.wav", wav_data, "audio/wav")},
                        data={"model": self._model},
                    )
                    resp.raise_for_status()
                    text = resp.json().get("text", "").strip()
                    _logger.debug("OpenRouter raw response: %r", text[:120])
                    return text
                except httpx.HTTPStatusError as exc:
                    _logger.warning(
                        "OpenRouter HTTP error (attempt %d/%d): %s — %s",
                        attempt + 1, 2, exc.response.status_code, exc.response.text[:200],
                    )
                except Exception as exc:
                    _logger.warning("OpenRouter error (attempt %d/%d): %s", attempt + 1, 2, exc)

                if attempt == 0:
                    await asyncio.sleep(0.5)

        _logger.error("OpenRouter Whisper failed after 2 attempts — falling back")
        return None

    async def _fallback_deepgram(self, frame: rtc.AudioFrame) -> str:
        """Use Deepgram nova-3 as fallback when OpenRouter is unavailable."""
        if not self._fallback_deepgram_key:
            _logger.warning("No Deepgram fallback key — returning empty transcript")
            return ""
        try:
            from livekit.plugins import deepgram
            dg_stt = deepgram.STT(model="nova-3", api_key=self._fallback_deepgram_key)
            event = await dg_stt.recognize(buffer=frame)
            if event.alternatives:
                text = event.alternatives[0].text
                _logger.info("Deepgram fallback succeeded: %r", text[:80])
                return text
        except Exception as exc:
            _logger.error("Deepgram fallback also failed: %s", exc)
        return ""
