from .common import crawl_listing, safe_source

SOURCES = [
    ("惠蓀講座", "https://oaa.nchu.edu.tw/zh-tw/ge-speech/page-detail.2751"),
    ("圖書館活動", "https://cal.lib.nchu.edu.tw/"),
    ("自主學習活動", "https://selfstudy.nchu.edu.tw/"),
    ("研習暨演講活動", "https://psfcost.nchu.edu.tw/"),
]

def run():
    results = []
    for name, url in SOURCES:
        results.append(safe_source(name, lambda n=name, u=url: crawl_listing(n, u, max_details=25)))
    return results
