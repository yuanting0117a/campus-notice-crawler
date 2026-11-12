from .common import safe_source, fetch, make_record, clean, extract_dates, extractive_summary
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

LIST_URL = "https://www.osa.nchu.edu.tw/osa/laa/sys/modules/osa_scholarship/index.html"
MAIN_URL = "https://www.osa.nchu.edu.tw/osa/laa/scholarship.html"

def assess(text):
    t = text or ""
    mandatory_patterns = [
        r"(須|需|應|限|僅限|必須).{0,30}(低收入戶|中低收入戶)",
        r"(低收入戶|中低收入戶).{0,30}(證明|資格).{0,20}(必備|檢附|限)",
        r"限(低收入戶|中低收入戶)",
    ]
    preference_patterns = [
        r"(優先|加分|酌予優先).{0,25}(低收入戶|中低收入戶)",
        r"(低收入戶|中低收入戶).{0,25}(優先|加分)"
    ]
    if re.search(r"A類[\\s\\S]{0,2500}B\\s*類", t):
        return {
            "eligibility_status": "needs_verification",
            "eligibility_reason": "此獎助金分 A、B 類：A 類不以低收入戶／中低收入戶身分為必要條件，但仍有家庭收入、財產、成績等門檻；B 類要求低收入戶／中低收入戶身分。",
            "low_income_condition": "separate_paths",
            "eligibility_paths": [
                {"path": "A類", "status": "needs_verification", "reason": "不要求低收入戶身分；需再核對家庭年收入、利息、財產、成績及其他限制。"},
                {"path": "B類", "status": "ineligible", "reason": "要求低收入戶或中低收入戶身分。"}
            ]
        }
    if any(re.search(p, t) for p in mandatory_patterns):
        return {"eligibility_status": "ineligible", "eligibility_reason": "公告文字顯示低收入戶／中低收入戶為必要條件；依使用者提供的資格資訊標示不符合。", "low_income_condition": "mandatory"}
    if any(re.search(p, t) for p in preference_patterns):
        return {"eligibility_status": "needs_verification", "eligibility_reason": "低收入戶似為優先條件，不應直接視為必要資格；仍需核對完整辦法。", "low_income_condition": "preference"}
    if any(k in t for k in ["低收入戶", "中低收入戶", "清寒", "經濟弱勢"]):
        return {"eligibility_status": "needs_verification", "eligibility_reason": "出現經濟條件字樣，但無法僅憑列表判斷是必要或優先條件。", "low_income_condition": "unclear"}
    return {"eligibility_status": "needs_verification", "eligibility_reason": "尚須核對年級、系所、成績、文件及其他個別條件。", "low_income_condition": "not_seen"}

def crawl_scholarship_table():
    html, final_url = fetch(LIST_URL)
    soup = BeautifulSoup(html, "lxml")
    records = []
    seen = set()
    for row in soup.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 4:
            continue
        title = clean(cells[0].get_text(" ", strip=True))
        criteria = clean(cells[2].get_text(" ", strip=True))
        if not title or title in {"獎學金名稱", "獎助學金名稱"} or len(title) < 5:
            continue
        if title in seen:
            continue
        # Ignore navigation/resource rows and keep only actual scholarship rows.
        if not any(k in title for k in ["獎學金", "獎助", "助學金", "Scholarship", "scholarship"]):
            continue
        seen.add(title)
        row_links = []
        for a in row.select("a[href]"):
            href = urljoin(final_url, a.get("href", ""))
            label = clean(a.get_text(" ", strip=True)) or clean(a.get("title", ""))
            if href.startswith(("http://", "https://")):
                row_links.append({"title": label or "相關文件", "url": href})
        detail = next((x for x in row_links if "nsn=" in x["url"].lower()), None)
        if detail is None:
            detail = next((x for x in row_links if "更多詳細資訊" in x["title"] or "詳細資訊" in x["title"]), None)
        docs = [x for x in row_links if re.search(r"\\.(pdf|docx?|xlsx?|pptx?)(?:$|[?#])", x["url"], re.I)]
        audience = clean(cells[1].get_text(" ", strip=True))
        deadline = clean(cells[3].get_text(" ", strip=True))
        content = "\\n".join([
            "獎學金名稱：" + title,
            "適用對象：" + audience,
            "獎助對象與條件：" + (criteria or "請查看官方公告"),
            "申請期限：" + deadline,
        ])
        source_url = detail["url"] if detail else LIST_URL
        rec = make_record("獎學金", title, source_url, content)
        rec.update({
            "full_text": content,
            "list_text": content,
            "summary": extractive_summary(content),
            "dates_found": extract_dates(content),
            "official_listing_url": LIST_URL,
            "detail_url": detail["url"] if detail else "",
            "attachments": docs,
            "application_documents": docs,
        })
        rec.update(assess(content))
        records.append(rec)
    return records

def run():
    return safe_source("獎學金", crawl_scholarship_table)
