from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "processed" / "api_models" / "models_response.json"
INTERNAL_PATH = ROOT / "processed" / "screening_aggregate" / "combined_models.json"
CATALOG_DIR = ROOT / "processed" / "organized_catalog"
OUTPUT_DIR = ROOT / "processed" / "api_compare"

MAINLINE_RE = re.compile(r"^mainline\s+([^:]+):\s*\(([^)]*)\)$", re.IGNORECASE)


def collapse(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def build_internal_aliases(name: str) -> set[str]:
    aliases = {name.casefold()}
    aliases.add(collapse(name))

    mainline_match = MAINLINE_RE.match(name)
    if mainline_match:
        base = mainline_match.group(1).strip().casefold()
        aliases.add(base)
        aliases.add(collapse(base))

    # Turn common display spacing into API-like variants.
    dashed = re.sub(r"\s+", "-", name.casefold())
    aliases.add(dashed)
    aliases.add(collapse(dashed))
    return aliases


def looks_like_real_model_name(name: str) -> bool:
    lowered = name.casefold()
    if len(name) > 240:
        return False
    if "div data-radix-popper-content-wrapper" in lowered:
        return False
    if lowered.startswith("div ") or lowered.startswith("<div"):
        return False
    if "aria-orientation" in lowered and "role=menu" in lowered:
        return False
    return True


def score_match(api_id: str, internal_name: str) -> tuple[int, str] | None:
    api_cf = api_id.casefold()
    api_collapsed = collapse(api_id)
    internal_aliases = build_internal_aliases(internal_name)

    if api_cf in internal_aliases:
        if internal_name.casefold() == api_cf:
            return 100, "exact_name"
        if internal_name.casefold().startswith("mainline "):
            return 98, "mainline_base"
        return 95, "normalized_alias"

    if api_collapsed in internal_aliases:
        return 93, "collapsed_alias"

    internal_cf = internal_name.casefold()
    if api_cf in internal_cf:
        return 70, "api_id_substring"

    api_tokens = tokenize(api_id)
    internal_tokens = tokenize(internal_name)
    if not api_tokens or not internal_tokens:
        return None

    overlap = api_tokens & internal_tokens
    if not overlap:
        return None

    coverage = len(overlap) / len(api_tokens)
    if coverage >= 0.75:
        return 60, "token_overlap"
    return None


def load_api_ids() -> list[str]:
    payload = json.loads(API_PATH.read_text(encoding="utf-8"))
    return sorted(
        [item["id"] for item in payload.get("data", []) if isinstance(item, dict) and "id" in item],
        key=str.casefold,
    )


def _load_catalog_fallback() -> list[dict]:
    """Rebuild internal model list from organized_catalog when aggregate is missing."""
    models = []
    for name in ("internal_official_slots.json", "internal_official_family_related.json", "internal_experimental.json"):
        path = CATALOG_DIR / name
        if path.exists():
            models.extend(json.loads(path.read_text(encoding="utf-8")))
    return models


def load_internal_models() -> list[dict]:
    if INTERNAL_PATH.exists():
        payload = json.loads(INTERNAL_PATH.read_text(encoding="utf-8"))
        return [item for item in payload["models"] if looks_like_real_model_name(item["name"])]
    return [item for item in _load_catalog_fallback() if looks_like_real_model_name(item.get("name", ""))]


def compare() -> dict:
    api_ids = load_api_ids()
    internal_models = load_internal_models()

    high_confidence = []
    possible_related = []
    unmatched = []

    for api_id in api_ids:
        scored = []
        for internal in internal_models:
            result = score_match(api_id, internal["name"])
            if result is None:
                continue
            score, reason = result
            scored.append(
                {
                    "score": score,
                    "reason": reason,
                    "internal_name": internal["name"],
                    "occurrence_count": internal["occurrence_count"],
                    "source_count": internal["source_count"],
                    "badges": internal["badges"],
                }
            )

        scored.sort(
            key=lambda item: (
                -item["score"],
                -item["occurrence_count"],
                item["internal_name"].casefold(),
            )
        )

        if scored and scored[0]["score"] >= 90:
            high_confidence.append(
                {
                    "api_id": api_id,
                    "matches": scored[:10],
                }
            )
        elif scored:
            possible_related.append(
                {
                    "api_id": api_id,
                    "matches": scored[:10],
                }
            )
        else:
            unmatched.append(api_id)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_model_count": len(api_ids),
        "high_confidence_count": len(high_confidence),
        "possible_related_count": len(possible_related),
        "unmatched_count": len(unmatched),
        "high_confidence": high_confidence,
        "possible_related": possible_related,
        "unmatched_api_ids": unmatched,
    }


def write_outputs(result: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "api_internal_model_matches.json"
    md_path = OUTPUT_DIR / "api_internal_model_matches.md"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# API / Internal Model Compare",
        "",
        f"- Generated at: `{result['generated_at']}`",
        f"- API model count: `{result['api_model_count']}`",
        f"- High confidence matches: `{result['high_confidence_count']}`",
        f"- Possible related matches: `{result['possible_related_count']}`",
        f"- Unmatched API ids: `{result['unmatched_count']}`",
        "",
        "## High Confidence",
        "",
    ]

    for item in result["high_confidence"]:
        lines.append(f"### `{item['api_id']}`")
        for match in item["matches"][:5]:
            lines.append(
                f"- `{match['internal_name']}` | score={match['score']} | reason={match['reason']} | badges={','.join(match['badges'])}"
            )
        lines.append("")

    lines.extend(["## Possible Related", ""])
    for item in result["possible_related"][:40]:
        lines.append(f"### `{item['api_id']}`")
        for match in item["matches"][:5]:
            lines.append(
                f"- `{match['internal_name']}` | score={match['score']} | reason={match['reason']} | badges={','.join(match['badges'])}"
            )
        lines.append("")

    lines.extend(["## Unmatched API IDs", ""])
    for api_id in result["unmatched_api_ids"]:
        lines.append(f"- `{api_id}`")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "outputs": [
                    str(json_path.relative_to(ROOT)),
                    str(md_path.relative_to(ROOT)),
                ],
                "high_confidence_count": result["high_confidence_count"],
                "possible_related_count": result["possible_related_count"],
                "unmatched_count": result["unmatched_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    result = compare()
    write_outputs(result)


if __name__ == "__main__":
    main()
