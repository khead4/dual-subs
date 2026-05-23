from __future__ import annotations

import json
import mimetypes
import os
import re
import tempfile
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

from .contracts import (
    ALLOW_DEMO_FALLBACK,
    DEFAULT_TEXT_MODEL,
    DEFAULT_TRANSCRIPTION_MODEL,
    LANGUAGES,
    LOCAL_TRANSLATION_PIVOT,
    LOCAL_WHISPER_COMPUTE_TYPE,
    LOCAL_WHISPER_DEVICE,
    LOCAL_WHISPER_MODEL,
    MessageLevel,
    ProcessingMessage,
    SubtitleCue,
    TRANSLATION_QUALITY_MODE,
    TranslationRequest,
)


def make_message(level: MessageLevel, text: str) -> ProcessingMessage:
    return ProcessingMessage(level=level, text=text)


def openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def local_transcription_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def local_translation_available() -> bool:
    try:
        import argostranslate.translate  # noqa: F401
    except ImportError:
        return False
    return True


def local_chinese_conversion_available() -> bool:
    try:
        import opencc  # noqa: F401
    except ImportError:
        return False
    return True


def language_label(code: str) -> str:
    return next((language.label for language in LANGUAGES if language.code == code), code)


def canonical_whisper_code(code: str) -> str:
    if code in {"zh-Hans", "zh-Hant"}:
        return "zh"
    if code == "pt-BR":
        return "pt"
    return code


def canonical_argos_code(code: str) -> str:
    return canonical_whisper_code(code)


@lru_cache(maxsize=1)
def get_opencc_module():
    import opencc

    return opencc


def convert_chinese_variant(text: str, *, target_code: str) -> str:
    if not text or target_code not in {"zh-Hans", "zh-Hant"}:
        return text

    if not local_chinese_conversion_available():
        return text

    opencc = get_opencc_module()
    config_name = "t2s" if target_code == "zh-Hans" else "s2t"
    return opencc.OpenCC(config_name).convert(text)


def prepare_local_translation_source(text: str, source_language: str) -> str:
    if source_language == "zh-Hant":
        return convert_chinese_variant(text, target_code="zh-Hans")
    return text


def finalize_local_translation_text(text: str, target_language: str) -> str:
    if target_language == "zh-Hant":
        return convert_chinese_variant(text, target_code="zh-Hant")
    if target_language == "zh-Hans":
        return convert_chinese_variant(text, target_code="zh-Hans")
    return text


def looks_like_translatable_text(text: str) -> bool:
    return any(character.isalnum() for character in text)


def installed_local_translation_languages() -> List[str]:
    if not local_translation_available():
        return []

    import argostranslate.translate

    languages = argostranslate.translate.get_installed_languages()
    return sorted({language.code for language in languages})


@lru_cache(maxsize=1)
def get_local_whisper_model():
    from faster_whisper import WhisperModel

    return WhisperModel(
        LOCAL_WHISPER_MODEL,
        device=LOCAL_WHISPER_DEVICE,
        compute_type=LOCAL_WHISPER_COMPUTE_TYPE,
    )


