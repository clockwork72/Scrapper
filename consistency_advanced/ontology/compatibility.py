"""Compatibility and subsumption helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .loader import CompatibilityRules, Vocabulary


@dataclass(frozen=True)
class HierarchyIndex:
    parent_map: Dict[str, str]
    derived_edges: Set[Tuple[str, str]]


def build_hierarchy_index(vocab: Vocabulary, rules: CompatibilityRules) -> HierarchyIndex:
    """Build a combined parent map for subsumption checks."""
    parent_map = vocab.parent_map()
    derived_edges: Set[Tuple[str, str]] = set()

    for parent, child in rules.purpose_subsumption:
        derived_edges.add((parent, child))
    for parent, child in rules.subject_subsumption:
        derived_edges.add((parent, child))

    return HierarchyIndex(parent_map=parent_map, derived_edges=derived_edges)


def is_subsumed(parent: str, child: str, index: HierarchyIndex) -> bool:
    """Return True if parent subsumes child via explicit rules or hierarchy."""
    if parent == child:
        return True
    if (parent, child) in index.derived_edges:
        return True

    current = child
    visited: Set[str] = set()
    while current in index.parent_map and current not in visited:
        visited.add(current)
        current = index.parent_map[current]
        if current == parent:
            return True
    return False


def purpose_in_closure(target: str, allowed: Iterable[str], index: HierarchyIndex) -> bool:
    """Check if target is within the closure of allowed purposes."""
    for allowed_uri in allowed:
        if is_subsumed(allowed_uri, target, index):
            return True
    return False


def is_context_compatible(a: Optional[str], b: Optional[str], rules: CompatibilityRules) -> bool:
    """Check compatibility for context terms."""
    if a is None or b is None:
        return True
    if a == b:
        return True

    for facet, entries in rules.context_compatibility.items():
        for rule in entries:
            if (rule.get("a") == a and rule.get("b") == b) or (rule.get("a") == b and rule.get("b") == a):
                return bool(rule.get("compatible", False))
    return True
