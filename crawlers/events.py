from .common import crawl_listing, safe_source, fetch, extract_detail, make_record, clean, extractive_summary
from bs4 import BeautifulSoup
from urllib.parse import urljoin

SOURCES = [
    ("圖書館活動", "https://cal.lib.nchu.edu.tw/"),
    ("自主學習活動", "https://selfstudy.nchu.edu.tw/"),
    ("研習暨演講活動", "https://psfcost.nchu.edu.tw/registration/"),
]

def crawl_lectures():
    """The lecture registration system uses ACTID links and a layout not covered by generic cards."""
    url = "https://psfcost.nchu.edu.tw/registration/"
    html, final_url = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    records, seen = [], set()
    for a in soup.select('a[href*="ACTID="], a[href*="actid="]'):
        href = urljoin(final_url, a.get("href", ""))
        if href in seen:
            continue
        seen.add(href)
        row = a.find_parent("tr")
        if row is None:
            row = a.parent
        row_text = clean(row.get_text(" ", strip=True))
        cells = row.find_all(["td", "th"], recursive=False) if row else []
        title = clean(cells[0].get_text(" ", strip=True)) if cells else ""
        title = title or clean(a.get_text(" ", strip=True))
        if not title or title.lower() in {"詳細資訊/報名", "event details/register", "報名"}:
            continue
        rec = make_record("研習暨演講活動", title, href, row_text or title,
                          {"list_text": row_text or title, "links": []})
        detail = extract_detail(href, title)
        if detail.get("fetch_status") == "ok":
            rec["full_text"] = detail.get("full_text") or rec["full_text"]
            rec["summary"] = extractive_summary(rec["full_text"])
            rec["dates_found"] = list(dict.fromkeys(rec["dates_found"] + detail.get("dates_found", [])))
            rec["detail_fetch_status"] = "ok"
        else:
            rec["detail_fetch_status"] = detail.get("fetch_status", "error")
        rec["registration_links"] = [{"title": "活動詳情／報名", "url": href}]
        records.append(rec)
    return records

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
        else:
            results.append(safe_source(name, lambda n=name, u=url: crawl_listing(n, u, max_details=25)))
    return results