def build_multipart_body(fields: List[tuple[str, str]], files: List[tuple[str, str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"----DualSubtitleBoundary{uuid4().hex}"
    chunks: List[bytes] = []

    for key, value in fields:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    for field_name, filename, payload, content_type in files:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        chunks.append(payload)
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def call_openai_json(endpoint: str, *, payload: dict | None = None, body: bytes | None = None, content_type: str = "application/json") -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    request_body = json.dumps(payload).encode("utf-8") if payload is not None else body
    request = urllib.request.Request(
        endpoint,
        data=request_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Provider request failed: {detail}") from exc


def extract_response_text(response_payload: dict) -> str:
    if response_payload.get("output_text"):
        return response_payload["output_text"]

    output_items = response_payload.get("output", [])
    for item in output_items:
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                return content["text"]
    raise RuntimeError("The translation response did not include output text.")


def subtitle_context_payload(cues: List[SubtitleCue], start_index: int, batch_size: int) -> List[dict]:
    context_start = max(0, start_index - 3)
    context_end = min(len(cues), start_index + batch_size + 3)
    return [
        {
            "cue_id": cue.cue_id,
            "start_ms": cue.start_ms,
            "end_ms": cue.end_ms,
            "text": cue.original_text,
            "translate_this_cue": start_index <= index < start_index + batch_size,
        }
        for index, cue in enumerate(cues[context_start:context_end], start=context_start)
    ]


def translate_cues_for_language_with_openai(
    cues: List[SubtitleCue], *, original_language: str, target_language: str, max_chars_per_line: int
) -> Dict[str, str]:
    batch_size = 20
    translated: Dict[str, str] = {}

    for start_index in range(0, len(cues), batch_size):
        batch = cues[start_index : start_index + batch_size]
        schema = {
            "type": "object",
            "properties": {
                "translations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cue_id": {"type": "string"},
                            "text": {"type": "string"},
                        },
                        "required": ["cue_id", "text"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["translations"],
            "additionalProperties": False,
        }

        prompt = {
            "original_language": original_language,
            "target_language": target_language,
            "quality_mode": TRANSLATION_QUALITY_MODE,
            "subtitle_constraints": {
                "max_chars_per_line": max_chars_per_line,
                "format": "plain text only; no cue numbers, speaker labels, markup, or explanations",
            },
            "instructions": [
                "Translate only the cues marked translate_this_cue=true.",
                "Use the surrounding cues as scene context to infer situation, tone, speaker intent, formality, relationships, and implied meaning.",
                "Prioritize naturalness and situational accuracy over literal word-for-word translation.",
                "Use idiomatic phrasing that a native viewer would expect in the target language.",
                "Preserve names, places, numbers, and important plot details.",
                "Keep subtitles concise for on-screen reading while preserving meaning.",
                "Return the same cue_id values for translated cues so timing stays synchronized.",
                "Do not add commentary or explanations.",
            ],
            "context_cues": subtitle_context_payload(cues, start_index, batch_size),
        }

        response_payload = call_openai_json(
            "https://api.openai.com/v1/responses",
            payload={
                "model": DEFAULT_TEXT_MODEL,
                "input": [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert audiovisual subtitle localizer. Your job is to produce "
                            "natural, situationally accurate subtitles that preserve intent, tone, and context. "
                            "Return only JSON that matches the requested schema."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(prompt, ensure_ascii=False),
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "subtitle_translation_batch",
                        "schema": schema,
                        "strict": True,
                    }
                },
            },
        )

        parsed = json.loads(extract_response_text(response_payload))
        translated_map = {item["cue_id"]: item for item in parsed["translations"]}

        for cue in batch:
            item = translated_map.get(cue.cue_id)
            if not item:
                raise RuntimeError(f"Missing translation for cue {cue.cue_id}.")
            translated[cue.cue_id] = item["text"].strip()

    return translated


def translate_cues_for_language_with_demo(cues: List[SubtitleCue], target_language: str) -> Dict[str, str]:
    translated: Dict[str, str] = {}
    for cue in cues:
        translated[cue.cue_id] = f"[{target_language}] {cue.original_text}"
    return translated


def translate_cues_for_language_with_argos(
    cues: List[SubtitleCue], *, original_language: str, target_language: str
) -> Dict[str, str]:
    import argostranslate.translate

    source_code = canonical_argos_code(original_language)
    target_code = canonical_argos_code(target_language)
    translated: Dict[str, str] = {}

    for cue in cues:
        source_text = prepare_local_translation_source(cue.original_text, original_language)
        if source_code == target_code:
            translated_text = source_text
        else:
            translated_text = argostranslate.translate.translate(source_text, source_code, target_code).strip()

            if not translated_text and source_code != LOCAL_TRANSLATION_PIVOT and target_code != LOCAL_TRANSLATION_PIVOT:
                pivot_text = argostranslate.translate.translate(
                    source_text,
                    source_code,
                    LOCAL_TRANSLATION_PIVOT,
                ).strip()
                if pivot_text:
                    translated_text = argostranslate.translate.translate(
                        pivot_text,
                        LOCAL_TRANSLATION_PIVOT,
                        target_code,
                    ).strip()

        if not translated_text and not looks_like_translatable_text(source_text):
            translated_text = source_text

        if not translated_text:
            translated_text = cue.original_text

        translated[cue.cue_id] = finalize_local_translation_text(translated_text, target_language)

    return translated


def transcribe_media_with_local_whisper(media_bytes: bytes, filename: str, language: str) -> List[SubtitleCue]:
    model = get_local_whisper_model()
    suffix = Path(filename).suffix or ".mp4"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(media_bytes)
        temp_path = Path(temp_file.name)

    try:
        segments_iter, info = model.transcribe(
            str(temp_path),
            language=canonical_whisper_code(language),
            task="transcribe",
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        segments = list(segments_iter)

        if not segments and getattr(info, "language", None):
            raise RuntimeError(
                f"Local Whisper detected {info.language} audio but did not return any subtitle segments."
            )

        cues: List[SubtitleCue] = []
        for index, segment in enumerate(segments, start=1):
            text = (segment.text or "").strip()
            if not text:
                continue
            cues.append(
                SubtitleCue(
                    cue_id=f"cue-{index:03d}",
                    start_ms=int(float(segment.start) * 1000),
                    end_ms=int(float(segment.end) * 1000),
                    original_text=text,
                    translations={},
                )
            )

        if not cues:
            raise RuntimeError("Local Whisper completed, but no timed subtitle cues were created.")

        return cues
    finally:
        temp_path.unlink(missing_ok=True)


def transcribe_media_with_openai(media_bytes: bytes, filename: str, language: str) -> List[SubtitleCue]:
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    multipart_body, boundary = build_multipart_body(
        fields=[
            ("model", DEFAULT_TRANSCRIPTION_MODEL),
            ("response_format", "verbose_json"),
            ("timestamp_granularities[]", "segment"),
            ("language", language),
        ],
        files=[("file", filename, media_bytes, content_type)],
    )

    response_payload = call_openai_json(
        "https://api.openai.com/v1/audio/transcriptions",
        body=multipart_body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )

    segments = response_payload.get("segments") or []
    if not segments and response_payload.get("text"):
        return [
            SubtitleCue(
                cue_id="cue-001",
                start_ms=0,
                end_ms=4000,
                original_text=response_payload["text"].strip(),
                translations={},
            )
        ]

    cues: List[SubtitleCue] = []
    for index, segment in enumerate(segments, start=1):
        text = segment.get("text", "").strip()
        if not text:
            continue
        cues.append(
            SubtitleCue(
                cue_id=f"cue-{index:03d}",
                start_ms=int(float(segment.get("start", 0)) * 1000),
                end_ms=int(float(segment.get("end", 0)) * 1000),
                original_text=text,
                translations={},
            )
        )
    return cues


def resolve_translations(
    cues: List[SubtitleCue],
    request_payload: TranslationRequest,
    messages: List[ProcessingMessage],
    progress_callback=None,
) -> List[SubtitleCue]:
    subtitle_language_1 = request_payload.target_languages[0]
    subtitle_language_2 = request_payload.target_languages[1]
    local_translation_codes = installed_local_translation_languages() if local_translation_available() else []
    source_code = canonical_argos_code(request_payload.original_language)
    target_code_1 = canonical_argos_code(subtitle_language_1)
    target_code_2 = canonical_argos_code(subtitle_language_2)
    missing_codes = sorted(
        {
            code
            for code in [source_code, target_code_1, target_code_2, LOCAL_TRANSLATION_PIVOT]
            if code not in local_translation_codes
        }
    )
    local_translation_ready = bool(local_translation_codes) and not missing_codes

    if local_translation_ready:
        if progress_callback:
            progress_callback(subtitle_language_1, 48)
        messages.append(
            make_message(
                MessageLevel.info,
                f"Translating the original transcript into Subtitle Language 1 with offline Argos models: {language_label(subtitle_language_1)}.",
            )
        )
        translations_language_1 = translate_cues_for_language_with_argos(
            cues,
            original_language=request_payload.original_language,
            target_language=subtitle_language_1,
        )
        messages.append(
            make_message(
                MessageLevel.info,
                f"Saved Subtitle Language 1 as {language_label(subtitle_language_1)}.",
            )
        )
        if progress_callback:
            progress_callback(subtitle_language_2, 60)
        messages.append(
            make_message(
                MessageLevel.info,
                f"Translating the original transcript into Subtitle Language 2 with offline Argos models: {language_label(subtitle_language_2)}.",
            )
        )
        translations_language_2 = translate_cues_for_language_with_argos(
            cues,
            original_language=request_payload.original_language,
            target_language=subtitle_language_2,
        )
        messages.append(
            make_message(
                MessageLevel.info,
                f"Saved Subtitle Language 2 as {language_label(subtitle_language_2)}.",
            )
        )
        if subtitle_language_1 in {"zh-Hans", "zh-Hant"} or subtitle_language_2 in {"zh-Hans", "zh-Hant"}:
            messages.append(
                make_message(
                    MessageLevel.info,
                    "Applied local Chinese script conversion so Simplified and Traditional subtitle lanes stay distinct.",
                )
            )
    elif openai_available():
        if local_translation_available() and missing_codes:
            messages.append(
                make_message(
                    MessageLevel.warning,
                    "Offline translation is installed, but the required Argos language packages are missing for: "
                    + ", ".join(missing_codes)
                    + ". Falling back to the configured OpenAI translation provider for this run.",
                )
            )
        if progress_callback:
            progress_callback(subtitle_language_1, 48)
        messages.append(
            make_message(
                MessageLevel.info,
                f"Translating the original transcript into Subtitle Language 1 with contextual, natural subtitle localization: {language_label(subtitle_language_1)}.",
            )
        )
        translations_language_1 = translate_cues_for_language_with_openai(
            cues,
            original_language=request_payload.original_language,
            target_language=subtitle_language_1,
            max_chars_per_line=request_payload.layout.max_chars_per_line,
        )
        messages.append(
            make_message(
                MessageLevel.info,
                f"Saved Subtitle Language 1 as {language_label(subtitle_language_1)}.",
            )
        )
        if progress_callback:
            progress_callback(subtitle_language_2, 60)
        messages.append(
            make_message(
                MessageLevel.info,
                f"Translating the original transcript into Subtitle Language 2 with contextual, natural subtitle localization: {language_label(subtitle_language_2)}.",
            )
        )
        translations_language_2 = translate_cues_for_language_with_openai(
            cues,
            original_language=request_payload.original_language,
            target_language=subtitle_language_2,
            max_chars_per_line=request_payload.layout.max_chars_per_line,
        )
        messages.append(
            make_message(
                MessageLevel.info,
                f"Saved Subtitle Language 2 as {language_label(subtitle_language_2)}.",
            )
        )
    elif ALLOW_DEMO_FALLBACK:
        messages.append(
            make_message(
                MessageLevel.warning,
                "OPENAI_API_KEY is missing, so the app is using demo translation placeholders. Add a provider key for real bilingual subtitle output.",
            )
        )
        if progress_callback:
            progress_callback(subtitle_language_1, 48)
        messages.append(
            make_message(
                MessageLevel.info,
                f"Creating demo Subtitle Language 1 output for {language_label(subtitle_language_1)}.",
            )
        )
        translations_language_1 = translate_cues_for_language_with_demo(cues, subtitle_language_1)
        messages.append(
            make_message(
                MessageLevel.info,
                f"Saved Subtitle Language 1 as {language_label(subtitle_language_1)}.",
            )
        )
        if progress_callback:
            progress_callback(subtitle_language_2, 60)
        messages.append(
            make_message(
                MessageLevel.info,
                f"Creating demo Subtitle Language 2 output for {language_label(subtitle_language_2)}.",
            )
        )
        translations_language_2 = translate_cues_for_language_with_demo(cues, subtitle_language_2)
        messages.append(
            make_message(
                MessageLevel.info,
                f"Saved Subtitle Language 2 as {language_label(subtitle_language_2)}.",
            )
        )
    else:
        raise RuntimeError(
            "Real subtitle translation is not configured yet. Install the offline translation pack with setup-local-ai.bat, or add OPENAI_API_KEY in .env."
        )

    translated: List[SubtitleCue] = []
    for cue in cues:
        translated.append(
            SubtitleCue(
                cue_id=cue.cue_id,
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                original_text=cue.original_text,
                translations={
                    subtitle_language_1: translations_language_1.get(cue.cue_id, ""),
                    subtitle_language_2: translations_language_2.get(cue.cue_id, ""),
                },
            )
        )
    return translated
