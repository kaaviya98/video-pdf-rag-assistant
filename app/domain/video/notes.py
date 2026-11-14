from __future__ import annotations

from pathlib import Path
from typing import Any

import sentry_sdk
from django.conf import settings

from app.domain.prompts import (
    VIDEO_FULL_TOPIC_NOTES_MESSAGE,
    VIDEO_SEGMENT_NOTES_SYSTEM_MESSAGE,
)
from app.domain.assets import AssetProcessingError, get_video_asset_docs_from_vector_db
from app.domain.video.transcript_parser import get_chunk_char_limits
from app.models.asset import Asset
from app.models.transcript import TranscriptLine
from app.utils.file_operations import (
    delete_files_in_local_dir,
    get_storage_path,
    upload_folder,
)
from app.utils.openai import init_asset_chat_model
from app.utils.openai import resolve_llm_config_for_asset
from app.utils.transcript_timestamps import replace_line_refs_with_timestamps

SEG_FULL_NOTES_FILENAME = "seg_full_notes.md"
FULL_NOTES_WITH_TIMESTAMPS_FILENAME = "full_notes_with_timestamps.md"


class VideoNotesError(Exception):
    pass


ESTIMATED_TRANSCRIPT_CHARS_PER_SEGMENT_DOC = 500
MIN_VIDEO_NOTES_MAX_CHARS = 4_000
DEFAULT_VIDEO_NOTES_TARGET_GROUPS = 10


def generate_notes(asset: Asset, *, upload: bool = True) -> list[Path]:
    try:
        docs = get_video_asset_docs_from_vector_db(asset)
    except AssetProcessingError as exc:
        raise VideoNotesError(str(exc)) from exc

    if not docs:
        raise VideoNotesError("No transcript segments found in vector database")

    paths = VideoAssetNotesGenerator(asset, docs).generate()
    if not paths:
        raise VideoNotesError("Notes generation produced no output files")

    if not any(path.name == SEG_FULL_NOTES_FILENAME for path in paths):
        raise VideoNotesError("Full notes file was not generated")

    if upload:
        _upload_notes_or_fail(asset)

    return paths


def _upload_notes_or_fail(asset: Asset) -> None:
    if not asset.ai_outputs_folder_url:
        raise VideoNotesError("ai_outputs_folder_url is required to upload notes")

    if not upload_notes_folder_if_configured(asset):
        raise VideoNotesError("Failed to upload notes to configured storage")

    asset.refresh_from_db(fields=["notes_upload_path"])
    if not (asset.notes_upload_path or "").strip():
        raise VideoNotesError("notes_upload_path was not set after notes upload")


