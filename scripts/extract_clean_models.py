from __future__ import annotations

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from model_utils import (
    NON_SOURCE_FILES,
    SECTION_RE,
    classify_source,
    normalize_name,
    normalize_whitespace,
    slugify_file_name,
    split_badge_suffix,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "筛选"
OUTPUT_DIR = ROOT / "processed" / "screening_per_file"


class MenuHtmlExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.items: list[dict] = []
        self.current_item: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.depth += 1
        attr_map = {key: value or "" for key, value in attrs}
        class_name = attr_map.get("class", "")
        role = attr_map.get("role", "")
        is_badge = "__menu-item-badge" in class_name
        is_item = (
            ("__menu-item" in class_name and role in {"menuitem", "menuitemradio"})
            or ("data-has-submenu" in attr_map and role == "menuitem")
        )

        if self.current_item and is_badge:
            self.current_item["badge_depth"] = self.depth
        if self.current_item and attr_map.get("data-model-picker-thinking-effort-label-extra") == "true":
            self.current_item["skip_text_depth"] = self.depth

        if is_item:
            self.current_item = {
                "start_depth": self.depth,
                "badge_depth": None,
                "skip_text_depth": None,
                "text_parts": [],
                "badge_parts": [],
                "kind": "parent"
                if "data-has-submenu" in attr_map or attr_map.get("aria-haspopup") == "menu"
                else "model",
                "has_submenu": "data-has-submenu" in attr_map or attr_map.get("aria-haspopup") == "menu",
                "role": role,
                "aria_expanded": attr_map.get("aria-expanded") or None,
                "data_testid": attr_map.get("data-testid") or None,
            }

    def handle_data(self, data: str) -> None:
        if not self.current_item:
            return
        if self.current_item["skip_text_depth"] is not None:
            return
        target = "text_parts"
        if self.current_item["badge_depth"] is not None:
            target = "badge_parts"
        self.current_item[target].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current_item and self.current_item["badge_depth"] == self.depth:
            self.current_item["badge_depth"] = None
        if self.current_item and self.current_item["skip_text_depth"] == self.depth:
            self.current_item["skip_text_depth"] = None

        if self.current_item and self.current_item["start_depth"] == self.depth:
            raw_name = normalize_whitespace("".join(self.current_item["text_parts"]))
            badge = normalize_whitespace("".join(self.current_item["badge_parts"])) or None
            if raw_name and raw_name not in {"Instant", "Thinking", "Pro", "使用最新模型", "配置…"}:
                self.items.append(
                    {
                        "name": normalize_name(raw_name),
                        "normalized_name": normalize_name(raw_name).casefold(),
                        "kind": self.current_item["kind"],
                        "badge": badge.casefold() if badge else None,
                        "has_submenu": self.current_item["has_submenu"],
                        "role": self.current_item["role"],
                        "aria_expanded": self.current_item["aria_expanded"],
                        "data_testid": self.current_item["data_testid"],
                    }
                )
            self.current_item = None

        self.depth -= 1


def discover_sources() -> list[Path]:
    if not SOURCE_DIR.exists():
        return []

    candidates = []
    for path in SOURCE_DIR.iterdir():
        if not path.is_file():
            continue
        if path.name in NON_SOURCE_FILES:
            continue
        if path.suffix.lower() not in {".txt", ".html"}:
            continue
        candidates.append(path)
    return sorted(candidates, key=lambda item: item.name.casefold())


def extract_from_text(path: Path, content: str) -> list[dict]:
    entries = []
    current_section = None
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = normalize_whitespace(raw_line)
        if not line:
            continue
        if line.startswith("Captured "):
            continue
        if line.startswith("ChatGPT Internal Models"):
            continue

        section_match = SECTION_RE.match(line)
        if section_match:
            current_section = normalize_name(section_match.group("section")).casefold()
            continue

        if set(line) == {"="}:
            continue

        name = normalize_name(line)
        badge = current_section
        if current_section is None:
            name, suffix_badge = split_badge_suffix(name)
            badge = suffix_badge

        if not name:
            continue

        entries.append(
            {
                "name": name,
                "normalized_name": name.casefold(),
                "kind": "model",
                "badge": badge,
                "has_submenu": False,
                "line_number": line_number,
            }
        )
    return entries


def extract_from_html(content: str) -> list[dict]:
    parser = MenuHtmlExtractor()
    parser.feed(content)
    parser.close()
    return parser.items


def write_output(source: Path, source_type: str, entries: list[dict]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{slugify_file_name(source)}.json"
    payload = {
        "source_file": source.name,
        "source_path": str(source),
        "source_relative_path": str(source.relative_to(ROOT)),
        "source_type": source_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "item_count": len(entries),
        "entries": entries,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    outputs = []
    for source in discover_sources():
        content = source.read_text(encoding="utf-8", errors="ignore")
        source_type = classify_source(source, content)
        if source_type == "html_menu":
            entries = extract_from_html(content)
        else:
            entries = extract_from_text(source, content)
        outputs.append(write_output(source, source_type, entries))

    summary = {
        "generated_files": [str(path.relative_to(ROOT)) for path in outputs],
        "source_count": len(outputs),
        "source_dir_exists": SOURCE_DIR.exists(),
        "source_relative_path": str(SOURCE_DIR.relative_to(ROOT)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
