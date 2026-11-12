from .common import crawl_listing, safe_source, fetch, page_text, links_from, make_record
from bs4 import BeautifulSoup
import re

LIST_URL = "https://www.osa.nchu.edu.tw/osa/laa/sys/modules/osa_scholarship/index.html"
MAIN_URL = "https://www.osa.nchu.edu.tw/osa/laa/scholarship.html"

def assess(text):
    t = text or ""
    # Conservative: only mark ineligible when low-income status is explicitly mandatory.
    mandatory_patterns = [
        r"(須|需|應|限|僅限|必須).{0,30}(低收入戶|中低收入戶)",
        r"(低收入戶|中低收入戶).{0,30}(證明|資格).{0,20}(必備|檢附|限)",
        r"限(低收入戶|中低收入戶)",
    ]
    preference_patterns = [r"(優先|加分|酌予優先).{0,25}(低收入戶|中低收入戶)",
                           r"(低收入戶|中低收入戶).{0,25}(優先|加分)"]
    # Split A/B categories instead of incorrectly treating the whole award as low-income-only.
    if re.search(r"A類[\s\S]{0,2500}B\s*類", t):
        return {
            "eligibility_status":"needs_verification",
            "eligibility_reason":"此獎助金分 A、B 類：A 類不以低收入戶／中低收入戶身分為必要條件，但仍有家庭收入、財產、成績等門檻；B 類要求低收入戶／中低收入戶身分，依目前已知資料不符合 B 類。",
            "low_income_condition":"separate_paths",
            "eligibility_paths":[
                {"path":"A類","status":"needs_verification","reason":"不要求低收入戶身分；需再核對家庭年收入、利息、財產、成績及其他限制。"},
                {"path":"B類","status":"ineligible","reason":"要求低收入戶或中低收入戶身分。"}
            ]
        }
    if any(re.search(p, t) for p in mandatory_patterns):
        return {"eligibility_status":"ineligible", "eligibility_reason":"公告文字顯示低收入戶／中低收入戶為必要條件；使用者已表示不具此身分。", "low_income_condition":"mandatory"}
    if any(re.search(p, t) for p in preference_patterns):
        return {"eligibility_status":"needs_verification", "eligibility_reason":"低收入戶似為優先條件，不應直接視為必要資格；仍需核對完整辦法。", "low_income_condition":"preference"}
    if any(k in t for k in ["低收入戶", "中低收入戶", "清寒", "經濟弱勢"]):
        return {"eligibility_status":"needs_verification", "eligibility_reason":"出現經濟條件字樣，但無法僅憑列表判斷是必要或優先條件。", "low_income_condition":"unclear"}
    return {"eligibility_status":"needs_verification", "eligibility_reason":"尚須核對年級、系所、成績、文件及其他個別條件。", "low_income_condition":"not_seen"}

def run():
    def crawl():
        records = crawl_listing("獎學金", LIST_URL, max_details=120)
        if not records:
            records = crawl_listing("獎學金", MAIN_URL, max_details=120)
        for rec in records:
            rec.update(assess(rec.get("full_text", "")))
            rec["official_listing_url"] = LIST_URL
            rec["application_documents"] = [x for x in rec.get("attachments", [])]
            # Keep the public JSON compact: PDF extraction can otherwise create enormous files.
            max_chars = 18000
            rec["full_text"] = (rec.get("full_text", "") or "")[:max_chars]
            rec["eligibility_original_text"] = rec.get("full_text", "")
            rec["summary"] = (rec.get("summary", "") or "")[:1800]
            rec["list_text"] = (rec.get("list_text", "") or "")[:4000]
            rec["attachment_texts"] = [
                dict(item, text=(item.get("text", "") or "")[:6000])
                for item in (rec.get("attachment_texts", []) or [])[:2]
            ]
        # Keep all records, including clearly ineligible ones.
        return records
    return safe_source("獎學金", crawl)
