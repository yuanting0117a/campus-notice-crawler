from __future__ import annotations
from datetime import datetime, timedelta
from urllib.parse import urlencode
from bs4 import BeautifulSoup
import re
from .common import SESSION

API = "https://www.taiwanbus.tw/eBUSPage/json/TimeTableAPIByWeek.aspx"
BUS_HOME = "https://www.tcbus.com.tw/"

def crawl_timetable():
    # Query the next service day so a schedule change taking effect tomorrow is captured.
    query_date = (datetime.now() + timedelta(days=1)).strftime("%Y/%m/%d")
    params = {"RouteId": "9015", "SearchDate": query_date, "inputType": "R01"}
    response = SESSION.get(API, params=params, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    sections = []
    current = None
    # The official timetable page contains four sections: 9015/9015A, outbound/return.
    for node in soup.find_all(["h1", "h2", "h3", "h4", "caption", "tr"]):
        if node.name != "tr":
            heading = " ".join(node.get_text(" ", strip=True).split())
            match = re.search(r"9015\s*[-－]\s*([0A])\s*(往程|返程)", heading)
            if match:
                current = {"route": "9015A" if match.group(1) == "A" else "9015",
                           "direction": "往程" if match.group(2) == "往程" else "返程",
                           "stop": "", "trips": []}
                sections.append(current)
            continue
        if current is None:
            continue
        cells = [" ".join(c.get_text(" ", strip=True).split()) for c in node.find_all(["td", "th"], recursive=False)]
        if len(cells) < 4:
            continue
        # Skip column headings; time is normally the second column.
        time_match = next((re.fullmatch(r"\d{3,4}", c) for c in cells if re.fullmatch(r"\d{3,4}", c)), None)
        if not time_match:
            continue
        time_index = next(i for i,c in enumerate(cells) if re.fullmatch(r"\d{3,4}", c))
        time = cells[time_index]
        if len(time) == 3:
            time = "0" + time
        stop = cells[1] if len(cells) > 1 else ""
        days = cells[time_index + 1] if len(cells) > time_index + 1 else ""
        operator = cells[time_index + 2] if len(cells) > time_index + 2 else ""
        notes = cells[time_index + 3] if len(cells) > time_index + 3 else ""
        current["stop"] = current["stop"] or stop
        current["trips"].append({"time": time[:2] + ":" + time[2:], "days": days,
                                 "operator": operator, "notes": notes})
    sections = [s for s in sections if s["trips"]]
    if not sections:
        raise RuntimeError("官方 9015 時刻表頁面格式改變或暫無班次，保留上次成功資料。")
    return {
        "source": "臺灣公路客運即時動態資訊網（官方時刻表）",
        "source_url": "https://www.taiwanbus.tw/eBUSPage/",
        "operator_url": BUS_HOME,
        "query_date": query_date,
        "updated_at": datetime.now().astimezone().isoformat(),
        "routes": sections,
        "notice": "班次可能因日期、例假日及業者調度調整；出發前請以官方即時資訊為準。"
    }

def crawl_route_notices():
    response = SESSION.get(BUS_HOME, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    notices = []
    for a in soup.select("a[href]"):
        title = " ".join(a.get_text(" ", strip=True).split())
        href = a.get("href", "")
        if not title or not re.search(r"9015\s*A?|A\s*線", title, re.I):
            continue
        url = href if href.startswith("http") else BUS_HOME.rstrip("/") + "/" + href.lstrip("/")
        notices.append({"title": title, "url": url})
    return notices[:20]

def run():
    data = crawl_timetable()
    try:
        data["notices"] = crawl_route_notices()
    except Exception as exc:
        data["notices"] = []
        data["notice_fetch_error"] = str(exc)
    return data
