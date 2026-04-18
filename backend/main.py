"""
main.py  –  FastAPI backend for dual-subtitle generator
==========================================================

Endpoints
---------
POST /api/process-video          Upload video + languages → {job_id}
GET  /api/status/{job_id}        SSE stream of progress events
GET  /api/video/{job_id}         Stream original video for in-browser playback
GET  /api/download/srt/{job_id}/{which}   Download primary.srt or secondary.srt
GET  /api/download/video/{job_id}         Download video with burned-in subtitles

SSE event shapes
----------------
  {"type":"stage",    "key":"prepare",   "label":"…", "progress":40, "eta":"0:22"}
  {"type":"progress", "overall":55,      "eta":"1:10"}
  {"type":"complete", "subtitles":[…],   "primarySrt":"…", "secondarySrt":"…"}
  {"type":"error",    "message":"…"}
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import uuid
from pathlib import Path
from queue import Empty, Queue
from shutil import copyfileobj
from tempfile import mkdtemp
from threading import Thread
from typing import Any, Optional

# Load .env file if present (OPENAI_API_KEY etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY")

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from json import dumps, loads

import language_codes
import pipeline
from language_codes import LANGUAGE_TO_NLLB, SUPPORTED_LANGUAGES, WHISPER_TO_NLLB
from pipeline import (
    _download_url_to_file,
    build_srt,
    burn_subtitles,
    check_ffmpeg,
    extract_audio,
    segments_to_frontend,
    transcribe_audio,
    translate_segments,
)

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(title="Dual Subtitle API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory job store ────────────────────────────────────────────────────────

jobs: dict[str, dict[str, Any]] = {}

# ── Stage metadata ─────────────────────────────────────────────────────────────

STAGE_LABELS: dict[str, str] = {
    "prepare":             "Prepare media",
    "transcribe":          "Transcribe audio",
    "translate_primary":   "Translate subtitle 1",
    "translate_secondary": "Translate subtitle 2",
    "write_srt":           "Write SRT files",
    "finalize":            "Finalize output",
}

# Weights determine how much of the overall progress bar each stage occupies.
STAGE_WEIGHTS: dict[str, int] = {
    "prepare":             5,
    "transcribe":          35,
    "translate_primary":   25,
    "translate_secondary": 25,
    "write_srt":           5,
    "finalize":            5,
}

STAGE_ORDER = list(STAGE_LABELS.keys())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _eta_string(seconds: float) -> str:
    """Convert remaining-seconds estimate to 'M:SS' string."""
    if seconds <= 0:
        return "0:00"
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


def _put(queue: Queue, event: dict) -> None:
    queue.put(dumps(event))


# ── Pipeline thread ────────────────────────────────────────────────────────────

def _pipeline_thread(
    job_id: str,
    primary_lang: str,
    secondary_lang: str,
    whisper_model: str,
) -> None:
    """All heavy work happens here, off the async event loop."""
    job = jobs[job_id]
    q: Queue = job["queue"]

    # ── Stage helpers ──────────────────────────────────────────────────────────

    def stage_start(key: str) -> None:
        _put(q, {
            "type":     "stage",
            "key":      key,
            "label":    STAGE_LABELS[key],
            "status":   "active",
            "progress": 0,
            "overall":  sum(
                STAGE_WEIGHTS[k]
                for k in STAGE_ORDER[:STAGE_ORDER.index(key)]
            ),
        })

    def stage_progress(key: str, done: int, total: int, label: str) -> None:
        pct = int(done / total * 100) if total else 0
        contribution = int(pct / 100 * STAGE_WEIGHTS[key])
        base = sum(
            STAGE_WEIGHTS[k]
            for k in STAGE_ORDER[:STAGE_ORDER.index(key)]
        )
        _put(q, {
            "type":     "stage",
            "key":      key,
            "label":    label,
            "status":   "active",
            "progress": pct,
            "overall":  base + contribution,
        })

    def stage_done(key: str) -> None:
        base = sum(
            STAGE_WEIGHTS[k]
            for k in STAGE_ORDER[: STAGE_ORDER.index(key) + 1]
        )
        _put(q, {
            "type":     "stage",
            "key":      key,
            "label":    STAGE_LABELS[key],
            "status":   "done",
            "progress": 100,
            "overall":  base,
        })

    # ── Pipeline execution ─────────────────────────────────────────────────────

    try:
        wdir: str = job["workdir"]

        # 1 · Prepare ──────────────────────────────────────────────────────────
        stage_start("prepare")

        if job.get("video_url"):
            _put(q, {"type": "stage", "key": "prepare", "label": "Downloading video…",
                     "status": "active", "progress": 0, "overall": 0})
            dl_path = os.path.join(wdir, "input.mp4")
            _download_url_to_file(job["video_url"], dl_path)
            job["video_path"] = dl_path

        audio_path = os.path.join(wdir, "audio.wav")
        extract_audio(job["video_path"], audio_path)
        stage_done("prepare")

        # 2 · Transcribe ───────────────────────────────────────────────────────
        stage_start("transcribe")

        def transcribe_cb(done: int, total: int, label: str) -> None:
            stage_progress("transcribe", done, total, label)

        segments, detected_iso = transcribe_audio(
            audio_path,
            model_size=whisper_model,
            progress_cb=transcribe_cb,
            language=job.get("source_language"),
        )
        stage_done("transcribe")

        # Resolve source NLLB code from Whisper's detected ISO language
        source_nllb: str = WHISPER_TO_NLLB.get(detected_iso, "eng_Latn")

        # 3 · Translate primary ────────────────────────────────────────────────
        stage_start("translate_primary")
        primary_nllb: str = LANGUAGE_TO_NLLB[primary_lang]

        def primary_cb(done: int, total: int, label: str) -> None:
            stage_progress("translate_primary", done, total, label)

        primary_segments = translate_segments(
            segments,
            source_nllb=source_nllb,
            target_nllb=primary_nllb,
            progress_cb=primary_cb,
            openai_api_key=OPENAI_API_KEY,
        )
        stage_done("translate_primary")

        # 4 · Translate secondary ──────────────────────────────────────────────
        stage_start("translate_secondary")
        secondary_nllb: str = LANGUAGE_TO_NLLB[secondary_lang]

        def secondary_cb(done: int, total: int, label: str) -> None:
            stage_progress("translate_secondary", done, total, label)

        secondary_segments = translate_segments(
            segments,
            source_nllb=source_nllb,
            target_nllb=secondary_nllb,
            progress_cb=secondary_cb,
            openai_api_key=OPENAI_API_KEY,
        )
        stage_done("translate_secondary")

        # 5 · Write SRT files ──────────────────────────────────────────────────
        stage_start("write_srt")

        primary_srt_path   = os.path.join(wdir, "primary.srt")
        secondary_srt_path = os.path.join(wdir, "secondary.srt")

        with open(primary_srt_path,   "w", encoding="utf-8") as f:
            f.write(build_srt(primary_segments))
        with open(secondary_srt_path, "w", encoding="utf-8") as f:
            f.write(build_srt(secondary_segments))

        job["primary_srt"]  = primary_srt_path
        job["secondary_srt"] = secondary_srt_path
        stage_done("write_srt")

        # 6 · Finalize ─────────────────────────────────────────────────────────
        stage_start("finalize")

        frontend_subs   = segments_to_frontend(segments, primary_segments, secondary_segments)
        primary_srt_text   = open(primary_srt_path,   encoding="utf-8").read()
        secondary_srt_text = open(secondary_srt_path, encoding="utf-8").read()

        job["subtitles"] = frontend_subs
        stage_done("finalize")

        _put(q, {
            "type":         "complete",
            "subtitles":    frontend_subs,
            "primarySrt":   primary_srt_text,
            "secondarySrt": secondary_srt_text,
        })

    except Exception as exc:
        tb = traceback.format_exc()
        print(f"\n[JOB {job_id}] PIPELINE ERROR:\n{tb}\n")
        _put(q, {"type": "error", "message": str(exc)})

    finally:
        q.put(None)  # sentinel – closes the SSE stream


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/api/languages")
async def get_languages():
    return {"languages": SUPPORTED_LANGUAGES}


@app.get("/api/health")
async def health_check():
    """
    Returns the status of all required dependencies.
    Open http://localhost:8000/api/health in your browser to diagnose issues.
    """
    checks: dict[str, str] = {}

    # FFmpeg
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if r.returncode != 0:
            checks["ffmpeg"] = f"MISSING – {r.stderr[:120]}"
        else:
            checks["ffmpeg"] = f"ok (version: {r.stdout.splitlines()[0]})"
    except Exception as e:
        checks["ffmpeg"] = f"MISSING – {e}"

    # Whisper
    try:
        import whisper
        checks["whisper"] = f"ok (version: {getattr(whisper, '__version__', 'unknown')})"
    except ImportError as e:
        checks["whisper"] = f"MISSING – {e}"

    # Transformers + torch
    try:
        import transformers
        import torch
        checks["transformers"] = (
            f"ok (version: {transformers.__version__}"
            f", CUDA: {torch.cuda.is_available()})"
        )
    except ImportError as e:
        checks["transformers"] = f"MISSING – {e}"

    all_ok = all(v.startswith("ok") for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "translation": "gpt-4o-mini" if OPENAI_API_KEY else "nllb-200-local",
    }


@app.get("/api/debug/{job_id}")
async def debug_job(job_id: str):
    """Returns the current state of a job including any error details."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id":    job_id,
        "primary_srt":  job.get("primary_srt"),
        "workdir":   job.get("workdir"),
        "subtitles": job.get("subtitles"),
    }


