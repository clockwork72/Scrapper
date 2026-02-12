"""Policy ingestion + segmentation placeholders."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class PolicyChunk:
    policy_id: str
    party_type: str  # "1P" or "3P"
    section_path: str
    char_start: int
    char_end: int
    chunk_hash: str
    text: str


@dataclass(frozen=True)
class PolicyDocument:
    policy_id: str
    party_type: str
    raw_text: str


def load_policy(source_path: str) -> PolicyDocument:
    """Load a policy file (PDF/HTML/TXT). Placeholder."""
    raise NotImplementedError("Implement PDF/HTML/TXT ingestion here.")


def build_section_tree(text: str) -> List[str]:
    """Parse headings/sections to build a section tree. Placeholder."""
    raise NotImplementedError("Implement H1/H2/H3 parsing and section tree.")


def chunk_policy(policy: PolicyDocument) -> Iterable[PolicyChunk]:
    """Chunk a policy by section with overlap. Placeholder."""
    raise NotImplementedError("Implement section-first chunking with provenance.")
