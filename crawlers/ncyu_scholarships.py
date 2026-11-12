from __future__ import annotations
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .common import safe_source, fetch, clean, make_record, extract_detail, extractive_summary
from .scholarships import classify, extract_dimensions, assess, deadline_fields

LIST_URL = "https://website.ncyu.edu.tw/life/Subject?nodeId=55082"
MAX_LIST_PAGES = 5
MAX_DETAIL_PAGES = 24
INTERNAL_CATEGORIES = {
    "余傳韜校長紀念獎助學金", "扶弱就學助學金", "清寒學生獎學金",
    "志翔清寒獎學金", "常德清寒學生獎學金", "廖金鳳老師紀念獎學金",
    "解碧華女士紀念獎學金", "王蕙山王郭恩思夫婦優秀清寒學生獎學金",
    "碩士清寒學生致學獎學金", "精進校務經營獎學金",
    "精進校務經營生活服務助學金"
}

def deadline_from_text(text):
    match = re.search(r"(?:截止|申請至|受理至|收件至|申請日期自即日起至)[：:，,\s]*(.{0,35}?(?:日|號))", text or "")
    raw = clean(match.group(0)) if match else ""
    return deadline_fields(raw, raw)[0], raw

def add_page_records(soup, page_url, source, scope, records, seen, detail_state):
    for a in soup.select('a[href*="/Subject/Detail/"]'):
        title = clean(a.get_text(" ", strip=True))
        href = urljoin(page_url, a.get("href", ""))
        if not title or href in seen or not any(k in title for k in ["獎學金", "獎助", "助學金"]):
            continue
        seen.add(href)
        detail_text = ""
        attachments = []
        detail_status = "not_fetched"
        if detail_state["count"] < MAX_DETAIL_PAGES:
            detail = extract_detail(href, title)
            detail_status = detail.get("fetch_status", "error")
            if detail_status == "ok":
                detail_text = detail.get("full_text", "")
                for link in detail.get("links", []):
                    if re.search(r"\.(pdf|docx?|xlsx?|pptx?)(?:$|[?#])", link.get("url", ""), re.I):
                        attachments.append(link)
                detail_state["count"] += 1
        full_text = "\n".join(x for x in [title, detail_text] if x)
        grades, departments = extract_dimensions(full_text, "")
        deadline_date, deadline_text = deadline_from_text(full_text)
        rec = make_record(source, title, href, full_text)
        rec.update({
            "source": source, "school_scope": scope, "list_text": title,
            "full_text": full_text, "summary": extractive_summary(full_text),
            "eligible_grades": grades, "eligible_departments": departments,
            "categories": classify(title, full_text, ""),
            "deadline_date": deadline_date, "deadline_text": deadline_text,
            "official_listing_url": LIST_URL, "detail_fetch_status": detail_status,
            "attachments": attachments, "application_documents": attachments,
            "registration_links": [],
        })
        rec.update(assess(full_text))
        records.append(rec)

def crawl_ncyu_scholarships():
    records, seen = [], set()
    detail_state = {"count": 0}

    # 校外獎助學金：公告依最新日期排序，先抓最近五頁，避免每小時掃描數百筆歷史公告。
    page_url = LIST_URL
    for _ in range(MAX_LIST_PAGES):
        html, final_url = fetch(page_url)
        soup = BeautifulSoup(html, "lxml")
        add_page_records(soup, final_url, "嘉義大學校外獎助學金", "external", records, seen, detail_state)
        next_link = next((a for a in soup.select("a[href]") if "下一頁" in clean(a.get_text(" ", strip=True))), None)
        if not next_link:
            break
        next_url = urljoin(final_url, next_link.get("href", ""))
        if not next_url or next_url == page_url:
            break
        page_url = next_url

    # 校內獎助學金：從官方導覽列找到各獎助學金分類頁，再抓取該分類最新公告。
    html, final_url = fetch(LIST_URL)
    soup = BeautifulSoup(html, "lxml")
    category_urls = {}
    for a in soup.select("a[href]"):
        label = clean(a.get_text(" ", strip=True))
        if label in INTERNAL_CATEGORIES:
            category_urls[label] = urljoin(final_url, a.get("href", ""))
    for label, category_url in category_urls.items():
        try:
            category_html, category_final = fetch(category_url)
            category_soup = BeautifulSoup(category_html, "lxml")
            add_page_records(category_soup, category_final, "嘉義大學校內獎助學金", "ncyu", records, seen, detail_state)
        except Exception as exc:
            print(f"[NCYU] category fetch failed: {label}: {exc}")

    if not records:
        raise RuntimeError("嘉義大學獎助學金列表未擷取到資料")
    print(f"[NCYU] captured {len(records)} records; fetched {detail_state['count']} detail pages; internal categories {len(category_urls)}")
    return records

def run():
    return safe_source("嘉義大學獎助學金", crawl_ncyu_scholarships)