@app.post("/api/process-video")
async def process_video(
    background_tasks: BackgroundTasks,
    video:            Optional[UploadFile] = File(None),
    videoUrl:         Optional[str]        = Form(None),
    primaryLanguage:  str                  = Form("English"),
    secondaryLanguage: str                 = Form("Chinese"),
    whisperModel:     str                  = Form("base"),
    sourceLanguage:   Optional[str]        = Form(None),
):
    """
    Accept either an uploaded video file OR a videoUrl string, spin off
    the pipeline in a background thread, and return a job_id.
    """
    if not video and not videoUrl:
        raise HTTPException(status_code=400, detail="Provide either a video file or a videoUrl.")
    if primaryLanguage not in LANGUAGE_TO_NLLB:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {primaryLanguage}")
    if secondaryLanguage not in LANGUAGE_TO_NLLB:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {secondaryLanguage}")

    job_id  = str(uuid.uuid4())
    workdir = mkdtemp(prefix="dualsub_")

    job: dict[str, Any] = {
        "workdir":        workdir,
        "queue":          Queue(),
        "subtitles":      None,
        "primary_srt":    None,
        "secondary_srt":  None,
        "source_language": sourceLanguage,
    }

    if video:
        ext        = Path(video.filename).suffix or ".mp4"
        video_path = os.path.join(workdir, f"video{ext}")
        with open(video_path, "wb") as f:
            copyfileobj(video.file, f)
        job["video_path"] = video_path
    else:
        job["video_url"] = videoUrl

    jobs[job_id] = job

    thread = Thread(
        target=_pipeline_thread,
        args=(job_id, primaryLanguage, secondaryLanguage, whisperModel),
        daemon=True,
    )
    thread.start()

    return {"jobId": job_id, "message": "Processing started"}


