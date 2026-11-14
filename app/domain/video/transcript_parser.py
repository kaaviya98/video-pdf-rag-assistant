from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

import numpy as np
from django.conf import settings
from langchain_community.utils.math import cosine_similarity

from app.domain.video.data_classes import VideoTranscriptChunk
from app.models.asset import Asset, AssetFileType
from app.models.organization import Organization
from app.models.transcript import TranscriptLine
from app.utils.embeddings import embed_video_transcript_window_texts


TIME_GROUP_DURATION_SECONDS = 2 * 60
MAX_CHUNK_DURATION_SECONDS = 5 * 60
MIN_CHUNK_DURATION_SECONDS = 2 * 60


def parse_asset_transcript_into_vector_chunks(
    asset: Asset,
) -> list[VideoTranscriptChunk]:
    if asset.file_type != AssetFileType.VIDEO:
        raise ValueError("Transcript chunk building is only supported for VIDEO assets")

    lines = list(
        TranscriptLine.objects.filter(asset=asset).order_by(
            "start_sec",
            "end_sec",
            "line_number",
        ),
    )
    return build_transcript_chunks_from_lines(
        lines,
        scope_key=asset.scope_key,
        organization=asset.organization if asset.organization_id else None,
    )


def build_transcript_chunks_from_lines(
    lines: Sequence[TranscriptLine],
    *,
    scope_key: str | None = None,
    organization: Organization | None = None,
) -> list[VideoTranscriptChunk]:
    if not lines:
        return []

    time_groups = _group_lines_by_time_span(lines)
    if not time_groups:
        return []

    texts = [" ".join(line.text for line in group) for group in time_groups]
    embeddings = embed_video_transcript_window_texts(
        texts,
        scope_key=scope_key,
        organization=organization,
    )

    chunk_line_groups = _merge_adjacent_time_groups_by_similarity(
        time_groups, embeddings
    )
    chunk_line_groups = _merge_short_tail_chunks(chunk_line_groups)

    chunks = _make_chunks_from_line_groups(chunk_line_groups)

    return rechunk_transcript_chunks_by_chars(chunks)


def _make_chunks_from_line_groups(
    chunk_line_groups: list[list[TranscriptLine]],
) -> list[VideoTranscriptChunk]:
    chunks: list[VideoTranscriptChunk] = []
    for index, lines_group in enumerate(chunk_line_groups, start=1):
        chunks.append(
            VideoTranscriptChunk(
                chunk_order=index,
                start_sec=lines_group[0].start_sec,
                end_sec=lines_group[-1].end_sec,
                lines=list(lines_group),
            ),
        )
    return chunks


def _group_lines_by_time_span(
    lines: Sequence[TranscriptLine],
) -> list[list[TranscriptLine]]:
    time_groups: list[list[TranscriptLine]] = []
    current: list[TranscriptLine] = []
    group_start: Decimal | None = None

    for line in lines:
        line_start = line.start_sec

        if not current:
            current = [line]
            group_start = line_start
            continue

        current_end = current[-1].end_sec
        assert group_start is not None

        if (current_end - group_start) >= Decimal(str(TIME_GROUP_DURATION_SECONDS)):
            time_groups.append(current)
            current = [line]
            group_start = line_start
        else:
            current.append(line)

    if current:
        time_groups.append(current)

    return time_groups


