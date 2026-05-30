from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_MODELS_PATH = ROOT / "processed" / "api_models" / "models_response.json"
INTERNAL_MODELS_PATH = ROOT / "processed" / "screening_aggregate" / "combined_models.json"
COMPARE_PATH = ROOT / "processed" / "api_compare" / "api_internal_model_matches.json"
OUTPUT_DIR = ROOT / "processed" / "organized_catalog"

MAINLINE_RE = re.compile(r"^mainline\s+([^:]+):\s*\(([^)]*)\)$", re.IGNORECASE)


def collapse(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def family_variants(api_id: str) -> set[str]:
    variants = {api_id.casefold(), collapse(api_id)}
    base = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", api_id.casefold())
    variants.add(base)
    variants.add(collapse(base))
    return {item for item in variants if item}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_official_family_index(api_ids: list[str]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for api_id in api_ids:
        pieces = family_variants(api_id)
        # Only keep the most human-meaningful family handles for matching.
        if api_id.startswith("gpt-") or api_id.startswith("o"):
            index[api_id] = pieces
    return index


def internal_aliases(name: str) -> set[str]:
    aliases = {name.casefold(), collapse(name)}
    aliases.add(re.sub(r"\s+", "-", name.casefold()))
    mainline_match = MAINLINE_RE.match(name)
    if mainline_match:
        base = mainline_match.group(1).strip().casefold()
        aliases.add(base)
        aliases.add(collapse(base))
    return {item for item in aliases if item}


def looks_like_family_related(name: str, official_family_index: dict[str, set[str]]) -> tuple[bool, list[str]]:
    aliases = internal_aliases(name)
    matched = []
    for api_id, family_keys in official_family_index.items():
        if aliases & family_keys:
            matched.append(api_id)
            continue
        if any(key and key in name.casefold() for key in family_keys if len(key) >= 3):
            matched.append(api_id)
    return bool(matched), sorted(set(matched), key=str.casefold)


def main() -> None:
    api_payload = load_json(API_MODELS_PATH)
    internal_payload = load_json(INTERNAL_MODELS_PATH)
    compare_payload = load_json(COMPARE_PATH)

    api_ids = sorted(
        [item["id"] for item in api_payload.get("data", []) if isinstance(item, dict) and "id" in item],
        key=str.casefold,
    )
    official_family_index = build_official_family_index(api_ids)

    high_confidence_internal = set()
    for item in compare_payload.get("high_confidence", []):
        for match in item.get("matches", []):
            if match.get("score", 0) >= 90:
                high_confidence_internal.add(match["internal_name"])

    exact_api_id_set = {api_id.casefold() for api_id in api_ids}

    official_api_models = [{"api_id": api_id} for api_id in api_ids]
    internal_official_slots = []
    internal_official_family_related = []
    internal_experimental = []

    for model in sorted(internal_payload["models"], key=lambda item: item["name"].casefold()):
        name = model["name"]
        aliases = internal_aliases(name)

        if name in high_confidence_internal or aliases & exact_api_id_set:
            internal_official_slots.append(model)
            continue

        related, families = looks_like_family_related(name, official_family_index)
        if related:
            enriched = dict(model)
            enriched["related_official_api_ids"] = families
            internal_official_family_related.append(enriched)
        else:
            internal_experimental.append(model)

    api_high_confidence = {item["api_id"] for item in compare_payload.get("high_confidence", [])}
    api_weak = {item["api_id"] for item in compare_payload.get("possible_related", [])}
    api_no_signal = [
        {"api_id": api_id}
        for api_id in api_ids
        if api_id not in api_high_confidence and api_id not in api_weak
    ]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "official_api_models": len(official_api_models),
            "internal_official_slots": len(internal_official_slots),
            "internal_official_family_related": len(internal_official_family_related),
            "internal_experimental": len(internal_experimental),
            "api_without_internal_signal": len(api_no_signal),
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = {
        "summary.json": summary,
        "official_api_models.json": official_api_models,
        "internal_official_slots.json": internal_official_slots,
        "internal_official_family_related.json": internal_official_family_related,
        "internal_experimental.json": internal_experimental,
        "api_without_internal_signal.json": api_no_signal,
    }
    for file_name, payload in files.items():
        (OUTPUT_DIR / file_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUTPUT_DIR / "official_api_models.txt").write_text(
        "\n".join(item["api_id"] for item in official_api_models) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "internal_official_slots.txt").write_text(
        "\n".join(item["name"] for item in internal_official_slots) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "internal_official_family_related.txt").write_text(
        "\n".join(item["name"] for item in internal_official_family_related) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "internal_experimental.txt").write_text(
        "\n".join(item["name"] for item in internal_experimental) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "api_without_internal_signal.txt").write_text(
        "\n".join(item["api_id"] for item in api_no_signal) + "\n",
        encoding="utf-8",
    )

    readme_lines = [
        "# Organized Model Catalog",
        "",
        "This is the canonical organized view for this workspace.",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Official API models: `{summary['counts']['official_api_models']}`",
        f"- Internal official slots: `{summary['counts']['internal_official_slots']}`",
        f"- Internal official-family related: `{summary['counts']['internal_official_family_related']}`",
        f"- Internal experimental-only: `{summary['counts']['internal_experimental']}`",
        f"- API models without internal signal: `{summary['counts']['api_without_internal_signal']}`",
        "",
        "## Buckets",
        "",
        "- `official_api_models.*`: raw official models returned by `/v1/models`.",
        "- `internal_official_slots.*`: internal names that directly map to official API models or `mainline` slots.",
        "- `internal_official_family_related.*`: internal names that still look tied to an official public family, but are not direct official IDs.",
        "- `internal_experimental.*`: internal-only names that look like experiments, campaigns, feature branches, or research buckets.",
        "- `api_without_internal_signal.*`: official API IDs that do not clearly show up in the internal list.",
        "",
        "## Suggested Reading Order",
        "",
        "1. `summary.json`",
        "2. `internal_official_slots.txt`",
        "3. `internal_official_family_related.txt`",
        "4. `internal_experimental.txt`",
        "5. `api_without_internal_signal.txt`",
    ]
    (OUTPUT_DIR / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "output_dir": str(OUTPUT_DIR.relative_to(ROOT)),
                "counts": summary["counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
