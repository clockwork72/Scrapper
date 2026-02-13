from pathlib import Path

from consistency_advanced.pipeline import run_pipeline


def test_pipeline_smoke(tmp_path: Path):
    fp = tmp_path / "fp.txt"
    tp = tmp_path / "tp.txt"

    fp.write_text(
        """
# Privacy Policy

## Sharing
We may share device identifiers with service providers for analytics.
""".strip(),
        encoding="utf-8",
    )
    tp.write_text(
        """
# Third Party Privacy Policy

## Data Collection
We collect device identifiers from partners for advertising and analytics.
""".strip(),
        encoding="utf-8",
    )

    out = tmp_path / "out"
    result = run_pipeline(
        first_party_policy_path=str(fp),
        third_party_policy_path=str(tp),
        output_dir=str(out),
    )

    assert "summary" in result
    assert "machine_report" in result
    assert (out / "summary.json").exists()
    assert (out / "report.machine.json").exists()
    assert (out / "graph.triples.jsonl").exists()
