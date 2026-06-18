"""ElevenLabs text-to-speech — generates hyper-realistic voice audio for calls."""
import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)


def generate_audio(text: str, voice_id: str = None) -> bytes | None:
    """Generate MP3 audio from text using ElevenLabs. Returns None if unavailable."""
    if not settings.ELEVENLABS_API_KEY:
        return None

    vid = voice_id or settings.ELEVENLABS_VOICE_ID
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"

    try:
        resp = httpx.post(
            url,
            headers={
                "xi-api-key": settings.ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "text": text[:4000],
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.80,
                    "style": 0.30,
                    "use_speaker_boost": True,
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.error(f"ElevenLabs TTS error: {e}")
        return None
