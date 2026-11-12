from __future__ import annotations
import re, time, json
from io import BytesIO
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NCHUCampusNoticeCrawler/1.0; +https://github.com/yuanting0117a/campus-notice-crawler)"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
TIMEOUT = 12

def fetch(url):
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    content_type = (r.headers.get("Content-Type") or "").lower()
    # Never decode binary documents (PDF, legacy Office, DOCX/XLSX ZIP containers) as HTML.
    signature = r.content[:8]
    if ("application/pdf" in content_type or
        "application/msword" in content_type or
        "application/vnd" in content_type or
        signature.startswith(b"%PDF-") or
        signature.startswith(b"PK\x03\x04") or
        signature.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))):
        raise ValueError("Binary attachment is not an HTML page")
    r.encoding = r.apparent_encoding or r.encoding
    return r.text, r.url

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()

def page_text(soup):
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    return clean(soup.get_text(" ", strip=True))

def absolute(base, href):
    return urljoin(base, href) if href else ""

def links_from(soup, base):
    out = []
    for a in soup.select("a[href]"):
        href = absolute(base, a.get("href"))
        title = clean(a.get_text(" ", strip=True)) or clean(a.get("title", ""))
        if href.startswith(("http://", "https://")) and title:
            out.append({"title": title, "url": href})
    return out

def extractive_summary(text, limit=5):
    sentences = [clean(x) for x in re.split(r"(?<=[。！？；])", text or "") if clean(x)]
    if len(sentences) <= limit:
        return " ".join(sentences)[:1200]
    keywords = ["日期", "時間", "地點", "報名", "截止", "名額", "對象", "資格", "費用", "學分", "講者", "申請", "文件", "清寒", "成績", "限"]
    ranked = sorted(enumerate(sentences), key=lambda p: (sum(k in p[1] for k in keywords), -p[0]), reverse=True)
    chosen = sorted(i for i, _ in ranked[:limit])
    return " ".join(sentences[i] for i in chosen)[:1200]

def extract_pdf_text(url):
    if not re.search(r"\.pdf($|\?)", url, re.I):
        return ""
    try:
        from pypdf import PdfReader
        response = SESSION.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        reader = PdfReader(BytesIO(response.content))
        return clean(" ".join(page.extract_text() or "" for page in reader.pages))
    except Exception:
        return ""

def extract_dates(text):
    patterns = [
        r"(?:民國)?\s*(?:1\d{2}|20\d{2})[年./-]\s*\d{1,2}[月./-]\s*\d{1,2}日?",
        r"20\d{2}/\d{1,2}/\d{1,2}",
        r"20\d{2}-\d{1,2}-\d{1,2}",
    ]
    found = []
    for p in patterns:
        found.extend(re.findall(p, text or ""))
    return list(dict.fromkeys(found))

def classify_audience(text):
    keys = ["本校學生", "全校學生", "大學部", "研究生", "碩士班", "博士班", "教職員", "不限", "限本校"]
    return [k for k in keys if k in (text or "")]

def extract_detail(url, title=""):
    try:
        # Attachments are retained as links; never parse their binary bytes as page text.
        if re.search(r"\.(pdf|docx?|xlsx?|pptx?|zip|jpg|jpeg|png)(?:$|[?#])", url, re.I):
            return {"title": title, "url": url, "full_text": "",
                    "links": [], "dates_found": [], "fetch_status": "binary_attachment"}
        html, final_url = fetch(url)
        soup = BeautifulSoup(html, "lxml")
        text = page_text(soup)
        return {"title": title or (soup.title.get_text(strip=True) if soup.title else ""),
                "url": final_url, "full_text": text, "links": links_from(soup, final_url),
                "dates_found": extract_dates(text), "fetch_status": "ok"}
    except Exception as e:
        return {"title": title, "url": url, "full_text": "", "links": [],
                "dates_found": [], "fetch_status": "error", "error": str(e)}

def make_record(source, title, url, text, extra=None):
    text = clean(text)
    rec = {
        "source": source, "title": clean(title) or "(未辨識標題)", "url": url,
        "full_text": text, "summary": extractive_summary(text), "summary_type": "規則式重點摘錄（保留完整原文供核對）",
        "dates_found": extract_dates(text), "audience_hints": classify_audience(text),
        "registration_links": [], "attachments": [], "important_notes": [k for k in ["限額", "額滿", "需事先報名", "報名截止", "僅限", "限本校", "費用", "免費", "需繳交", "需檢附", "候補", "審核", "取消"] if k in text], "last_checked": datetime.now(timezone.utc).isoformat(),
    }
    extra = extra or {}
    for link in extra.get("links", []):
        label = link["title"].lower()
        href = link["url"]
        if any(k in label for k in ["報名", "register", "申請", "下載", "簡章", "辦法", "表單"]):
            (rec["attachments"] if re.search(r"\.(pdf|docx?|xlsx?)($|\?)", href, re.I) else rec["registration_links"]).append(link)
    rec.update({k:v for k,v in extra.items() if k != "links"})
    return rec

