# 興大校園情報站與爬蟲

自動整理國立中興大學校園活動與獎學金公告，並提供手機也能使用的查詢網站。

## 網站

部署完成後網址：
https://yuanting0117a.github.io/campus-notice-crawler/

## 蒐集來源

### 校園活動
- [中興大學圖書館活動](https://cal.lib.nchu.edu.tw/)
- [中興大學自主學習系統](https://selfstudy.nchu.edu.tw/)
- [研習暨演講活動報名系統](https://psfcost.nchu.edu.tw/registration/)

惠蓀講座已移除：該頁面是講者報名資訊，不屬於要蒐集的校園活動公告。

### 獎學金
- [中興大學學務處獎學金公告](https://www.osa.nchu.edu.tw/osa/laa/scholarship.html)
- [獎學金列表](https://www.osa.nchu.edu.tw/osa/laa/sys/modules/osa_scholarship/index.html)

## 功能
- 活動與獎學金分頁、關鍵字搜尋。
- 獎學金資格標示；低收入戶必要條件、優先條件與待確認條件分開處理。
- 保留官方公告、報名與附件連結及可取得的原文。
- GitHub Actions 定期更新資料並部署網站。

## 資料檔案
- `data/activities.json`：校園活動。
- `data/scholarships.json`：獎學金。
- `data/run_status.json`：最近一次爬取狀態。

## 注意事項
資料擷取可能受學校網站改版或存取限制影響；畫面顯示的資格判斷是依公告文字整理，正式申請前請以承辦單位最新簡章為準。
