from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from .contracts import (
    ALLOW_DEMO_FALLBACK,
    DEMO_SOURCE_LINES,
    FFMPEG_BINARY,
    SUPPORTED_DIRECT_TRANSCRIPTION_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    ArtifactSummary,
    Deliverable,
    JobStatus,
    MessageLevel,
    ProcessingMessage,
    Provider,
    RenderPlan,
    SourceKind,
    SubtitleLaneConfig,
    TranslationJob,
    TranslationRequest,
)
from .providers import (
    local_transcription_available,
    local_translation_available,
    make_message,
    openai_available,
    resolve_translations,
    transcribe_media_with_local_whisper,
    transcribe_media_with_openai,
)
from .subtitles import (
    build_dual_ass,
    build_srt_track,
    build_vtt_track,
    overlay_payload_for,
    parse_subtitle_bytes,
)


@dataclass
class ArtifactBlob:
    filename: str
    content_type: str
    payload: bytes


JOBS: Dict[str, TranslationJob] = {}
ARTIFACTS: Dict[str, ArtifactBlob] = {}
JOB_LOCK = threading.Lock()
WORK_ROOT = Path(__file__).resolve().parent.parent
LOCAL_TEMP_ROOT = Path(tempfile.gettempdir()) / "dual-subtitle-studio"
LOCAL_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def extension_for(filename: Optional[str]) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lower()


def find_ffmpeg_binary() -> Optional[str]:
    direct_binary = shutil.which(FFMPEG_BINARY)
    if direct_binary:
        return direct_binary

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def provider_notes_for(request_payload: TranslationRequest) -> List[str]:
    notes = []

    if request_payload.kind == SourceKind.external_link and request_payload.provider in {
        Provider.netflix,
        Provider.hulu,
        Provider.prime_video,
    }:
        notes.append(
            "Netflix, Hulu, and Prime links usually need a browser companion flow or user-provided subtitle/audio access because DRM blocks direct extraction."
        )

    if request_payload.output_mode.value == "burned_export":
        notes.append(
            "Burned-in export needs ffmpeg on the server or a separate media worker. This API will generate subtitle assets first."
        )

    return notes


def transcript_strategy_for(request_payload: TranslationRequest) -> str:
    if request_payload.kind == SourceKind.upload_subtitles:
        return "Reuse uploaded subtitle timing as the original cue source."
    if request_payload.kind == SourceKind.external_link:
        return "Extract public captions when possible, otherwise fetch or transcribe public media into timed cues."
    return "Transcribe uploaded media audio into timed subtitle cues in the original language."


def render_plan_for(request_payload: TranslationRequest) -> RenderPlan:
    merge_strategy = (
        "Burn translated subtitle lanes back into the exported video when a media renderer is available."
        if request_payload.output_mode.value == "burned_export"
        else "Attach dual subtitle lanes as a player overlay and downloadable subtitle package."
    )
    return RenderPlan(
        original_transcript_source=transcript_strategy_for(request_payload),
        merge_strategy=merge_strategy,
        safe_area_percent=request_payload.layout.safe_area_percent,
        lane_gap_px=request_payload.layout.track_gap_px,
        lanes=[
            SubtitleLaneConfig(lane="A", language=request_payload.target_languages[0], vertical_order=1),
            SubtitleLaneConfig(lane="B", language=request_payload.target_languages[1], vertical_order=2),
        ],
    )


def deliverables_for(request_payload: TranslationRequest) -> List[Deliverable]:
    items = [
        Deliverable(
            kind="timed_transcript",
            description="Normalized cue list with original-language timestamps and cue IDs.",
        ),
        Deliverable(
            kind="dual_subtitle_tracks",
            description="Two translated subtitle lanes bound to the same timing map.",
        ),
    ]

    if request_payload.output_mode.value == "stream_overlay":
        items.append(
            Deliverable(
                kind="stream_overlay",
                description="Browser-ready subtitle overlay payload for synchronized playback.",
            )
        )
    elif request_payload.output_mode.value == "subtitle_download":
        items.append(
            Deliverable(
                kind="subtitle_package",
                description="Downloadable subtitle outputs such as VTT, SRT, and ASS.",
            )
        )
    else:
        items.append(
            Deliverable(
                kind="video_export",
                description="A burned-in video export when a renderer and supported source media are available.",
            )
        )

    return items


