from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPARE_PATH = ROOT / "processed" / "api_compare" / "api_internal_model_matches.json"
OUTPUT_DIR = ROOT / "processed" / "api_compare"


def load_compare() -> dict:
    return json.loads(COMPARE_PATH.read_text(encoding="utf-8"))


def build_tiers(compare: dict) -> dict:
    high_confidence = []
    weak_related = []
    no_signal = []

    for item in compare["high_confidence"]:
        high_confidence.append(
            {
                "api_id": item["api_id"],
                "top_match": item["matches"][0]["internal_name"] if item["matches"] else None,
                "top_reason": item["matches"][0]["reason"] if item["matches"] else None,
                "all_matches": item["matches"],
            }
        )

    for item in compare["possible_related"]:
        weak_related.append(
            {
                "api_id": item["api_id"],
                "top_match": item["matches"][0]["internal_name"] if item["matches"] else None,
                "top_reason": item["matches"][0]["reason"] if item["matches"] else None,
                "all_matches": item["matches"],
            }
        )

    for api_id in compare["unmatched_api_ids"]:
        no_signal.append({"api_id": api_id})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "high_confidence": len(high_confidence),
            "weak_related": len(weak_related),
            "no_signal": len(no_signal),
        },
        "high_confidence": high_confidence,
        "weak_related": weak_related,
        "no_signal": no_signal,
    }


def write_outputs(tiers: dict) -> None:
    json_path = OUTPUT_DIR / "api_match_tiers.json"
    md_path = OUTPUT_DIR / "api_match_tiers.md"

    json_path.write_text(json.dumps(tiers, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# API Match Tiers",
        "",
        f"- Generated at: `{tiers['generated_at']}`",
        f"- High confidence: `{tiers['counts']['high_confidence']}`",
        f"- Weak related: `{tiers['counts']['weak_related']}`",
        f"- No signal: `{tiers['counts']['no_signal']}`",
        "",
        "## High Confidence",
        "",
    ]

    for item in tiers["high_confidence"]:
        lines.append(f"- `{item['api_id']}` -> `{item['top_match']}` ({item['top_reason']})")

    lines.extend(["", "## Weak Related", ""])
    for item in tiers["weak_related"]:
        lines.append(f"- `{item['api_id']}` -> `{item['top_match']}` ({item['top_reason']})")

    lines.extend(["", "## No Signal", ""])
    for item in tiers["no_signal"]:
        lines.append(f"- `{item['api_id']}`")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "outputs": [
                    str(json_path.relative_to(ROOT)),
                    str(md_path.relative_to(ROOT)),
                ],
                "counts": tiers["counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    compare = load_compare()
    tiers = build_tiers(compare)
    write_outputs(tiers)


if __name__ == "__main__":
    main()
