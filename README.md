# 奶蛙小課堂 · AI Daily

每天五張 AI 新知導讀，和奶蛙一起了解新技術、新發現與新應用。點開標題閱讀進展與觀察，選「稍後再看」或「下一個發現」，完成後明天再見。

純 HTML / CSS / JavaScript，無建置步驟、無第三方 JavaScript 套件。網站完全靜態；Python 在 GitHub Actions 中呼叫 DeepSeek 生成卡片，API 金鑰不會傳到瀏覽器。

## 本機預覽

在此資料夾執行 `npm start`，開啟 http://localhost:4173 。或直接執行 `python3 -m http.server 4173`。請用 HTTP 預覽，不要雙擊 HTML（瀏覽器會阻擋本機 JSON 載入）。

## 上傳 GitHub / 啟用網站

1. 建立 GitHub repository，預設分支使用 `main`。
2. 將本資料夾內容放在 repository 根目錄，包含 `.github/workflows/pages.yml` 和 `assets/guide.png`。
3. 在 repository 的 **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。
4. 按下方步驟設定 DeepSeek 金鑰，再在 **Actions → Update cards and deploy Pages → Run workflow** 執行一次。
5. 部署完成後，網址為 `https://你的帳號.github.io/儲存庫名稱/`；若 repository 名稱為 `你的帳號.github.io`，網址就是該根網域。

日後推送到 main 會自動部署。全部資源使用相對路徑，支援專案子目錄。Pages 發佈包只含網站檔案；公開倉庫中的腳本仍可被閱讀，因此絕不可把金鑰寫入任何檔案。

## 設定 DeepSeek（只需一次）

1. 打開 https://github.com/centaurus-xie/naiwa-learn/settings/secrets/actions 。
2. 點 **New repository secret**，Name 填 `LLM_API_KEY`，Secret 貼上 DeepSeek API Key，按 **Add secret**。
3. 確認 DeepSeek API 帳戶有可用餘額；API 使用費計入該帳戶。
4. 推送新版程式後，在 Actions 執行 **Run workflow**。
5. 查看 **Generate DeepSeek cards** 步驟是否成功，並重新整理網站：底部應顯示「新卡發布」及時間。

官方 endpoint 固定為 `https://api.deepseek.com/chat/completions`。API 的 `model` 是必填值；本程式預設 `deepseek-flash`，使用 JSON Output、非思考模式，無需你另外選模型。官方文件：https://api-docs.deepseek.com/api/create-chat-completion/ 。

只有生成步驟會取得 Secret。每次最多三次模型請求（初稿加兩次修訂）、五篇正文各最多 12,000 字元、每次輸出最多 4,000 tokens。修訂會額外消耗 API 額度；金鑰、餘額、連線及 API 回應結構錯誤不自動重試。API 轉址會被拒絕，不將金鑰帶到其他位址。同一香港日期已有成功版本時不再次生成，沒有未使用文章時也不呼叫模型。優先使用有效快取；快取失效時嘗試讀回目前線上版本。兩者都不可用時才退回隨附卡片，此時可能重新生成。

## 每日更新如何運作

