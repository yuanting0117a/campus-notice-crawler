# 興大校園情報站與爬蟲

自動整理國立中興大學學生可能用得到的公告、獎助學金、職涯／實習、國際交流、宿舍與系所資訊，並提供 9015／9015A 公車官方時刻表。

## 網站
https://yuanting0117a.github.io/campus-notice-crawler/

## 蒐集來源
### 校園資訊
- 中興大學校級最新公告：https://www.nchu.edu.tw/news/id/index
- 學務處獎助學金：https://www.osa.nchu.edu.tw/osa/laa/sys/modules/osa_scholarship/index.html
- 生涯發展中心、實習與就業：https://www.osa.nchu.edu.tw/osa/cdc/sys/modules/tadnews/index.php
- 國際事務處、交換與海外活動：https://oia.nchu.edu.tw/index.php/zh/
- 宿舍公告：https://www.osa.nchu.edu.tw/osa/dorm/sys/
- 電機系公告：https://www.ee.nchu.edu.tw/wb_announcement01.asp?cno=0&pageno=1&url=11
- 教務處選課與學籍：https://oaa.nchu.edu.tw/course-news
- 圖書館活動：https://cal.lib.nchu.edu.tw/
- 自主學習活動：https://selfstudy.nchu.edu.tw/
- 研習暨演講活動：https://psfcost.nchu.edu.tw/registration/index/actlist.jsp

### 交通
- 9015／9015A 官方時刻表：https://www.taiwanbus.tw/eBUSPage/
- 台中客運公告：https://www.tcbus.com.tw/
- 台中市公車即時動態：https://citybus.taichung.gov.tw/

## 功能
- 校園新消息：校級公告、學生活動、實習、交換、宿舍與電機系公告。
- 我的獎學金：依使用者自行設定的學制、年級、科系及其他條件進行初步比對；個人條件只存在瀏覽器本機，不上傳。
- 9015／9015A：讀取官方時刻表，保留路線、方向、發車時間、行駛日、客運業者與備註。
- 保留官方來源、詳細頁、報名連結與附件。
- GitHub Actions 每小時更新資料並部署網站；來源讀取失敗時盡可能保留前次成功資料。

## 資料檔案
- `data/activities.json`：校園公告與活動。
- `data/scholarships_1.json`、`data/scholarships_2.json`：獎學金資料分片。
- `data/transit_9015.json`：9015／9015A 官方時刻表。
- `data/run_status.json`：最近一次爬取狀態。

## 注意
資格比對是依公告文字進行初步整理；未明確的條件會標示待確認。申請資格、班次與異動仍以學校及客運業者最新公告為準。
