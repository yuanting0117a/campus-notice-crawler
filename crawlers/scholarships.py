from .common import safe_source, fetch, make_record, clean, extract_dates, extract_detail, crawl_related_pages, is_registration_link, extractive_summary
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

LIST_URL = "https://www.osa.nchu.edu.tw/osa/laa/sys/modules/osa_scholarship/index.html"
MAIN_URL = "https://www.osa.nchu.edu.tw/osa/laa/scholarship.html"

def clean_title(value):
    title = clean(value)
    # Remove duplicated application-window text from display titles.
    title = re.sub(r"[（(]收件(?:期間|時間)[：:].*$", "", title)
    title = re.sub(r"收件(?:期間|時間)[：:].*$", "", title)
    # The university appends an English translation to many Chinese announcement titles.
    markers = [
        r"Assistant Professor", r"Scholarships and Grants", r"Staff and Students",
        r"National Chung Hsing", r"Financial and Economic Law",
        r"Application dates?", r"For TAIWANESE", r"Marketing Scholar",
        r"Memorial Scholarship Application", r"Scholarship Application Dates"
    ]
    positions = [m.start() for p in markers if (m := re.search(p, title, re.I))]
    if positions:
        title = title[:min(positions)].strip(" -:：,，")
    # Catch bilingual titles whose English translation begins immediately after a Chinese closing bracket.
    title = re.split(r"(?<=[)）])(?=[A-Z][a-z]{2,}(?:\s|$))", title, maxsplit=1)[0]
    return clean(title).strip(" -:：,，")

def classify(title, audience, criteria):
    text = " ".join([title or "", audience or "", criteria or ""])
    categories = []
    if any(k in text for k in ["低收入戶", "中低收入戶", "清寒", "弱勢", "家庭突遭變故", "經濟弱勢", "助學金", "家境清寒"]):
        categories.append("清寒／經濟弱勢")
    if any(k in text for k in ["原住民", "身心障礙", "特殊境遇", "單親", "僑生", "新住民", "女性學生", "懷孕", "扶養未滿"]):
        categories.append("特殊身分")
    if any(k in text for k in ["成績", "操行", "排名", "前百分之", "不及格", "學業平均"]):
        categories.append("成績要求")
    departments = ["電機", "資訊工程", "資工", "生命科學", "農資", "管理", "法政", "獸醫",
                   "食品", "行銷", "物理", "化學", "機械", "材料", "土木", "環工",
                   "文學院", "理學院", "工學院", "電資學院", "生科院"]
    if any(k in text for k in departments) or re.search(r"系(大學部|在學|學生)|學院(大學部|在學|學生)", text):
        categories.append("系所／學院限定")
    if any(k in text for k in ["企業", "公司", "基金會", "協會", "捐助", "捐贈", "紀念獎學金"]):
        categories.append("企業／民間捐助")
    if not categories:
        categories.append("一般／其他")
    return categories

def short_summary(audience, criteria, deadline):
    parts = []
    if audience:
        parts.append("對象：" + audience)
    if deadline:
        parts.append("截止：" + deadline)
    if criteria:
        brief = re.sub(r"更多詳細資訊.*$", "", criteria)
        brief = re.sub(r"https?://\S+", "", brief)
        brief = re.sub(r"\s+", " ", brief).strip(" ：:，,")
        if len(brief) > 72:
            brief = brief[:72].rstrip() + "…"
        if brief:
            parts.append("條件摘要：" + brief)
    return "｜".join(parts)

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
    if re.search(r"A類[\s\S]{0,2500}B\s*類", t):
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
        raw_title = clean(cells[0].get_text(" ", strip=True))
        title = clean_title(raw_title)
        audience = clean(cells[1].get_text(" ", strip=True))
        criteria = clean(cells[2].get_text(" ", strip=True))
        deadline = clean(cells[3].get_text(" ", strip=True))
        if not title or title in {"獎學金名稱", "獎助學金名稱"} or len(title) < 5:
            continue
        if title in seen:
            continue
        if not any(k in title for k in ["獎學金", "獎助", "助學金", "獎助學金"]):
            continue
        seen.add(title)
        row_links = []
        for a in row.select("a[href]"):
            href = urljoin(final_url, a.get("href", ""))
            label = clean_title(a.get_text(" ", strip=True)) or clean(a.get("title", "")) or "相關文件"
            if href.startswith(("http://", "https://")):
                row_links.append({"title": label, "url": href})
        detail = next((x for x in row_links if "nsn=" in x["url"].lower()), None)
        if detail is None:
            detail = next((x for x in row_links if "更多詳細資訊" in x["title"] or "詳細資訊" in x["title"]), None)
        docs = [x for x in row_links if re.search(r"\.(pdf|docx?|xlsx?|pptx?)(?:$|[?#])", x["url"], re.I)]
        categories = classify(title, audience, criteria)
        content = "\n".join([
            "獎學金名稱：" + title,
            "適用對象：" + audience,
            "獎助對象與條件：" + (criteria or "請查看官方公告"),
            "申請期限：" + deadline,
        ])
        source_url = detail["url"] if detail else LIST_URL
        rec = make_record("獎學金", title, source_url, content)
        rec.update({
            "title": title,
            "source_title": raw_title,
            "full_text": content,
            "list_text": content,
            "summary": short_summary(audience, criteria, deadline),
            "dates_found": extract_dates(content),
            "target_level": audience,
            "categories": categories,
            "primary_category": categories[0],
            "official_listing_url": LIST_URL,
            "detail_url": detail["url"] if detail else "",
            "attachments": docs,
            "application_documents": docs,
        })
        rec.update(assess(content))
        # Follow the scholarship announcement and its information links, but not online application forms.
        if detail:
            detail_page = extract_detail(detail["url"], title)
            if detail_page.get("fetch_status") == "ok":
                linked_pages, linked_docs = crawl_related_pages(detail_page["links"], detail_page["url"])
                detail_text = detail_page.get("full_text", "")
                linked_text = "\\n".join(p["full_text"] for p in linked_pages if p["full_text"])
                combined = "\\n".join(x for x in [content, detail_text, linked_text] if x)
                rec["full_text"] = combined
                rec["summary"] = extractive_summary(combined)
                rec["linked_pages"] = linked_pages
                rec["dates_found"] = list(dict.fromkeys(rec["dates_found"] + detail_page.get("dates_found", []) +
                    [d for p in linked_pages for d in p.get("dates_found", [])]))
                rec["registration_links"] = [x for x in detail_page.get("links", []) if is_registration_link(x)]
                rec["attachments"] = list({x["url"]: x for x in docs + [
                    x for x in detail_page.get("links", []) + linked_docs
                    if re.search(r"\\.(pdf|docx?|xlsx?|pptx?)(?:$|[?#])", x.get("url", ""), re.I)
                ]}.values())
                rec["application_documents"] = rec["attachments"]
                rec["detail_fetch_status"] = "ok"
            else:
                rec["detail_fetch_status"] = detail_page.get("fetch_status", "error")
        records.append(rec)
    return records

def run():
    return safe_source("獎學金", crawl_scholarship_table)
