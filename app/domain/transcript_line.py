from typing import Iterable

from app.models.asset import Asset
from app.models.transcript import TranscriptLine


def get_transcript_for_timestamp(
    asset: Asset,
    timestamp: float | None = None,
    *,
    period_start: float | None = None,
    period_end: float | None = None,
) -> str:
    period_requested = period_start is not None or period_end is not None
    if period_requested:
        overlapping = _transcript_lines_overlapping_period(
            asset, period_start, period_end
        )
        if overlapping:
            return _format_transcript_lines(overlapping)
        timestamp = _fallback_second_inside_period(period_start, period_end)
        if timestamp is None:
            return ""

    if timestamp is None:
        return ""

    covering = list(
        TranscriptLine.objects.filter(
            asset=asset,
            start_sec__lte=timestamp,
            end_sec__gte=timestamp,
        ).order_by("line_number"),
    )
    if covering:
        return _format_transcript_lines(covering)

    nearest = _nearest_transcript_line_by_start(asset, timestamp)
    if nearest is None:
        return ""
    nearby = _transcript_lines_by_line_number_range(
        asset, nearest.line_number, radius=1
    )
    return _format_transcript_lines(nearby)


def get_transcript_for_time_period(
    asset: Asset,
    period_start: float | None = None,
    period_end: float | None = None,
) -> str:
    return get_transcript_for_timestamp(
        asset,
        timestamp=None,
        period_start=period_start,
        period_end=period_end,
    )


def get_transcript_for_line_numbers(asset: Asset, line_numbers: Iterable[int]) -> str:
    nums = sorted({int(n) for n in line_numbers})
    if not nums:
        return ""
    lines = TranscriptLine.objects.filter(
        asset=asset,
        line_number__in=nums,
    ).order_by("line_number")
    return _format_transcript_lines(lines)


def _format_transcript_lines(lines: Iterable[TranscriptLine]) -> str:
    return "\n".join(f"[L{l.line_number}]{l.text}" for l in lines)


def _fallback_second_inside_period(
    period_start: float | None,
    period_end: float | None,
) -> float | None:
    if period_start is not None and period_end is not None:
        return (period_start + period_end) / 2.0
    if period_start is not None:
        return period_start
    return period_end


def _transcript_lines_overlapping_period(
    asset: Asset,
    period_start: float | None,
    period_end: float | None,
) -> list[TranscriptLine]:
    qs = TranscriptLine.objects.filter(asset=asset)
    if period_start is not None:
        qs = qs.filter(end_sec__gte=period_start)
    if period_end is not None:
        qs = qs.filter(start_sec__lte=period_end)
    return list(qs.order_by("line_number"))


def _nearest_transcript_line_by_start(
    asset: Asset, seconds: float
) -> TranscriptLine | None:
    before = (
        TranscriptLine.objects.filter(asset=asset, start_sec__lte=seconds)
        .order_by("-start_sec")
        .first()
    )
    after = (
        TranscriptLine.objects.filter(asset=asset, start_sec__gt=seconds)
        .order_by("start_sec")
        .first()
    )
    candidates = [line for line in (before, after) if line is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda line: abs(float(line.start_sec) - seconds))


def _transcript_lines_by_line_number_range(
    asset: Asset,
    center_line_number: int,
    *,
    radius: int,
) -> list[TranscriptLine]:
    low = max(1, center_line_number - radius)
    high = center_line_number + radius
    return list(
        TranscriptLine.objects.filter(
            asset=asset,
            line_number__gte=low,
            line_number__lte=high,
        ).order_by("line_number"),
    )