- 香港時間約 08:17 由 GitHub Actions 抓取 Hugging Face 公開 RSS。
- 篩選最近 45 天、主站及腳本允許的組織文章。社群文章不代表平台背書；卡片顯示實際發布者。
- 優先挑選尚未使用的近期文章並抓取正文；不足五篇時搭配已用文章，避開最近 100 道完全相同的問題。沒有未用文章時保留原卡，不宣稱有新內容。
- DeepSeek 根據正文生成五張繁體中文新知導讀，每張對應一篇文章：正面是具體陳述式標題，展開後用三個短段落介紹「新進展與機制、意義與 insight、限制與觀察」。推論須明確標示，不得包裝成已證實事實。
- 為相容舊資料，JSON 的 `question` / `answer` 欄位分別承載標題與導讀。驗證字數、中文、重複標題、來源索引及原文證據，拒絕帶問號的考題式標題。證據驗證不等於對 insight 的語意查證。
- `promptVersion` 變更時會重新選取近期文章並生成新版，不受當天已生成或文章已使用的限制；新版本成功後恢復每日一次限制。
- 原文證據匹配只是機械驗證，不保證答案完全正確；介面標示 AI 整理並保留原文連結。完整文章正文不公開到資料檔。
- 字數按所有字元計算（含英文、標點、空格、換行），prompt 目標為 150–240 字元，檢查範圍仍為 80–320。格式、長度或證據不合格時，將校驗結果與實際字數回饋模型，最多修訂兩次。
- 修訂後仍不合格則回退到上一版，狀態為 `content-retained`，正常部署、不將 workflow 標為失敗，也不變更舊版發布時間。沒有旧版 AI 卡片時保留隨附概念卡。
- 抓取、金鑰或 API 服務錯誤則保留卡片並將 workflow 標為失敗，避免持續的設定故障被掩蓋。測試環境隔離 Actions 輸出與摘要，模擬失敗不會顯示為真實生成故障。
- 回退資料也須通過完整五張卡的結構校驗；快取或線上版本損壞時使用本次 checkout 保留的卡片，再退回隨附概念卡。寫入採暫存檔原子替換，部署前再次校驗，沒有可用卡片就停止部署，不用壞檔覆蓋網站。若 fork 到其他倉庫，須修改腳本中的 `PUBLISHED_FEED` 為自己的 Pages 資料網址。
- 畫面分別顯示「新卡發布」及「檢查」時間；缺少金鑰或首次生成未成功時會顯示尚未生成 AI 新卡。
- 新資料部署到 Pages，不自動提交至 Git。本機 `npm run update` 需要環境變數 `LLM_API_KEY`，不要將金鑰直接貼入會保存歷史的終端機指令。
- 排程可能延遲，公開倉庫連續 60 天沒有活動時 GitHub 可能停用排程；可在 Actions 重新啟用並手動執行。

## 學習進度

進度存於目前瀏覽器的 localStorage。每日以使用者裝置日期重置；重新開啟或重新整理時，如果線上已有新的 `editionId`，會載入新卡片並重置這批進度。同一版本重載則保留進度，僅更新檢查時間不會重置。已開啟的頁面不自動中斷閱讀，需重新整理才能取得新版本。「稍後再看」將該卡放到隊尾，「下一個發現」將它標為已讀。清除瀏覽資料會重置進度，不跨裝置同步。

網頁只接受完整、唯一的五張卡；損壞的進度不採用。卡片請求最多等待 15 秒，失敗或資料不完整時使用本機保存的卡片；跨日會重置閱讀進度。沒有本機卡片時顯示重新整理提示，不顯示空白畫面。這不是離線 PWA，首次載入網站仍需要網路。

## 驗證

`npm test` 與 `python3 -m unittest discover -s tests -p 'test_*.py'`。

瀏覽器故障檢查：執行 `python3 tests/browser_server.py`，開啟 `http://127.0.0.1:4192/?fault=healthy`，讀一張後改用 `invalid-json`、`incomplete`、`unavailable`、`bad-date` 或 `new-edition`。僅修改測試伺服器的記憶體回應，不修改資料檔、不呼叫付費 API。自動測試使用模擬 API 回應；不代替真實 DeepSeek 與 GitHub Pages 部署驗證。

## 視覺素材

`assets/guide.png` 是使用者提供的角色原圖，介面以 CSS 裁切呈現。原角色的權利仍屬其權利人；此專案不授予該角色的再使用權。字体使用 Google Fonts 的 DM Sans / Noto Sans TC，無法連線時退回本機字體。

介面依極簡、柔和圓角卡片的方向設計；Mobbin 的 Luma 內頁當時無法公開檢視，因此並非逐頁複製。
