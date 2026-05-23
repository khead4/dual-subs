from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .contracts import (
    ALLOW_DEMO_FALLBACK,
    FFMPEG_BINARY,
    LANGUAGES,
    ArtifactSummary,
    LanguageOption,
    TranslationJob,
    TranslationRequest,
)
from .providers import (
    installed_local_translation_languages,
    local_chinese_conversion_available,
    local_transcription_available,
    local_translation_available,
    openai_available,
)
from .pipeline import ARTIFACTS, JOBS, enqueue_request, find_ffmpeg_binary, process_request, should_process_inline


app = FastAPI(
    title="Dual Subtitle Studio API",
    version="0.2.0",
    description="Provider-backed dual-language timed subtitle translation and rendering API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

APP_ROOT = Path(__file__).resolve().parent.parent


def build_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@app.get("/api/health")
def healthcheck() -> dict:
    offline_transcription = local_transcription_available()
    offline_translation_languages = installed_local_translation_languages()
    offline_translation = local_translation_available() and bool(offline_translation_languages)
    cloud_provider = openai_available()
    subtitle_generation_ready = (offline_transcription or cloud_provider) and (offline_translation or cloud_provider)

    return {
        "status": "ok",
        "service": "dual-subtitle-studio",
        "openai_configured": cloud_provider,
        "ffmpeg_available": bool(find_ffmpeg_binary()),
        "demo_fallback_enabled": ALLOW_DEMO_FALLBACK,
        "offline_transcription_ready": offline_transcription,
        "offline_translation_ready": offline_translation,
        "offline_translation_languages": offline_translation_languages,
        "chinese_conversion_ready": local_chinese_conversion_available(),
        "subtitle_generation_ready": subtitle_generation_ready,
        "job_processing_mode": "inline" if should_process_inline() else "background",
    }


@app.get("/api/languages", response_model=List[LanguageOption])
def get_languages() -> List[LanguageOption]:
    return LANGUAGES


@app.post("/api/jobs", response_model=TranslationJob)
def create_job(request: Request, payload: TranslationRequest) -> TranslationJob:
    return process_request(
        base_url=build_base_url(request),
        request_payload=payload,
        media_bytes=None,
        subtitle_bytes=None,
    )


@app.post("/api/jobs/submit", response_model=TranslationJob)
async def submit_job(
    request: Request,
    metadata: str = Form(...),
    media_file: Optional[UploadFile] = File(default=None),
    subtitle_file: Optional[UploadFile] = File(default=None),
) -> TranslationJob:
    try:
        metadata_payload = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON.") from exc

    if media_file is not None and media_file.filename:
        metadata_payload["source_filename"] = media_file.filename
    if subtitle_file is not None and subtitle_file.filename:
        metadata_payload["subtitles_filename"] = subtitle_file.filename

    request_payload = TranslationRequest.model_validate(metadata_payload)
    media_bytes = await media_file.read() if media_file is not None else None
    subtitle_bytes = await subtitle_file.read() if subtitle_file is not None else None

    return enqueue_request(
        base_url=build_base_url(request),
        request_payload=request_payload,
        media_bytes=media_bytes,
        subtitle_bytes=subtitle_bytes,
    )


@app.get("/api/jobs/{job_id}", response_model=TranslationJob)
def get_job(job_id: str) -> TranslationJob:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/artifacts/{artifact_id}")
def get_artifact(artifact_id: str) -> Response:
    artifact = ARTIFACTS.get(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found.")

    return Response(
        content=artifact.payload,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{artifact.filename}"',
            "Content-Length": str(len(artifact.payload)),
        },
    )


@app.get("/favicon.ico")
def get_favicon() -> FileResponse:
    return FileResponse(APP_ROOT / "favicon.svg", media_type="image/svg+xml")


@app.get("/")
def get_index() -> FileResponse:
    return FileResponse(APP_ROOT / "index.html")


app.mount("/", StaticFiles(directory=APP_ROOT, html=True), name="static")
