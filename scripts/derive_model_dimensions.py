# -*- coding: utf-8 -*-
"""
derive_model_dimensions.py  — 内部模型命名情报解析（打地基步骤）

输入: processed/screening_aggregate/combined_models.json （去重内部总表）
输出: processed/insights/
    - model_dimensions.json   每个模型一条，附解析出的结构化维度
    - dimension_summary.json  各维度的聚合计数（前端洞察面板直接读这个）

解析的维度（全部 best-effort，从名字字符串推断）:
    generation     代际：gpt-5.1..5.5 / gpt-4 / gpt-4o / o1/o3/o4 / davinci ...
    codename       项目代号：big_dipper / andromeda / sonic(berry) / lupo / thinky ...
    tiers          受众/部署档：paid / unpaid / free / pro / plus / biz / no_auth ...
    capabilities   能力标签：search / memory / reasoning / genui / subagent ...
    is_campaign    是否 A/B 实验条目（campaign:<slug>:<arm>）
    campaign_slug  实验名
    campaign_arm   实验分组（a/b/c...）
    personality_trait/trait_direction/trait_category  人格轴 / more-less / 轴分组
    date_tag       名字里的日期戳归一到 YYYY-MM（可能为 None）
    checkpoint     训练检查点标签（s1500 等），可能为 None
    checkpoint_step 同上但纯数值，便于排序，可能为 None
    compute_hint   算力/推理强度提示：juice / thinky / thinking / nopctx ...
    juice_level    算力档数值（juice32 / j8 → 32 / 8），可能为 None
    is_mainline    是否 mainline 已上线槽位
    deploy_variant mainline 括号里的部署变体（paid / biz / no_browse ...），可能为 None

注意：这是离线静态分析，纯字符串推断，不访问网络。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "processed" / "screening_aggregate" / "combined_models.json"
OUT_DIR = ROOT / "processed" / "insights"


def _norm(name: str) -> str:
    """归一：小写 + 非字母数字折叠为单空格。空格名/下划线名统一处理。"""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


# --- 代际 ---------------------------------------------------------------- #
def generation(name: str) -> str | None:
    nl = name.lower()
    # GPT-5.x：覆盖 gpt53 / gpt 5.3 / gpt5.2 / gpt_5_5 / 5p3 / 起始 "5.4 ..."
    # 注意：不能用结尾 \b —— "gpt53_..." 里 3 后面是下划线（属单词字符），\b 会失配。
    m = re.search(r"5p([1-5])\b", nl)
    if m:
        return f"gpt-5.{m.group(1)}"
    m = re.search(r"gpt[ _]?5[._ ]?([1-5])(?![0-9])", nl)
    if m:
        return f"gpt-5.{m.group(1)}"
    m = re.match(r"5[._]([1-5])(?![0-9])", nl)
    if m:
        return f"gpt-5.{m.group(1)}"
    # o 系列
    m = re.search(r"\bo([134])(?:[ _-]?mini|[ _-]?preview)?\b", nl)
    if m:
        return f"o{m.group(1)}"
    # GPT-4 家族
    if re.search(r"gpt[ _-]?4o", nl) or "4o" in nl:
        return "gpt-4o"
    if re.search(r"gpt[ _-]?4[._]5", nl):
        return "gpt-4.5"
    if re.search(r"gpt[ _-]?4\b", nl):
        return "gpt-4"
    if "davinci" in nl or "babbage" in nl:
        return "legacy-gpt-3"
    return None


# --- 代号家族 ------------------------------------------------------------ #
# 规范代号 -> 匹配用的归一化片段（已 _norm 风格，空格分词）
CODENAMES = {
    "big_dipper": ["big dipper", "bigdipper"],
    "andromeda": ["andromeda"],
    "sonicberry": ["sonicberry", "sonic berry"],
    "sonic": ["sonic"],            # 注意：sonicberry 已先匹配，sonic 兜底
    "lupo": ["lupo"],
    "thinky": ["thinky", "thinkier", "thinkiest"],
    "paragen": ["paragen"],
    "feather": ["feather"],
    "spmini": ["spmini", "sp mini"],
    "blender": ["blender"],
    "garlic": ["garlic"],
    "elk": ["elk"],
    "orion": ["orion"],
    "nectarine": ["nectarine"],
    "quench": ["quench"],
    "spud": ["spud"],
    "bidi": ["bidi"],
}


def codename(norm_name: str) -> str | None:
    # 先匹配更具体的（sonicberry 优先于 sonic）
    for code in ("big_dipper", "andromeda", "sonicberry", "lupo", "thinky",
                 "paragen", "feather", "spmini", "blender", "garlic",
                 "elk", "orion", "nectarine", "quench", "spud", "bidi", "sonic"):
        for frag in CODENAMES[code]:
            if frag in norm_name:
                return code
    return None


# --- 受众/部署档 --------------------------------------------------------- #
TIER_WORDS = ["unpaid", "paid", "free", "pro", "plus", "team",
              "enterprise", "biz", "no_auth", "noauth"]


def tiers(name: str) -> list[str]:
    nl = name.lower()
    found = []
    for t in TIER_WORDS:
        pat = t.replace("_", "[ _]?")
        if re.search(r"(^|[^a-z])" + pat + r"($|[^a-z])", nl):
            key = "no_auth" if t in ("no_auth", "noauth") else t
            if key not in found:
                found.append(key)
    return found


# --- 能力标签 ------------------------------------------------------------ #
# 规范能力 -> 归一化匹配片段
CAPABILITIES = {
    "search": ["search", "presearch", "browse"],
    "memory": ["memory"],
    "reasoning": ["reasoning", "reason"],
    "genui": ["genui", "widget", "widgets"],
    "subagent": ["subagent"],
    "canvas": ["canvas", "canmore"],
    "artifacts": ["artifact", "artifacts"],
    "image": ["image", "images"],
    "entity": ["entity"],
    "multilingual": ["multilingual"],
    "personality": ["personality", "person inst", "persona"],
    "automations": ["automation", "automations"],
    "voice": ["voice"],
    "vision": ["vision"],
    "code": ["codex", "coding"],
    "math": ["math"],
    "tools": ["tool", "tools"],
    "shopping": ["shopping", "product policy"],
}


def capabilities(norm_name: str) -> list[str]:
    found = []
    for cap, frags in CAPABILITIES.items():
        if any(f in norm_name for f in frags):
            found.append(cap)
    return found


# --- 日期戳 -------------------------------------------------------------- #
def date_tag(name: str) -> str | None:
    nl = name.lower()
    # 20251209 / 2025-12-09 / 20260423
    m = re.search(r"20(\d{2})[-_]?(\d{2})[-_]?\d{2}", nl)
    if m:
        return f"20{m.group(1)}-{m.group(2)}"
    # 011526 = MMDDYY（美式）：011526 -> 2026-01
    m = re.search(r"\b(0[1-9]|1[0-2])(\d{2})(\d{2})\b", nl)
    if m:
        return f"20{m.group(3)}-{m.group(1)}"
    # _0528 / 0427_ 这种 MMDD（无年份）
    m = re.search(r"(?:^|[_\- ])(0[1-9]|1[0-2])(\d{2})(?:[_\- ]|$)", nl)
    if m:
        return f"??-{m.group(1)}"
    return None


# --- 训练检查点 ---------------------------------------------------------- #
def checkpoint(name: str) -> tuple[str | None, int | None]:
    """返回 (检查点标签, 数值)。数值用于前端排序/分布。"""
    nl = name.lower()
    m = re.search(r"[_\- ]s(\d{3,4})\b", nl)
    if m:
        return f"s{m.group(1)}", int(m.group(1))
    m = re.search(r"step[_\- ]?(\d+)", nl)
    if m:
        return f"step{m.group(1)}", int(m.group(1))
    return None, None


# --- 算力/推理强度提示 --------------------------------------------------- #
COMPUTE_WORDS = ["juice", "thinky", "thinking", "nopctx", "heap", "effort"]


def compute_hint(norm_name: str) -> list[str]:
    return [w for w in COMPUTE_WORDS if w in norm_name]


def juice_level(name: str) -> int | None:
    """提取算力档数值：juice32 / j8 / Juice 16 ...
    数字后须紧跟空格/下划线/结尾，天然排除 j16k(上下文长度)、j5p、jr/jb 等噪声。"""
    nl = name.lower()
    m = re.search(r"juice[ _]?(\d{1,4})(?![0-9a-z])", nl)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:^|[ _])j(\d{1,4})(?:[ _]|$)", nl)
    if m:
        return int(m.group(1))
    return None


# --- mainline 部署变体 --------------------------------------------------- #
def mainline_info(name: str) -> tuple[bool, str | None]:
    """返回 (是否 mainline, 部署变体)。部署变体取括号里的内容，如 paid / biz_no_browse。"""
    nl = name.lower()
    is_ml = bool(re.search(r"\bmainline\b", nl))
    variant = None
    m = re.search(r"\(([^)]+)\)", name)
    if m:
        variant = m.group(1).strip().lower()
    return is_ml, variant


# --- campaign 拆解 ------------------------------------------------------- #
def campaign_parts(name: str) -> tuple[bool, str | None, str | None]:
    if not name.lower().startswith("campaign:"):
        return False, None, None
    parts = name.split(":")
    slug = parts[1] if len(parts) > 1 else None
    arm = parts[2] if len(parts) > 2 else None
    return True, slug, arm


# --- 实验臂角色 ---------------------------------------------------------- #
# 从 campaign_arm 推断这一臂在 A/B 实验里的角色。顺序=优先级。
ARM_ROLES = [
    ("control", ["control"]),
    ("treatment", ["treatment"]),
    ("baseline", ["baseline"]),
    ("production", ["prod"]),
    ("default", ["default"]),
    ("sideline", ["sideline"]),
    ("holdout", ["holdout"]),
    ("candidate", ["candidate", "cand"]),
]


def arm_role(arm: str | None) -> str | None:
    if not arm:
        return None
    a = arm.lower()
    for role, frags in ARM_ROLES:
        if any(f in a for f in frags):
            return role
    return None


# --- 条目类型 ------------------------------------------------------------ #
# 很多内部名其实不是面向用户的模型，而是研发管线产物（分类器/评测/安全/路由等）。
# 把它们和真模型区分开，前端可一键过滤掉噪声。
RESEARCH_WORDS = [
    "classifier", "classification", "eval", "safety", "routing", "router",
    "ner", "canary", "feedback", "smoke", "smoketest", "grader", "probe",
    "holdout", "dogfooding", "eligibility", "ablation", "sideline",
    "rl", "sft", "reward", "judge", "scorer", "heap", "tune", "teacher",
]


def kind(name: str, norm_name: str, is_ml: bool, is_camp: bool) -> str:
    """粗分类：deploy_slot（已上线槽位）/ research_artifact（研发管线产物）/ model。"""
    if is_ml:
        return "deploy_slot"
    # 词边界匹配，避免 "rl" 误伤 "world" 之类
    for w in RESEARCH_WORDS:
        if re.search(r"(^|[ _\-])" + re.escape(w) + r"($|[ _\-])", norm_name):
            return "research_artifact"
    return "model"


# --- 人格特质矩阵 -------------------------------------------------------- #
# GPT-5.3 的 "diversity_traits" 系列：约 23 个语气/人格轴，各带 more/less 方向。
# 形如  campaign:gpt53_diversity_traits...:t_conversational_more
# 同时兼容空格写法与 prose_structure / markdown_structure 这类双词特质。
PERSONALITY_TRAITS = [
    "conversational", "empathetic", "supportive", "practical", "optimistic",
    "dismissive", "literal", "idiomatic", "simple", "analytical", "didactic",
    "dispassionate", "ironic", "obsequious", "critical", "confident",
    "friendly", "curious", "serious", "expository", "direct", "succinct",
    "agreeable", "emoji_use", "prose_structure", "markdown_structure",
]


# 特质分组：前端按类别折叠展示。键=特质，值=类别。
TRAIT_CATEGORY = {
    # 情感倾向
    "empathetic": "emotional", "supportive": "emotional", "optimistic": "emotional",
    "friendly": "emotional", "dismissive": "emotional", "agreeable": "emotional",
    "obsequious": "emotional",
    # 表达方式
    "conversational": "expressive", "literal": "expressive", "idiomatic": "expressive",
    "ironic": "expressive", "expository": "expressive", "direct": "expressive",
    "succinct": "expressive",
    # 认知风格
    "analytical": "cognitive", "didactic": "cognitive", "dispassionate": "cognitive",
    "critical": "cognitive", "confident": "cognitive", "curious": "cognitive",
    "serious": "cognitive", "simple": "cognitive", "practical": "cognitive",
    # 排版格式
    "prose_structure": "format", "markdown_structure": "format", "emoji_use": "format",
}


def trait_category(trait: str | None) -> str | None:
    return TRAIT_CATEGORY.get(trait) if trait else None


def personality(norm_name: str) -> tuple[str | None, str | None]:
    """返回 (特质, 方向)。方向 = more / less / None。norm_name 已折叠为空格分隔。"""
    # prose_structure / markdown_structure 在 norm 后是 "prose structure"
    for trait in PERSONALITY_TRAITS:
        frag = trait.replace("_", " ")
        m = re.search(r"(?:^|\s)" + re.escape(frag) + r"\s+(more|less)\b", norm_name)
        if m:
            return trait, m.group(1)
        # 也允许特质单独出现（无 more/less），但仅当名字明显属于人格实验时才算
        if re.search(r"(?:^|\s)" + re.escape(frag) + r"(?:\s|$)", norm_name) and \
           ("trait" in norm_name or "personality" in norm_name or "diversity" in norm_name):
            return trait, None
    return None, None


def derive(model: dict) -> dict:
    name = model["name"]
    nn = _norm(name)
    is_camp, slug, arm = campaign_parts(name)
    is_ml, variant = mainline_info(name)
    trait, direction = personality(nn)
    ckpt_label, ckpt_num = checkpoint(name)
    return {
        "name": name,
        "kind": kind(name, nn, is_ml, is_camp),
        "generation": generation(name),
        "codename": codename(nn),
        "tiers": tiers(name),
        "capabilities": capabilities(nn),
        "personality_trait": trait,
        "trait_direction": direction,
        "trait_category": trait_category(trait),
        "is_campaign": is_camp,
        "campaign_slug": slug,
        "campaign_arm": arm,
        "arm_role": arm_role(arm),
        "date_tag": date_tag(name),
        "checkpoint": ckpt_label,
        "checkpoint_step": ckpt_num,
        "compute_hint": compute_hint(nn),
        "juice_level": juice_level(name),
        "is_mainline": is_ml,
        "deploy_variant": variant,
        # 透传原表里有用的字段
        "badges": model.get("badges", []),
        "occurrence_count": model.get("occurrence_count", 0),
        "source_count": model.get("source_count", 0),
    }


def summarize(rows: list[dict]) -> dict:
    def count_scalar(key):
        c = Counter()
        for r in rows:
            v = r.get(key)
            c[v if v is not None else "(none)"] += 1
        return dict(c.most_common())

    def count_list(key):
        c = Counter()
        for r in rows:
            vals = r.get(key) or []
            if not vals:
                c["(none)"] += 1
            for v in vals:
                c[v] += 1
        return dict(c.most_common())

    def count_pair(trait_key, dir_key):
        """特质 × 方向 交叉计数，形如 {'conversational': {'more':5,'less':5}}。"""
        c = {}
        for r in rows:
            t = r.get(trait_key)
            if not t:
                continue
            d = r.get(dir_key) or "(none)"
            c.setdefault(t, Counter())[d] += 1
        return {t: dict(v.most_common()) for t, v in
                sorted(c.items(), key=lambda x: -sum(x[1].values()))}

    return {
        "total": len(rows),
        "kind": count_scalar("kind"),
        "generation": count_scalar("generation"),
        "codename": count_scalar("codename"),
        "arm_role": count_scalar("arm_role"),
        "personality_trait": count_pair("personality_trait", "trait_direction"),
        "tiers": count_list("tiers"),
        "capabilities": count_list("capabilities"),
        "compute_hint": count_list("compute_hint"),
        "juice_level": count_scalar("juice_level"),
        "trait_category": count_scalar("trait_category"),
        "date_tag": count_scalar("date_tag"),
        "is_campaign": count_scalar("is_campaign"),
        "is_mainline": count_scalar("is_mainline"),
        "deploy_variant": count_scalar("deploy_variant"),
        "has_checkpoint": {
            "yes": sum(1 for r in rows if r.get("checkpoint")),
            "no": sum(1 for r in rows if not r.get("checkpoint")),
        },
    }


def main() -> None:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    models = payload["models"]
    rows = [derive(m) for m in models]
    summary = summarize(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "model_dimensions.json").write_text(
        json.dumps({"generated_from": str(INPUT.relative_to(ROOT)),
                    "count": len(rows), "models": rows},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "dimension_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps({
        "output_dir": str(OUT_DIR.relative_to(ROOT)),
        "count": len(rows),
        "generation": summary["generation"],
        "codename_top": dict(list(summary["codename"].items())[:12]),
        "capabilities": summary["capabilities"],
        "tiers": summary["tiers"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
