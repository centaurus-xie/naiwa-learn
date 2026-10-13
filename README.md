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

只有生成步驟會取得 Secret。每次最多六次模型請求，合格卡片保留，只補修尚未通過的卡片。五篇正文各最多 12,000 字元，另附每篇最多 24 個原文證據選項；輸出上限為每張待生成卡片 1,200 tokens（初稿最多 6,000）。修訂會額外消耗 API 額度；金鑰、餘額、連線及 API 回應結構錯誤不自動重試。API 轉址會被拒絕，不將金鑰帶到其他位址。同一香港日期已有成功版本時不再次生成，沒有未使用文章時也不呼叫模型。優先使用有效快取；快取失效時嘗試讀回目前線上版本。兩者都不可用時才退回隨附卡片，此時可能重新生成。

查看日誌：打開 [GitHub Actions](https://github.com/centaurus-xie/naiwa-learn/actions)，左側選 **Update cards and deploy Pages** → 選日期對應的运行 → 點 **deploy** 任務 → 展開 **Generate DeepSeek cards (repair up to 6 requests)**。新版每輪列出合格張數及未通過卡片的具體原因，不打印金鑰、原始模型回應或全文。舊版若只有修訂與保留提示，無法從中還原當時的具體拒絕原因。

## 每日更新如何運作

- 香港時間約 08:17 由 GitHub Actions 並行抓取 Hugging Face、[MIT News](https://news.mit.edu/rss)、[Google Research](https://research.google/blog/)、[Microsoft Research](https://www.microsoft.com/en-us/research/blog/)、[香港科技大學](https://hkust.edu.hk/news/news)及[量子位](https://www.qbitai.com/feed)的公開 RSS，不依賴瀏覽器跨站抓取。
- 篩選最近 45 天的 AI 相關文章，只接受各來源允許的網域與文章路徑。Hugging Face 限主站與允許的組織文章；社群文章不代表平台背書。正文使用各站專用區域抽取，排除導航與腳本。
- 每批五篇必須來自五個不同平台，每個平台最多一篇；同平台的不同欄目或組織帳號不分開計數。不足五個可讀平台時保留原卡，不放寬上限。至少涵蓋兩個應用領域，模型評測選題至多一篇。依中英文標題與摘要的關鍵字初篩醫療、科學、教育、環境、機器人交通、創意及工作工具；這是選題啟發式，不是對文章含義的完整判斷，生成 prompt 也要求保留應用主線。生成標題再次限制評測類至多一張。
- 同等新鮮度下優先納入中國內地、香港的來源；來源地區不等於事件發生地。量子位標注「媒體報導」，不能將報導宣稱當成官方發布或獨立驗證。香港科大 RSS 的舊文章子網域轉換至已驗證的新官方文章網域，其他轉址仍不接受。
- 候選池最多 24 篇，初始選題的正文最多請求 18 篇，每篇只嘗試一次，失敗時重新搭配其他候選。模型連續三輪仍缺乏可歸屬的原文支持時，嘗試替換未通過卡片的同平台文章，最多額外請求四篇正文，仍遵守五個平台、應用領域與評測上限。單一 RSS 故障不丟棄其他來源；來源或題材不足以組成均衡五篇時不呼叫模型，標記 `selection-unavailable` 並讓 workflow 失敗，不捏造應用來湊數。
- 優先挑選尚未使用的近期文章並抓取正文；不足五篇時搭配已用文章，避開最近 100 道完全相同的問題。沒有未用文章時保留原卡，不宣稱有新內容。
- DeepSeek 根據正文生成五張繁體中文新知導讀，每張對應一篇文章：正面是具體陳述式標題，展開後用三個短段落介紹「新進展與機制、意義與 insight、限制與觀察」。推論須明確標示，不得包裝成已證實事實。
- 為相容舊資料，JSON 的 `question` / `answer` 欄位分別承載標題與導讀。驗證字數、中文、重複標題、來源索引及原文證據，拒絕帶問號的考題式標題。新增 `actor` 記錄具名主體，須在來源及導讀首段出現；無法確認研發者時只作具名報導歸屬，不把發布平台當成研發者。蒸餾的「教師模型／學生模型」須明說不是真人。字串及證據驗證不等於歸屬或 insight 的語意查證。
- `promptVersion` 變更時會重新選取近期文章並生成新版，不受當天已生成或文章已使用的限制；新版本成功後恢復每日一次限制。
- 原文證據匹配只是機械驗證，不保證答案完全正確；介面標示 AI 整理並保留原文連結。完整文章正文不公開到資料檔。
- 模型輸出恰好三個文字段落，由程序以空行拼接，避免空行格式錯誤；每段目標 40–65 字元，總計約 124–199 字元。字數按所有字元計算（含英文、標點、空格、換行），檢查範圍仍為 80–320。證據由模型選擇原文片段索引，程序綁定逐字原文，不讓模型重抄或翻譯證據。這只消除格式與抄寫失誤，不代表語意已查證。
- 格式、長度或證據不合格時，將所有未通過卡片的原因與實際字數回饋模型，只補修這些卡片，最多共六次請求。第四輪起重新組織失敗卡片而非沿用失敗稿，符合條件時換同平台文章；已合格卡片不重寫，事實與來源校驗不放寬。
- 六次後仍不合格，狀態為 `generation-failed`，記錄嘗試次數與最後具體原因並讓 workflow 失敗。網站為維持可讀性仍展示先前版本，不變更舊版發布時間；這不是今日更新成功。沒有舊版 AI 卡片時保留隨附概念卡。
- 抓取、金鑰或 API 服務錯誤則保留卡片並將 workflow 標為失敗，避免持續的設定故障被掩蓋。測試環境隔離 Actions 輸出與摘要，模擬失敗不會顯示為真實生成故障。
- 回退資料也須通過完整五張卡的結構校驗；快取或線上版本損壞時使用本次 checkout 保留的卡片，再退回隨附概念卡。寫入採暫存檔原子替換，部署前再次校驗，沒有可用卡片就停止部署，不用壞檔覆蓋網站。若 fork 到其他倉庫，須修改腳本中的 `PUBLISHED_FEED` 為自己的 Pages 資料網址。
- 資料以 UTC 儲存生成完成與檢查完成時間；畫面固定轉為香港時間（UTC+8），使用 24 小時制，並標示時區，不依賴瀏覽器所在時區。「新卡發布」是生成完成時間，不是排程預定時間；Actions 延遲或手動執行可能在 08:17 之後完成。缺少金鑰或首次生成未成功時會顯示尚未生成 AI 新卡。
- 新資料部署到 Pages，不自動提交至 Git。本機 `npm run update` 需要環境變數 `LLM_API_KEY`，不要將金鑰直接貼入會保存歷史的終端機指令。
- 排程可能延遲，公開倉庫連續 60 天沒有活動時 GitHub 可能停用排程；可在 Actions 重新啟用並手動執行。

## 學習進度

進度存於目前瀏覽器的 localStorage。每日以香港日期重置；重新開啟或重新整理時，如果線上已有新的 `editionId`，會載入新卡片並重置這批進度。同一版本重載則保留進度，僅更新檢查時間不會重置。已開啟的頁面不自動中斷閱讀，需重新整理才能取得新版本。「稍後再看」將該卡放到隊尾，「下一個發現」將它標為已讀。清除瀏覽資料會重置進度，不跨裝置同步。

讀完第一張後出現「今日已讀」小入口，依閱讀順序回看本批已讀卡片與原文，完成五張後仍可使用。回看只讀、不改變進度；入口與同批進度一起保存，跨日或新版本重置。不提供跨版本的歷史收藏。

網頁只接受完整、唯一的五張卡；損壞的進度不採用。卡片請求最多等待 15 秒，失敗或資料不完整時使用本機保存的卡片；跨日會重置閱讀進度。沒有本機卡片時顯示重新整理提示，不顯示空白畫面。這不是離線 PWA，首次載入網站仍需要網路。

## 驗證

`npm test` 與 `python3 -m unittest discover -s tests -p 'test_*.py'`。

瀏覽器故障檢查：執行 `python3 tests/browser_server.py`，開啟 `http://127.0.0.1:4192/?fault=healthy`，讀一張後改用 `invalid-json`、`incomplete`、`unavailable`、`bad-date`、`new-edition` 或 `timezone`。`timezone` 以 10/12 07:36 UTC、10/13 06:45 UTC 檢查香港顯示 15:36、14:45，失敗原因是明確標記的本機顯示測試。僅修改測試伺服器的記憶體回應，不修改資料檔、不呼叫付費 API。自動測試使用模擬 API 回應；不代替真實 DeepSeek 與 GitHub Pages 部署驗證。

## 視覺素材

`assets/guide.png` 是使用者提供的角色原圖，介面以 CSS 裁切呈現。原角色的權利仍屬其權利人；此專案不授予該角色的再使用權。字体使用 Google Fonts 的 DM Sans / Noto Sans TC，無法連線時退回本機字體。

介面依極簡、柔和圓角卡片的方向設計；Mobbin 的 Luma 內頁當時無法公開檢視，因此並非逐頁複製。
