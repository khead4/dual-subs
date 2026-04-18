"""
pipeline.py
-----------
End-to-end processing pipeline for dual-subtitle generation.

Order of operations
-------------------
1. extract_audio   – FFmpeg strips audio to 16 kHz WAV
2. transcribe      – Whisper produces timed segments + detects source language
3. translate x2    – NLLB-200 translates every segment into both target languages
4. build_srt       – Produces SRT content from any segment list
5. burn_subtitles  – (optional) FFmpeg burns both SRT tracks into the video
"""

from __future__ import annotations

import subprocess
import os
import textwrap
from pathlib import Path
from typing import Callable, Generator

# Type aliases
Segment = dict
ProgressCb = Callable[[int, int, str], None]


# ── FFmpeg check ───────────────────────────────────────────────────────────────

def check_ffmpeg() -> None:
    """Raise RuntimeError with a clear message if FFmpeg is not on PATH."""
    result = subprocess.run(
        ["ffmpeg", "-version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg not found. Install it and make sure it is on your PATH.\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )


# ── Audio extraction ───────────────────────────────────────────────────────────

def extract_audio(video_path: str, audio_path: str) -> str:
    """
    Use FFmpeg to pull audio from *video_path*, re-sample to 16 kHz mono WAV,
    and write the result to *audio_path*.  Returns *audio_path* on success.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg audio extraction failed:\n{result.stderr[-1500:]}"
        )
    return audio_path


# ── Transcription ──────────────────────────────────────────────────────────────

def transcribe_audio(
    audio_path: str,
    model_size: str = "base",
    progress_cb: ProgressCb | None = None,
    language: str | None = None,
) -> tuple[list[Segment], str]:
    """
    Transcribe *audio_path* with Whisper.

    Returns (segments, detected_language_iso).
    Each segment: {id, start, end, text, language}
    """
    import whisper

    if progress_cb:
        progress_cb(0, 1, "Loading Whisper model…")

    model = whisper.load_model(model_size)

    if progress_cb:
        progress_cb(0, 1, "Transcribing audio…")

    result = model.transcribe(
        audio_path,
        verbose=False,
        word_timestamps=False,
        task="transcribe",
        fp16=False,
        language=language,   # None = auto-detect, or e.g. "japanese"
    )

    segments: list[Segment] = []
    for seg in result["segments"]:
        segments.append({
            "id":       seg["id"],
            "start":    round(seg["start"], 3),
            "end":      round(seg["end"],   3),
            "text":     seg["text"].strip(),
            "language": result["language"],
        })

    if progress_cb:
        progress_cb(1, 1, "Transcription complete")

    return segments, result["language"]


# ── Translation ────────────────────────────────────────────────────────────────

# NLLB language name map for GPT prompts
NLLB_TO_NAME: dict[str, str] = {
    "eng_Latn": "English",
    "zho_Hans": "Chinese (Simplified)",
    "zho_Hant": "Chinese (Traditional)",
    "jpn_Jpan": "Japanese",
    "kor_Hang": "Korean",
    "spa_Latn": "Spanish",
    "fra_Latn": "French",
    "deu_Latn": "German",
    "por_Latn": "Portuguese",
    "rus_Cyrl": "Russian",
    "arb_Arab": "Arabic",
    "hin_Deva": "Hindi",
    "swe_Latn": "Swedish",
    "fin_Latn": "Finnish",
    "dan_Latn": "Danish",
    "khk_Cyrl": "Mongolian",
    "ita_Latn": "Italian",
    "nld_Latn": "Dutch",
    "pol_Latn": "Polish",
    "tur_Latn": "Turkish",
    "vie_Latn": "Vietnamese",
    "tha_Thai": "Thai",
    "ind_Latn": "Indonesian",
}


def translate_segments_gpt(
    segments: list[Segment],
    source_nllb: str,
    target_nllb: str,
    api_key: str,
    batch_size: int = 40,
    progress_cb: ProgressCb | None = None,
) -> list[Segment]:
    """
    Translate segments using OpenAI GPT-4o-mini.
    Sends batches of subtitle lines with context so GPT can produce
    natural, consistent translations across the whole scene.
    """
    from openai import OpenAI

    client    = OpenAI(api_key=api_key)
    src_name  = NLLB_TO_NAME.get(source_nllb, source_nllb)
    tgt_name  = NLLB_TO_NAME.get(target_nllb, target_nllb)
    translated: list[Segment] = []

    for batch_start in range(0, len(segments), batch_size):
        batch = segments[batch_start : batch_start + batch_size]
        texts = [s["text"] for s in batch]

        numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))

        system_prompt = (
            f"You are a professional subtitle translator specialising in {src_name} to {tgt_name}. "
            f"Translate each numbered subtitle line from {src_name} to {tgt_name}. "
            "Rules:\n"
            "- Return ONLY the translated lines, numbered the same way\n"
            "- Keep the same line count — never merge or split lines\n"
            "- Preserve character names, sound effects (e.g. *sighs*), and ellipses\n"
            "- Use natural spoken language, not literal word-for-word translation\n"
            "- Keep translations concise — they must fit on screen as subtitles"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": numbered},
            ],
            temperature=0.3,
        )

        result_text = response.choices[0].message.content.strip()
        lines = result_text.split("\n")

        # Strip numbering (e.g. "1. ", "1) ")
        clean: list[str] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Remove leading "N." or "N)"
            import re
            line = re.sub(r"^\d+[.)]\s*", "", line)
            clean.append(line)

        # Pad or trim to match batch size
        while len(clean) < len(batch):
            clean.append(batch[len(clean)]["text"])
        clean = clean[: len(batch)]

        for seg, text in zip(batch, clean):
            translated.append({**seg, "text": text})

        if progress_cb:
            done = min(batch_start + batch_size, len(segments))
            progress_cb(done, len(segments), f"Translated {done}/{len(segments)} lines")

    return translated


def translate_segments(
    segments: list[Segment],
    source_nllb: str,
    target_nllb: str,
    batch_size: int = 8,
    progress_cb: ProgressCb | None = None,
    openai_api_key: str | None = None,
) -> list[Segment]:
    """
    Translate segments.  Uses GPT-4o-mini when an OpenAI API key is provided,
    otherwise falls back to the local NLLB-200 model.
    """
    if openai_api_key:
        return translate_segments_gpt(
            segments, source_nllb, target_nllb,
            api_key=openai_api_key,
            batch_size=40,
            progress_cb=progress_cb,
        )

    # ── Local NLLB fallback ────────────────────────────────────────────────────
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    MODEL_ID = "facebook/nllb-200-distilled-600M"

    if progress_cb:
        progress_cb(0, len(segments), "Loading NLLB-200 model…")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)
    model.eval()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)

    translated: list[Segment] = []

    for batch_start in range(0, len(segments), batch_size):
        batch = segments[batch_start : batch_start + batch_size]
        texts = [s["text"] for s in batch]

        tokenizer.src_lang = source_nllb
        inputs = tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        ).to(device)

        try:
            forced_bos = tokenizer.convert_tokens_to_ids(target_nllb)
            if forced_bos == tokenizer.unk_token_id:
                raise ValueError(
                    f"Language code '{target_nllb}' not found in NLLB tokenizer."
                )
        except AttributeError:
            if target_nllb not in tokenizer.lang_code_to_id:
                raise ValueError(
                    f"Language code '{target_nllb}' not found in NLLB tokenizer."
                )
            forced_bos = tokenizer.lang_code_to_id[target_nllb]

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                forced_bos_token_id=forced_bos,
                max_length=512,
            )

        decoded = tokenizer.batch_decode(output_ids, skip_special_tokens=True)

        for seg, text in zip(batch, decoded):
            translated.append({**seg, "text": text})

        if progress_cb:
            progress_cb(
                min(batch_start + batch_size, len(segments)),
                len(segments),
                f"Translated {min(batch_start + batch_size, len(segments))} segments",
            )

    return translated


# ── SRT helpers ────────────────────────────────────────────────────────────────

def _srt_timestamp(seconds: float) -> str:
    """Convert fractional seconds to SRT HH:MM:SS,mmm format."""
    ms  = int(round(seconds * 1000))
    h   = ms // 3_600_000;  ms %= 3_600_000
    m   = ms // 60_000;     ms %= 60_000
    s   = ms // 1_000;      ms %= 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(segments: list[Segment]) -> str:
    """
    Build a complete SRT string from *segments*.

    Lines are blank-line separated as per spec.
    """
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(seg['start'])} --> {_srt_timestamp(seg['end'])}")
        lines.append(seg["text"].strip())
        lines.append("")
    return "\n".join(lines)


# ── Subtitle burning ───────────────────────────────────────────────────────────

def burn_subtitles(
    video_path: str,
    primary_srt_path: str,
    secondary_srt_path: str,
    output_path: str,
    progress_cb: ProgressCb | None = None,
) -> str:
    """
    Burn two SRT subtitle tracks into *video_path* using FFmpeg's
    ``subtitles`` filter.  The primary track appears near the centre;
    the secondary track sits at the bottom.
    """
    if progress_cb:
        progress_cb(0, 1, "Burning subtitles with FFmpeg…")

    primary_style   = "FontSize=22,PrimaryColour=&H00FFFFFF,Outline=1,MarginV=62"
    secondary_style = "FontSize=20,PrimaryColour=&H00C8C8C8,Outline=1,MarginV=10"

    # Escape Windows-style paths for the FFmpeg filter string
    def _esc(p: str) -> str:
        return p.replace("\\", "/").replace(":", "\\:")

    vf = (
        f"subtitles='{_esc(primary_srt_path)}':force_style='{primary_style}',"
        f"subtitles='{_esc(secondary_srt_path)}':force_style='{secondary_style}'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("FFmpeg subtitle burn failed. Check ffmpeg is installed.")

    if progress_cb:
        progress_cb(1, 1, "Subtitle burn complete")

    return output_path


# ── Frontend helper ────────────────────────────────────────────────────────────

def segments_to_frontend(
    original:  list[Segment],
    primary:   list[Segment],
    secondary: list[Segment],
) -> list[dict]:
    """
    Zip three parallel segment lists into the shape the React player expects:
    [{start, end, primary, secondary}, …]
    """
    return [
        {
            "start":     orig["start"],
            "end":       orig["end"],
            "primary":   p["text"],
            "secondary": s["text"],
        }
        for orig, p, s in zip(original, primary, secondary)
    ]


# ── URL downloader ─────────────────────────────────────────────────────────────

def _download_url_to_file(url: str, dest_path: str) -> None:
    """
    Download a video from a URL.
    - Direct video links (.mp4/.mov/etc.) -> requests
    - Other platform links (YouTube, Vimeo, etc.) -> yt-dlp
    """
    import requests

    lower = url.lower()
    direct_exts = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv", ".wmv")

    if any(lower.split("?")[0].endswith(ext) for ext in direct_exts):
        try:
            resp = requests.get(
                url,
                stream=True,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=60,
            )
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        except Exception as exc:
            raise RuntimeError(f"Direct download failed: {exc}") from exc
    else:
        try:
            import yt_dlp
        except ImportError:
            raise RuntimeError(
                "yt-dlp is required to download from YouTube/Vimeo/etc.\n"
                "Install it with: pip install yt-dlp\n"
                "Or paste a direct .mp4/.mov URL instead."
            )

        ydl_opts = {
            "format":  "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best",
            "outtmpl": dest_path,
            "quiet":   True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as exc:
            raise RuntimeError(f"yt-dlp download failed: {exc}") from exc

    if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
        raise RuntimeError("Downloaded file is empty or missing.")
