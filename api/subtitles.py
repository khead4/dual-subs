from __future__ import annotations

import json
import re
import textwrap
from typing import List

from .contracts import SubtitleCue, TranslationRequest


def parse_timestamp(value: str) -> int:
    normalized = value.strip().replace(",", ".")
    parts = normalized.split(":")
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_part = parts[2]
    elif len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds_part = parts[1]
    else:
        raise ValueError(f"Unsupported timestamp: {value}")

    if "." in seconds_part:
        seconds_value, millis_value = seconds_part.split(".", 1)
    else:
        seconds_value, millis_value = seconds_part, "0"

    seconds = int(seconds_value)
    millis = int(millis_value.ljust(3, "0")[:3])
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis


def format_vtt_timestamp(total_ms: int) -> str:
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def format_srt_timestamp(total_ms: int) -> str:
    return format_vtt_timestamp(total_ms).replace(".", ",")


def format_ass_timestamp(total_ms: int) -> str:
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    centiseconds = round(millis / 10)
    if centiseconds == 100:
        seconds += 1
        centiseconds = 0
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def normalize_subtitle_text(text: str) -> str:
    collapsed = re.sub(r"<[^>]+>", "", text.replace("\r", ""))
    collapsed = re.sub(r"\n+", " ", collapsed)
    return collapsed.strip()


def parse_srt(text: str) -> List[SubtitleCue]:
    cues: List[SubtitleCue] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())

    for index, block in enumerate(blocks, start=1):
        lines = [line for line in block.split("\n") if line.strip()]
        if len(lines) < 2:
            continue

        if "-->" in lines[0]:
            cue_id = f"cue-{index:03d}"
            timing_line = lines[0]
            body_lines = lines[1:]
        else:
            cue_id = lines[0].strip() or f"cue-{index:03d}"
            timing_line = lines[1]
            body_lines = lines[2:]

        if "-->" not in timing_line:
            continue

        start_value, end_value = [part.strip() for part in timing_line.split("-->", 1)]
        body = normalize_subtitle_text("\n".join(body_lines))
        if not body:
            continue

        cues.append(
            SubtitleCue(
                cue_id=cue_id,
                start_ms=parse_timestamp(start_value),
                end_ms=parse_timestamp(end_value.split(" ")[0]),
                original_text=body,
                translations={},
            )
        )

    return cues


def parse_vtt(text: str) -> List[SubtitleCue]:
    cues: List[SubtitleCue] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())

    for index, block in enumerate(blocks, start=1):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if lines[0].startswith("WEBVTT") or lines[0].startswith("NOTE") or lines[0].startswith("STYLE"):
            continue

        if "-->" in lines[0]:
            cue_id = f"cue-{index:03d}"
            timing_line = lines[0]
            body_lines = lines[1:]
        elif len(lines) > 1 and "-->" in lines[1]:
            cue_id = lines[0].strip() or f"cue-{index:03d}"
            timing_line = lines[1]
            body_lines = lines[2:]
        else:
            continue

        start_value, end_value = [part.strip() for part in timing_line.split("-->", 1)]
        body = normalize_subtitle_text("\n".join(body_lines))
        if not body:
            continue

        cues.append(
            SubtitleCue(
                cue_id=cue_id,
                start_ms=parse_timestamp(start_value.split(" ")[0]),
                end_ms=parse_timestamp(end_value.split(" ")[0]),
                original_text=body,
                translations={},
            )
        )

    return cues


def parse_subtitle_bytes(filename: str, payload: bytes) -> List[SubtitleCue]:
    text = payload.decode("utf-8-sig")
    lower_name = filename.lower()
    if lower_name.endswith(".srt"):
        return parse_srt(text)
    if lower_name.endswith(".vtt"):
        return parse_vtt(text)
    raise ValueError("Only SRT and VTT subtitle uploads are supported in this version.")


def build_vtt_track(cues: List[SubtitleCue], language: str) -> str:
    lines = ["WEBVTT", ""]
    for cue in cues:
        lines.append(cue.cue_id)
        lines.append(f"{format_vtt_timestamp(cue.start_ms)} --> {format_vtt_timestamp(cue.end_ms)}")
        lines.append(cue.translations.get(language, cue.original_text))
        lines.append("")
    return "\n".join(lines)


def build_srt_track(cues: List[SubtitleCue], language: str) -> str:
    lines: List[str] = []
    for index, cue in enumerate(cues, start=1):
        lines.append(str(index))
        lines.append(f"{format_srt_timestamp(cue.start_ms)} --> {format_srt_timestamp(cue.end_ms)}")
        lines.append(cue.translations.get(language, cue.original_text))
        lines.append("")
    return "\n".join(lines)


def escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def contains_dense_script(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]", text))


def line_width_for_text(text: str, max_chars_per_line: int) -> int:
    if contains_dense_script(text) and " " not in text:
        return max(10, int(max_chars_per_line * 0.72))
    return max(12, max_chars_per_line)


def collapse_wrapped_lines(lines: List[str], separator: str) -> List[str]:
    if len(lines) <= 2:
        return lines

    midpoint = max(1, len(lines) // 2)
    return [
        separator.join(lines[:midpoint]).strip(),
        separator.join(lines[midpoint:]).strip(),
    ]


def wrap_text_for_ass(text: str, max_chars_per_line: int) -> str:
    normalized = normalize_subtitle_text(text)
    if not normalized:
        return ""

    if " " in normalized:
        wrapped_lines = textwrap.wrap(
            normalized,
            width=line_width_for_text(normalized, max_chars_per_line),
            break_long_words=False,
            break_on_hyphens=False,
        )
        separator = " "
    else:
        wrapped_lines = textwrap.wrap(
            normalized,
            width=line_width_for_text(normalized, max_chars_per_line),
            break_long_words=True,
            break_on_hyphens=False,
        )
        separator = ""

    if not wrapped_lines:
        wrapped_lines = [normalized]

    wrapped_lines = collapse_wrapped_lines(wrapped_lines, separator)
    return escape_ass_text("\n".join(line for line in wrapped_lines if line))


def ass_font_sizes(max_chars_per_line: int) -> tuple[int, int]:
    if max_chars_per_line <= 22:
        return 42, 38
    if max_chars_per_line <= 28:
        return 38, 34
    if max_chars_per_line <= 34:
        return 36, 32
    return 34, 30


def build_dual_ass(cues: List[SubtitleCue], request_payload: TranslationRequest) -> str:
    safe_area = int(1080 * request_payload.layout.safe_area_percent / 100)
    lane_a_font_size, lane_b_font_size = ass_font_sizes(request_payload.layout.max_chars_per_line)
    side_margin = 110
    bottom_margin = max(safe_area, 92)
    top_lane_margin = bottom_margin + request_payload.layout.track_gap_px + (lane_b_font_size * 2) + 20
    lane_a = request_payload.target_languages[0]
    lane_b = request_payload.target_languages[1]

    header = f"""[Script Info]
Title: Dual Subtitle Studio
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: LaneA,Segoe UI Semibold,{lane_a_font_size},&H00FFFFFF,&H000000FF,&H00111111,&H64000000,-1,0,0,0,100,100,0,0,1,3,0,2,{side_margin},{side_margin},{top_lane_margin},1
Style: LaneB,Segoe UI Semibold,{lane_b_font_size},&H00F8F3C0,&H000000FF,&H00111111,&H64000000,-1,0,0,0,100,100,0,0,1,3,0,2,{side_margin},{side_margin},{bottom_margin},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

    dialogue_lines: List[str] = []
    for cue in cues:
        start_time = format_ass_timestamp(cue.start_ms)
        end_time = format_ass_timestamp(cue.end_ms)
        dialogue_lines.append(
            f"Dialogue: 0,{start_time},{end_time},LaneA,,0,0,0,,{wrap_text_for_ass(cue.translations.get(lane_a, cue.original_text), request_payload.layout.max_chars_per_line)}"
        )
        dialogue_lines.append(
            f"Dialogue: 1,{start_time},{end_time},LaneB,,0,0,0,,{wrap_text_for_ass(cue.translations.get(lane_b, cue.original_text), request_payload.layout.max_chars_per_line)}"
        )

    return header + "\n".join(dialogue_lines) + "\n"


def overlay_payload_for(cues: List[SubtitleCue], request_payload: TranslationRequest) -> bytes:
    overlay = {
        "safe_area_percent": request_payload.layout.safe_area_percent,
        "track_gap_px": request_payload.layout.track_gap_px,
        "max_chars_per_line": request_payload.layout.max_chars_per_line,
        "theme": request_payload.layout.theme,
        "lane_a_language": request_payload.target_languages[0],
        "lane_b_language": request_payload.target_languages[1],
        "cues": [
            {
                "cue_id": cue.cue_id,
                "start_ms": cue.start_ms,
                "end_ms": cue.end_ms,
                "original_text": cue.original_text,
                "lane_a_text": cue.translations.get(request_payload.target_languages[0], cue.original_text),
                "lane_b_text": cue.translations.get(request_payload.target_languages[1], cue.original_text),
            }
            for cue in cues
        ],
    }
    return json.dumps(overlay, indent=2, ensure_ascii=False).encode("utf-8")
