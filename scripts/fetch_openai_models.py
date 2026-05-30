from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
OUTPUT_DIR = ROOT / "processed" / "api_models"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def fetch_models(api_key: str) -> dict:
    req = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def write_outputs(payload: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

    json_path = OUTPUT_DIR / "models_response.json"
    txt_path = OUTPUT_DIR / "model_ids.txt"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    model_ids = sorted(
        [item["id"] for item in payload.get("data", []) if isinstance(item, dict) and "id" in item],
        key=str.casefold,
    )
    txt_path.write_text("\n".join(model_ids) + ("\n" if model_ids else ""), encoding="utf-8")

    print(
        json.dumps(
            {
                "fetched_at": timestamp,
                "model_count": len(model_ids),
                "outputs": [
                    str(json_path.relative_to(ROOT)),
                    str(txt_path.relative_to(ROOT)),
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    load_dotenv(ENV_PATH)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY is missing in .env or environment.", file=sys.stderr)
        return 1
    if "****" in api_key:
        print("OPENAI_API_KEY in .env is still masked. Replace it with the real key first.", file=sys.stderr)
        return 2

    try:
        payload = fetch_models(api_key)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 3
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 4

    write_outputs(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
