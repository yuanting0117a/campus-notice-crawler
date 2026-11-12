from .common import crawl_listing, safe_source, fetch, make_record, clean, extract_dates, extractive_summary
from bs4 import BeautifulSoup
from urllib.parse import urljoin

SOURCES = [
    ("圖書館活動", "https://cal.lib.nchu.edu.tw/"),
    ("自主學習活動", "https://selfstudy.nchu.edu.tw/"),
    ("研習暨演講活動", "https://psfcost.nchu.edu.tw/registration/index/actlist.jsp"),
    ("學校最新公告", "https://www.nchu.edu.tw/news/id/index"),
    ("生涯發展與實習", "https://www.osa.nchu.edu.tw/osa/cdc/sys/modules/tadnews/index.php"),
    ("國際交流與交換", "https://oia.nchu.edu.tw/index.php/zh/"),
    ("宿舍公告", "https://www.osa.nchu.edu.tw/osa/dorm/sys/"),
    ("電機系公告", "https://www.ee.nchu.edu.tw/wb_announcement01.asp?cno=0&pageno=1&url=11"),
    ("教務處選課與學籍", "https://oaa.nchu.edu.tw/course-news"),
    ("研究競賽與獎補助", "https://research.nchu.edu.tw/"),
]

def crawl_lectures():
    """Parse the registration system's actual activity table: one row becomes one event card."""
    url = "https://psfcost.nchu.edu.tw/registration/index/actlist.jsp"
    html, final_url = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    records, seen = [], set()
    for row in soup.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 4:
            continue
        title = clean(cells[0].get_text(" ", strip=True))
        if not title or title.lower() in {"活動名稱", "event"} or ("活動名稱" in title and "event" in title.lower()):
            continue
        links = []
        for a in row.select("a[href]"):
            href = urljoin(final_url, a.get("href", ""))
            label = clean(a.get_text(" ", strip=True)) or "活動詳情／報名"
            if href.startswith(("http://", "https://")):
                links.append({"title": label, "url": href})
        activity_time = clean(cells[2].get_text(" ", strip=True))
        registration_time = clean(cells[1].get_text(" ", strip=True))
        participants = clean(cells[3].get_text(" ", strip=True))
        registration = links[-1]["url"] if links else final_url
        key = (title, activity_time, registration)
        if key in seen:
            continue
        seen.add(key)
        content = "\n".join([
            "活動時間：" + activity_time,
            "報名期間：" + registration_time,
            "名額資訊：" + participants,
        ])
        rec = make_record("研習暨演講活動", title, registration, content, {"links": links})
        rec.update({
            "full_text": content,
            "summary": content,
            "dates_found": extract_dates(content),
            "list_text": content,
            "registration_links": links or [{"title": "活動列表", "url": final_url}],
            "event_time": activity_time,
            "registration_time": registration_time,
            "participant_info": participants,
        })
        records.append(rec)
    return records

def crawl_library_events():
    # The library course catalogue and handout download page are course resources,
    # not individual campus events; avoid ingesting their whole-page text as one card.
    records = crawl_listing("圖書館活動", "https://cal.lib.nchu.edu.tw/", max_details=25)
    navigation_titles = [
        "開課列表", "講義下載", "申請資源利用課程", "課程滿意度調查",
        "數位課程搶先看", "報名迷你課程", "管理登入"
    ]
    return [r for r in records if not any(k in (r.get("title", "") or "") for k in navigation_titles)]

def diagnose_selfstudy():
    url = "https://selfstudy.nchu.edu.tw/"
    html, final_url = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    records = crawl_listing("自主學習活動", url, max_details=25)
    if not records:
        scripts = [x.get("src") for x in soup.select("script[src]") if x.get("src")]
        print({"selfstudy_diagnostic": {"final_url": final_url, "html_length": len(html),
              "title": soup.title.get_text(strip=True) if soup.title else "",
              "scripts": scripts[:20], "anchors": len(soup.select("a[href]"))}})
    return records

def run():
    results = []
    for name, url in SOURCES:
        if name == "自主學習活動":
            results.append(safe_source(name, diagnose_selfstudy))
        elif name == "研習暨演講活動":
            results.append(safe_source(name, crawl_lectures))
        elif name == "圖書館活動":
            results.append(safe_source(name, crawl_library_events))
        else:
            # Keep each additional official source bounded to avoid long Actions runs.
            results.append(safe_source(name, lambda n=name, u=url: crawl_listing(n, u, max_details=5)))
    return results
