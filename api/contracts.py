from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


def load_local_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        project_root = Path(__file__).resolve().parent.parent
    else:
        project_root = env_path.parent

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            os.environ.setdefault(key, value)

    local_ai_root = project_root / ".local-ai"
    path_defaults = {
        "XDG_DATA_HOME": local_ai_root / "share",
        "XDG_CONFIG_HOME": local_ai_root / "config",
        "XDG_CACHE_HOME": local_ai_root / "cache",
        "STANZA_RESOURCES_DIR": local_ai_root / "stanza_resources",
        "HF_HOME": local_ai_root / "huggingface",
    }

    for key, path in path_defaults.items():
        os.environ.setdefault(key, str(path))
        Path(os.environ[key]).mkdir(parents=True, exist_ok=True)


load_local_env()


SUPPORTED_DIRECT_TRANSCRIPTION_EXTENSIONS = {
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".wav",
    ".webm",
}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}
DEFAULT_TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1")
DEFAULT_TRANSCRIPTION_MODEL = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
TRANSLATION_QUALITY_MODE = os.getenv("TRANSLATION_QUALITY_MODE", "contextual_natural")
ALLOW_DEMO_FALLBACK = os.getenv("ALLOW_DEMO_TRANSLATION", "0").lower() not in {"0", "false", "no"}
FFMPEG_BINARY = os.getenv("FFMPEG_BINARY", "ffmpeg")
LOCAL_WHISPER_MODEL = os.getenv("LOCAL_WHISPER_MODEL", "small")
LOCAL_WHISPER_DEVICE = os.getenv("LOCAL_WHISPER_DEVICE", "cpu")
LOCAL_WHISPER_COMPUTE_TYPE = os.getenv("LOCAL_WHISPER_COMPUTE_TYPE", "int8")
LOCAL_TRANSLATION_PIVOT = os.getenv("LOCAL_TRANSLATION_PIVOT", "en")

DEMO_SOURCE_LINES = {
    "ja": [
        "\u3053\u306e\u30b7\u30fc\u30f3\u306f\u30c7\u30e2\u751f\u6210\u306e\u305f\u3081\u306e\u30bb\u30ea\u30d5\u3067\u3059\u3002",
        "\u5b9f\u969b\u306e\u97f3\u58f0\u8ee2\u5199\u3068\u7ffb\u8a33\u3092\u6709\u52b9\u306b\u3059\u308b\u3068\u3001\u3053\u3053\u306b\u672c\u7269\u306e\u5b57\u5e55\u304c\u8868\u793a\u3055\u308c\u307e\u3059\u3002",
    ],
    "en": [
        "This scene is using demo subtitle generation.",
        "Connect a real transcription and translation provider to replace this preview with actual subtitles.",
    ],
    "zh-Hans": [
        "\u8fd9\u4e2a\u753b\u9762\u6b63\u5728\u4f7f\u7528\u6f14\u793a\u5b57\u5e55\u751f\u6210\u3002",
        "\u63a5\u5165\u771f\u5b9e\u7684\u8f6c\u5199\u4e0e\u7ffb\u8bd1\u670d\u52a1\u540e\uff0c\u8fd9\u91cc\u4f1a\u663e\u793a\u5b9e\u9645\u5b57\u5e55\u3002",
    ],
    "zh-Hant": [
        "\u9019\u500b\u756b\u9762\u6b63\u5728\u4f7f\u7528\u793a\u7bc4\u5b57\u5e55\u751f\u6210\u3002",
        "\u63a5\u5165\u771f\u5be6\u7684\u8f49\u5beb\u8207\u7ffb\u8b6f\u670d\u52d9\u5f8c\uff0c\u9019\u88e1\u6703\u986f\u793a\u5be6\u969b\u5b57\u5e55\u3002",
    ],
}


class SourceKind(str, Enum):
    upload_video = "upload_video"
    upload_subtitles = "upload_subtitles"
    external_link = "external_link"