def build_steps() -> List[str]:
    return [
        "source_received",
        "original_transcript_created",
        "subtitle_language_1_translated",
        "subtitle_language_2_translated",
        "dual_subtitles_attached",
        "video_output_prepared",
    ]


def create_job_record(job_id: str, request_payload: TranslationRequest) -> TranslationJob:
    return TranslationJob(
        job_id=job_id,
        status=JobStatus.queued,
        created_at=utc_now(),
        request=request_payload,
        progress_percent=0,
        current_step="Queued for processing",
        estimated_seconds_remaining=None,
        transcript_strategy=transcript_strategy_for(request_payload),
        render_plan=render_plan_for(request_payload),
        provider_notes=provider_notes_for(request_payload),
        steps=build_steps(),
        deliverables=deliverables_for(request_payload),
        messages=[],
        artifacts=[],
        cues=[],
    )


def store_job(job: TranslationJob) -> TranslationJob:
    with JOB_LOCK:
        JOBS[job.job_id] = job
    return job


def get_job_record(job_id: str) -> Optional[TranslationJob]:
    with JOB_LOCK:
        return JOBS.get(job_id)


def update_job_record(job_id: str, **changes) -> TranslationJob:
    with JOB_LOCK:
        job = JOBS[job_id]
        for key, value in changes.items():
            setattr(job, key, value)
        return job


def append_job_message(job_id: str, message: ProcessingMessage) -> None:
    with JOB_LOCK:
        JOBS[job_id].messages.append(message)


def extend_job_messages(job_id: str, messages: List[ProcessingMessage]) -> None:
    if not messages:
        return
    with JOB_LOCK:
        JOBS[job_id].messages.extend(messages)


def set_job_stage(
    job_id: str,
    *,
    status: JobStatus,
    progress_percent: int,
    current_step: str,
    estimated_seconds_remaining: Optional[int] = None,
) -> None:
    update_job_record(
        job_id,
        status=status,
        progress_percent=progress_percent,
        current_step=current_step,
        estimated_seconds_remaining=estimated_seconds_remaining,
    )


def create_artifact(base_url: str, kind: str, filename: str, content_type: str, payload: bytes) -> ArtifactSummary:
    artifact_id = f"artifact_{uuid4().hex[:12]}"
    with JOB_LOCK:
        ARTIFACTS[artifact_id] = ArtifactBlob(filename=filename, content_type=content_type, payload=payload)
    return ArtifactSummary(
        artifact_id=artifact_id,
        kind=kind,
        filename=filename,
        content_type=content_type,
        download_url=f"{base_url}/api/artifacts/{artifact_id}",
    )


def should_process_inline() -> bool:
    mode = os.getenv("JOB_PROCESSING_MODE", "").strip().lower()
    if mode in {"inline", "sync", "synchronous"}:
        return True
    if mode in {"background", "async", "thread"}:
        return False

    return bool(os.getenv("VERCEL"))


def fetch_public_subtitle_url(source_url: str) -> bytes:
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "DualSubtitleStudio/0.2"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fetch_public_media_url(source_url: str) -> bytes:
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "DualSubtitleStudio/0.2"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def build_demo_cues(request_payload: TranslationRequest):
    source_lines = DEMO_SOURCE_LINES.get(request_payload.original_language, DEMO_SOURCE_LINES["en"])
    cues = []
    for index, line in enumerate(source_lines, start=1):
        start_ms = (index - 1) * 4500
        end_ms = start_ms + 3800
        cues.append(
            {
                "cue_id": f"cue-{index:03d}",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "original_text": line,
                "translations": {},
            }
        )

    from .contracts import SubtitleCue

    return [SubtitleCue(**cue) for cue in cues]


