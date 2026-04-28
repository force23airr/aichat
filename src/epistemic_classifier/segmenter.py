from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SPEAKER_LINE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")
TURN_HEADER = re.compile(r"^#{1,6}\s+Turn\s+\d+\s+\(([^)]+)\)\s*$", re.IGNORECASE)
HEADER = re.compile(r"^#{1,6}\s+")
BULLET = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+?)\s*$")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=(?:[\"'“”‘’])?[A-Z])")

# Common abbreviations whose internal periods must NOT trigger sentence splits.
# Trailing-period abbreviations (e.g., "Dr." in "Dr. Smith said hi.") and
# multi-period ones ("e.g.", "i.e.") are both handled by masking before splitting.
_ABBREVIATIONS = (
    "Dr", "Mr", "Mrs", "Ms", "Prof", "Sr", "Jr", "St",
    "vs", "etc", "No", "Inc", "Ltd", "Co",
    "e.g", "i.e", "cf", "viz",
    "U.S", "U.K", "a.m", "p.m", "A.M", "P.M",
)
_ABBR_MASK = "\x00"
_ABBR_PATTERNS = [
    (re.compile(rf"\b{re.escape(abbr)}\."), abbr.replace(".", _ABBR_MASK) + _ABBR_MASK)
    for abbr in _ABBREVIATIONS
]


@dataclass(frozen=True)
class Segment:
    original: str
    cleaned: str
    speaker: str | None
    sentence_index: int
    prior_sentence: str | None = None


def strip_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    masked = text
    for pattern, replacement in _ABBR_PATTERNS:
        masked = pattern.sub(replacement, masked)
    parts = SENTENCE_BOUNDARY.split(masked)
    return [part.replace(_ABBR_MASK, ".").strip() for part in parts if part.strip()]


def _emit_sentence(
    sentence: str,
    speaker: str | None,
    index: int,
    prior: str | None,
) -> Segment:
    return Segment(
        original=sentence.strip(),
        cleaned=strip_markdown(sentence),
        speaker=speaker,
        sentence_index=index,
        prior_sentence=prior,
    )


def segment_text(text: str, speaker: str | None = None) -> list[Segment]:
    segments: list[Segment] = []
    paragraph: list[str] = []
    in_code = False
    prior: str | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph, prior
        if not paragraph:
            return
        block = " ".join(paragraph).strip()
        paragraph = []
        for sentence in split_sentences(block):
            segment = _emit_sentence(sentence, speaker, len(segments), prior)
            if segment.cleaned:
                segments.append(segment)
                prior = segment.cleaned

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            flush_paragraph()
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line:
            flush_paragraph()
            continue
        if HEADER.match(line):
            flush_paragraph()
            continue
        bullet_match = BULLET.match(line)
        if bullet_match:
            flush_paragraph()
            bullet_text = bullet_match.group(1)
            # A bullet may contain multiple sentences; classify each separately
            # so a long bullet with several ideas isn't stamped with one label.
            bullet_sentences = split_sentences(bullet_text) or [bullet_text]
            for sentence in bullet_sentences:
                segment = _emit_sentence(sentence, speaker, len(segments), prior)
                if segment.cleaned:
                    segments.append(segment)
                    prior = segment.cleaned
            continue
        paragraph.append(line)
        if line.endswith((".", "?", "!")):
            flush_paragraph()

    flush_paragraph()
    return segments


def parse_transcript(transcript_path: str | Path) -> list[Segment]:
    path = Path(transcript_path)
    segments: list[Segment] = []
    current_speaker: str | None = None
    current_lines: list[str] = []
    prior_by_speaker: dict[str | None, str | None] = {}

    def flush_turn() -> None:
        nonlocal current_lines
        if not current_lines:
            return
        if current_speaker is None:
            current_lines = []
            return
        parsed = segment_text("\n".join(current_lines), speaker=current_speaker)
        prior = prior_by_speaker.get(current_speaker)
        for segment in parsed:
            indexed = Segment(
                original=segment.original,
                cleaned=segment.cleaned,
                speaker=current_speaker,
                sentence_index=len(segments),
                prior_sentence=prior,
            )
            segments.append(indexed)
            prior = indexed.cleaned
        prior_by_speaker[current_speaker] = prior
        current_lines = []

    in_code = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            current_lines.append(line)
            continue
        if not in_code:
            speaker_match = SPEAKER_LINE.match(line.strip())
            if speaker_match:
                flush_turn()
                current_speaker = speaker_match.group(1).strip()
                rest = speaker_match.group(2).strip()
                current_lines = [rest] if rest else []
                continue
            turn_match = TURN_HEADER.match(line.strip())
            if turn_match:
                flush_turn()
                current_speaker = turn_match.group(1).strip()
                current_lines = []
                continue
        current_lines.append(line)

    flush_turn()
    return segments
