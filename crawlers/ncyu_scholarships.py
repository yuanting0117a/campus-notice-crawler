from __future__ import annotations
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from .common import safe_source, fetch, clean, make_record, extract_detail, extractive_summary
from .scholarships import classify, extract_dimensions, assess, deadline_fields

LIST_URL = "https://website.ncyu.edu.tw/life/Subject?nodeId=55082"
MAX_LIST_PAGES = 5
MAX_DETAIL_PAGES = 15

def crawl_ncyu_scholarships():
    records = []
    seen = set()
    page_url = LIST_URL
    pages = 0
    detail_count = 0
    while page_url and pages < MAX_LIST_PAGES:
        html, final_url = fetch(page_url)
        soup = BeautifulSoup(html, "lxml")
        pages += 1
        for a in soup.select('a[href*="/Subject/Detail/"]'):
            title = clean(a.get_text(" ", strip=True))
            href = urljoin(final_url, a.get("href", ""))
            if not title or href in seen or not any(k in title for k in ["獎學金", "獎助", "助學金"]):
                continue
            seen.add(href)
            is_internal = any(k in title for k in [
                "余傳韜校長", "扶弱就學", "清寒學生獎學金", "志翔清寒",
                "常德清寒", "廖金鳳", "解碧華", "王蕙山", "碩士清寒",
                "精進校務經營"
            ])
            source = "嘉義大學校內獎助學金" if is_internal else "嘉義大學校外獎助學金"
            list_text = title
            detail_text = ""
            attachments = []
            detail_status = "not_fetched"
            if detail_count < MAX_DETAIL_PAGES:
                detail = extract_detail(href, title)
                detail_status = detail.get("fetch_status", "error")
                if detail_status == "ok":
                    detail_text = detail.get("full_text", "")
                    for link in detail.get("links", []):
                        if re.search(r"\.(pdf|docx?|xlsx?|pptx?)(?:$|[?#])", link.get("url", ""), re.I):
                            attachments.append(link)
                    detail_count += 1
            full_text = "\n".join(x for x in [title, detail_text] if x)
            grades, departments = extract_dimensions(full_text, "")
            rec = make_record(source, title, href, full_text)
            rec.update({
                "source": source,
                "school_scope": "ncyu" if is_internal else "external",
                "list_text": list_text,
                "full_text": full_text,
                "summary": extractive_summary(full_text),
                "eligible_grades": grades,
                "eligible_departments": departments,
                "categories": classify(title, full_text, ""),
                "deadline_date": deadline_fields("", full_text)[0],
                "deadline_text": "",
                "official_listing_url": LIST_URL,
                "detail_fetch_status": detail_status,
                "attachments": attachments,
                "application_documents": attachments,
                "registration_links": [],
            })
            rec.update(assess(full_text))
            records.append(rec)
        next_link = next((a for a in soup.select("a[href]") if "下一頁" in clean(a.get_text(" ", strip=True))), None)
        if not next_link:
            break
        next_url = urljoin(final_url, next_link.get("href", ""))
        if next_url == page_url:
            break
        page_url = next_url
    if not records:
        raise RuntimeError("嘉義大學獎助學金列表未擷取到資料")
    return records

def run():
    return safe_source("嘉義大學獎助學金", crawl_ncyu_scholarships)
