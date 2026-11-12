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
    if any(re.search(p, t) for p in mandatory_patterns):
        return {"eligibility_status":"ineligible", "eligibility_reason":"公告文字顯示低收入戶／中低收入戶為必要條件；使用者已表示不具此身分。", "low_income_condition":"mandatory"}
    if any(re.search(p, t) for p in preference_patterns):
        return {"eligibility_status":"needs_verification", "eligibility_reason":"低收入戶似為優先條件，不應直接視為必要資格；仍需核對完整辦法。", "low_income_condition":"preference"}
    if any(k in t for k in ["低收入戶", "中低收入戶", "清寒", "經濟弱勢"]):
        return {"eligibility_status":"needs_verification", "eligibility_reason":"出現經濟條件字樣，但無法僅憑列表判斷是必要或優先條件。", "low_income_condition":"unclear"}
    return {"eligibility_status":"needs_verification", "eligibility_reason":"尚須核對年級、系所、成績、文件及其他個別條件。", "low_income_condition":"not_seen"}

def run():
    def crawl():
        records = crawl_listing("獎學金", LIST_URL, max_details=250)
        if not records:
            records = crawl_listing("獎學金", MAIN_URL, max_details=100)
        for rec in records:
            rec.update(assess(rec.get("full_text", "")))
            rec["official_listing_url"] = LIST_URL
            rec["application_documents"] = [x for x in rec.get("attachments", [])]
            rec["eligibility_original_text"] = rec.get("full_text", "")
        # Keep all records, including clearly ineligible ones.
        return records
    return safe_source("獎學金", crawl)
