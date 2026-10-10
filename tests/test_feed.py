import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('updater', ROOT / 'scripts/update_cards.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)

class FeedTests(unittest.TestCase):
    def test_untrusted_future_and_duplicate_items(self):
        concepts = json.loads((ROOT / 'data/concepts.json').read_text())
        def item(url, date='Sat, 10 Oct 2026 00:00:00 GMT'):
            return f'<item><title>Agent update</title><link>{url}</link><pubDate>{date}</pubDate></item>'
        good = 'https://huggingface.co/blog/agent-test'
        xml = '<rss><channel>' + item(good) * 2 + item('https://evil.example/agent') + item('https://huggingface.co/blog/random-user/agent') + item(good+'-future','Sat, 10 Oct 2027 00:00:00 GMT') + '</channel></rss>'
        result = updater.build_cards(xml, concepts, datetime(2026,10,11,tzinfo=timezone.utc))
        self.assertEqual(len(result),5)
        self.assertEqual(sum('newsTitle' in c for c in result),1)
        self.assertEqual(result[0]['sourceUrl'],good)
        self.assertEqual(len({c['id'] for c in result}),5)

if __name__ == '__main__':
    unittest.main()
