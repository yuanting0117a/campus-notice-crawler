from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from crawlers.events import run as run_events
from crawlers.scholarships import run as run_scholarships

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

def load_previous(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at": None, "sources": []}

def merge_fail_safe(previous, fresh):
    old = {x.get("source"): x for x in previous.get("sources", [])}
    merged = []
    for item in fresh:
        if item["status"] == "error" and old.get(item["source"], {}).get("records"):
            keep = old[item["source"]].copy()
            keep["last_attempt"] = item.get("checked_at")
            keep["last_error"] = item.get("error", "unknown")
            keep["status"] = "stale_previous_data"
            merged.append(keep)
        else:
            merged.append(item)
    return merged

def write_dataset(filename, fresh):
    path = DATA / filename
    previous = load_previous(path)
    result = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "Asia/Taipei",
        "policy": "不去重；來源失敗時保留上次成功資料；原文優先於摘要。",
        "sources": merge_fail_safe(previous, fresh),
    }
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

def main():
    events = write_dataset("activities.json", run_events())
    scholarships = write_dataset("scholarships.json", [run_scholarships()])
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "events": [{"source":s["source"],"status":s["status"],"count":s["count"],"error":s.get("error")} for s in events["sources"]],
        "scholarships": [{"source":s["source"],"status":s["status"],"count":s["count"],"error":s.get("error")} for s in scholarships["sources"]],
    }
    (DATA / "run_status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
