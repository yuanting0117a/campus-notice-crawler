from .common import crawl_listing, safe_source, fetch
from bs4 import BeautifulSoup

SOURCES = [
    ("圖書館活動", "https://cal.lib.nchu.edu.tw/"),
    ("自主學習活動", "https://selfstudy.nchu.edu.tw/"),
    ("研習暨演講活動", "https://psfcost.nchu.edu.tw/registration/"),
]

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
        else:
            results.append(safe_source(name, lambda n=name, u=url: crawl_listing(n, u, max_details=25)))
    return results