def _merge_adjacent_time_groups_by_similarity(
    time_groups: list[list[TranscriptLine]],
    embeddings: list[list[float]],
) -> list[list[TranscriptLine]]:
    if not time_groups:
        return []

    assert len(time_groups) == len(embeddings)

    chunk_line_groups: list[list[TranscriptLine]] = []
    current_indices: list[int] = [0]

    similarities: list[float] = []
    for i in range(len(time_groups) - 1):
        res = cosine_similarity([embeddings[i]], [embeddings[i + 1]])
        similarities.append(float(res[0][0]))

    if similarities:
        global_threshold = _similarity_percentile_threshold(similarities)
        count = len(similarities)
        radius = min(3, max(1, count // 20))
    else:
        global_threshold = 0.0
        radius = 1

    for idx in range(1, len(time_groups)):
        candidate_indices = current_indices + [idx]
        if _duration_seconds_for_time_group_span(
            time_groups,
            first_group_index=current_indices[0],
            last_group_index=idx,
        ) > Decimal(str(MAX_CHUNK_DURATION_SECONDS)):
            chunk_line_groups.append(_flatten_time_groups(time_groups, current_indices))
            current_indices = [idx]
            continue

        transition_index = idx - 1
        is_split, _reason = _should_split_at_similarity_valley(
            transition_index,
            similarities,
            global_threshold,
            radius,
        )

        if is_split and _duration_seconds_for_time_group_span(
            time_groups,
            first_group_index=current_indices[0],
            last_group_index=current_indices[-1],
        ) >= Decimal(str(MIN_CHUNK_DURATION_SECONDS)):
            chunk_line_groups.append(_flatten_time_groups(time_groups, current_indices))
            current_indices = [idx]
            continue

        current_indices.append(idx)

    if current_indices:
        chunk_line_groups.append(_flatten_time_groups(time_groups, current_indices))

    return chunk_line_groups


def _flatten_time_groups(
    time_groups: list[list[TranscriptLine]],
    indices: list[int],
) -> list[TranscriptLine]:
    merged: list[TranscriptLine] = []
    for index in indices:
        merged.extend(time_groups[index])
    return merged


def _duration_seconds_for_time_group_span(
    time_groups: list[list[TranscriptLine]],
    *,
    first_group_index: int,
    last_group_index: int,
) -> Decimal:
    first_line = time_groups[first_group_index][0]
    last_line = time_groups[last_group_index][-1]
    return last_line.end_sec - first_line.start_sec


def _merge_short_tail_chunks(
    chunks: list[list[TranscriptLine]],
) -> list[list[TranscriptLine]]:
    if len(chunks) < 2:
        return chunks

    last = chunks[-1]
    prev = chunks[-2]

    last_duration = last[-1].end_sec - last[0].start_sec
    prev_duration = prev[-1].end_sec - prev[0].start_sec

    if last_duration < Decimal(str(MIN_CHUNK_DURATION_SECONDS)) and (
        (last_duration + prev_duration) <= Decimal(str(MAX_CHUNK_DURATION_SECONDS))
    ):
        return chunks[:-2] + [prev + last]

    return chunks


def _similarity_percentile_threshold(similarities: list[float]) -> float:
    count = len(similarities)
    if count == 0:
        return 0.0
    if count < 5:
        p = 10
    elif count < 15:
        p = 20
    else:
        p = 25
    return float(np.percentile(similarities, p))


def _should_split_at_similarity_valley(
    index: int,
    similarities: list[float],
    threshold: float,
    radius: int,
) -> tuple[bool, str]:
    if not similarities:
        return False, ""

    val = similarities[index]

    if val >= threshold:
        return False, ""

    start = max(0, index - radius)
    end = min(len(similarities), index + radius + 1)
    neighborhood = similarities[start:index] + similarities[index + 1 : end]

    if not neighborhood:
        return True, "global_outlier (isolated)"

    neigh = np.array(neighborhood, dtype=float)
    neigh_mean = float(neigh.mean())
    neigh_std = float(neigh.std()) or 1e-6

    z_score = (val - neigh_mean) / neigh_std

    local_floor = float(np.percentile(neigh, 10))
    is_local_drop = z_score <= -1.0
    is_strong_valley = val <= (local_floor + 1e-9)

    if is_local_drop and is_strong_valley:
        reason = f"val={val:.4f}, z={z_score:.2f}, floor={local_floor:.4f}"
        return True, reason

    return False, ""


def rechunk_transcript_chunks_by_chars(
    chunks: list[VideoTranscriptChunk],
) -> list[VideoTranscriptChunk]:
    if not chunks:
        return []

    max_chars, min_chars = get_chunk_char_limits()
    new_chunks: list[VideoTranscriptChunk] = []
    current_chunk_lines: list[TranscriptLine] = []
    current_len = 0

    def flush_chunk_if_any(next_order: int) -> int:
        nonlocal current_chunk_lines, current_len
        if not current_chunk_lines:
            return next_order

        new_chunks.append(
            VideoTranscriptChunk(
                chunk_order=next_order,
                start_sec=current_chunk_lines[0].start_sec,
                end_sec=current_chunk_lines[-1].end_sec,
                lines=list(current_chunk_lines),
            ),
        )
        current_chunk_lines = []
        current_len = 0
        return next_order + 1

    next_order = 1

    for chunk in chunks:
        for line in chunk.lines:
            line_text = line.text or ""
            line_chars = len(line_text)

            if not current_chunk_lines:
                current_chunk_lines.append(line)
                current_len = line_chars
                continue

            projected_len = current_len + 1 + line_chars

            if projected_len > max_chars and current_len >= min_chars:
                next_order = flush_chunk_if_any(next_order)
                current_chunk_lines.append(line)
                current_len = line_chars
                continue

            current_chunk_lines.append(line)
            current_len = projected_len

    flush_chunk_if_any(next_order)

    return new_chunks


def get_chunk_char_limits() -> tuple[int, int]:
    max_chars = getattr(settings, "VIDEO_MAX_CHUNK_CHARS", 2200)
    min_chars = getattr(settings, "VIDEO_MIN_CHUNK_CHARS", 1200)
    if min_chars > max_chars:
        min_chars = int(max_chars * 0.25)
    return int(max_chars), int(min_chars)
