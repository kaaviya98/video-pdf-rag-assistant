from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import sentry_sdk
import webvtt
from webvtt.errors import (
    MalformedCaptionError,
    MalformedFileError,
    MissingFilenameError,
)

from app.utils.text import normalize_text


class TranscriptParseError(Exception):
    """Raised when a VTT transcript cannot be parsed or ingested."""


@dataclass(frozen=True, slots=True)
class ParsedTranscriptLine:
    line_number: int
    start_sec: Decimal
    end_sec: Decimal
    text: str


@dataclass(frozen=True, slots=True)
class VttCueWithCollapsedWhitespace:
    start_sec: float
    end_sec: float
    text: str


def parse_vtt_file(vtt_path: str) -> list[ParsedTranscriptLine]:
    vtt = read_vtt_document(vtt_path)
    cues = vtt_cues_with_collapsed_whitespace_text(vtt)
    if not cues:
        return []
    return parsed_transcript_lines_in_chronological_order(cues)


def read_vtt_document(vtt_path: str):
    try:
        return webvtt.read(vtt_path)
    except (
        MalformedFileError,
        MalformedCaptionError,
        MissingFilenameError,
        OSError,
    ) as exc:
        message = f"Failed to parse VTT transcript: {exc}"
        sentry_sdk.capture_exception(exc)
        raise TranscriptParseError(message) from exc


def vtt_cues_with_collapsed_whitespace_text(vtt) -> list[VttCueWithCollapsedWhitespace]:
    cues: list[VttCueWithCollapsedWhitespace] = []
    for cue in vtt:
        text = normalize_text(cue.text or "")
        if not text:
            continue
        cues.append(
            VttCueWithCollapsedWhitespace(
                start_sec=cue.start_in_seconds,
                end_sec=cue.end_in_seconds,
                text=text,
            ),
        )
    return cues


def parsed_transcript_lines_in_chronological_order(
    cues: list[VttCueWithCollapsedWhitespace],
) -> list[ParsedTranscriptLine]:
    ordered = sorted(cues, key=lambda c: (c.start_sec, c.end_sec))
    return [
        ParsedTranscriptLine(
            line_number=index,
            start_sec=Decimal(str(cue.start_sec)),
            end_sec=Decimal(str(cue.end_sec)),
            text=cue.text,
        )
        for index, cue in enumerate(ordered, start=1)
    ]