def summarize_ffmpeg_detail(detail: str) -> str:
    lines = [line.strip() for line in detail.splitlines() if line.strip()]
    if not lines:
        return "ffmpeg did not return a readable error message."

    if "received signal 2" in detail.lower():
        return "Video rendering was interrupted before it finished. Keep the local server window open and run the app with start-local.bat so the export can complete."

    tail_lines = lines[-8:]
    return " ".join(tail_lines)


def probe_media_duration_seconds(ffmpeg_path: str, input_path: Path, temp_dir: Path) -> Optional[float]:
    probe = subprocess.run(
        [ffmpeg_path, "-i", input_path.name],
        capture_output=True,
        text=True,
        cwd=temp_dir,
        check=False,
    )
    detail = f"{probe.stdout}\n{probe.stderr}"
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", detail)
    if not match:
        return None

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def burn_subtitles_to_video(
    media_bytes: bytes,
    source_filename: str,
    ass_payload: bytes,
    progress_callback=None,
) -> Optional[bytes]:
    ffmpeg_path = find_ffmpeg_binary()
    if not ffmpeg_path:
        return None

    source_extension = extension_for(source_filename) or ".mp4"
    temp_dir = LOCAL_TEMP_ROOT / f"ffmpeg-{uuid4().hex[:10]}"
    temp_dir.mkdir(exist_ok=True)
    try:
        input_path = temp_dir / f"source{source_extension}"
        ass_path = temp_dir / "dual_subtitles.ass"
        output_path = temp_dir / "dual_subtitles_burned.mp4"
        input_path.write_bytes(media_bytes)
        ass_path.write_bytes(ass_payload)
        total_duration_seconds = probe_media_duration_seconds(ffmpeg_path, input_path, temp_dir)

        command = [
            ffmpeg_path,
            "-y",
            "-progress",
            "pipe:1",
            "-nostats",
            "-i",
            input_path.name,
            "-vf",
            f"ass={ass_path.name}",
            "-c:a",
            "copy",
            output_path.name,
        ]

        process = subprocess.Popen(
            command,
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        detail_lines: List[str] = []
        rendered_seconds = 0.0
        speed_multiplier = 1.0

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            detail_lines.append(line)
            detail_lines = detail_lines[-16:]

            if line.startswith("out_time_ms="):
                try:
                    rendered_seconds = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    rendered_seconds = rendered_seconds

                if progress_callback:
                    eta_seconds = None
                    if total_duration_seconds and speed_multiplier > 0:
                        remaining_media_seconds = max(total_duration_seconds - rendered_seconds, 0)
                        eta_seconds = int(remaining_media_seconds / speed_multiplier)
                    progress_callback(rendered_seconds, total_duration_seconds, eta_seconds)

            elif line.startswith("speed="):
                speed_text = line.split("=", 1)[1].rstrip("x")
                try:
                    speed_multiplier = float(speed_text)
                except ValueError:
                    speed_multiplier = speed_multiplier

        return_code = process.wait()
        if return_code != 0:
            detail = "\n".join(detail_lines)
            raise RuntimeError(f"ffmpeg could not attach the subtitles to the video. {summarize_ffmpeg_detail(detail)}")
        return output_path.read_bytes()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def resolve_source_cues(
    request_payload: TranslationRequest,
    *,
    media_bytes: Optional[bytes],
    subtitle_bytes: Optional[bytes],
    messages: List[ProcessingMessage],
):
    media_name = request_payload.source_filename or "media"

    if request_payload.kind == SourceKind.external_link:
        source_url = str(request_payload.source_url or "")
        url_extension = extension_for(source_url)
        if url_extension in SUBTITLE_EXTENSIONS:
            messages.append(make_message(MessageLevel.info, "Fetching a public subtitle file from the provided link."))
            payload = fetch_public_subtitle_url(source_url)
            return parse_subtitle_bytes(source_url, payload)

        if url_extension in SUPPORTED_DIRECT_TRANSCRIPTION_EXTENSIONS:
            messages.append(make_message(MessageLevel.info, "Fetching a public media file from the provided link."))
            fetched_media = fetch_public_media_url(source_url)
            if local_transcription_available():
                messages.append(
                    make_message(
                        MessageLevel.info,
                        "Transcribing linked media with the local Whisper model.",
                    )
                )
                return transcribe_media_with_local_whisper(
                    fetched_media,
                    source_url,
                    request_payload.original_language,
                )
            if openai_available():
                messages.append(make_message(MessageLevel.info, "Transcribing linked media with the configured speech-to-text provider."))
                return transcribe_media_with_openai(fetched_media, source_url, request_payload.original_language)
            if ALLOW_DEMO_FALLBACK:
                messages.append(
                    make_message(
                        MessageLevel.warning,
                        "Using demo subtitle timing because no transcription provider is configured for this linked media.",
                    )
                )
                return build_demo_cues(request_payload)

        if ALLOW_DEMO_FALLBACK:
            messages.append(
                make_message(
                    MessageLevel.warning,
                    "This link cannot be extracted directly in the current environment, so demo subtitles were generated for preview instead.",
                )
            )
            return build_demo_cues(request_payload)

        raise RuntimeError(
            "This link could not be processed into real subtitles in the current environment. Install the local Whisper setup with setup-local-ai.bat, add OPENAI_API_KEY in .env, or provide a source that already includes subtitle data."
        )

    if not media_bytes:
        raise RuntimeError("No media bytes were supplied for transcription.")

    media_extension = extension_for(media_name)
    if media_extension not in SUPPORTED_DIRECT_TRANSCRIPTION_EXTENSIONS:
        if ALLOW_DEMO_FALLBACK:
            messages.append(
                make_message(
                    MessageLevel.warning,
                    "This file type is not supported for direct transcription here, so demo subtitles were generated for preview.",
                )
            )
            return build_demo_cues(request_payload)
        raise RuntimeError("This media format is not directly supported for transcription.")

    if local_transcription_available():
        messages.append(make_message(MessageLevel.info, "Transcribing uploaded media with the local Whisper model."))
        return transcribe_media_with_local_whisper(media_bytes, media_name, request_payload.original_language)

    if openai_available():
        messages.append(make_message(MessageLevel.info, "Transcribing uploaded media with the configured speech-to-text provider."))
        return transcribe_media_with_openai(media_bytes, media_name, request_payload.original_language)

    if ALLOW_DEMO_FALLBACK:
        messages.append(
            make_message(
                MessageLevel.warning,
                "Using demo subtitle timing because no transcription provider is configured for uploaded video yet.",
            )
        )
        return build_demo_cues(request_payload)

    raise RuntimeError(
        "Real subtitles are not configured yet for uploaded video. Install the local Whisper setup with setup-local-ai.bat, or add OPENAI_API_KEY in .env so the app can transcribe the original audio into timed cues."
    )


def build_artifacts(
    *,
    base_url: str,
    job_id: str,
    request_payload: TranslationRequest,
    cues,
    media_bytes: Optional[bytes],
    render_progress_callback=None,
    render_error_callback=None,
) -> List[ArtifactSummary]:
    artifacts: List[ArtifactSummary] = []
    lane_a = request_payload.target_languages[0]
    lane_b = request_payload.target_languages[1]

    lane_a_vtt = build_vtt_track(cues, lane_a).encode("utf-8")
    lane_b_vtt = build_vtt_track(cues, lane_b).encode("utf-8")
    lane_a_srt = build_srt_track(cues, lane_a).encode("utf-8")
    lane_b_srt = build_srt_track(cues, lane_b).encode("utf-8")
    dual_ass = build_dual_ass(cues, request_payload).encode("utf-8")
    overlay_json = overlay_payload_for(cues, request_payload)

    artifacts.append(create_artifact(base_url, "lane_a_vtt", f"{job_id}-{lane_a}.vtt", "text/vtt", lane_a_vtt))
    artifacts.append(create_artifact(base_url, "lane_b_vtt", f"{job_id}-{lane_b}.vtt", "text/vtt", lane_b_vtt))
    artifacts.append(create_artifact(base_url, "lane_a_srt", f"{job_id}-{lane_a}.srt", "application/x-subrip", lane_a_srt))
    artifacts.append(create_artifact(base_url, "lane_b_srt", f"{job_id}-{lane_b}.srt", "application/x-subrip", lane_b_srt))
    artifacts.append(create_artifact(base_url, "dual_ass", f"{job_id}-dual.ass", "text/plain", dual_ass))
    artifacts.append(create_artifact(base_url, "overlay_payload", f"{job_id}-overlay.json", "application/json", overlay_json))

    if request_payload.output_mode.value == "burned_export" and media_bytes and request_payload.source_filename:
        try:
            burned_video = burn_subtitles_to_video(
                media_bytes,
                request_payload.source_filename,
                dual_ass,
                progress_callback=render_progress_callback,
            )
        except Exception as exc:
            burned_video = None
            if render_error_callback:
                render_error_callback(str(exc))
        if burned_video:
            content_type = mimetypes.guess_type("video.mp4")[0] or "video/mp4"
            artifacts.append(create_artifact(base_url, "burned_video", f"{job_id}-dual-burned.mp4", content_type, burned_video))

    return artifacts


def run_job_processing(
    *,
    job_id: str,
    base_url: str,
    request_payload: TranslationRequest,
    media_bytes: Optional[bytes],
    subtitle_bytes: Optional[bytes],
) -> TranslationJob:
    try:
        set_job_stage(
            job_id,
            status=JobStatus.extracting,
            progress_percent=12,
            current_step="Finding the original transcript",
            estimated_seconds_remaining=None,
        )
        source_messages: List[ProcessingMessage] = []
        cues = resolve_source_cues(
            request_payload,
            media_bytes=media_bytes,
            subtitle_bytes=subtitle_bytes,
            messages=source_messages,
        )
        extend_job_messages(job_id, source_messages)
        if not cues:
            raise RuntimeError("No subtitle cues could be generated from the provided source.")

        append_job_message(
            job_id,
            make_message(
                MessageLevel.info,
                f"Captured the original transcript with {len(cues)} timed subtitle cues.",
            ),
        )
        update_job_record(
            job_id,
            status=JobStatus.transcribing,
            progress_percent=34,
            current_step="Original transcript ready",
        )

        update_job_record(
            job_id,
            status=JobStatus.translating,
            progress_percent=46,
            current_step="Translating Subtitle Language 1 and Subtitle Language 2",
        )
        translation_messages: List[ProcessingMessage] = []
        def translation_progress_callback(language_code: str, progress_percent: int) -> None:
            language_position = 1 if language_code == request_payload.target_languages[0] else 2
            update_job_record(
                job_id,
                status=JobStatus.translating,
                progress_percent=progress_percent,
                current_step=f"Translating Subtitle Language {language_position}",
                estimated_seconds_remaining=None,
            )

        translated_cues = resolve_translations(
            cues,
            request_payload,
            translation_messages,
            progress_callback=translation_progress_callback,
        )
        extend_job_messages(job_id, translation_messages)
        append_job_message(
            job_id,
            make_message(
                MessageLevel.info,
                "Attached Subtitle Language 1 and Subtitle Language 2 to the shared subtitle timeline so both tracks stay synchronized.",
            ),
        )

        update_job_record(
            job_id,
            status=JobStatus.rendering,
            progress_percent=72,
            current_step="Preparing synchronized subtitle files",
        )

        def render_progress_callback(rendered_seconds: float, total_duration_seconds: Optional[float], eta_seconds: Optional[int]) -> None:
            if total_duration_seconds and total_duration_seconds > 0:
                render_ratio = min(max(rendered_seconds / total_duration_seconds, 0.0), 1.0)
                progress_percent = int(75 + (render_ratio * 24))
            else:
                progress_percent = 78

            update_job_record(
                job_id,
                status=JobStatus.rendering,
                progress_percent=progress_percent,
                current_step="Rendering the burned-in video",
                estimated_seconds_remaining=eta_seconds,
            )

        def render_error_callback(error_message: str) -> None:
            append_job_message(
                job_id,
                make_message(
                    MessageLevel.warning,
                    f"Video rendering could not finish, so the app will use browser playback with generated subtitle overlays instead. {error_message}",
                ),
            )

        artifacts = build_artifacts(
            base_url=base_url,
            job_id=job_id,
            request_payload=request_payload,
            cues=translated_cues,
            media_bytes=media_bytes,
            render_progress_callback=render_progress_callback,
            render_error_callback=render_error_callback,
        )

        burned_video_artifact = next((artifact for artifact in artifacts if artifact.kind == "burned_video"), None)
        if request_payload.output_mode.value == "burned_export":
            if burned_video_artifact:
                append_job_message(
                    job_id,
                    make_message(
                        MessageLevel.info,
                        "The generated video now includes both subtitle languages and is ready to play or download.",
                    ),
                )
            else:
                append_job_message(
                    job_id,
                    make_message(
                        MessageLevel.warning,
                        "A burned-in video file was requested, but this environment does not currently have ffmpeg available. Subtitle assets were generated instead.",
                    ),
                )
        else:
            append_job_message(
                job_id,
                make_message(
                    MessageLevel.info,
                    "The dual-language subtitle output is ready for synchronized playback and file download.",
                ),
            )

        update_job_record(
            job_id,
            status=JobStatus.complete,
            progress_percent=100,
            current_step="Video ready",
            estimated_seconds_remaining=0,
            artifacts=artifacts,
            cues=translated_cues,
        )
    except Exception as exc:
        update_job_record(
            job_id,
            status=JobStatus.blocked,
            progress_percent=0,
            current_step="Generation failed",
            estimated_seconds_remaining=None,
            artifacts=[],
            cues=[],
        )
        append_job_message(job_id, make_message(MessageLevel.error, str(exc)))

    job = get_job_record(job_id)
    assert job is not None
    return job


def enqueue_request(
    *,
    base_url: str,
    request_payload: TranslationRequest,
    media_bytes: Optional[bytes],
    subtitle_bytes: Optional[bytes],
) -> TranslationJob:
    job_id = f"job_{uuid4().hex[:10]}"
    job = store_job(create_job_record(job_id, request_payload))

    if should_process_inline():
        return run_job_processing(
            job_id=job_id,
            base_url=base_url,
            request_payload=request_payload,
            media_bytes=media_bytes,
            subtitle_bytes=subtitle_bytes,
        )

    worker = threading.Thread(
        target=run_job_processing,
        kwargs={
            "job_id": job_id,
            "base_url": base_url,
            "request_payload": request_payload,
            "media_bytes": media_bytes,
            "subtitle_bytes": subtitle_bytes,
        },
        daemon=True,
    )
    worker.start()
    return job


def process_request(
    *,
    base_url: str,
    request_payload: TranslationRequest,
    media_bytes: Optional[bytes],
    subtitle_bytes: Optional[bytes],
) -> TranslationJob:
    job_id = f"job_{uuid4().hex[:10]}"
    store_job(create_job_record(job_id, request_payload))
    return run_job_processing(
        job_id=job_id,
        base_url=base_url,
        request_payload=request_payload,
        media_bytes=media_bytes,
        subtitle_bytes=subtitle_bytes,
    )