class VideoAssetNotesGenerator:
    def __init__(self, asset: Asset, docs: list[dict[str, Any]]) -> None:
        self._asset = asset
        self._docs = docs
        self._llm: Any | None = None
        self._llm_config = resolve_llm_config_for_asset(asset)

    def generate(self) -> list[Path]:
        if not self._docs:
            return []

        group_paths = self._create_notes_for_sub_parts_of_transcript(self._docs)
        if not group_paths:
            return []

        full_notes_path = self._create_full_notes_from_sub_part_notes(group_paths)
        timestamped_path = self._replace_line_numbers_in_full_notes_with_timestamps(
            full_notes_path,
        )
        return group_paths + [full_notes_path, timestamped_path]

    def _output_dir(self) -> Path:
        notes_root = getattr(settings, "VIDEO_NOTES_LOCAL_DIR", "var/video_notes")
        asset_dir = Path(notes_root) / str(self._asset.id)
        asset_dir.mkdir(parents=True, exist_ok=True)
        return asset_dir

    def _create_notes_for_sub_parts_of_transcript(
        self, docs: list[dict[str, Any]]
    ) -> list[Path]:
        group_size = self._compute_group_size(len(docs))
        groups = self._build_groups(docs, group_size)

        paths: list[Path] = []
        for group in groups:
            ordered_line_numbers = self._ordered_line_numbers_for_doc_group(group)
            raw_transcript = self._build_raw_transcript_for_line_numbers(
                ordered_line_numbers
            )
            if not raw_transcript.strip():
                continue
            paths.append(
                self._create_sub_part_notes_markdown_file(
                    group, ordered_line_numbers, raw_transcript
                ),
            )
        return paths

    def _create_sub_part_notes_markdown_file(
        self,
        group: list[dict[str, Any]],
        ordered_line_numbers: list[int],
        raw_transcript: str,
    ) -> Path:
        segment_orders = [d.get("segment_order") for d in group]
        label = "_".join(str(o) for o in segment_orders if o is not None)
        header = (
            f"Segment orders in this group: {segment_orders}\n"
            f"Transcript line numbers: {ordered_line_numbers}"
        )
        input_for_group = (
            header
            + "\n\n--------------------------------------------------\nTRANSCRIPT\n--------------------------------------------------\n\n"
            + raw_transcript
        )
        notes_md = self._generate_notes_markdown(
            input_for_group, prompt=VIDEO_SEGMENT_NOTES_SYSTEM_MESSAGE
        )
        path = self._output_dir() / f"seg_{label}_notes.md"
        path.write_text(notes_md, encoding="utf-8")
        return path

    def _create_full_notes_from_sub_part_notes(
        self, group_note_paths: list[Path]
    ) -> Path:
        combined = "\n\n".join(p.read_text(encoding="utf-8") for p in group_note_paths)
        input_text = (
            "COMBINED NOTES TO FORMAT AS FULL TOPIC-BASED NOTES:\n\n" + combined
        )
        full_notes_md = self._generate_notes_markdown(
            input_text, prompt=VIDEO_FULL_TOPIC_NOTES_MESSAGE
        )
        full_path = self._output_dir() / SEG_FULL_NOTES_FILENAME
        full_path.write_text(full_notes_md, encoding="utf-8")
        return full_path

    def _replace_line_numbers_in_full_notes_with_timestamps(
        self, full_notes_path: Path
    ) -> Path:
        full_notes_md = full_notes_path.read_text(encoding="utf-8")
        full_with_ts = replace_line_refs_with_timestamps(self._asset, full_notes_md)
        timestamped_path = full_notes_path.parent / FULL_NOTES_WITH_TIMESTAMPS_FILENAME
        timestamped_path.write_text(
            (full_with_ts or "").rstrip() + "\n", encoding="utf-8"
        )
        return timestamped_path

    def _generate_notes_markdown(self, input_text: str, *, prompt: str) -> str:
        if not (input_text or "").strip():
            return ""

        if not self._llm_config.api_key:
            raise VideoNotesError("OPENAI_API_KEY must be set to generate notes")

        full_prompt = (
            prompt
            + "\n\n--------------------------------------------------\nINPUT\n--------------------------------------------------\n\n"
            + input_text.strip()
        )

        try:
            response = self._llm_client().invoke(full_prompt)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            raise VideoNotesError(f"Notes generation failed: {exc}") from exc

        if hasattr(response, "content"):
            return str(response.content).strip()
        return str(response).strip()

    def _llm_client(self) -> Any:
        if self._llm is None:
            self._llm = init_asset_chat_model(self._asset, config=self._llm_config)
        return self._llm

    def _ordered_line_numbers_for_doc_group(
        self, group: list[dict[str, Any]]
    ) -> list[int]:
        line_numbers: list[int] = []
        for doc in group:
            line_numbers.extend(doc.get("transcript_line_numbers") or [])
        seen: set[int] = set()
        ordered: list[int] = []
        for ln in line_numbers:
            if ln not in seen:
                seen.add(ln)
                ordered.append(ln)
        ordered.sort()
        return ordered

    def _build_raw_transcript_for_line_numbers(self, line_numbers: list[int]) -> str:
        if not line_numbers:
            return ""

        lines = list(
            TranscriptLine.objects.filter(
                asset=self._asset,
                line_number__in=line_numbers,
            ).order_by("line_number")
        )
        return "\n".join(f"[L{l.line_number}]{l.text}" for l in lines)

    def _compute_group_size(self, num_docs: int) -> int:
        if num_docs <= 0:
            return 1

        max_chars, _ = get_chunk_char_limits()
        max_chars = max(max_chars, MIN_VIDEO_NOTES_MAX_CHARS)
        max_by_chars = max(1, max_chars // ESTIMATED_TRANSCRIPT_CHARS_PER_SEGMENT_DOC)

        target_groups = int(
            getattr(
                settings, "VIDEO_NOTES_TARGET_GROUPS", DEFAULT_VIDEO_NOTES_TARGET_GROUPS
            )
        )
        target_groups = max(1, target_groups)

        size_by_target = (num_docs + target_groups - 1) // target_groups
        size = max(1, min(max_by_chars, size_by_target))
        return min(size, num_docs)

    def _build_groups(
        self,
        docs: list[dict[str, Any]],
        group_size: int,
    ) -> list[list[dict[str, Any]]]:
        if not docs:
            return []

        groups: list[list[dict[str, Any]]] = [
            docs[i : i + group_size] for i in range(0, len(docs), group_size)
        ]

        if len(groups) >= 2 and len(groups[-1]) == 1:
            groups[-2].extend(groups[-1])
            groups.pop()

        return groups


def get_full_video_notes_text(asset: Asset) -> str:
    notes_base = Path(getattr(settings, "VIDEO_NOTES_LOCAL_DIR", "var/video_notes"))
    asset_dir = notes_base / str(asset.id)
    full_notes_path = asset_dir / SEG_FULL_NOTES_FILENAME
    if not full_notes_path.is_file():
        return ""
    try:
        return full_notes_path.read_text(encoding="utf-8")
    except Exception:
        return ""


def upload_notes_folder_if_configured(asset: Asset) -> bool:
    notes_dir = Path(
        getattr(settings, "VIDEO_NOTES_LOCAL_DIR", "var/video_notes")
    ) / str(asset.id)
    if not asset.ai_outputs_folder_url:
        return False
    if not notes_dir.is_dir():
        raise VideoNotesError(f"Notes output directory does not exist: {notes_dir}")

    if not (asset.notes_upload_path or "").strip():
        raise VideoNotesError(
            "notes_upload_path must be provided when creating the video asset",
        )

    upload_folder(
        notes_dir,
        str(asset.ai_outputs_folder_url),
        use_settings_secret=True,
        public_read=True,
        content_type=None,
        http_method="PUT",
    )

    notes_key = get_storage_path(
        filename=FULL_NOTES_WITH_TIMESTAMPS_FILENAME,
        existing_object_path=asset.notes_upload_path,
    )
    if "/" not in notes_key:
        raise VideoNotesError(
            "notes_upload_path must be a storage folder prefix or full object key",
        )

    asset.update_notes_upload_path(notes_key)

    delete_files_in_local_dir(
        notes_dir,
        exclude_filenames={SEG_FULL_NOTES_FILENAME},
    )
    return True
