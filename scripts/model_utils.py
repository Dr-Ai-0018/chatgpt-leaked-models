from __future__ import annotations

import html
import re
from pathlib import Path


NON_SOURCE_FILES = {
    "README.md",
    "NOTES.md",
    "PROJECT_GPT_PROMPT.md",
    "prepare.txt",
    "prepare响应.txt",
    "chatgpt.com.har",
}

SOURCE_EXTENSIONS = {".txt", ".html"}

SECTION_RE = re.compile(r"^=+\s*(?P<section>[^()=]+?)\s*\(\d+\)\s*=+$")
BADGE_SUFFIX_RE = re.compile(r"^(?P<name>.+?)(?P<badge>alpha|mainline|beta)$")


def normalize_whitespace(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\u200b", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_name(text: str) -> str:
    text = normalize_whitespace(text)
    text = text.strip("`\"'[]{}<>")
    return text.strip()


def slugify_file_name(path: Path) -> str:
    stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", path.stem)
    stem = stem.strip("._")
    if stem:
        return stem
    return "_".join(f"u{ord(ch):04x}" for ch in path.stem) or "source"


def classify_source(path: Path, content: str) -> str:
    if "<div" in content or 'role="menuitem' in content or "data-has-submenu" in content:
        return "html_menu"
    return "text_list"


def split_badge_suffix(text: str) -> tuple[str, str | None]:
    match = BADGE_SUFFIX_RE.match(text)
    if not match:
        return text, None
    return match.group("name").rstrip(), match.group("badge")


# 抓取页面时混入的 DOM / 菜单 markup 残渣（不是模型名）。
# 典型样本：尖括号被去掉后的 "div data-radix-popper-content-wrapper ... class= aria- ..." 长串。
_DOM_JUNK_RE = re.compile(
    r"data-(?:radix|testid|orientation|state|side|align|highlighted)"
    r"|aria-(?:hidden|checked|expanded|controls|haspopup|orientation)"
    r"|role=menu|popper|xmlns|class=|menu-item|thinking-effort"
    r"|pointer-events|transform translate|currentColor|collection-item",
    re.I,
)


def looks_like_dom(name: str) -> bool:
    """True 表示 name 实为抓取残留的 DOM/markup，应当丢弃（坏死数据）。

    只认 markup 特征或异常超长（>800），不用 len>80 那种阈值——避免误伤
    83~90 字符的合法 campaign 名。"""
    n = str(name or "")
    if len(n) > 800:
        return True
    return bool(_DOM_JUNK_RE.search(n))
