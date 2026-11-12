from __future__ import annotations
from datetime import datetime, timedelta
from urllib.parse import urlencode
from bs4 import BeautifulSoup
import re
from .common import SESSION

API = "https://www.taiwanbus.tw/eBUSPage/json/TimeTableAPIByWeek.aspx"
BUS_HOME = "https://www.tcbus.com.tw/"

def crawl_timetable():
    query_date = (datetime.now() + timedelta(days=1)).strftime("%Y/%m/%d")
    params = {"RouteId": "9015", "SearchDate": query_date, "inputType": "R01"}
    response = SESSION.get(API, params=params, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    sections = []
    # Locate each official route/direction heading, then parse the next timetable table.
    heading_nodes = []
    for string in soup.find_all(string=re.compile(r"9015\\s*[-－]\\s*[0A]\\s*(往程|返程)")):
        node = string.parent
        if node and node not in heading_nodes:
            heading_nodes.append(node)
    for heading in heading_nodes:
        label = " ".join(heading.get_text(" ", strip=True).split())
        match = re.search(r"9015\\s*[-－]\\s*([0A])\\s*(往程|返程)", label)
        if not match:
            continue
        table = heading.find_next("table")
        if table is None:
            continue
        section = {"route": "9015A" if match.group(1) == "A" else "9015",
                   "direction": match.group(2), "stop": "", "trips": []}
        for row in table.select("tr"):
            cells = [" ".join(c.get_text(" ", strip=True).split()) for c in row.find_all(["td", "th"], recursive=False)]
            time_index = next((i for i,c in enumerate(cells) if re.fullmatch(r"\\d{3,4}", c)), None)
            if time_index is None:
                continue
            raw_time = cells[time_index].zfill(4)
            section["stop"] = section["stop"] or (cells[1] if len(cells) > 1 else "")
            section["trips"].append({
                "time": raw_time[:2] + ":" + raw_time[2:],
                "days": cells[time_index + 1] if len(cells) > time_index + 1 else "",
                "operator": cells[time_index + 2] if len(cells) > time_index + 2 else "",
                "notes": cells[time_index + 3] if len(cells) > time_index + 3 else ""
            })
        if section["trips"]:
            sections.append(section)
    # Deduplicate repeated headings/tables if the page uses nested layout wrappers.
    unique = {}
    for section in sections:
        unique[(section["route"], section["direction"])] = section
    sections = list(unique.values())
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
