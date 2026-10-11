import importlib.util
import json
import unittest
import tempfile
import contextlib
import io
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('updater', ROOT / 'scripts/update_cards.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)

class FeedTests(unittest.TestCase):
    def setUp(self):
        # Tests must never write simulated failures to a real Actions step.
        self.environment = patch.dict('os.environ', {'GITHUB_OUTPUT':'', 'GITHUB_STEP_SUMMARY':'', 'LLM_API_KEY':''})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        capture = contextlib.redirect_stderr(io.StringIO())
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def test_mock_missing_key_does_not_pollute_real_actions_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory)/'real-summary'
            output = Path(directory)/'real-output'
            with patch.dict('os.environ', {'GITHUB_STEP_SUMMARY':str(summary), 'GITHUB_OUTPUT':str(output)}):
                result = unittest.TestResult()
                FeedTests('test_missing_secret_preserves_edition_and_returns_failure').run(result)
            self.assertTrue(result.wasSuccessful())
            self.assertFalse(summary.exists())
            self.assertFalse(output.exists())

    def test_diagnostics_identify_validation_without_echoing_untrusted_errors(self):
        self.assertIn('80–320',updater.failure_reason(ValueError('Invalid card field: answer')))
        self.assertIn('逐字',updater.failure_reason(ValueError('Evidence not found in source')))
        self.assertIn('餘額不足',updater.failure_reason(RuntimeError('DeepSeek returned HTTP 402')))
        self.assertNotIn('secret-123',updater.failure_reason(ValueError('secret-123\n::error::injected')))

    def test_failure_reason_reaches_final_step_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'output'
            summary=Path(directory)/'summary'
            with patch.dict('os.environ',{'GITHUB_OUTPUT':str(output),'GITHUB_STEP_SUMMARY':str(summary)}):
                updater.report_failure(updater.failure_reason(ValueError('Evidence not found in source')))
            self.assertTrue(output.read_text().startswith('failure_reason='))
            self.assertIn('逐字',output.read_text())
            self.assertIn('上一批卡片已保留',summary.read_text())

    def test_untrusted_future_and_duplicate_items(self):
        def item(url, date='Sat, 10 Oct 2026 00:00:00 GMT'):
            return f'<item><title>Agent update</title><link>{url}</link><pubDate>{date}</pubDate></item>'
        good = 'https://huggingface.co/blog/agent-test'
        xml = '<rss><channel>' + item(good) * 2 + item('https://evil.example/agent') + item('https://huggingface.co/blog/random-user/agent') + item(good+'-future','Sat, 10 Oct 2027 00:00:00 GMT') + '</channel></rss>'
        result = updater.parse_feed(xml, datetime(2026,10,11,tzinfo=timezone.utc))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['url'],good)

    def test_extracts_body_not_scripts_or_comments(self):
        parser = updater.ArticleParser()
        parser.feed('<nav>bad</nav><div class="blog-content"><p>Real article</p><script>bad</script><div class="not-prose">bad</div><p>More text</p></div><p>bad</p>')
        text = updater.normalize(''.join(parser.text))
        self.assertEqual(text,'Real article More text')

    def fixture(self):
        sources = [{'url':f'https://huggingface.co/blog/test-{i}', 'sourceName':'Publisher',
                    'publishedAt':'2026-10-10', 'title':f'Article {i}',
                    'body':'The model improves efficiency using a smaller architecture.'} for i in range(5)]
        cards = [{'sourceIndex':i, 'category':'模型效率', 'question':f'第{i}篇文章介紹以更小架構改善模型效率',
                  'answer':'根據文章，模型採用更小的架構來提升運作效率；這是作者的說明，並不代表所有任務都有相同表現。\n\n這可能意味著，資源有限的部署情境值得重新評估較小模型的適用性。\n\n文章摘錄未提供具體測試條件，實際效益仍需依任務驗證。',
                  'evidence':'The model improves efficiency'} for i in range(5)]
        return sources, {'cards':cards}

    def test_valid_sources_are_bound_by_code(self):
        sources, result = self.fixture()
        result['cards'][0]['sourceUrl']='https://evil.example'
        cards = updater.validate_cards(result,sources,[])
        self.assertEqual(cards[0]['sourceUrl'],sources[0]['url'])
        self.assertEqual(len({c['id'] for c in cards}),5)

    def test_rejects_fake_evidence_duplicates_and_missing_cards(self):
        for kind in ['evidence','source','question','missing']:
            with self.subTest(kind=kind):
                sources, result = self.fixture()
                if kind=='evidence': result['cards'][0]['evidence']='This evidence does not exist'
                if kind=='source': result['cards'][1]['sourceIndex']=0
                if kind=='question': result['cards'][1]['question']=result['cards'][0]['question']
                if kind=='missing': result['cards'].pop()
                with self.assertRaises(ValueError): updater.validate_cards(result,sources,[])

    def test_rejects_previous_questions(self):
        sources, result = self.fixture()
        with self.assertRaises(ValueError):
            updater.validate_cards(result,sources,[result['cards'][0]['question']])

    def test_no_news_does_not_call_paid_api(self):
        sources, _ = self.fixture()
        previous={'mode':'llm','promptVersion':updater.PROMPT_VERSION,'sourceHistory':[s['url'] for s in sources],'cards':['old']}
        with patch.object(updater,'get_public',return_value=b'feed'), patch.object(updater,'parse_feed',return_value=sources), patch.object(updater,'generate') as generate:
            result, changed = updater.refresh(previous,datetime(2026,10,11,tzinfo=timezone.utc),'test-key')
        self.assertFalse(changed)
        self.assertEqual(result['cards'],['old'])
        self.assertEqual(result['status'],'no-new-articles')
        generate.assert_not_called()

    def test_at_most_one_generation_per_hong_kong_day(self):
        sources, _ = self.fixture()
        previous={'mode':'llm','promptVersion':updater.PROMPT_VERSION,'generatedAt':'2026-10-10T23:00:00+00:00','cards':['old']}
        with patch.object(updater,'get_public',return_value=b'feed'), patch.object(updater,'parse_feed',return_value=sources), patch.object(updater,'generate') as generate:
            result, changed = updater.refresh(previous,datetime(2026,10,11,1,tzinfo=timezone.utc),'test-key')
        self.assertFalse(changed)
        self.assertEqual(result['status'],'already-generated-today')
        generate.assert_not_called()

    def test_missing_secret_preserves_edition_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data').mkdir()
            target=root/'data/cards.json'
            previous={'editionId':'old','generatedAt':'2026-10-10','cards':['old']}
            target.write_text(json.dumps(previous))
            with patch.object(updater,'ROOT',root), patch.dict('os.environ',{'LLM_API_KEY':''}), patch.object(updater,'get_public') as fetch:
                self.assertEqual(updater.main(),1)
            result=json.loads(target.read_text())
            self.assertEqual(result['cards'],previous['cards'])
            self.assertEqual(result['generatedAt'],previous['generatedAt'])
            self.assertEqual(result['status'],'update-failed')
            fetch.assert_not_called()

    def test_successful_refresh_uses_bodies_and_preserves_history(self):
        sources, result = self.fixture()
        cards = updater.validate_cards(result,sources,[])
        previous={'cards':[], 'mode':'llm', 'promptVersion':updater.PROMPT_VERSION, 'sourceHistory':['https://huggingface.co/blog/older']}
        with patch.object(updater,'get_public',return_value=b'feed'), patch.object(updater,'parse_feed',return_value=sources), patch.object(updater,'article_body',return_value=sources[0]['body']), patch.object(updater,'generate',return_value=cards) as generate:
            payload, changed = updater.refresh(previous,datetime(2026,10,11,tzinfo=timezone.utc),'test-key')
        self.assertTrue(changed)
        self.assertEqual(len(payload['cards']),5)
        self.assertEqual(len(payload['sourceHistory']),6)
        self.assertIn('body',generate.call_args.args[0][0])
        self.assertNotIn('test-key',json.dumps(payload))

    def test_old_prompt_regenerates_even_on_same_day_with_same_articles(self):
        sources, result = self.fixture()
        cards = updater.validate_cards(result,sources,[])
        previous={'mode':'llm','generatedAt':'2026-10-11T00:00:00+00:00',
                  'sourceHistory':[s['url'] for s in sources], 'cards':['old exam cards']}
        with patch.object(updater,'get_public',return_value=b'feed'), patch.object(updater,'parse_feed',return_value=sources), patch.object(updater,'article_body',return_value=sources[0]['body']), patch.object(updater,'generate',return_value=cards) as generate:
            payload, changed = updater.refresh(previous,datetime(2026,10,11,1,tzinfo=timezone.utc),'test-key')
        self.assertTrue(changed)
        self.assertEqual(payload['promptVersion'],updater.PROMPT_VERSION)
        generate.assert_called_once()

    def test_rejects_exam_question_headlines(self):
        sources, result = self.fixture()
        result['cards'][0]['question']='這篇文章如何改善模型的運作效率？'
        with self.assertRaisesRegex(ValueError,'declarative'):
            updater.validate_cards(result,sources,[])

    def test_api_contract_and_truncated_output(self):
        from unittest.mock import MagicMock
        sources, result = self.fixture()
        response=MagicMock()
        response.__enter__.return_value=response
        response.read.return_value=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}).encode()
        with patch.object(updater,'urlopen',return_value=response) as call:
            cards=updater.generate(sources,[],'test-key')
        request=call.call_args.args[0]
        self.assertEqual(request.full_url,updater.API_URL)
        payload=json.loads(request.data)
        self.assertEqual(payload['model'],'deepseek-flash')
        self.assertEqual(payload['response_format'],{'type':'json_object'})
        self.assertEqual(len(cards),5)
        response.read.return_value=json.dumps({'choices':[{'finish_reason':'length'}]}).encode()
        with patch.object(updater,'urlopen',return_value=response) as call, self.assertRaises(updater.ContentRejected):
            updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,3)

    def test_length_repair_succeeds_with_one_revision(self):
        from unittest.mock import MagicMock
        sources, valid = self.fixture()
        invalid=json.loads(json.dumps(valid))
        invalid['cards'][0]['answer']='過長的導讀'*100
        responses=[]
        for draft in [invalid, valid]:
            response=MagicMock()
            response.__enter__.return_value=response
            response.read.return_value=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(draft)}}]}).encode()
            responses.append(response)
        with patch.object(updater,'urlopen',side_effect=responses) as call:
            result=updater.generate(sources,[],'test-key')
        self.assertEqual(len(result),5)
        self.assertEqual(call.call_count,2)
        repair=json.loads(call.call_args.args[0].data)['messages'][-1]['content']
        self.assertIn('80–320',repair)
        self.assertIn('"answer": 500',repair)

    def test_content_rollback_is_success_and_keeps_previous_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data').mkdir()
            target=root/'data/cards.json'
            previous={'editionId':'old','generatedAt':'2026-10-10','cards':['old']}
            target.write_text(json.dumps(previous))
            with patch.object(updater,'ROOT',root), patch.object(updater,'refresh',side_effect=updater.ContentRejected('length')), patch.object(updater,'report_failure') as report:
                self.assertEqual(updater.main(),0)
            result=json.loads(target.read_text())
            self.assertEqual(result['editionId'],'old')
            self.assertEqual(result['cards'],['old'])
            self.assertEqual(result['generatedAt'],'2026-10-10')
            self.assertEqual(result['status'],'content-retained')
            report.assert_not_called()

if __name__ == '__main__':
    unittest.main()
