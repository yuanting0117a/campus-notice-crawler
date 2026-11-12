from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .common import fetch, clean, extract_detail, extract_pdf_text, make_record, extractive_summary
from .scholarships import assess, extract_dimensions, deadline_fields

# Official NKNU scholarship and student-assistance entry points.
LIST_PAGES = [
    ("高師大獎助學金一覽表", "https://sso.nknu.edu.tw/OSA/Scholarship/ScholarshipS.aspx"),
    ("高師大學生就學助學", "https://sso.nknu.edu.tw/Services/Web/Default.aspx?cMenuId=561&cWebIdx=596"),
    ("高師大校園行政公告", "https://news.nknu.edu.tw/nknu_News/lastNewsList.aspx?cat=SCHOOLADMIN"),
    ("高師大校園活動公告", "https://news.nknu.edu.tw/nknu_News/lastNewsList.aspx?cat=CAMPUS"),
]
KEYWORDS = ("獎學金", "獎助學金", "助學金", "就學補助", "急難慰助", "生活助學", "獎勵金", "補助")
EXCLUDE = ("獲獎名單", "得獎名單", "錄取名單", "核定名單", "成果名單")
MAX_DETAILS = 80


def is_pdf_link(link):
    title = clean(link.get("title", ""))
    url = link.get("url", "")
    return bool(re.search(r"\.pdf(?:$|[?#])", title, re.I)
                or re.search(r"\.pdf(?:$|[?#])", url, re.I)
                or ("pdf" in title.lower() and url))


def parse_deadline(text):
    text = clean(text or "")
    date = r"(?:(?:民國)?(?:1\d{2}|20\d{2})\s*[年./-]\s*)?\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?"
    patterns = [
        rf"(?:截止日期|截止日|申請截止|收件截止|受理至|申請至|收件至|截止至|截至)\s*[：:]?\s*({date})",
        rf"(?:於|在)\s*({date})\s*(?:前|截止|止)",
        rf"(?:至|到)\s*({date})(?:止|截止|為止)?",
    ]
    found = []
    for pattern in patterns:
        found.extend(re.finditer(pattern, text))
    if not found:
        return "", ""
    match = max(found, key=lambda m: m.start(1))
    raw = re.sub(r"\s+", "", match.group(1))
    parsed = deadline_fields(raw, raw)[0]
    return parsed, clean(match.group(0))


def discover_links(soup, page_url):
    found = {}
    for a in soup.select("a[href]"):
        title = clean(a.get_text(" ", strip=True)) or clean(a.get("title", ""))
        href = urljoin(page_url, a.get("href", ""))
        if not title or not href.startswith(("http://", "https://")):
            continue
        parent = a.find_parent(["tr", "li", "article"])
        row_text = clean(parent.get_text(" ", strip=True)) if parent else title
        combined = title + " " + row_text
        if not any(k in combined for k in KEYWORDS):
            continue
        if "補助" in combined and not any(k in combined for k in ("學生", "學士", "碩士", "博士", "在學", "本校")):
            continue
        if any(k in combined for k in EXCLUDE):
            continue
        # Keep announcement pages, not the attachment or application form itself.
        if re.search(r"\.(pdf|docx?|xlsx?|pptx?|zip)(?:$|[?#])", href, re.I):
            continue
        if href not in found:
            found[href] = {"title": title, "url": href, "list_text": row_text}
    return list(found.values())


def crawl_nknu_scholarships():
    discovered = {}
    warnings = []
    for label, url in LIST_PAGES:
        try:
            page_url = url
            page_seen = set()
            page_count = 0
            while page_url and page_url not in page_seen and page_count < 5:
                page_seen.add(page_url)
                html, final_url = fetch(page_url)
                soup = BeautifulSoup(html, "lxml")
                links = discover_links(soup, final_url)
                for link in links:
                    discovered.setdefault(link["url"], {**link, "listing_source": label})
                next_link = next((a for a in soup.select("a[href]") if any(k in clean(a.get_text(" ", strip=True)) for k in ("下一頁", "下頁", "Next", "›", "»"))), None)
                page_count += 1
                page_url = urljoin(final_url, next_link.get("href", "")) if next_link else ""
            print(f"[NKNU] {label}: scanned {page_count} page(s), candidates accumulated {len(discovered)}")
        except Exception as exc:
            warnings.append(f"{label}讀取失敗：{exc}")

    records = []
    for item in list(discovered.values())[:MAX_DETAILS]:
        title, url = item["title"], item["url"]
        detail = extract_detail(url, title)
        detail_text = detail.get("full_text", "") if detail.get("fetch_status") == "ok" else ""
        attachments = []
        attachment_texts = []
        for link in detail.get("links", []):
            if is_pdf_link(link):
                attachments.append(link)
        for attachment in attachments[:4]:
            text = extract_pdf_text(attachment["url"])
            if text:
                attachment_texts.append({
                    "name": attachment.get("title", "公告 PDF"),
                    "url": attachment["url"],
                    "text": text[:12000],
                })
        full_text = "\n".join(
            x for x in [title, item.get("list_text", ""), detail_text] +
            ["附件「" + x["name"] + "」內容：" + x["text"] for x in attachment_texts] if x
        )
        grades, departments = extract_dimensions("", full_text)
        deadline_date, deadline_text = parse_deadline(full_text)
        rec = make_record("高雄師範大學獎助學金", title, url, full_text)
        rec.update({
            "source": "高師大獎助學金",
            "school_scope": "nknu",
            "list_text": item.get("list_text", ""),
            "full_text": full_text,
            "summary": extractive_summary(full_text),
            "eligible_grades": grades,
            "eligible_departments": departments,
            "categories": [],
            "deadline_date": deadline_date,
            "deadline_text": deadline_text,
            "official_listing_url": LIST_PAGES[0][1],
            "detail_fetch_status": detail.get("fetch_status", "error"),
            "attachments": attachments,
            "application_documents": attachments,
            "attachment_texts": attachment_texts,
            "registration_links": [],
            "listing_source": item.get("listing_source", ""),
        })
        rec.update(assess(full_text))
        records.append(rec)

    if not records:
        if warnings:
            raise RuntimeError("高師大官方獎助學金來源均無法讀取：" + "；".join(warnings))
        raise RuntimeError("高師大官方獎助學金頁面未擷取到公告；需檢查頁面是否改版或需登入")
    print(f"[NKNU] captured {len(records)} records; PDF texts {sum(len(x['attachment_texts']) for x in records)}")
    if warnings:
        print("[NKNU] WARNINGS: " + " | ".join(warnings))
    return records, warnings


def run():
    from datetime import datetime, timezone
    started = datetime.now(timezone.utc).isoformat()
    try:
        records, warnings = crawl_nknu_scholarships()
        return {
            "source": "高師大獎助學金",
            "status": "partial" if warnings else "ok",
            "checked_at": started,
            "count": len(records),
            "records": records,
            "warnings": warnings,
            "attachment_count": sum(len(x.get("attachments", [])) for x in records),
            "attachment_text_count": sum(len(x.get("attachment_texts", [])) for x in records),
        }
    except Exception as exc:
        return {
            "source": "高師大獎助學金",
            "status": "error",
            "checked_at": started,
            "count": 0,
            "records": [],
            "error": str(exc),
        }
