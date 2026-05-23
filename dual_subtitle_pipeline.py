import argparse
import subprocess
import sys
import re
from pathlib import Path
from typing import Dict, List

# ============================================================
# Language registry (data-driven, extensible)
# ============================================================

LANGUAGE_REGISTRY: Dict[str, Dict] = {
    "ja": {
        "name": "Japanese",
        "scripts": ["hiragana", "katakana", "kanji"],
    },
    "zh": {
        "name": "Chinese",
        "scripts": ["han"],
    },
    "en": {
        "name": "English",
        "scripts": ["latin"],
    },
    # Add more languages here later — no logic changes needed
}

# ------------------------------------------------------------
# Unicode ranges per script
# ------------------------------------------------------------

SCRIPT_RANGES = {
    "hiragana": (0x3040, 0x309F),
    "katakana": (0x30A0, 0x30FF),
    "kanji": (0x4E00, 0x9FFF),
    "han": (0x4E00, 0x9FFF),
    "latin": (0x0041, 0x007A),
}

# ============================================================
# Utility helpers
# ============================================================

def fail(message: str):
    print(f"\n❌ ERROR: {message}\n", file=sys.stderr)
    sys.exit(1)

def run(cmd: List[str], label: str):
    print(f"\n▶ {label}")
    print("  " + " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        fail(f"Command failed during step: {label}")

def char_in_script(ch: str, script: str) -> bool:
    if script not in SCRIPT_RANGES:
        return False
    start, end = SCRIPT_RANGES[script]
    return start <= ord(ch) <= end

# ============================================================
# FFmpeg: extract clean audio
# ============================================================

def extract_audio(video: Path, audio_out: Path):
    run(
        [
            "ffmpeg",
            "-y",
            "-i", str(video),
            "-map", "0:a:0",
            "-ac", "1",
            "-ar", "16000",
            str(audio_out),
        ],
        "Extracting mono 16 kHz audio"
    )

# ============================================================
# Whisper: forced transcription (NO translation)
# ============================================================

def run_whisper(audio: Path, output_dir: Path, native_lang: str):
    run(
        [
            sys.executable,
            "-m", "whisper",
            str(audio),
            "--model", "medium",
            "--language", native_lang,
            "--task", "transcribe",
            "--output_format", "srt",
            "--no_condition_on_previous_text",
            "--output_dir", str(output_dir),
        ],
        "Running Whisper transcription"
    )

# ============================================================
# Subtitle loading & cleanup
# ============================================================

def load_srt_text(srt_path: Path) -> str:
    if not srt_path.exists():
        fail("Expected SRT file was not produced by Whisper")

    raw = srt_path.read_text(encoding="utf-8", errors="ignore")

    # Remove cue numbers and timestamps
    raw = re.sub(r"\d+\n\d\d:\d\d:\d\d.*?\n", "", raw)

    return raw.strip()

# ============================================================
# Language verification
# ============================================================

def verify_language(text: str, expected_lang: str):
    if expected_lang not in LANGUAGE_REGISTRY:
        fail(f"Unsupported language code: {expected_lang}")

    scripts = LANGUAGE_REGISTRY[expected_lang]["scripts"]

    total_chars = 0
    matching_chars = 0

    for ch in text:
        if ch.isspace():
            continue

        total_chars += 1
        for script in scripts:
            if char_in_script(ch, script):
                matching_chars += 1
                break

    if total_chars == 0:
        fail("Transcript is empty after parsing")

    ratio = matching_chars / total_chars
    print(f"🔎 Language match ratio: {ratio:.2f}")

    # Conservative threshold to prevent silent translation
    if ratio < 0.50:
        fail(
            f"Transcript language mismatch.\n"
            f"Expected: {LANGUAGE_REGISTRY[expected_lang]['name']}\n"
            f"Match ratio: {ratio:.2f}"
        )

# ============================================================
# Main pipeline
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Phase‑1 dual subtitle pipeline (native transcription only)"
    )
    parser.add_argument("--video", required=True, help="Input video file")
    parser.add_argument("--native", required=True, help="Native language code (e.g., ja)")
    args = parser.parse_args()

    if args.native not in LANGUAGE_REGISTRY:
        fail(f"Unsupported language: {args.native}")

    video = Path(args.video).resolve()
    if not video.exists():
        fail("Input video file does not exist")

    work_dir = Path("work")
    work_dir.mkdir(exist_ok=True)

    audio_path = work_dir / "audio.wav"
    srt_path = work_dir / "audio.srt"

    print("\n===================================")
    print(" Phase‑1: Native Transcription")
    print("===================================\n")

    extract_audio(video, audio_path)
    run_whisper(audio_path, work_dir, args.native)

    text = load_srt_text(srt_path)
    verify_language(text, args.native)

    print("\n✅ SUCCESS")
    print(f"Native subtitle verified: {srt_path.resolve()}")

if __name__ == "__main__":
    main()