def crawl_listing(source, url, max_details=50, title_selector=None):
    html, final_url = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    records, seen = [], set()
    # Capture rows/cards first, retaining the whole row's original text.
    for node in soup.select("tr, article, .item, .event, .activity, .news, .card, .list-group-item, .event-item, .activity-item"):
        text = clean(node.get_text(" ", strip=True))
        anchors = node.select("a[href]")
        if not anchors or len(text) < 12:
            continue
        # Prefer an announcement/detail page over a downloadable application form.
        detail_anchors = [a for a in anchors if not re.search(
            r"\.(pdf|docx?|xlsx?|pptx?|zip|jpg|jpeg|png)($|[?#])",
            absolute(final_url, a.get("href")), re.I)]
        a = next((x for x in detail_anchors if "nsn=" in x.get("href", "").lower()
                  or "actid=" in x.get("href", "").lower()), None)
        if a is None and detail_anchors:
            a = detail_anchors[0]
        if a is None:
            continue
        href = absolute(final_url, a.get("href"))
        # Keep the announcement heading from the first meaningful link, even when
        # the chosen destination is a separate "more details" link.
        title_anchor = next((x for x in anchors if clean(x.get_text(" ", strip=True))
                             and not re.search(r"\.(pdf|docx?|xlsx?|pptx?|zip|jpg|jpeg|png)($|[?#])",
                                               absolute(final_url, x.get("href")), re.I)), a)
        title = clean(title_anchor.get_text(" ", strip=True)) or clean(title_anchor.get("title", ""))
        # Ignore document/resource rows that are not actual activity announcements.
        if re.search(r"\.(pdf|docx?|xlsx?|pptx?|zip|jpg|jpeg|png)(?:$|[?#])", href, re.I):
            continue
        if any(k in (title + " " + text + " " + href).lower()
               for k in ["隱私", "個資", "同意書", "privacy", "consent", "policy"]):
            continue
        if href in seen or urlparse(href).netloc != urlparse(final_url).netloc:
            continue
        seen.add(href)
        links = links_from(node, final_url)
        records.append(make_record(source, title, href, text, {"links": links, "list_text": text}))
    # Fallback: collect plausible detail links if page layout is not row-based.
    if not records:
        for link in links_from(soup, final_url):
            href = link["url"]
            if urlparse(href).netloc != urlparse(final_url).netloc or href in seen:
                continue
            if any(x in href.lower() for x in ["login", "logout", "javascript:", "mailto:"]):
                continue
            # Generic navigation fallbacks must not be mistaken for announcements.
            # PDFs and privacy/consent/policy pages are resources, not event listings.
            if re.search(r"\.pdf(?:$|[?#])", href, re.I):
                continue
            if any(k in (link["title"] + " " + href).lower()
                   for k in ["隱私", "個資", "同意書", "privacy", "consent", "policy"]):
                continue
            seen.add(href)
            records.append(make_record(source, link["title"], href, link["title"], {"links": []}))
            if len(records) >= max_details:
                break
    # Enrich a limited number of records with their detail pages.
    for rec in records[:max_details]:
        if rec["url"] == final_url:
            continue
        detail = extract_detail(rec["url"], rec["title"])
        if detail["fetch_status"] == "ok":
            rec["full_text"] = detail["full_text"] or rec["full_text"]
            rec["summary"] = extractive_summary(rec["full_text"])
            rec["dates_found"] = list(dict.fromkeys(rec["dates_found"] + detail["dates_found"]))
            rec["registration_links"] = list({x["url"]:x for x in rec["registration_links"] + [
                l for l in detail["links"] if any(k in l["title"].lower() for k in ["報名","register","申請","填寫"])
            ]}.values())
            rec["attachments"] = list({x["url"]:x for x in rec["attachments"] + [
                l for l in detail["links"] if re.search(r"\.(pdf|docx?|xlsx?)($|\?)", l["url"], re.I)
            ]}.values())
            rec["attachment_texts"] = []
            for attachment in rec["attachments"][:5]:
                if attachment["url"].lower().split("?")[0].endswith(".pdf"):
                    extracted = extract_pdf_text(attachment["url"])
                    if extracted:
                        rec["attachment_texts"].append({"name": attachment["title"], "url": attachment["url"], "text": extracted})
            rec["detail_fetch_status"] = "ok"
        else:
            rec["detail_fetch_status"] = "error"
            rec["detail_error"] = detail.get("error", "")
    return records

def safe_source(source, fn):
    started = datetime.now(timezone.utc).isoformat()
    try:
        records = fn()
        return {"source": source, "status": "ok" if records else "empty",
                "checked_at": started, "count": len(records), "records": records}
    except Exception as e:
        return {"source": source, "status": "error", "checked_at": started,
                "count": 0, "records": [], "error": str(e)}
