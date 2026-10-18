"""Preview fixtures stay isolated even when HTML is cached or tabs differ."""
import io
import json
import unittest
from unittest.mock import Mock

from browser_server import Handler


class BrowserPreviewTests(unittest.TestCase):
    def response(self, fault):
        handler = object.__new__(Handler)
        handler.path = '/data/cards.json'
        handler.headers = {'Referer': 'http://127.0.0.1:4192/?fault=' + fault}
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = io.BytesIO()
        handler.do_GET()
        return handler.wfile.getvalue(), handler.send_response.call_args.args[0]

    def test_cached_html_does_not_need_to_set_shared_server_state(self):
        body, status = self.response('reading')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(len(data['cards']), 5)
        self.assertEqual(len({card['id'] for card in data['cards']}), 5)
        self.assertTrue(all('不是真實新聞' in card['answer'] for card in data['cards']))
        self.assertTrue(all(len(card['answer'].split('\n\n')) == 3 for card in data['cards']))

    def test_one_tabs_failure_does_not_leak_into_another_tabs_fixture(self):
        bad, _ = self.response('invalid-json')
        with self.assertRaises(ValueError):
            json.loads(bad)
        healthy, status = self.response('healthy')
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(healthy)['cards']), 5)
        preview, _ = self.response('reading')
        self.assertTrue(json.loads(preview)['editionId'].startswith('browser-reading-preview'))

    def test_unavailable_feed_remains_an_http_failure(self):
        _, status = self.response('unavailable')
        self.assertEqual(status, 503)

    def test_guide_fixture_has_distinct_topics_and_explicitly_synthetic_content(self):
        body, status = self.response('guide')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(len({card['category'] for card in data['cards']}), 5)
        self.assertEqual(data['status'], 'updated')
        self.assertTrue(all('不是真實新聞' in card['answer'] for card in data['cards']))

    def test_failure_details_fixture_never_claims_to_be_a_real_generation_result(self):
        body, _ = self.response('guide-failed')
        data = json.loads(body)
        self.assertEqual(data['status'], 'generation-failed')
        self.assertEqual(data['generationAttempts'], 6)
        self.assertIn('這不是實際生成結果', data['updateReason'])

    def test_term_fixture_has_separate_synthetic_notes_and_a_title_only_term(self):
        body, status=self.response('terms')
        data=json.loads(body)
        self.assertEqual(status,200)
        self.assertEqual(len(data['cards']),5)
        for card in data['cards']:
            self.assertEqual(len(card['terms']),3)
            self.assertIn('不是真實新聞',card['answer'])
            self.assertIn('標題詞',card['question'])
            self.assertNotIn('標題詞',card['answer'])
            for term in card['terms']:
                self.assertNotIn(term['definition'],card['answer'])
                self.assertIn('虛構',term['definition'])

    def test_language_fixture_has_distinct_complete_synthetic_editions(self):
        body, status=self.response('i18n')
        data=json.loads(body)
        self.assertEqual(status,200)
        for card in data['cards']:
            simplified=card['translations']['zh-Hans']
            english=card['translations']['en']
            self.assertIn('不是真实新闻',simplified['answer'])
            self.assertIn('not real news',english['answer'])
            for version in [simplified,english]:
                self.assertEqual(len(version['answer'].split('\n\n')),3)
                self.assertEqual(len(version['terms']),3)
                self.assertNotIn('id',version)
                self.assertNotIn('sourceUrl',version)


if __name__ == '__main__':
    unittest.main()
