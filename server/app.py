"""GPT 内测模型情报终端 — backend.

Serves a single-page "hacker style" dashboard on port 3323, exposes the
organized model catalog as JSON, and refreshes the official OpenAI
`/v1/models` snapshot on a daily schedule (best effort — works offline too).

Run:
    python server/app.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_file

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
PROCESSED = ROOT / "processed"
WEB_DIR = ROOT / "web"

API_MODELS_PATH = PROCESSED / "api_models" / "models_response.json"
CATALOG_DIR = PROCESSED / "organized_catalog"
INSIGHTS_DIR = PROCESSED / "insights"
STATE_PATH = PROCESSED / "server_state.json"
HISTORY_PATH = PROCESSED / "history.json"

DEFAULT_PORT = int(os.environ.get("PORT", "3323"))
FETCH_INTERVAL = int(os.environ.get("FETCH_INTERVAL_SECONDS", str(24 * 60 * 60)))

app = Flask(__name__)

# In-process lock so a scheduled refresh and a manual /api/refresh never overlap.
_refresh_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# State helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"last_fetch_at": None, "last_fetch_ok": None, "last_refresh_at": None}


def save_state(state: dict) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


# --------------------------------------------------------------------------- #
# History snapshots — only recorded when the official id set actually changes
# --------------------------------------------------------------------------- #
def _official_id_set(payload: dict) -> set[str]:
    return {m["id"] for m in payload.get("data", []) if isinstance(m, dict) and "id" in m}


def load_history() -> dict:
    return load_json(HISTORY_PATH, {"events": []})


def record_snapshot(before: set[str], after: set[str]) -> dict | None:
    """Append a snapshot event iff the model set changed. The first ever call
    seeds a 'baseline' event. Returns the event written, or None when unchanged."""
    history = load_history()
    events = history.setdefault("events", [])
    added = sorted(after - before)
    removed = sorted(before - after)

    if not events:
        event = {"timestamp": _now_iso(), "total": len(after), "added": [], "removed": [], "baseline": True}
    elif added or removed:
        event = {"timestamp": _now_iso(), "total": len(after), "added": added, "removed": removed}
    else:
        return None  # nothing changed → don't store a snapshot

    events.append(event)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return event


# --------------------------------------------------------------------------- #
# Data shaping
# --------------------------------------------------------------------------- #
def official_models() -> list[dict]:
    payload = load_json(API_MODELS_PATH, {"data": []})
    out = []
    for item in payload.get("data", []):
        if not isinstance(item, dict) or "id" not in item:
            continue
        created = item.get("created")
        created_iso = None
        if isinstance(created, (int, float)):
            created_iso = datetime.fromtimestamp(created, timezone.utc).isoformat()
        out.append(
            {
                "id": item["id"],
                "object": item.get("object"),
                "owned_by": item.get("owned_by"),
                "created": created,
                "created_iso": created_iso,
            }
        )
    out.sort(key=lambda m: (m["created"] or 0), reverse=True)
    return out


def _trim_internal(entry: dict) -> dict:
    return {
        "name": entry.get("name"),
        "badges": entry.get("badges", []),
        "occurrence_count": entry.get("occurrence_count", 0),
        "source_count": entry.get("source_count", 0),
        "has_submenu": entry.get("has_submenu", False),
        "related_official_api_ids": entry.get("related_official_api_ids", []),
    }


def internal_buckets() -> dict:
    slots = load_json(CATALOG_DIR / "internal_official_slots.json", [])
    family = load_json(CATALOG_DIR / "internal_official_family_related.json", [])
    experimental = load_json(CATALOG_DIR / "internal_experimental.json", [])
    return {
        "official_slots": [_trim_internal(e) for e in slots],
        "family_related": [_trim_internal(e) for e in family],
        "experimental": [_trim_internal(e) for e in experimental],
    }


def summary() -> dict:
    catalog = load_json(CATALOG_DIR / "summary.json", {"counts": {}, "generated_at": None})
    state = load_state()
    return {
        "counts": catalog.get("counts", {}),
        "catalog_generated_at": catalog.get("generated_at"),
        "official_total": len(official_models()),
        "last_fetch_at": state.get("last_fetch_at"),
        "last_fetch_ok": state.get("last_fetch_ok"),
        "last_refresh_at": state.get("last_refresh_at"),
        "fetch_interval_seconds": FETCH_INTERVAL,
        "snapshot_count": len(load_history().get("events", [])),
    }


# --------------------------------------------------------------------------- #
# Refresh pipeline
# --------------------------------------------------------------------------- #
def _run_script(name: str) -> tuple[bool, str]:
    """Run a pipeline script with the current interpreter, from scripts/."""
    proc = subprocess.run(
        [sys.executable, name],
        cwd=str(SCRIPTS_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    ok = proc.returncode == 0
    return ok, (proc.stdout or "") + (proc.stderr or "")


def run_refresh() -> dict:
    """Fetch official models (best effort), then re-classify against the frozen
    internal aggregate. Returns the refresh report."""
    if not _refresh_lock.acquire(blocking=False):
        return {"ok": False, "skipped": True, "reason": "refresh already running"}
    try:
        state = load_state()
        report = {"steps": []}

        before = _official_id_set(load_json(API_MODELS_PATH, {"data": []}))
        fetch_ok, fetch_log = _run_script("fetch_openai_models.py")
        report["steps"].append({"step": "fetch", "ok": fetch_ok, "log": fetch_log.strip()[-2000:]})
        state["last_fetch_at"] = _now_iso()
        state["last_fetch_ok"] = fetch_ok

        # Record a snapshot only when the official model set actually changed.
        if fetch_ok:
            after = _official_id_set(load_json(API_MODELS_PATH, {"data": []}))
            event = record_snapshot(before, after)
            report["snapshot"] = event  # None when unchanged
            if event and not event.get("baseline"):
                report["changed"] = {"added": event["added"], "removed": event["removed"]}

        # Re-classify even when fetch fails so the catalog stays internally consistent.
        pipeline_ok = True
        for script in ("compare_api_and_internal_models.py", "classify_api_match_tiers.py", "organize_model_catalog.py"):
            ok, log = _run_script(script)
            report["steps"].append({"step": script, "ok": ok, "log": log.strip()[-1000:]})
            pipeline_ok = pipeline_ok and ok

        state["last_refresh_at"] = _now_iso()
        save_state(state)
        report["fetch_ok"] = fetch_ok
        report["pipeline_ok"] = pipeline_ok
        report["ok"] = fetch_ok and pipeline_ok
        report["summary"] = summary()
        return report
    finally:
        _refresh_lock.release()


def _scheduler_loop() -> None:
    """Daily fetch loop. Fetches on startup if the last fetch is older than the
    interval, then sleeps one interval and repeats."""
    while True:
        state = load_state()
        last = state.get("last_fetch_at")
        due = True
        if last:
            try:
                elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
                due = elapsed >= FETCH_INTERVAL
            except ValueError:
                due = True
        if due:
            try:
                run_refresh()
            except Exception as exc:  # noqa: BLE001 - never let the loop die
                print(f"[scheduler] refresh failed: {exc}", file=sys.stderr)
        time.sleep(FETCH_INTERVAL)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return send_file(WEB_DIR / "index.html")


@app.route("/api/summary")
def api_summary():
    return jsonify(summary())


@app.route("/api/official")
def api_official():
    models = official_models()
    return jsonify({"count": len(models), "models": models})


@app.route("/api/internal")
def api_internal():
    buckets = internal_buckets()
    category = request.args.get("category")
    if category in buckets:
        return jsonify({"category": category, "count": len(buckets[category]), "models": buckets[category]})
    return jsonify(
        {
            "counts": {k: len(v) for k, v in buckets.items()},
            **buckets,
        }
    )


@app.route("/api/history")
def api_history():
    events = load_history().get("events", [])
    return jsonify({"count": len(events), "events": list(reversed(events))})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    report = run_refresh()
    if report.get("skipped"):
        status = 409
    elif report.get("ok"):
        status = 200
    else:
        status = 502
    return jsonify(report), status


# --------------------------------------------------------------------------- #
# Insights — 情报洞察
# --------------------------------------------------------------------------- #
def _build_insights() -> dict:
    """Build the full insights payload with cross-tabulations."""
    dim_summary = load_json(INSIGHTS_DIR / "dimension_summary.json", {})
    dim_models = load_json(INSIGHTS_DIR / "model_dimensions.json", {"models": []})
    models = dim_models.get("models", [])

    # Cross-tabulations — one pass over all models
    from collections import Counter

    gen_x_codename: Counter = Counter()
    gen_x_capability: Counter = Counter()
    kind_gen_tier: Counter = Counter()

    for m in models:
        gen = m.get("generation") or ""
        code = m.get("codename") or ""
        kind = m.get("kind") or ""
        caps = m.get("capabilities") or []
        tiers = m.get("tiers") or []

        if gen and code:
            gen_x_codename[(gen, code)] += 1
        for cap in caps:
            if gen:
                gen_x_capability[(gen, cap)] += 1
        for tier in (tiers or [""]):
            if kind and gen:
                kind_gen_tier[(kind, gen, tier or "(none)")] += 1

    # Personality matrix — flatten for heatmap
    raw_traits = dim_summary.get("personality_trait", {})
    personality_matrix = []
    trait_cat = dim_summary.get("trait_category", {})
    # Build a trait→category lookup from models
    tc_lookup = {}
    for m in models:
        t = m.get("personality_trait")
        c = m.get("trait_category")
        if t and c:
            tc_lookup[t] = c

    for trait, dirs in raw_traits.items():
        personality_matrix.append({
            "trait": trait,
            "category": tc_lookup.get(trait, "other"),
            "more": dirs.get("more", 0),
            "less": dirs.get("less", 0),
        })
    personality_matrix.sort(key=lambda x: (x["category"], x["trait"]))

    # Compact model list for drill-down
    compact_models = [
        {
            "name": m.get("name", ""),
            "kind": m.get("kind"),
            "generation": m.get("generation"),
            "codename": m.get("codename"),
            "tiers": m.get("tiers", []),
            "capabilities": m.get("capabilities", []),
            "personality_trait": m.get("personality_trait"),
            "trait_direction": m.get("trait_direction"),
            "badges": m.get("badges", []),
        }
        for m in models
    ]

    return {
        "summary": dim_summary,
        "cross": {
            "gen_x_codename": [
                {"gen": g, "codename": c, "count": n}
                for (g, c), n in gen_x_codename.most_common()
            ],
            "gen_x_capability": [
                {"gen": g, "capability": c, "count": n}
                for (g, c), n in gen_x_capability.most_common()
            ],
            "kind_gen_tier": [
                {"kind": k, "gen": g, "tier": t, "count": n}
                for (k, g, t), n in kind_gen_tier.most_common()
            ],
        },
        "personality_matrix": personality_matrix,
        "models": compact_models,
    }


@app.route("/api/insights")
def api_insights():
    return jsonify(_build_insights())


# Start the daily fetch scheduler as a daemon thread.
# Works both under `python app.py` and gunicorn (module import).
# The _refresh_lock prevents overlapping runs across workers.
threading.Thread(target=_scheduler_loop, daemon=True).start()


if __name__ == "__main__":
    print(f"=> GPT 内测模型情报终端  http://127.0.0.1:{DEFAULT_PORT}")
    app.run(host="0.0.0.0", port=DEFAULT_PORT, debug=False, use_reloader=False)
