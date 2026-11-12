from __future__ import annotations
from datetime import datetime, timedelta
from urllib.parse import urlencode, urljoin
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
    heading_nodes = []
    for string in soup.find_all(string=re.compile(r"9015\s*[-－]\s*[0A]\s*(往程|返程)")):
        node = string.parent
        if node and node not in heading_nodes:
            heading_nodes.append(node)
    for heading in heading_nodes:
        label = " ".join(heading.get_text(" ", strip=True).split())
        match = re.search(r"9015\s*[-－]\s*([0A])\s*(往程|返程)", label)
        if not match:
            continue
        table = heading.find_next("table")
        if table is None:
            continue
        section = {"route": "9015A" if match.group(1) == "A" else "9015",
                   "direction": match.group(2), "stop": "", "trips": []}
        for row in table.select("tr"):
            cells = [" ".join(c.get_text(" ", strip=True).split()) for c in row.find_all(["td", "th"], recursive=False)]
            time_index = next((i for i,c in enumerate(cells) if re.fullmatch(r"\d{3,4}", c)), None)
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
        image_alt = " ".join(img.get("alt", "") for img in a.select("img")).strip()
        href = urljoin(BUS_HOME, a.get("href", ""))
        combined = " ".join([title, image_alt, href])
        if not re.search(r"9015", combined, re.I):
            continue
        notice = {"title": title or image_alt or "9015 路線公告", "url": href, "images": []}
        try:
            page_response = SESSION.get(href, timeout=20)
            page_response.raise_for_status()
            page = BeautifulSoup(page_response.text, "lxml")
            for img in page.select("img[src]"):
                src = urljoin(href, img.get("src", ""))
                alt = " ".join(img.get("alt", "").split())
                if re.search(r"/newsfile/[^/]+-\d+\.(png|jpe?g|webp)(?:$|[?#])", src, re.I):
                    notice["images"].append({"url": src, "alt": alt or "9015／9015A 官方時刻表"})
            notice["text"] = " ".join(page.get_text(" ", strip=True).split())[:1200]
        except Exception as exc:
            notice["fetch_error"] = str(exc)
        notice["images"] = notice["images"][:1]
        notices.append(notice)
    return notices[:10]

def run():
    data = {
        "source": "臺灣公路客運即時動態資訊網（官方時刻表）",
        "source_url": "https://www.taiwanbus.tw/eBUSPage/",
        "operator_url": BUS_HOME,
        "updated_at": datetime.now().astimezone().isoformat(),
        "routes": [],
        "notices": [],
        "notice": "班次可能因日期、例假日及業者調度調整；出發前請以官方即時資訊為準。"
    }
    try:
        timetable = crawl_timetable()
        data.update(timetable)
        data["timetable_status"] = "ok"
    except Exception as exc:
        data["timetable_status"] = "error"
        data["timetable_error"] = str(exc)
    try:
        data["notices"] = crawl_route_notices()
    except Exception as exc:
        data["notice_fetch_error"] = str(exc)
    # The operator's first image on a 9015 notice is the official 9015/9015A timetable.
    # If the third-party timetable endpoint changes format, treat that current image as a valid fallback.
    has_official_9015_image = any(
        "9015" in (notice.get("title", "") or "")
        and any("/newsfile/" in image.get("url", "") for image in notice.get("images", []))
        for notice in data["notices"]
    )
    if data["timetable_status"] == "error" and has_official_9015_image:
        data["timetable_status"] = "image_only"
        data["timetable_note"] = "已改用台中客運最新公告中的 9015／9015A 原始時刻表圖片。"
        data.pop("timetable_error", None)
    return data
