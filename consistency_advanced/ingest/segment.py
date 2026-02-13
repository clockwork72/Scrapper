"""Stage 0: ingest, clean, section-tree build, and chunking with provenance."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path
from typing import Iterable, List

from bs4 import BeautifulSoup

from consistency_advanced.core.models import ClauseNode, PolicyChunk, PolicyDocument, SectionNode


@dataclass(frozen=True)
class Section:
    """Backward-compatible section object used by tests and callers."""

    section_id: str
    title: str
    level: int
    section_path: str
    start_offset: int
    end_offset: int


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+\.)\s+(.+?)\s*$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def _normalize_heading(text: str) -> str:
    text = _LINK_RE.sub(lambda m: m.group(1), text)
    return re.sub(r"\s+", " ", text).strip()


def _is_title_like(text: str) -> bool:
    if len(text) > 90:
        return False
    words = [w for w in re.split(r"\s+", text) if w]
    if not words:
        return False
    caps = sum(1 for w in words if w[:1].isupper())
    return caps / len(words) >= 0.6


def _is_fallback_heading(text: str, prev_blank: bool, next_blank: bool) -> bool:
    if not (prev_blank and next_blank):
        return False
    if text.endswith((".", ";", ",")):
        return False
    return _is_title_like(text) or text.endswith(":")


def _extract_toc_titles(lines: List[str]) -> list[str]:
    titles: list[str] = []
    toc_mode = False
    toc_window = 0
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            if toc_mode:
                toc_window += 1
            if toc_window >= 6:
                toc_mode = False
            continue

        low = line.lower()
        if "table of contents" in low or (low == "contents" and idx < 30):
            toc_mode = True
            toc_window = 0
            continue

        if not toc_mode:
            continue

        match = _BULLET_RE.match(line)
        if not match:
            toc_window += 1
            if toc_window >= 6:
                toc_mode = False
            continue

        title = _normalize_heading(match.group(1))
        if title:
            titles.append(title)

    return titles


def clean_policy_text(raw_text: str) -> str:
    """Best-effort cleaner preserving legal/policy content and headings."""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    if _TAG_RE.search(text):
        soup = BeautifulSoup(text, "lxml")
        text = soup.get_text("\n")

    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        line = _LINK_RE.sub(lambda m: m.group(1), line)
        line = _MULTI_SPACE_RE.sub(" ", line).strip()
        if not line:
            cleaned_lines.append("")
            continue
        # Keep only text-rich lines.
        if sum(ch.isalnum() for ch in line) < 3:
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = _BLANK_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def load_policy(source_path: str, *, policy_id: str, party_type: str) -> PolicyDocument:
    """Load a policy file and produce section/clauses with provenance ids."""
    path = Path(source_path)
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    cleaned_text = clean_policy_text(raw_text)
    sections = build_section_tree(cleaned_text)

    section_nodes = [
        SectionNode(
            section_id=s.section_id,
            level=s.level,
            title=s.title,
            section_path=s.section_path,
            start_offset=s.start_offset,
            end_offset=s.end_offset,
        )
        for s in sections
    ]

    clauses = build_clause_nodes(cleaned_text, policy_id=policy_id, sections=sections)
    definitions = extract_definitions(clauses)

    return PolicyDocument(
        policy_id=policy_id,
        party_type=party_type,
        source_path=str(path),
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        sections=section_nodes,
        clauses=clauses,
        definitions=definitions,
    )


def build_section_tree(text: str) -> List[Section]:
    """Parse headings/sections to build a section tree."""
    if not text:
        return [Section("section_1", "Document", 1, "Document", 0, 0)]

    lines = text.splitlines()
    toc_titles = {t.lower() for t in _extract_toc_titles(lines)}

    sections: list[Section] = []
    stack: list[Section] = []
    cursor = 0

    for idx, raw in enumerate(lines):
        line = raw.rstrip("\n")
        stripped = line.strip()
        line_start = cursor
        cursor += len(raw) + 1
        if not stripped:
            continue

        heading_level: int | None = None
        heading_text: str | None = None

        m = _HEADING_RE.match(stripped)
        if m:
            heading_level = len(m.group(1))
            heading_text = _normalize_heading(m.group(2))
        else:
            prev_blank = idx == 0 or not lines[idx - 1].strip()
            next_blank = idx == len(lines) - 1 or not lines[idx + 1].strip()
            candidate = _normalize_heading(stripped)
            if candidate.lower() in toc_titles:
                heading_level = 2
                heading_text = candidate
            elif _is_fallback_heading(candidate, prev_blank, next_blank):
                heading_level = 2
                heading_text = candidate

        if heading_level is None or not heading_text:
            continue

        while stack and stack[-1].level >= heading_level:
            stack.pop()

        section_id = f"section_{len(sections) + 1}"
        path_parts = [s.title for s in stack] + [heading_text]
        section_path = " > ".join(path_parts)

        sections.append(
            Section(
                section_id=section_id,
                title=heading_text,
                level=heading_level,
                section_path=section_path,
                start_offset=line_start,
                end_offset=-1,
            )
        )
        stack.append(sections[-1])

    if not sections:
        return [Section("section_1", "Document", 1, "Document", 0, len(text))]

    for i, sec in enumerate(sections):
        end_offset = sections[i + 1].start_offset if i + 1 < len(sections) else len(text)
        sections[i] = Section(
            section_id=sec.section_id,
            title=sec.title,
            level=sec.level,
            section_path=sec.section_path,
            start_offset=sec.start_offset,
            end_offset=end_offset,
        )

    return sections


def _line_clause_spans(text: str, start_offset: int, end_offset: int) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    segment = text[start_offset:end_offset]
    local_cursor = 0
    for raw_line in segment.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        global_start = start_offset + local_cursor
        local_cursor += len(raw_line)
        if not stripped:
            continue
        # Remove common bullet markers while preserving provenance offsets.
        bullet_match = _BULLET_RE.match(stripped)
        if bullet_match:
            candidate = bullet_match.group(1).strip()
        else:
            candidate = stripped
        if candidate.startswith("#"):
            continue
        if len(candidate) < 8:
            continue
        # Split long lines into sentence-like clauses.
        pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", candidate)
        if len(pieces) == 1:
            quote = candidate
            out.append((global_start, global_start + len(quote), quote))
            continue
        running = 0
        for piece in pieces:
            piece = piece.strip()
            if len(piece) < 6:
                running += len(piece) + 1
                continue
            ps = global_start + running
            pe = ps + len(piece)
            out.append((ps, pe, piece))
            running += len(piece) + 1
    return out


def build_clause_nodes(text: str, *, policy_id: str, sections: list[Section]) -> list[ClauseNode]:
    clauses: list[ClauseNode] = []
    for sec in sections:
        spans = _line_clause_spans(text, sec.start_offset, sec.end_offset)
        for s, e, quote in spans:
            clause_id = f"{policy_id}.{sec.section_id}.clause_{len(clauses) + 1}"
            clauses.append(
                ClauseNode(
                    clause_id=clause_id,
                    policy_id=policy_id,
                    section_id=sec.section_id,
                    section_path=sec.section_path,
                    start_char=s,
                    end_char=e,
                    text=quote,
                )
            )
    return clauses


def extract_definitions(clauses: list[ClauseNode]) -> dict[str, str]:
    """Collect simple glossary-style definitions for downstream extraction context."""
    definitions: dict[str, str] = {}
    pattern = re.compile(r"^\s*([A-Z][A-Za-z0-9\-\s]{2,50})\s+(?:means|refers to|is defined as)\s+(.+)$", re.I)
    for clause in clauses:
        m = pattern.match(clause.text)
        if not m:
            continue
        key = re.sub(r"\s+", " ", m.group(1)).strip().lower()
        val = m.group(2).strip()
        if key and val and key not in definitions:
            definitions[key] = val
    return definitions


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def chunk_policy(
    policy: PolicyDocument,
    *,
    target_tokens: int = 1000,
    overlap_percent: float = 0.12,
    min_tokens: int = 120,
) -> Iterable[PolicyChunk]:
    """Chunk by section first; then split large sections while preserving section provenance."""
    clauses_by_section: dict[str, list[ClauseNode]] = {}
    section_path_by_id: dict[str, str] = {s.section_id: s.section_path for s in policy.sections}
    for clause in policy.clauses:
        clauses_by_section.setdefault(clause.section_id, []).append(clause)

    chunk_count = 0
    overlap_target = max(1, int(target_tokens * max(0.0, min(0.5, overlap_percent))))

    for section in policy.sections:
        sec_clauses = clauses_by_section.get(section.section_id, [])
        if not sec_clauses:
            continue

        window: list[ClauseNode] = []
        window_tokens = 0
        emitted_in_section = False

        def flush_window(items: list[ClauseNode]) -> PolicyChunk:
            nonlocal chunk_count
            chunk_count += 1
            text = "\n".join(c.text for c in items).strip()
            start = min(c.start_char for c in items)
            end = max(c.end_char for c in items)
            chunk_hash = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
            return PolicyChunk(
                chunk_id=f"{policy.policy_id}.chunk_{chunk_count}",
                policy_id=policy.policy_id,
                party_type=policy.party_type,
                section_id=section.section_id,
                section_path=section_path_by_id.get(section.section_id, section.section_path),
                char_start=start,
                char_end=end,
                chunk_hash=chunk_hash,
                text=text,
                clause_ids=[c.clause_id for c in items],
            )

        for clause in sec_clauses:
            c_tokens = max(1, _word_count(clause.text))
            if window and window_tokens + c_tokens > target_tokens:
                yield flush_window(window)
                emitted_in_section = True

                # overlap in same section only
                if overlap_target > 0:
                    overlap_items: list[ClauseNode] = []
                    overlap_tokens = 0
                    for existing in reversed(window):
                        t = max(1, _word_count(existing.text))
                        if overlap_tokens + t > overlap_target:
                            break
                        overlap_items.insert(0, existing)
                        overlap_tokens += t
                    window = overlap_items
                    window_tokens = overlap_tokens
                else:
                    window = []
                    window_tokens = 0

            window.append(clause)
            window_tokens += c_tokens

        if window and window_tokens >= min_tokens:
            yield flush_window(window)
        elif window and not emitted_in_section:
            # Keep one short chunk if the section is short overall.
            yield flush_window(window)
