from __future__ import annotations
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .common import safe_source, fetch, clean, make_record, extract_detail, extractive_summary, extract_pdf_text
from .scholarships import classify, extract_dimensions, assess, deadline_fields

LIST_URL = "https://website.ncyu.edu.tw/life/Subject?nodeId=55082"
MAX_LIST_PAGES = 5
MAX_DETAIL_PAGES = 80
INTERNAL_CATEGORIES = {
    "余傳韜校長紀念獎助學金", "扶弱就學助學金", "清寒學生獎學金",
    "志翔清寒獎學金", "常德清寒學生獎學金", "廖金鳳老師紀念獎學金",
    "解碧華女士紀念獎學金", "王蕙山王郭恩思夫婦優秀清寒學生獎學金",
    "碩士清寒學生致學獎學金", "精進校務經營獎學金",
    "精進校務經營生活服務助學金"
}

# Additional official NCYU college/department scholarship boards.
# Only the first/latest listing page is scanned; each announcement's detail page is fetched.
DEPARTMENT_LISTS = {
    "管理學院": "https://website.ncyu.edu.tw/gramgt/Subject?nodeId=35097",
    "農藝學系": "https://website.ncyu.edu.tw/agri/Subject?nodeId=15136",
    "體育與健康休閒學系": "https://website.ncyu.edu.tw/dpe/Subject?nodeId=9477",
    "生物機電工程學系": "https://website.ncyu.edu.tw/bioeng/Subject?nodeId=65120",
    "園藝學系": "https://website.ncyu.edu.tw/hortsci/Subject?nodeId=15113",
    "木質材料與設計學系": "https://website.ncyu.edu.tw/fps/Subject?nodeId=12515",
}

def deadline_from_text(text):
    text = clean(text or "")
    date_pattern = r"(?:(?:民國)?(?:1\d{2}|20\d{2})\s*[年./-]\s*)?\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?"
    patterns = [
        rf"(?:收件截止日|截止日期|截止日|申請截止日|申請截止|受理至|收件至|申請至|截止至|截至)\s*[：:，,]?\s*({date_pattern})",
        rf"(?:自|從).{{0,50}}?(?:至|到)\s*({date_pattern})",
        rf"(?:至|到)\s*({date_pattern})(?:止|截止|為止)?",
        rf"(?:於|在)\s*({date_pattern})\s*(?:前|截止|止)",
    ]
    candidates = []
    for pattern in patterns:
        candidates.extend(re.finditer(pattern, text))
    if not candidates:
        return "", ""
    match = max(candidates, key=lambda item: item.start(1))
    date_raw = re.sub(r"\s+", "", match.group(1))
    deadline_date = deadline_fields(date_raw, date_raw)[0]
    return deadline_date, clean(match.group(0))


def is_document_link(link):
    label = clean(link.get("title", ""))
    href = link.get("url", "") or ""
    extension = r"\.(pdf|docx?|xlsx?|pptx?|odt|ods|odp|zip)"
    return bool(re.search(extension + r"(?:\b|$|[?#])", label, re.I)
                or re.search(extension + r"(?:$|[?#])", href, re.I))


def is_application_link(link):
    label = clean(link.get("title", ""))
    href = link.get("url", "") or ""
    if "adm.ncyu.edu.tw" in href and any(word in label for word in ["申請", "獎學金", "助學金"]):
        return True
    if ("website.ncyu.edu.tw" not in href and "ServerFile/Get" not in href
            and any(word in label for word in ["獎學金申請", "助學金申請", "獎助學金申請",
                                                "申請表單", "填寫獎學金", "填寫助學金"])):
        return True
    return False