@app.get("/api/status/{job_id}")
async def stream_status(job_id: str):
    """
    Server-Sent Events stream.  Each event is a JSON line.
    Stays open until the pipeline thread pushes None (sentinel).
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    q: Queue = job["queue"]

    async def event_generator():
        while True:
            try:
                item = q.get_nowait()
            except Empty:
                await asyncio.sleep(0.25)
                continue

            if item is None:
                yield 'data: {"type":"closed"}\n\n'
                break

            try:
                parsed = loads(item)
            except Exception:
                parsed = {"type": "raw", "data": item}

            yield f"data: {dumps(parsed)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection":    "keep-alive",
        },
    )


@app.get("/api/video/{job_id}")
async def serve_video(job_id: str, request: Request):
    """
    Stream the original video for in-browser playback with full Range request
    support. Browsers require 206 Partial Content responses to seek/scrub video.
    """
    job = jobs.get(job_id)
    if not job or not job.get("video_path"):
        raise HTTPException(status_code=404, detail="Job not found")

    video_path = job["video_path"]
    file_size  = os.path.getsize(video_path)

    range_header = request.headers.get("Range")

    if range_header:
        # Parse "bytes=start-end"
        range_val  = range_header.strip().replace("bytes=", "")
        parts      = range_val.split("-")
        start      = int(parts[0])
        end        = int(parts[1]) if parts[1] else file_size - 1
        end        = min(end, file_size - 1)
        chunk_size = end - start + 1

        def iter_file():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range":  f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges":  "bytes",
                "Content-Length": str(chunk_size),
            },
        )
    else:
        # No Range header — send the whole file
        def iter_full():
            with open(video_path, "rb") as f:
                while True:
                    data = f.read(65536)
                    if not data:
                        break
                    yield data

        return StreamingResponse(
            iter_full(),
            status_code=200,
            media_type="video/mp4",
            headers={
                "Accept-Ranges":  "bytes",
                "Content-Length": str(file_size),
            },
        )


@app.get("/api/download/srt/{job_id}/{which}")
async def download_srt(job_id: str, which: str):
    """
    Download primary.srt or secondary.srt.
    *which* must be 'primary' or 'secondary'.
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if which == "primary":
        path     = job.get("primary_srt")
        filename = "primary.srt"
    elif which == "secondary":
        path     = job.get("secondary_srt")
        filename = "secondary.srt"
    else:
        raise HTTPException(status_code=400, detail="which must be 'primary' or 'secondary'")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="SRT not ready yet")
    return FileResponse(path, media_type="text/plain", filename=filename)


@app.get("/api/download/video/{job_id}")
async def download_burned_video(job_id: str):
    """
    Burns subtitles into the video (if not already done) and returns the file.
    This may take a while for long videos – the client should show a spinner.
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.get("subtitles"):
        raise HTTPException(status_code=400, detail="Processing not complete yet")

    workdir     = job["workdir"]
    burned_path = os.path.join(workdir, "output_burned.mp4")

    if not os.path.exists(burned_path):
        burn_subtitles(
            video_path=job["video_path"],
            primary_srt_path=job["primary_srt"],
            secondary_srt_path=job["secondary_srt"],
            output_path=burned_path,
        )

    return FileResponse(
        burned_path,
        media_type="video/mp4",
        filename="dual_subtitles.mp4",
    )


@app.delete("/api/job/{job_id}")
async def cleanup_job(job_id: str):
    """Remove job files and record from memory."""
    job = jobs.pop(job_id, None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    workdir = job.get("workdir")
    if workdir and os.path.exists(workdir):
        shutil.rmtree(workdir, ignore_errors=True)
    return {"status": "deleted"}
