from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from crawlers.events import run as run_events
from crawlers.scholarships import run as run_scholarships
from crawlers.ncyu_scholarships import run as run_ncyu_scholarships
from crawlers.transit import run as run_transit

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
    scholarships = write_dataset("scholarships.json", [run_scholarships(), run_ncyu_scholarships()])
    # The NCHU scholarship source is the university internal list; tag it explicitly for profile filtering.
    for source in scholarships["sources"]:
        if source.get("source") == "獎學金":
            for record in source.get("records", []):
                record.setdefault("school_scope", "nchu")
    # Keep transit timetable separate so it can be displayed independently.
    transit_path = DATA / "transit_9015.json"
    previous_transit = {}
    try:
        previous_transit = json.loads(transit_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    try:
        transit = run_transit()
        transit["status"] = "ok"
        transit_path.write_text(json.dumps(transit, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        transit = previous_transit
        transit["status"] = "stale_previous_data" if transit else "error"
        transit["last_error"] = str(exc)
        if transit:
            transit_path.write_text(json.dumps(transit, ensure_ascii=False, indent=2), encoding="utf-8")
    # Split all university scholarship sources into two size-balanced JSON files.
    all_records = [record for source in scholarships["sources"] for record in source.get("records", [])]
    buckets = [[], []]
    sizes = [0, 0]
    for record in all_records:
        payload_size = len(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        target = 0 if sizes[0] <= sizes[1] else 1
        buckets[target].append(record)
        sizes[target] += payload_size
    for index, bucket in enumerate(buckets, start=1):
        shard = {
            "schema_version": 1,
            "updated_at": scholarships["updated_at"],
            "timezone": scholarships["timezone"],
            "policy": scholarships["policy"],
            "sources": [{"source": "獎學金", "status": "ok", "count": len(bucket), "records": bucket}],
        }
        shard_path = DATA / f"scholarships_{index}.json"
        shard_path.write_text(json.dumps(shard, ensure_ascii=False, indent=2), encoding="utf-8")
        actual_size = shard_path.stat().st_size
        if actual_size >= 90 * 1024 * 1024:
            raise RuntimeError(f"{shard_path.name} is too large ({actual_size} bytes); refusing to publish.")
    (DATA / "scholarships.json").unlink(missing_ok=True)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "events": [{"source":s["source"],"status":s["status"],"count":s["count"],"error":s.get("error")} for s in events["sources"]],
        "scholarships": [{"source":s["source"],"status":s["status"],"count":s["count"],"error":s.get("error"),"warnings":s.get("warnings",[]),"detail_pages_fetched":s.get("detail_pages_fetched"),"internal_categories_crawled":s.get("internal_categories_crawled"),"department_boards_crawled":s.get("department_boards_crawled"),"attachment_count":s.get("attachment_count")} for s in scholarships["sources"]],
        "transit": {"status": transit.get("timetable_status", transit.get("status", "error")), "routes": len(transit.get("routes", [])), "notice_count": len(transit.get("notices", [])), "error": transit.get("timetable_error") or transit.get("last_error")},
    }
    (DATA / "run_status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("Scholarship shards:", [(p.name, p.stat().st_size) for p in sorted(DATA.glob("scholarships_*.json"))])

if __name__ == "__main__":
    main()
