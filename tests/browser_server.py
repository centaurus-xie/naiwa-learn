"""Local browser fault checks, never shipped to Pages or calls an LLM.

Run from the repository root: python3 tests/browser_server.py
Use /?fault=healthy, invalid-json, incomplete, unavailable, new-edition,
bad-date, timezone, reading, guide, guide-failed, terms.
This server only changes its own in-memory response; repository data stays intact.
"""
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != '/data/cards.json':
            return super().do_GET()
        # Derive the fixture from this tab's referrer, not a shared global.
        # Cached HTML navigations need not request '/' again, and two tabs may
        # intentionally exercise different failures at the same time.
        referrer = urlsplit(self.headers.get('Referer', ''))
        self.fault = parse_qs(referrer.query).get('fault', ['healthy'])[0]
        status = 200
        data = json.loads((ROOT / 'data/cards.json').read_text(encoding='utf-8'))
        if self.fault in {'reading', 'guide', 'guide-failed', 'terms'}:
            # Explicitly synthetic, long-form fixture for mobile layout checks.
            # Never published or mixed into the real feed.
            answer = ('這是一張本機介面測試卡，不是真實新聞。這個段落用來確認手機上較長的中文內容是否清楚易讀，'
                      '並檢查標題、具名主體與正文之間的留白。讀者應該能自然地一路往下閱讀，而不是一直尋找按鈕。\n\n'
                      '第二段測試連續閱讀：點開第一張後，下一張會直接顯示內容；選擇稍後再看不應增加已讀數。'
                      '即使離開後重新整理，同一批卡片也應保留已讀進度與展開狀態，不需要再次逐張點開。\n\n'
                      '最後一段用來檢查底部安全距離。固定操作欄不應蓋住段落、原文連結或今日已讀入口。'
                      '這些文字只用來驗證排版與互動，不代表任何真實的研究結果、產品功能或醫療建議。')
            data = {'editionId':'browser-reading-preview-v1','cards':[
                {'id':'reading-preview-'+str(i),'category':'介面預覽','actor':'本機排版測試',
                 'question':f'第{i+1}張預覽：長標題與三段導讀，在手機上也能輕鬆閱讀，不必反覆點開',
                 'answer':answer,'sourceName':'本機介面測試 · 非真實新聞','sourceUrl':'https://example.com/',
                 'newsTitle':'Long-source-title-preview: 較長的原文標題會自然換行，而不是擠出畫面'} for i in range(5)]}
            if self.fault == 'terms':
                data['editionId']='browser-terms-preview-v1'
                for card in data['cards']:
                    card.update({'question':'本機注釋預覽：術語甲與標題詞，不是真實新聞',
                                 'answer':answer.replace('這個段落','術語甲所在的這個段落',1).replace('第二段測試','術語乙出現在第二段測試',1),
                                 'terms':[
                                     {'term':'術語甲','definition':'這是虛構的測試詞，只用來檢查點擊注釋、關閉與正文留白。'},
                                     {'term':'術語乙','definition':'這也是虛構的測試詞，用來檢查切換注釋時只展開一條。'},
                                     {'term':'標題詞','definition':'這個虛構詞只出現在標題，用來檢查已讀回看內的注釋入口。'}]})
            elif self.fault != 'reading':
                data.update({'editionId':'browser-guide-preview-'+self.fault,
                             'generatedAt':'2026-10-16T00:17:00Z','checkedAt':'2026-10-16T00:18:00Z',
                             'status':'updated'})
                for card, category in zip(data['cards'], ['醫療應用','環境能源','工作工具','機器人交通','創意設計']):
                    card.update({'category':category,'question':'本機預覽：'+category+'的用途與限制，用於測試奶蛙主題引導'})
                if self.fault == 'guide-failed':
                    data.update({'generatedAt':'2026-10-12T07:36:00Z',
                                 'status':'generation-failed','generationAttempts':6,
                                 'updateReason':'本機顯示測試：卡2導讀長度不符；這不是實際生成結果。'})
        elif self.fault == 'incomplete':
            data['cards'] = data['cards'][:4]
        elif self.fault == 'new-edition':
            data['editionId'] = 'browser-audit-new-edition'
            data['cards'][0]['question'] = '新版本 · ' + data['cards'][0]['question']
        elif self.fault == 'bad-date':
            data['generatedAt'] = 'not-a-date'
            data['checkedAt'] = {}
        elif self.fault == 'timezone':
            data.update({'generatedAt':'2026-10-12T07:36:41.746691+00:00',
                         'checkedAt':'2026-10-13T06:45:42.611353+00:00',
                         'status':'generation-failed','generationAttempts':6,
                         'updateReason':'本機顯示測試：這不是實際生成結果。'})
        elif self.fault == 'unavailable':
            status = 503
        body = b'{broken json' if self.fault == 'invalid-json' else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1',4192),partial(Handler,directory=str(ROOT)))
    server.serve_forever()
