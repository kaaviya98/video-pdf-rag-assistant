from __future__ import annotations

import sentry_sdk
from django.db import DatabaseError, IntegrityError, transaction

from app.models.asset import Asset, AssetFileType
from app.models.transcript import TranscriptLine
from app.utils.logger import get_logger
from app.utils.file_operations import delete_file, resolve_file_source_to_local_path
from app.domain.video.vtt import (
    ParsedTranscriptLine,
    TranscriptParseError,
    parse_vtt_file,
)


logger = get_logger()


@transaction.atomic
def create_transcript_lines_from_vtt(
    asset: Asset,
    vtt_source: str | None = None,
) -> list[TranscriptLine]:
    validate_transcript_lines_can_be_created(asset)

    vtt_url = get_vtt_url(asset, vtt_source)
    vtt_path, is_temp_download = resolve_file_source_to_local_path(
        vtt_url,
        use_settings_secret=True,
    )

    try:
        parsed_lines = parse_vtt_file(vtt_path)
        if not parsed_lines:
            raise TranscriptParseError("No parsed lines provided")
        objects: list[TranscriptLine] = [
            TranscriptLine(
                asset=asset,
                line_number=line.line_number,
                start_sec=line.start_sec,
                end_sec=line.end_sec,
                text=line.text,
            )
            for line in parsed_lines
        ]

        return TranscriptLine.objects.bulk_create(objects, batch_size=1000)

    except (IntegrityError, DatabaseError, ValueError, TypeError) as exc:
        message = f"Failed to ingest VTT transcript for asset {asset.id}: {exc}"
        logger.exception(message)
        sentry_sdk.capture_exception(exc)
        raise TranscriptParseError(message) from exc
    finally:
        if is_temp_download:
            delete_file(vtt_path)


def get_vtt_url(asset: Asset, vtt_source: str | None) -> str:
    source = vtt_source or asset.captions_url
    if not source:
        message = "No VTT source provided for video asset"
        raise TranscriptParseError(message)
    return str(source)


def validate_transcript_lines_can_be_created(asset: Asset) -> None:
    if asset.file_type != AssetFileType.VIDEO:
        raise TranscriptParseError(
            "Transcript lines ingestion is only supported for VIDEO assets"
        )
    if TranscriptLine.objects.filter(asset=asset).exists():
        raise TranscriptParseError("Transcript lines already exist for this asset")