class Provider(str, Enum):
    youtube = "youtube"
    netflix = "netflix"
    hulu = "hulu"
    prime_video = "prime_video"
    generic = "generic"


class OutputMode(str, Enum):
    stream_overlay = "stream_overlay"
    subtitle_download = "subtitle_download"
    burned_export = "burned_export"


class JobStatus(str, Enum):
    queued = "queued"
    extracting = "extracting"
    transcribing = "transcribing"
    translating = "translating"
    rendering = "rendering"
    complete = "complete"
    blocked = "blocked"


class MessageLevel(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


class LanguageOption(BaseModel):
    code: str
    label: str


class LayoutPreferences(BaseModel):
    safe_area_percent: int = Field(default=14, ge=8, le=24)
    track_gap_px: int = Field(default=14, ge=6, le=32)
    max_chars_per_line: int = Field(default=28, ge=18, le=42)
    theme: str = Field(default="cinema")


class SubtitleLaneConfig(BaseModel):
    lane: str
    language: str
    vertical_order: int


class RenderPlan(BaseModel):
    original_transcript_source: str
    merge_strategy: str
    safe_area_percent: int
    lane_gap_px: int
    lanes: List[SubtitleLaneConfig]


class Deliverable(BaseModel):
    kind: str
    description: str


class ArtifactSummary(BaseModel):
    artifact_id: str
    kind: str
    filename: str
    content_type: str
    download_url: str


class ProcessingMessage(BaseModel):
    level: MessageLevel
    text: str


class TranslationRequest(BaseModel):
    kind: SourceKind
    provider: Provider = Provider.generic
    output_mode: OutputMode = OutputMode.stream_overlay
    source_url: Optional[HttpUrl] = None
    original_language: str = Field(min_length=2, max_length=16)
    target_languages: List[str] = Field(min_length=2, max_length=2)
    layout: LayoutPreferences = Field(default_factory=LayoutPreferences)
    source_filename: Optional[str] = None
    subtitles_filename: Optional[str] = None

    @model_validator(mode="after")
    def validate_request(self) -> "TranslationRequest":
        if len(self.target_languages) != 2:
            raise ValueError("Exactly two target languages are required.")
        if self.target_languages[0] == self.target_languages[1]:
            raise ValueError("Target languages must be different.")
        if self.original_language in self.target_languages:
            raise ValueError("Subtitle languages must be different from the original language.")
        if self.kind == SourceKind.external_link and not self.source_url:
            raise ValueError("A source URL is required for external links.")
        return self


class SubtitleCue(BaseModel):
    cue_id: str
    start_ms: int
    end_ms: int
    original_text: str
    translations: Dict[str, str]


class TranslationJob(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    request: TranslationRequest
    progress_percent: int = 0
    current_step: str = "Waiting to start"
    estimated_seconds_remaining: Optional[int] = None
    transcript_strategy: str
    render_plan: RenderPlan
    provider_notes: List[str]
    steps: List[str]
    deliverables: List[Deliverable]
    messages: List[ProcessingMessage]
    artifacts: List[ArtifactSummary]
    cues: List[SubtitleCue]


LANGUAGES = [
    LanguageOption(code="ja", label="Japanese"),
    LanguageOption(code="en", label="English"),
    LanguageOption(code="zh-Hans", label="Chinese (Simplified)"),
    LanguageOption(code="zh-Hant", label="Chinese (Traditional)"),
    LanguageOption(code="ko", label="Korean"),
    LanguageOption(code="es", label="Spanish"),
    LanguageOption(code="fr", label="French"),
    LanguageOption(code="de", label="German"),
    LanguageOption(code="it", label="Italian"),
    LanguageOption(code="pt-BR", label="Portuguese (Brazil)"),
    LanguageOption(code="ar", label="Arabic"),
    LanguageOption(code="hi", label="Hindi"),
]
