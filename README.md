# 奶蛙小課堂 · AI Daily

每天五張 AI 小卡，和學習夥伴奶蛙一起學習。點開答案，選「再看看」或「記住了」，完成後明天再見。

純 HTML / CSS / JavaScript，無建置步驟、無第三方 JavaScript 套件、無 API 金鑰。Python 只用於 GitHub Actions 每日更新資料；網站本身完全靜態。

## 本機預覽

在此資料夾執行 `npm start`，開啟 http://localhost:4173 。或直接執行 `python3 -m http.server 4173`。請用 HTTP 預覽，不要雙擊 HTML（瀏覽器會阻擋本機 JSON 載入）。

## 上傳 GitHub / 啟用網站

1. 建立 GitHub repository，預設分支使用 `main`。
2. 將本資料夾內容放在 repository 根目錄，包含 `.github/workflows/pages.yml` 和 `assets/guide.png`。
3. 在 repository 的 **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。
4. 在 **Actions → Update cards and deploy Pages → Run workflow** 執行一次。
5. 部署完成後，網址為 `https://你的帳號.github.io/儲存庫名稱/`；若 repository 名稱為 `你的帳號.github.io`，網址就是該根網域。

日後推送到 main 會自動部署。全部資源使用相對路徑，支援專案子目錄。workflow 只發佈網站檔案，不會公開測試或更新腳本。

## 每日更新如何運作

- 香港時間約 08:17 由 GitHub Actions 抓取 Hugging Face 公開 RSS。
- 篩選最近 45 天、主站及腳本允許的組織文章。社群文章不代表平台背書；卡片顯示實際發布者。
- 原文英文標題連結到對應的中文概念卡。概念解釋是人工撰寫的基礎知識，**不是對文章的自動翻譯或 AI 摘要**；不推斷文章未提供的內容。
- 選最多五種不同概念；不足時補基礎卡。沒有新文章時，內容可能重複，不會憑空生成新聞。可在 `data/concepts.json` 擴充概念與關鍵字。
- 抓取失敗會保留快取版本；快取不存在時使用倉庫隨附卡片。畫面顯示最後成功抓取日期。
- 新資料部署到 Pages，不自動提交至 Git。可在本機執行 `npm run update` 更新 JSON。
- 排程可能延遲，公開倉庫連續 60 天沒有活動時 GitHub 可能停用排程；可在 Actions 重新啟用並手動執行。

## 學習進度

進度存於目前瀏覽器的 localStorage。每日以使用者裝置日期重置；同一天已開始的五張卡固定，更新網站也不會打斷學習。「再看看」將該卡放到隊尾，直到選擇「記住了」才算完成。清除瀏覽資料會重置進度，不跨裝置同步。

## 驗證

`npm test` 與 `python3 -m unittest discover -s tests -p 'test_*.py'`。

## 視覺素材

`assets/guide.png` 是使用者提供的角色原圖，介面以 CSS 裁切呈現。原角色的權利仍屬其權利人；此專案不授予該角色的再使用權。字体使用 Google Fonts 的 DM Sans / Noto Sans TC，無法連線時退回本機字體。

介面依極簡、柔和圓角卡片的方向設計；Mobbin 的 Luma 內頁當時無法公開檢視，因此並非逐頁複製。
