"""Quick OpenAI-backed consistency run.

Usage:
  OPENAI_API_KEY=... python consistency_advanced/examples/run_openai_test.py \
    --first-party path/to/first_party_policy.txt \
    --third-party path/to/third_party_policy.txt \
    --out /tmp/consistency_openai
"""
from __future__ import annotations

import argparse
import json

from consistency_advanced.pipeline import run_pipeline_openai


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--first-party", required=True)
    p.add_argument("--third-party", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--extract-model", default="gpt-4.1")
    p.add_argument("--verifier-model", default="gpt-4.1-mini")
    args = p.parse_args()

    result = run_pipeline_openai(
        first_party_policy_path=args.first_party,
        third_party_policy_path=args.third_party,
        output_dir=args.out,
        extract_model=args.extract_model,
        verifier_model=args.verifier_model,
    )

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
