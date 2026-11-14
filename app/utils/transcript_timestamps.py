from __future__ import annotations

import re

from app.models.asset import Asset  # noqa: TC001
from app.models.transcript import TranscriptLine

NOTES_TIMESTAMP_STYLE = """<style>
.video-timestamp { color: #6b7280; font-weight: 500; }
</style>

"""

_LINE_REF_RE = re.compile(r"\bL\s*(\d+)\b", re.IGNORECASE)

_COMMA_LINE_NUM_SUFFIX_RE = re.compile(r",\s*(?!L)(\d+)\b")

_PAREN_SEGMENT_RE = re.compile(r"\(([^)]*)\)")

_BRACKET_SEGMENT_RE = re.compile(r"\[\s*([^]]*)\s*\]")


def replace_line_refs_with_timestamps(
    asset: Asset,
    markdown: str,
    *,
    wrap_for_styling: bool = True,
    prepend_style: bool = True,
) -> str:
    """
    Turn transcript line refs into display timestamps.

    Handles sloppy model output in one pair of parentheses or brackets, for example:
    - (L12), (l12), (L0012)
    - (L12-L18) hyphen; model output may use Unicode en/em dash between line numbers
    - (L12, L18), (L12; L18), (L12 / L18), (L12 | L18), (L12 and L18)
    - messy spaces: ( L  12 ,   L 18 )
    """
    line_map = line_number_to_timestamps(asset)
    if not line_map:
        return markdown

    text = _replace_paren_line_refs(
        markdown,
        line_map,
        wrap_for_styling=wrap_for_styling,
    )
    text = _replace_bracket_line_refs(
        text,
        line_map,
        wrap_for_styling=wrap_for_styling,
    )

    if prepend_style and wrap_for_styling and text.strip():
        text = NOTES_TIMESTAMP_STYLE + text
    return text


def extract_line_numbers_from_markup(text: str) -> list[int]:
    normalized = _normalize_line_ref_segment(text)
    nums = [int(m.group(1)) for m in _LINE_REF_RE.finditer(normalized)]
    if not nums:
        return nums
    for m in _COMMA_LINE_NUM_SUFFIX_RE.finditer(normalized):
        try:
            nums.append(int(m.group(1)))
        except ValueError:
            continue
    return _dedupe_preserve_order(nums)


def line_number_to_timestamps(asset: Asset) -> dict[int, tuple[float, float]]:
    lines = TranscriptLine.objects.filter(asset=asset).only(
        "line_number",
        "start_sec",
        "end_sec",
    )
    return {tl.line_number: (float(tl.start_sec), float(tl.end_sec)) for tl in lines}


# --- Internal ---


def _replace_paren_line_refs(
    markdown: str,
    line_map: dict[int, tuple[float, float]],
    *,
    wrap_for_styling: bool,
) -> str:
    def repl(match: re.Match[str]) -> str:
        inner = match.group(1)
        if "(" in inner:
            return match.group(0)
        nums = extract_line_numbers_from_markup(inner)
        if not nums:
            return match.group(0)
        for n in nums:
            if n in line_map:
                return _format_timestamp_for_line(
                    n,
                    line_map,
                    wrap_for_styling=wrap_for_styling,
                )
        return match.group(0)

    return _PAREN_SEGMENT_RE.sub(repl, markdown)


def _replace_bracket_line_refs(
    markdown: str,
    line_map: dict[int, tuple[float, float]],
    *,
    wrap_for_styling: bool,
) -> str:
    def repl(match: re.Match[str]) -> str:
        inner = match.group(1)
        if "[" in inner:
            return match.group(0)
        nums = extract_line_numbers_from_markup(inner)
        if not nums:
            return match.group(0)
        for n in nums:
            if n in line_map:
                return _format_timestamp_for_line(
                    n,
                    line_map,
                    wrap_for_styling=wrap_for_styling,
                )
        return match.group(0)

    return _BRACKET_SEGMENT_RE.sub(repl, markdown)


def _format_timestamp_for_line(
    line_number: int,
    line_map: dict[int, tuple[float, float]],
    *,
    wrap_for_styling: bool,
) -> str:
    start_sec, _ = line_map[line_number]
    ts = _sec_to_timestamp(start_sec)
    wrapped = _wrap_timestamp(ts, wrap_for_styling=wrap_for_styling)
    return f"({wrapped})"


def _normalize_line_ref_segment(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+and\s+", ", ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*[;|]\s*", ", ", s)
    return re.sub(r"\s+/\s+", ", ", s)


def _dedupe_preserve_order(nums: list[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for n in nums:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _sec_to_timestamp(sec: float) -> str:
    sec = max(0, float(sec))
    total_secs = int(sec)
    m, s = divmod(total_secs, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _wrap_timestamp(ts: str, *, wrap_for_styling: bool) -> str:
    if wrap_for_styling:
        return f'<span class="video-timestamp">{ts}</span>'
    return ts
