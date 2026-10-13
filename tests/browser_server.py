"""Local browser fault checks, never shipped to Pages or calls an LLM.

Run from the repository root: python3 tests/browser_server.py
Use /?fault=healthy, invalid-json, incomplete, unavailable, new-edition, bad-date, timezone.
This server only changes its own in-memory response; repository data stays intact.
"""
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    fault = 'healthy'

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/':
            Handler.fault = parse_qs(url.query).get('fault', ['healthy'])[0]
        if url.path != '/data/cards.json':
            return super().do_GET()
        status = 200
        data = json.loads((ROOT / 'data/cards.json').read_text(encoding='utf-8'))
        if self.fault == 'incomplete':
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
