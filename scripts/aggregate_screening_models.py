from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from model_utils import looks_like_dom, normalize_name


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "processed" / "screening_per_file"
OUTPUT_DIR = ROOT / "processed" / "screening_aggregate"


def load_payloads() -> list[dict]:
    payloads = []
    for path in sorted(INPUT_DIR.glob("*.json"), key=lambda item: item.name.casefold()):
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
    return payloads


def aggregate_entries(payloads: list[dict]) -> tuple[list[dict], dict[str, int]]:
    combined: dict[str, dict] = {}
    source_counter: Counter[str] = Counter()

    for payload in payloads:
        source_name = payload["source_file"]
        for entry in payload["entries"]:
            normalized_name = normalize_name(entry["normalized_name"])
            if looks_like_dom(entry.get("name", "")) or looks_like_dom(normalized_name):
                continue  # 丢弃抓取残留的 DOM markup（坏死数据）
            source_counter[source_name] += 1
            if normalized_name not in combined:
                combined[normalized_name] = {
                    "name": entry["name"],
                    "normalized_name": normalized_name,
                    "occurrence_count": 0,
                    "source_files": set(),
                    "badges": set(),
                    "kinds": set(),
                    "roles": set(),
                    "raw_names": set(),
                    "has_submenu": False,
                }

            target = combined[normalized_name]
            target["occurrence_count"] += 1
            target["source_files"].add(source_name)
            if entry.get("badge"):
                target["badges"].add(entry["badge"])
            if entry.get("kind"):
                target["kinds"].add(entry["kind"])
            if entry.get("role"):
                target["roles"].add(entry["role"])
            target["raw_names"].add(entry["name"])
            target["has_submenu"] = target["has_submenu"] or bool(entry.get("has_submenu"))

    merged_entries = []
    for value in combined.values():
        merged_entries.append(
            {
                "name": value["name"],
                "normalized_name": value["normalized_name"],
                "occurrence_count": value["occurrence_count"],
                "source_count": len(value["source_files"]),
                "source_files": sorted(value["source_files"], key=str.casefold),
                "badges": sorted(value["badges"], key=str.casefold),
                "kinds": sorted(value["kinds"], key=str.casefold),
                "roles": sorted(value["roles"], key=str.casefold),
                "raw_names": sorted(value["raw_names"], key=str.casefold),
                "has_submenu": value["has_submenu"],
            }
        )

    merged_entries.sort(key=lambda item: (item["name"].casefold(), item["name"]))
    return merged_entries, dict(sorted(source_counter.items(), key=lambda item: item[0].casefold()))


def write_outputs(payloads: list[dict], merged_entries: list[dict], source_counter: dict[str, int]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUTPUT_DIR / "combined_models.json"
    txt_path = OUTPUT_DIR / "all_models_deduped.txt"

    json_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_directory": str(INPUT_DIR.relative_to(ROOT)),
        "input_file_count": len(payloads),
        "unique_model_count": len(merged_entries),
        "source_entry_counts": source_counter,
        "models": merged_entries,
    }
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(
        "\n".join(entry["name"] for entry in merged_entries) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    payloads = load_payloads()
    merged_entries, source_counter = aggregate_entries(payloads)
    write_outputs(payloads, merged_entries, source_counter)
    summary = {
        "input_file_count": len(payloads),
        "unique_model_count": len(merged_entries),
        "outputs": [
            str((OUTPUT_DIR / "combined_models.json").relative_to(ROOT)),
            str((OUTPUT_DIR / "all_models_deduped.txt").relative_to(ROOT)),
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