def add_page_records(soup, page_url, source, scope, records, seen, detail_state):
    for a in soup.select('a[href*="/Subject/Detail/"]'):
        title = clean(a.get_text(" ", strip=True))
        href = urljoin(page_url, a.get("href", ""))
        if not title or href in seen or not any(k in title for k in ["獎學金", "獎助", "助學金"]):
            continue
        # Skip award-result lists; they are not open applications.
        if re.search(r"(錄取名單|獲獎名單|得獎名單|獲選名單|核定名單|得獎學生名單)", title):
            continue
        # Pure rule/establishment documents are reference material, not an open application notice.
        if re.search(r"(獎助學金|獎學金).{0,20}(設置要點|辦法)$", title) and not re.search(r"(申請公告|受理申請|申請自|申請至)", title):
            continue
        # Older academic-year notices are no longer current application opportunities.
        old_year = re.search(r"(11[0-4])(?:學年度|年度|年|[-－][12])", title)
        if old_year:
            continue
        seen.add(href)
        detail_text = ""
        attachments = []
        attachment_texts = []
        registration_links = []
        detail_status = "not_fetched"
        if detail_state["count"] < MAX_DETAIL_PAGES:
            detail = extract_detail(href, title)
            detail_status = detail.get("fetch_status", "error")
            if detail_status == "ok":
                detail_text = detail.get("full_text", "")
                for link in detail.get("links", []):
                    if is_document_link(link):
                        attachments.append(link)
                    elif is_application_link(link):
                        registration_links.append(link)
                # Many NCYU notices put the actual eligibility rules in attached PDFs,
                # while the HTML detail page contains only a title and download link.
                pdf_attachments = [x for x in attachments if re.search(r"\.pdf(?:$|[?#])", x.get("title", ""), re.I) or re.search(r"\.pdf(?:$|[?#])", x.get("url", ""), re.I)]
                for attachment in pdf_attachments[:3]:
                    extracted = extract_pdf_text(attachment["url"])
                    if extracted:
                        attachment_texts.append({
                            "name": attachment.get("title", "公告附件"),
                            "url": attachment["url"],
                            "text": extracted[:12000],
                        })
                if attachment_texts:
                    detail_text = "\n".join([detail_text] + [
                        "附件「" + x["name"] + "」內容：" + x["text"] for x in attachment_texts
                    ])
                detail_state["count"] += 1
        full_text = "\n".join(x for x in [title, detail_text] if x)
        grades, departments = extract_dimensions(full_text, "")
        title_deadline, title_deadline_text = deadline_from_text(title)
        detail_deadline, detail_deadline_text = deadline_from_text(detail_text)
        deadline_candidates = [x for x in [title_deadline, detail_deadline] if x]
        deadline_conflict_text = ""
        if len(set(deadline_candidates)) > 1:
            # When the heading and detailed body disagree, use the earlier date conservatively
            # and expose both original texts so the user can verify with the official source.
            deadline_date = min(deadline_candidates)
            deadline_text = f"標題：{title_deadline_text}；內文：{detail_deadline_text}"
            deadline_conflict_text = "公告標題與內文的申請期限不一致，暫以較早日期提醒；請以官方申請系統／承辦單位確認。"
        else:
            deadline_date = deadline_candidates[0] if deadline_candidates else ""
            deadline_text = title_deadline_text or detail_deadline_text
        rec = make_record(source, title, href, full_text)
        rec.update({
            "source": source, "school_scope": scope, "list_text": title,
            "full_text": full_text, "summary": extractive_summary(full_text),
            "eligible_grades": grades, "eligible_departments": departments,
            "categories": classify(title, full_text, ""),
            "deadline_date": deadline_date, "deadline_text": deadline_text, "deadline_conflict_text": deadline_conflict_text,
            "official_listing_url": LIST_URL, "detail_fetch_status": detail_status,
            "attachments": attachments, "application_documents": attachments,
            "attachment_texts": attachment_texts,
            "registration_links": registration_links,
        })
        rec.update(assess(full_text))
        records.append(rec)

def crawl_ncyu_scholarships():
    records, seen = [], set()
    detail_state = {"count": 0}
    warnings = []

    # 校外獎助學金：公告依最新日期排序，先抓最近五頁，避免每小時掃描數百筆歷史公告。
    page_url = LIST_URL
    for page_number in range(1, MAX_LIST_PAGES + 1):
        html, final_url = fetch(page_url)
        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(" ", strip=True)
        if "系統錯誤" in page_text or "造成錯誤的原因" in page_text:
            warnings.append(f"校外獎助學金第 {page_number} 頁分頁回傳系統錯誤，僅保留已成功取得的公告")
            break
        add_page_records(soup, final_url, "嘉義大學校外獎助學金", "external", records, seen, detail_state)
        next_link = next((a for a in soup.select("a[href]") if "下一頁" in clean(a.get_text(" ", strip=True))), None)
        if not next_link:
            break
        if page_number == MAX_LIST_PAGES:
            warnings.append(f"校外獎助學金僅掃描前 {MAX_LIST_PAGES} 頁，未涵蓋官方全部歷史公告")
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

    # Expand coverage to official college/department scholarship boards.
    department_pages_fetched = 0
    for unit_name, unit_url in DEPARTMENT_LISTS.items():
        try:
            unit_html, unit_final = fetch(unit_url)
            unit_soup = BeautifulSoup(unit_html, "lxml")
            before_count = len(records)
            add_page_records(unit_soup, unit_final, f"嘉義大學院系獎助學金（{unit_name}）", "ncyu", records, seen, detail_state)
            department_pages_fetched += 1
            print(f"[NCYU] department board {unit_name}: +{len(records) - before_count} records")
        except Exception as exc:
            warnings.append(f"院系獎助學金頁面讀取失敗：{unit_name}：{exc}")

    if not records:
        raise RuntimeError("嘉義大學獎助學金列表未擷取到資料")
    attachment_count = sum(len(record.get("attachments", [])) for record in records)
    print(f"[NCYU] captured {len(records)} records; fetched {detail_state['count']} detail pages; internal categories {len(category_urls)}; department boards {department_pages_fetched}/{len(DEPARTMENT_LISTS)}; attachments {attachment_count}")
    if warnings:
        print("[NCYU] WARNINGS: " + " | ".join(warnings))
    return records, warnings, detail_state["count"], len(category_urls), department_pages_fetched

def run():
    from datetime import datetime, timezone
    started = datetime.now(timezone.utc).isoformat()
    try:
        records, warnings, detail_count, category_count, department_count = crawl_ncyu_scholarships()
        return {
            "source": "嘉義大學獎助學金",
            "status": "partial" if warnings else ("ok" if records else "empty"),
            "checked_at": started,
            "count": len(records),
            "records": records,
            "warnings": warnings,
            "detail_pages_fetched": detail_count,
            "internal_categories_crawled": category_count,
            "department_boards_crawled": department_count,
            "attachment_count": sum(len(record.get("attachments", [])) for record in records),
        }
    except Exception as exc:
        return {"source": "嘉義大學獎助學金", "status": "error", "checked_at": started,
                "count": 0, "records": [], "error": str(exc)}
