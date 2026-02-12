"""RDF graph build placeholder."""
from __future__ import annotations


def build_triples(normalized_ops: list) -> list:
    """Convert normalized ops into RDF-like triples. Placeholder."""
    raise NotImplementedError("Implement RDF triple generation.")


def write_graph(triples: list, output_path: str) -> None:
    """Write triples to a graph store or file. Placeholder."""
    raise NotImplementedError("Implement graph store write.")
