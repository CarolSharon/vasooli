"""Generate non-sensitive Twilio fallback recordings using macOS speech."""

import subprocess
import tempfile
import wave
from pathlib import Path

import lameenc

MESSAGES = {
    "service-unavailable": "Namaste. Our payment assistant is temporarily unavailable. We will contact you later. Please do not share your OTP, PIN, CVV, or password with anyone.",
    "payment-confirmed": "Thank you. Your payment is already confirmed. No further action is needed.",
    "human-transfer-unavailable": "Our support team is currently unavailable. A team member will contact you during business hours.",
}
OUTPUT = Path(__file__).resolve().parents[1] / "backend/app/static/audio"


def generate(name: str, message: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        aiff = Path(directory) / "speech.aiff"
        wav = Path(directory) / "speech.wav"
        subprocess.run(["say", "-o", aiff, message], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", aiff, wav], check=True)
        with wave.open(str(wav), "rb") as source:
            encoder = lameenc.Encoder()
            encoder.set_bit_rate(64)
            encoder.set_in_sample_rate(source.getframerate())
            encoder.set_channels(source.getnchannels())
            encoder.set_quality(2)
            encoded = encoder.encode(source.readframes(source.getnframes())) + encoder.flush()
        (OUTPUT / f"{name}.mp3").write_bytes(encoded)


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, text in MESSAGES.items():
        generate(filename, text)
