"""Ontology loading utilities for the advanced consistency pipeline."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class VocabTerm:
    uri: str
    label: str
    parent: Optional[str] = None
    alt_labels: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Vocabulary:
    actions: List[VocabTerm]
    subjects: List[VocabTerm]
    data_categories: List[VocabTerm]
    purposes: List[VocabTerm]
    views: List[VocabTerm]
    recipients: List[VocabTerm]
    legal_bases: List[VocabTerm]
    context: Dict[str, List[VocabTerm]]

    def label_to_uri(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for term in self.actions + self.subjects + self.purposes + self.views + self.recipients + self.legal_bases:
            mapping[term.label] = term.uri
            for alt in term.alt_labels:
                mapping[alt] = term.uri
        for _, terms in self.context.items():
            for term in terms:
                mapping[term.label] = term.uri
                for alt in term.alt_labels:
                    mapping[alt] = term.uri
        return mapping

    def parent_map(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for term in self.actions + self.subjects + self.purposes + self.views + self.recipients + self.legal_bases:
            if term.parent:
                mapping[term.uri] = term.parent
        for _, terms in self.context.items():
            for term in terms:
                if term.parent:
                    mapping[term.uri] = term.parent
        return mapping


@dataclass(frozen=True)
class CompatibilityRules:
    purpose_subsumption: List[Tuple[str, str]]
    subject_subsumption: List[Tuple[str, str]]
    context_compatibility: Dict[str, List[Dict[str, object]]]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_vocab(path: str | Path) -> Vocabulary:
    """Load vocabulary from a JSON file or a vocab directory."""
    path = Path(path)
    if path.is_dir():
        return _load_vocab_dir(path)
    if path.suffix.lower() != ".json":
        raise ValueError("Use vocab.json or vocab/ directory to avoid YAML dependencies.")
    return _load_vocab_json(path)


def _to_terms(items: Iterable[dict]) -> List[VocabTerm]:
    terms: List[VocabTerm] = []
    for item in items:
        uri = item.get("uri") or item.get("id")
        if not uri:
            # Skip malformed terms but keep loader tolerant of mixed vocab formats.
            continue
        label = item.get("label") or item.get("preferred_label") or str(uri).split(":", 1)[-1]
        terms.append(
            VocabTerm(
                uri=uri,
                label=label,
                parent=item.get("parent") or item.get("parent_id"),
                alt_labels=tuple(item.get("alt_labels", [])),
            )
        )
    return terms


def _load_vocab_json(path: Path) -> Vocabulary:
    data = _load_json(path)
    context = {key: _to_terms(items) for key, items in data.get("context", {}).items()}
    subjects = _to_terms(data.get("subjects", []))
    return Vocabulary(
        actions=_to_terms(data.get("actions", [])),
        subjects=subjects,
        data_categories=subjects,
        purposes=_to_terms(data.get("purposes", [])),
        views=_to_terms(data.get("views", [])),
        recipients=[],
        legal_bases=[],
        context=context,
    )


def _load_vocab_dir(path: Path) -> Vocabulary:
    def load_terms(file_name: str) -> List[VocabTerm]:
        payload = _load_json(path / file_name)
        return _to_terms(payload.get("terms", []))

    actions = load_terms("actions.json")
    purposes = load_terms("purposes.json")
    data_categories = load_terms("data_categories.json")
    recipients = load_terms("recipients.json")
    legal_bases = load_terms("legal_bases.json")
    views = load_terms("views.json")

    return Vocabulary(
        actions=actions,
        subjects=data_categories,
        data_categories=data_categories,
        purposes=purposes,
        views=views,
        recipients=recipients,
        legal_bases=legal_bases,
        context={},
    )


def load_rules(path: str | Path) -> CompatibilityRules:
    """Load compatibility rules (JSON only for now)."""
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("Use compatibility_rules.json for now to avoid extra YAML dependencies.")
    data = _load_json(path)
    return CompatibilityRules(
        purpose_subsumption=[(item["parent"], item["child"]) for item in data.get("purpose_subsumption", [])],
        subject_subsumption=[(item["parent"], item["child"]) for item in data.get("subject_subsumption", [])],
        context_compatibility=data.get("context_compatibility", {}),
    )
