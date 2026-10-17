import importlib.util
import json
import unittest
import tempfile
import contextlib
import io
from unittest.mock import patch, MagicMock
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
        output_capture = contextlib.redirect_stdout(io.StringIO())
        output_capture.__enter__()
        self.addCleanup(output_capture.__exit__, None, None, None)

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
            self.assertIn('這不代表今日更新成功',summary.read_text())

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
        urls=['https://news.mit.edu/2026/test-0-1010','https://research.google/blog/test-1/',
              'https://www.microsoft.com/en-us/research/blog/test-2/','https://huggingface.co/blog/test-3',
              'https://hkust.edu.hk/news/test-4']
        names=['MIT News','Google Research','Microsoft Research','Hugging Face','香港科技大學（HKUST）']
        actors=['MIT','Google','Microsoft','Hugging Face','HKUST']
        titles=['AI for medical diagnosis','AI for protein prediction','AI architecture improves efficiency','AI engineering tools','AI image generation']
        sources = [{'url':urls[i], 'sourceName':names[i], 'platform':names[i],
                    'publishedAt':'2026-10-10T00:00:00+00:00', 'title':titles[i],
                    'body':actors[i]+': The model improves efficiency using a smaller architecture.'} for i in range(5)]
        cards = [{'sourceIndex':i, 'actor':actors[i], 'category':'模型效率', 'question':f'第{i}篇文章介紹以更小架構改善模型效率',
                  'answer':actors[i]+' 團隊在文章中說明，模型採用更小的架構來提升運作效率；這並不代表所有任務都有相同表現。\n\n這可能意味著，資源有限的部署情境值得重新評估較小模型的適用性。\n\n文章摘錄未提供具體測試條件，實際效益仍需依任務驗證。',
                  'evidence':'The model improves efficiency'} for i in range(5)]
        return sources, {'cards':cards}

    def edition(self):
        sources, raw = self.fixture()
        return {'mode':'llm','promptVersion':updater.PROMPT_VERSION,'editionId':'stable',
                'generatedAt':'2026-10-10T00:00:00+00:00',
                'cards':updater.validate_cards(raw,sources,[]),
                'sourceHistory':[s['url'] for s in sources],'questionHistory':[]}

    def api_response(self, body):
        response=MagicMock()
        response.__enter__.return_value=response
        response.url=updater.API_URL
        response.read.return_value=body
        return response

    def completion(self, draft):
        return self.api_response(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(draft)}}]}).encode())

    def structured_fixture(self):
        sources, raw=self.fixture()
        for card in raw['cards']:
            card['paragraphs']=card.pop('answer').split('\n\n')
            card.pop('evidence')
            card['evidenceIndex']=0
        return sources, raw

    def test_structured_drafts_compile_three_paragraphs_and_literal_evidence(self):
        sources, raw=self.structured_fixture()
        raw['cards'][0]['paragraphs'][1]=' \n '+raw['cards'][0]['paragraphs'][1]+'\n\n '
        with patch.object(updater,'api_open',return_value=self.completion(raw)):
            cards=updater.generate(sources,[],'test-key')
        for index, card in enumerate(cards):
            self.assertEqual(len(card['answer'].split('\n\n')),3)
            self.assertEqual(card['evidence'],updater.evidence_options(sources[index]['body'])[0])
            self.assertIn(card['evidence'],sources[index]['body'])
            self.assertNotIn('paragraphs',card)
            self.assertNotIn('evidenceIndex',card)

    def test_only_failed_card_is_requested_again_and_valid_cards_stay_unchanged(self):
        sources, valid=self.fixture()
        invalid=json.loads(json.dumps(valid))
        invalid['cards'][0]['answer']='導讀過長'*150
        replies=[self.completion(invalid),self.completion({'cards':[valid['cards'][0]]})]
        with patch.object(updater,'api_open',side_effect=replies) as call:
            cards=updater.generate(sources,[],'test-key')
        repair=json.loads(call.call_args.args[0].data)
        context=json.loads(repair['messages'][-1]['content'])
        self.assertEqual(context['targetSourceIndexes'],[0])
        self.assertEqual(len(context['articles']),1)
        self.assertEqual(context['acceptedCardCount'],4)
        self.assertEqual(repair['max_tokens'],1600)
        self.assertEqual(cards[1:],updater.validate_cards(valid,sources,[])[1:])
        self.assertEqual(call.call_count,2)

    def test_all_failed_cards_receive_precise_feedback_in_one_pass(self):
        sources, valid=self.fixture()
        invalid=json.loads(json.dumps(valid))
        invalid['cards'][0]['answer']='過長的導讀'*100
        invalid['cards'][1]['actor']='不存在的機構'
        replies=[self.completion(invalid),self.completion({'cards':valid['cards'][:2]})]
        with patch.object(updater,'api_open',side_effect=replies) as call:
            cards=updater.generate(sources,[],'test-key')
        context=json.loads(json.loads(call.call_args.args[0].data)['messages'][-1]['content'])
        self.assertEqual(context['targetSourceIndexes'],[0,1])
        self.assertEqual(len(context['validationFeedback']),2)
        self.assertEqual(context['validationFeedback'][0]['lengths']['answer'],500)
        self.assertIn('具名',context['validationFeedback'][1]['reason'])
        self.assertEqual(len(cards),5)

    def test_sixth_attempt_can_complete_a_batch_without_regenerating_good_cards(self):
        sources, valid=self.fixture()
        invalid=json.loads(json.dumps(valid));invalid['cards'][0]['answer']='過長的導讀'*100
        replies=[self.completion(invalid) for _ in range(5)]+[self.completion({'cards':[valid['cards'][0]]})]
        with patch.object(updater,'api_open',side_effect=replies) as call:
            cards=updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,6)
        self.assertEqual(len(cards),5)
        self.assertEqual(cards[1:],updater.validate_cards(valid,sources,[])[1:])
        cold=json.loads(json.loads(call.call_args_list[3].args[0].data)['messages'][-1]['content'])
        self.assertEqual(cold['previousDrafts'],[])
        self.assertEqual(cold['targetSourceIndexes'],[0])

    def test_grounding_failures_can_switch_articles_but_not_valid_cards(self):
        sources, valid=self.fixture()
        invalid=json.loads(json.dumps(valid));invalid['cards'][0]['evidence']='A fabricated quotation not in the source'
        alternative={**sources[0],'url':sources[0]['url']+'-alternative'}
        replies=[self.completion(invalid) for _ in range(3)]+[self.completion({'cards':[valid['cards'][0]]})]
        with patch.object(updater,'api_open',side_effect=replies),patch.object(updater,'article_body',return_value=sources[0]['body']) as read:
            cards=updater.generate(sources,[],'test-key',alternatives=[alternative])
        self.assertEqual(cards[0]['sourceUrl'],alternative['url'])
        self.assertEqual(cards[1:],updater.validate_cards(valid,sources,[])[1:])
        self.assertNotEqual(sources[0]['url'],alternative['url'])
        read.assert_called_once_with(alternative['url'])

    def test_evidence_options_stay_literal_and_bounded_for_long_chinese_and_english(self):
        for body in [('原文證據與適用限制。'*1200)+'結束',('The research team reports a grounded mechanism. '*400)+'End.']:
            options=updater.evidence_options(body)
            self.assertTrue(options)
            self.assertLessEqual(len(options),24)
            self.assertTrue(all(10<=len(e)<=180 and updater.normalize(e) in updater.normalize(body) for e in options))

    def test_invalid_evidence_indices_and_wrong_paragraph_counts_do_not_bypass_validation(self):
        for kind in ['index','paragraphs']:
            sources, raw=self.structured_fixture()
            if kind=='index': raw['cards'][0]['evidenceIndex']=999
            else: raw['cards'][0]['paragraphs']=raw['cards'][0]['paragraphs'][:2]
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                updater.validate_cards(raw,sources,[])

    def test_harmless_numeric_strings_are_normalized_but_wrong_indices_are_rejected(self):
        sources, raw=self.structured_fixture()
        for card in raw['cards']:
            card['sourceIndex']=str(card['sourceIndex']);card['evidenceIndex']='0'
        with patch.object(updater,'api_open',return_value=self.completion(raw)):
            self.assertEqual(len(updater.generate(sources,[],'test-key')),5)
        raw['cards'][0]['evidenceIndex']=True
        with self.assertRaisesRegex(ValueError,'evidence selection'):updater.validate_cards(raw,sources,[])

    def test_success_dates_record_completion_not_start_of_generation(self):
        sources, raw=self.fixture();cards=updater.validate_cards(raw,sources,[])
        class CompletedClock(datetime):
            @classmethod
            def now(cls,tz=None):return datetime(2026,10,14,1,10,tzinfo=timezone.utc)
        with patch.object(updater,'datetime',CompletedClock),patch.object(updater,'collect_articles',return_value=sources),patch.object(updater,'select_sources',return_value=sources),patch.object(updater,'generate',return_value=cards):
            payload,_=updater.refresh({'cards':[]},datetime(2026,10,14,1,tzinfo=timezone.utc),'test-key')
        self.assertEqual(payload['generatedAt'],'2026-10-14T01:10:00+00:00')

    def test_kept_benchmark_and_headline_rules_also_apply_across_partial_revisions(self):
        sources, valid=self.fixture()
        invalid=json.loads(json.dumps(valid))
        for index in range(2):invalid['cards'][index]['question']=f'第{index}個模型在新基準評測中的排名進展'
        with patch.object(updater,'api_open',side_effect=[self.completion(invalid),self.completion({'cards':[valid['cards'][1]]})]) as call:
            cards=updater.generate(sources,[],'test-key')
        self.assertEqual(sum(bool(updater.BENCHMARK.search(c['question'])) for c in cards),1)
        repair=json.loads(json.loads(call.call_args.args[0].data)['messages'][-1]['content'])
        self.assertEqual(repair['remainingBenchmarkSlots'],0)

    def test_terminal_rejection_keeps_a_safe_card_specific_reason_and_attempt_count(self):
        sources, raw=self.fixture();raw['cards'][2]['answer']='過長的導讀'*100
        with patch.object(updater,'api_open',return_value=self.completion(raw)) as call:
            with self.assertRaises(updater.ContentRejected) as raised:updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,6)
        self.assertEqual(raised.exception.attempts,6)
        self.assertIn('卡3',str(raised.exception))
        self.assertIn('80–320',str(raised.exception))
        self.assertNotIn('test-key',str(raised.exception))

    def test_alternate_article_history_records_what_was_published_not_initial_plan(self):
        sources, raw=self.fixture();cards=updater.validate_cards(raw,sources,[])
        original=sources[0]['url'];cards[0]['sourceUrl']=original+'-alternative'
        with patch.object(updater,'collect_articles',return_value=sources),patch.object(updater,'select_sources',return_value=sources),patch.object(updater,'generate',return_value=cards):
            payload, _=updater.refresh({'cards':[]},datetime(2026,10,14,tzinfo=timezone.utc),'test-key')
        self.assertIn(cards[0]['sourceUrl'],payload['sourceHistory'])
        self.assertNotIn(original,payload['sourceHistory'])

    def rss(self, sources):
        return ('<rss><channel>'+''.join('<item><title>'+s['title']+'</title><link>'+s['url']+'</link><pubDate>Sat, 10 Oct 2026 00:00:00 GMT</pubDate></item>' for s in sources)+'</channel></rss>').encode()

    def test_each_platform_only_accepts_its_own_article_paths(self):
        sources, _=self.fixture()
        sources.append({'title':'人工智能醫療工具','url':'https://www.qbitai.com/2026/10/502544.html'})
        now=datetime(2026,10,12,tzinfo=timezone.utc)
        xml=self.rss(sources).decode().replace('</channel>',
            '<item><title>AI medical news</title><link>https://evil.example/2026/news</link><pubDate>Sat, 10 Oct 2026 00:00:00 GMT</pubDate></item></channel>')
        for key, source in updater.SOURCES.items():
            with self.subTest(source=key):
                parsed=updater.parse_feed(xml,now,key)
                self.assertTrue(parsed)
                self.assertTrue(all(updater.allowed_article(a['url'],source) for a in parsed))

    def test_atom_dates_tracking_duplicates_and_irrelevant_news(self):
        xml='''<feed xmlns="http://www.w3.org/2005/Atom">
        <entry><title>AI improves medical diagnosis</title><link href="https://research.google/blog/health/?utm_source=rss"/><published>2026-10-10T00:00:00Z</published></entry>
        <entry><title>AI improves medical diagnosis</title><link href="https://research.google/blog/health/#section"/><updated>2026-10-10T00:00:00Z</updated></entry>
        <entry><title>Office holiday hours</title><link href="https://research.google/blog/hours/"/><updated>2026-10-10T00:00:00Z</updated></entry>
        <entry><title>AI from the future</title><link href="https://research.google/blog/future/"/><updated>2027-10-10T00:00:00Z</updated></entry>
        </feed>'''
        articles=updater.parse_feed(xml,datetime(2026,10,12,tzinfo=timezone.utc),'google')
        self.assertEqual([a['url'] for a in articles],['https://research.google/blog/health/'])

    def test_each_body_adapter_excludes_navigation_and_related_articles(self):
        for source in updater.SOURCES.values():
            classes=' '.join(source['classes'])
            parser=updater.ArticleParser(source['classes'])
            parser.feed('<nav>bad navigation</nav><div class="'+classes+'"><p>Real article</p><script>bad script</script><p>Supported facts</p></div><footer>bad footer</footer>')
            with self.subTest(platform=source['name']):
                self.assertEqual(updater.normalize(''.join(parser.text)),'Real article Supported facts')

    def test_general_institution_announcements_do_not_fill_application_slots(self):
        xml='''<rss><channel><item><title>University announces a new education initiative</title>
        <link>https://news.mit.edu/2026/initiative-1010</link><pubDate>Sat, 10 Oct 2026 00:00:00 GMT</pubDate>
        <description>New classrooms for science, AI and other subjects.</description></item></channel></rss>'''
        self.assertEqual(updater.parse_feed(xml,datetime(2026,10,12,tzinfo=timezone.utc),'mit'),[])

    def test_partial_feed_failure_does_not_discard_other_platforms(self):
        from urllib.error import URLError
        sources, _=self.fixture()
        def fetch(url):
            if url==updater.FEED: raise URLError('offline')
            return self.rss(sources)
        with patch.object(updater,'get_public',side_effect=fetch):
            articles=updater.collect_articles(datetime(2026,10,12,tzinfo=timezone.utc))
        self.assertEqual({a['platform'] for a in articles},{'MIT News','Google Research','Microsoft Research','香港科技大學（HKUST）'})
        self.assertEqual(len(articles),4)

    def test_public_fetch_rejects_unknown_urls_and_cross_host_redirects(self):
        with patch.object(updater,'urlopen') as call:
            with self.assertRaisesRegex(ValueError,'publisher URL'): updater.get_public('https://evil.example/news')
            call.assert_not_called()
        response=self.api_response(b'private data')
        response.url='https://evil.example/news'
        with patch.object(updater,'urlopen',return_value=response),self.assertRaisesRegex(ValueError,'redirect'):
            updater.get_public(updater.SOURCES['mit']['feed'])
        response.read.assert_not_called()

    def test_selection_balances_platforms_and_application_domains(self):
        sources, _=self.fixture()
        prolific=[{**sources[3],'url':sources[3]['url']+'-'+str(i),'title':'AI benchmark score '+str(i)} for i in range(20)]
        with patch.object(updater,'article_body',return_value='supported body'):
            selected=updater.select_sources(prolific+sources,[])
        platforms=[s['platform'] for s in selected]
        self.assertEqual(len(set(platforms)),5)
        self.assertTrue(all(platforms.count(p)==1 for p in platforms))
        tags=[updater.article_tags(s) for s in selected]
        self.assertGreaterEqual(len({domain for domain,_ in tags if domain}),2)
        self.assertLessEqual(sum(benchmark for _,benchmark in tags),1)

    def test_platform_compares_bodies_and_prefers_useful_article_over_newest_theory(self):
        sources, _=self.fixture()
        sources[0]={**sources[0], 'publishedAt':'2026-10-15T00:00:00Z',
                    'title':'AI diagnosis theorem proves a new convergence rate',
                    'summary':'A formal proof of a theoretical bound.'}
        practical={**sources[0], 'url':sources[0]['url']+'-practical',
                   'publishedAt':'2026-10-14T00:00:00Z',
                   'title':'AI assists hospital diagnosis in a small pilot',
                   'summary':'Doctors use a prototype to detect disease in hospital workflows.'}
        def read(url):
            if url==practical['url']: return 'Hospital doctors detect disease. Compared with manual screening, the prototype has privacy limitations.'
            if url==sources[0]['url']: return 'We prove a theorem with a convergence rate and an asymptotic regret bound.'
            return 'A supported research finding.'
        with patch.object(updater,'article_body',side_effect=read) as call:
            selected=updater.select_sources(sources+[practical],[],datetime(2026,10,16,tzinfo=timezone.utc))
        self.assertIn(practical['url'],[a['url'] for a in selected])
        self.assertNotIn(sources[0]['url'],[a['url'] for a in selected])
        self.assertEqual(call.call_count,6)
        self.assertEqual(len({a['platform'] for a in selected}),5)

    def test_body_comparison_does_not_trust_an_applied_clickbait_teaser(self):
        sources, _=self.fixture()
        sources[0]={**sources[0], 'title':'AI tool for medical diagnosis',
                    'summary':'Available hospital demo detects disease, compared with a prototype with limitations.'}
        sources[0].pop('body')  # RSS metadata, before either full text is read.
        real={**sources[0], 'url':sources[0]['url']+'-real', 'summary':'A research finding.'}
        self.assertGreater(updater.editorial_score(sources[0]),updater.editorial_score(real))
        def read(url):
            if url==sources[0]['url']: return 'A theorem about convergence rates. We derive a formal proof.'
            if url==real['url']: return 'Hospital doctors detect disease. A pilot has privacy limitations compared with manual screening.'
            return 'Supported research content.'
        with patch.object(updater,'article_body',side_effect=read):
            selected=updater.select_sources(sources+[real],[])
        self.assertIn(real['url'],[a['url'] for a in selected])

    def test_two_readable_competitors_per_platform_are_compared_before_selecting(self):
        sources, _=self.fixture()
        competitors=[{**a,'url':a['url']+'-other'} for a in sources]
        with patch.object(updater,'article_body',return_value='Supported research content.') as read, patch.object(updater,'api_open') as paid:
            selected=updater.select_sources(sources+competitors,[])
        self.assertEqual(len(selected),5)
        self.assertEqual(read.call_count,10)
        self.assertEqual(len({c.args[0] for c in read.call_args_list}),10)
        paid.assert_not_called()

    def test_chinese_applied_story_beats_pure_theory_without_banning_research(self):
        sources, _=self.fixture()
        theoretical={**sources[0], 'title':'大模型收敛率定理与理论证明', 'body':'提出收敛率分析与理论界限。'}
        practical={**sources[0], 'title':'研究论文介绍医院AI诊断原型',
                   'body':'医院开展小规模试点，辅助医生诊断，通过对比识别遗漏，说明隐私限制。'}
        self.assertGreater(updater.editorial_score(practical),updater.editorial_score(theoretical))
        plain={**practical,'title':'医院AI诊断原型'}
        self.assertEqual(updater.editorial_score(practical),updater.editorial_score(plain))

    def test_editorial_signals_are_capped_and_old_news_has_a_recency_penalty(self):
        sources, _=self.fixture()
        body='Hospital doctors detect disease using a prototype with privacy limitations compared with manual screening. '
        article={**sources[0],'body':body,'publishedAt':'2026-10-15T00:00:00Z'}
        now=datetime(2026,10,16,tzinfo=timezone.utc)
        score=updater.editorial_score(article,now)
        self.assertEqual(score,updater.editorial_score({**article,'body':body*100},now))
        self.assertEqual(score-3,updater.editorial_score({**article,'publishedAt':'2026-10-02T00:00:00Z'},now))
        self.assertEqual(score-7,updater.editorial_score({**article,'publishedAt':'2026-09-16T00:00:00Z'},now))

    def test_awards_and_fundraising_do_not_beat_substantive_application_stories(self):
        sources, _=self.fixture()
        body='A hospital prototype can detect disease, with privacy limitations compared with manual screening.'
        application={**sources[0],'title':'AI medical diagnosis pilot','body':body}
        for title in ['AI entrepreneurship competition winners announced','大模型公司完成新一轮融资']:
            with self.subTest(title=title):
                self.assertGreater(updater.editorial_score(application),updater.editorial_score({**application,'title':title}))

    def test_prolific_platform_does_not_hide_its_useful_article_outside_pool(self):
        sources, _=self.fixture()
        theory=[{**sources[0],'url':sources[0]['url']+'-theory-'+str(i),
                 'title':'AI theorem with a convergence rate '+str(i),'body':'Formal proof of a theorem.'} for i in range(30)]
        practical={**sources[0],'url':sources[0]['url']+'-practical',
                   'title':'Hospital AI diagnosis pilot', 'summary':'Hospital doctors detect disease. A prototype has privacy limitations.'}
        with patch.object(updater,'article_body',return_value=practical['summary']) as read:
            selected=updater.select_sources(theory+sources[1:]+[practical],[])
        self.assertIn(practical['url'],[a['url'] for a in selected])
        self.assertLessEqual(read.call_count,18)

    def test_selection_looks_beyond_two_when_application_diversity_is_missing(self):
        sources, _=self.fixture()
        articles=[{**a,'url':a['url']+'-'+str(i),'title':'AI medical diagnosis in a hospital',
                   'summary':'Hospital doctors detect disease.'} for a in sources for i in range(2)]
        extra={**sources[0],'url':sources[0]['url']+'-science','title':'AI protein prediction', 'summary':''}
        with patch.object(updater,'article_body',return_value='Supported research content.') as read:
            selected=updater.select_sources(articles+[extra],[])
        self.assertIn(extra['url'],[a['url'] for a in selected])
        self.assertEqual(read.call_count,11)

    def test_comparison_budget_keeps_valid_plan_even_if_competitors_are_unreadable(self):
        sources, _=self.fixture()
        articles=[{**a,'url':a['url']+'-'+str(i)} for a in sources for i in range(6)]
        good={a['url']+'-0' for a in sources}
        def read(url):
            if url not in good: raise TimeoutError()
            return 'A supported research finding.'
        with patch.object(updater,'article_body',side_effect=read) as call:
            selected=updater.select_sources(articles,[])
        self.assertEqual({a['url'] for a in selected},good)
        self.assertEqual(call.call_count,18)
        self.assertEqual(len({c.args[0] for c in call.call_args_list}),18)

    def test_fresh_unused_candidates_still_take_priority_over_repeated_articles(self):
        sources, _=self.fixture()
        seen={**sources[0],'url':sources[0]['url']+'-seen',
              'title':'Hospital AI diagnosis pilot', 'body':'Hospital doctors detect disease. A prototype has privacy limitations.'}
        selected=updater.choose_edition(sources+[seen],[seen['url']])
        self.assertNotIn(seen['url'],[a['url'] for a in selected])

    def test_generation_prompt_teaches_nonacademic_style_without_invented_uses(self):
        sources, raw=self.fixture()
        with patch.object(updater,'api_open',return_value=self.completion(raw)) as call:
            updater.generate(sources,[],'test-key')
        system=json.loads(call.call_args.args[0].data)['messages'][0]['content']
        self.assertIn('這不是論文摘要或學術課堂',system)
        self.assertIn('原型、試點與已部署產品必須區分',system)
        self.assertIn('不能為了接地氣編造',system)
        self.assertIn('不寫進標題或正文',system)
        self.assertIn('用途與變化，不堆縮寫',system)
        self.assertIn('不猜測縮寫全稱',system)
        self.assertIn('"terms":[]',system)
        self.assertNotIn('並順手解釋',system)

    def test_terms_are_saved_separately_without_changing_the_answer(self):
        sources, raw=self.fixture()
        draft=raw['cards'][0]
        draft['terms']=[{'term':'模型','definition':'本篇用來處理資料、產生結果的運算系統。'}]
        result=updater.validate_one(draft,sources[0],[])
        self.assertEqual(result['terms'],draft['terms'])
        self.assertEqual(result['answer'],draft['answer'])
        self.assertNotIn(draft['terms'][0]['definition'],result['answer'])
        changed={**draft,'terms':[{'term':'模型','definition':'本篇用來處理資料的運算系統；這是測試注釋。'}]}
        self.assertNotEqual(result['id'],updater.validate_one(changed,sources[0],[])['id'])

    def test_bad_optional_terms_do_not_reject_good_cards(self):
        sources, raw=self.fixture()
        for terms in [None,{},42,'bad',[None,{},42],
                      [{'term':'模型','definition':'太短'}],
                      [{'term':'模型','definition':'中'*121}],
                      [{'term':'模型','definition':'請看 https://example.com/相關解釋'}],
                      [{'term':'不在正文','definition':'這是不應展示在介面中的測試注釋。'}],
                      [{'term':'模型','definition':'An English-only definition.'}]]:
            with self.subTest(terms=terms):
                card=updater.validate_one({**raw['cards'][0],'terms':terms},sources[0],[])
                self.assertEqual(card['terms'],[])

    def test_terms_normalization_deduplication_and_three_note_limit(self):
        definition='這是測試用的短注釋，不代表真實新聞內容。'
        card={'question':'模型 架構 效率 資源 MIT', 'terms':[
            {'term':term,'definition':' '+definition+'\n'} for term in [' 模型 ','模型','MIT','mit','架構','效率']]}
        self.assertEqual(updater.card_terms(card),[
            {'term':term,'definition':definition} for term in ['模型','MIT','架構']])

    def test_term_matching_uses_literal_text_and_ascii_boundaries(self):
        definition='這是測試用的短注釋，不代表真實新聞內容。'
        terms=[{'term':term,'definition':definition} for term in ['AI','VLA','a(b)','C++']]
        self.assertEqual(updater.card_terms({'question':'chair NVLA', 'terms':terms}),[])
        matched=updater.card_terms({'question':'AI的用途 a(b) C++', 'terms':terms})
        self.assertEqual([term['term'] for term in matched],['AI','a(b)','C++'])

    def test_structured_paragraph_notes_are_available_in_bounded_repair_context(self):
        draft={'paragraphs':['模型的用途。','觀察。','限制。'], 'terms':[
            {'term':'模型','definition':'這是測試用的短注釋，不代表真實新聞。'}]}
        self.assertEqual(updater.feedback_draft(draft)['terms'],draft['terms'])

    def test_notes_use_the_same_generation_call_with_a_bounded_output_budget(self):
        sources, raw=self.fixture()
        for card in raw['cards']:
            card['terms']=[{'term':'模型','definition':'本篇用來處理資料、產生結果的運算系統。'}]
        with patch.object(updater,'api_open',return_value=self.completion(raw)) as call:
            generated=updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,1)
        self.assertEqual(json.loads(call.call_args.args[0].data)['max_tokens'],8000)
        self.assertTrue(all(len(card['terms'])==1 for card in generated))

    def test_repair_replacements_use_editorial_order_not_feed_input_order(self):
        sources, valid=self.fixture()
        invalid=json.loads(json.dumps(valid));invalid['cards'][0]['actor']='不存在的團隊'
        theory={**sources[0],'url':sources[0]['url']+'-theory',
                'title':'AI medical diagnosis theorem and convergence analysis','body':'A formal proof of a theorem.'}
        practical={**sources[0],'url':sources[0]['url']+'-practical',
                   'title':'Hospital AI medical diagnosis pilot',
                   'summary':'Hospital doctors detect disease. A prototype has privacy limitations.'}
        practical.pop('body')
        replies=[self.completion(invalid) for _ in range(3)]+[self.completion({'cards':[valid['cards'][0]]})]
        with patch.object(updater,'api_open',side_effect=replies),patch.object(updater,'article_body',return_value=sources[0]['body']) as read:
            cards=updater.generate(sources,[],'test-key',alternatives=[theory,practical])
        read.assert_called_once_with(practical['url'])
        self.assertEqual(cards[0]['sourceUrl'],practical['url'])

    def test_one_article_per_platform_is_a_hard_rule(self):
        sources, raw=self.fixture()
        sources[-1]['platform']=sources[0]['platform']
        self.assertIsNone(updater.choose_edition(sources,[]))
        with patch.object(updater,'article_body') as request,self.assertRaises(updater.SelectionUnavailable):
            updater.select_sources(sources,[])
        request.assert_not_called()
        with self.assertRaisesRegex(ValueError,'Repeated publisher platform'):
            updater.validate_cards(raw,sources,[])

    def test_chinese_topics_and_media_labels_are_preserved(self):
        cases=[('人工智能助力医疗诊断','醫療健康'),('大模型预测电网天气风险','環境能源'),
               ('物理AI加速机器人落地','機器人交通'),('DeepSeek助手新增办公插件','工作與工具')]
        for title,domain in cases:
            with self.subTest(title=title):
                xml=self.rss([{'title':title,'url':'https://www.qbitai.com/2026/10/502544.html'}])
                articles=updater.parse_feed(xml,datetime(2026,10,12,tzinfo=timezone.utc),'qbitai')
                self.assertEqual(len(articles),1)
                self.assertEqual(updater.article_tags(articles[0])[0],domain)
                self.assertIn('媒體報導',articles[0]['sourceName'])
                self.assertEqual(articles[0]['region'],'中國內地')

    def test_hkust_feed_uses_verified_current_article_host(self):
        xml=self.rss([{'title':'AI tools for medical diagnosis','url':'https://news.hkust.edu.hk/news/new-ai-tool'},
                      {'title':'AI external story','url':'https://evil.example/news/ai-tool'}])
        articles=updater.parse_feed(xml,datetime(2026,10,12,tzinfo=timezone.utc),'hkust')
        self.assertEqual([a['url'] for a in articles],['https://hkust.edu.hk/news/new-ai-tool'])
        self.assertEqual(articles[0]['region'],'香港')

    def test_regional_candidates_are_preferred_without_relaxing_topic_rules(self):
        sources, _=self.fixture()
        regional={**sources[3],'platform':'量子位','region':'中國內地',
                  'url':'https://www.qbitai.com/2026/10/502544.html'}
        selected=updater.choose_edition(sources+[regional],[])
        self.assertIn(regional['url'],[s['url'] for s in selected])
        self.assertEqual(len({s['platform'] for s in selected}),5)
        self.assertGreaterEqual(len({updater.article_tags(s)[0] for s in selected if updater.article_tags(s)[0]}),2)

    def test_failed_body_is_replaced_without_rereading_successful_bodies(self):
        sources, _=self.fixture()
        failed=updater.choose_edition(sources,[])[0]
        replacement={**failed,'url':failed['url']+'-replacement','publishedAt':'2026-10-09T00:00:00Z'}
        def read(url):
            if url==failed['url']: raise TimeoutError()
            return 'supported body'
        with patch.object(updater,'article_body',side_effect=read) as call:
            selected=updater.select_sources(sources+[replacement],[])
        self.assertNotIn(failed['url'],[s['url'] for s in selected])
        requests=[c.args[0] for c in call.call_args_list]
        self.assertEqual(len(requests),len(set(requests)))

    def test_article_network_work_is_bounded_even_when_bodies_all_fail(self):
        sources, _=self.fixture()
        articles=[{**source,'url':source['url']+'-'+str(i)} for source in sources for i in range(8)]
        with patch.object(updater,'article_body',side_effect=TimeoutError()) as call:
            with self.assertRaises(ValueError): updater.select_sources(articles,[])
        self.assertLessEqual(call.call_count,18)

    def test_unbalanced_topics_roll_back_without_a_paid_model_call(self):
        previous=self.edition()
        previous['promptVersion']='discovery-brief-v2'
        sources=[{**previous['cards'][3],'url':'https://huggingface.co/blog/only-'+str(i),
                  'platform':'Hugging Face','publishedAt':'2026-10-10T00:00:00Z','title':'AI architecture '+str(i)} for i in range(5)]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'data').mkdir()
            target=root/'data/cards.json'; target.write_text(json.dumps(previous))
            with patch.object(updater,'ROOT',root),patch.dict('os.environ',{'LLM_API_KEY':'test-key'}),patch.object(updater,'collect_articles',return_value=sources),patch.object(updater,'generate') as paid:
                self.assertEqual(updater.main(),1)
            paid.assert_not_called()
            after=json.loads(target.read_text())
            self.assertEqual(after['status'],'selection-unavailable')
            self.assertIn('平台',after['updateReason'])
            self.assertEqual(after['cards'],previous['cards'])
            self.assertEqual(after['generatedAt'],previous['generatedAt'])

    def test_actor_must_be_named_supported_and_introduced_in_first_paragraph(self):
        for kind in ['generic','invented','substring','missing-introduction']:
            sources, raw=self.fixture()
            if kind=='generic': raw['cards'][0]['actor']='作者'
            elif kind=='invented': raw['cards'][0]['actor']='Imaginary Lab'
            elif kind=='substring':
                sources[0]['body']=sources[0]['body'].replace('MIT','Limitations')
                sources[0]['sourceName']='Independent Lab'
            else: raw['cards'][0]['answer']=raw['cards'][0]['answer'].replace('MIT','某團隊',1)
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'attribution'):
                updater.validate_cards(raw,sources,[])
        sources, raw=self.fixture()
        raw['cards'][0]['answer']=raw['cards'][0]['answer'].replace('\n','\r\n')
        self.assertEqual(updater.validate_cards(raw,sources,[])[0]['actor'],'MIT')

    def test_model_cannot_turn_multiple_cards_into_benchmark_headlines(self):
        sources, raw=self.fixture()
        for i in range(2): raw['cards'][i]['question']=f'第{i}個模型在新基準評測中的排名進展'
        with self.assertRaisesRegex(ValueError,'benchmark headlines'): updater.validate_cards(raw,sources,[])

    def test_bad_completion_envelopes_do_not_start_paid_revisions(self):
        sources, _ = self.fixture()
        for raw in [b'<html>service unavailable</html>',b'null',b'{"error":{}}',b'{"choices":[]}',b'{"choices":[null]}',b'x'*(updater.MAX_API_BYTES+1)]:
            with self.subTest(body=raw[:50]), patch.object(updater,'api_open',return_value=self.api_response(raw)) as call:
                with self.assertRaises(updater.APIResponseError):
                    updater.generate(sources,[],'test-key')
                self.assertEqual(call.call_count,1)

    def test_http_auth_balance_and_network_failures_do_not_retry(self):
        from urllib.error import HTTPError, URLError
        sources, _ = self.fixture()
        for error in [HTTPError(updater.API_URL,401,'unauthorized',{},None),HTTPError(updater.API_URL,402,'balance',{},None),URLError('offline'),TimeoutError()]:
            with self.subTest(error=type(error).__name__), patch.object(updater,'api_open',side_effect=error) as call:
                with self.assertRaises((RuntimeError,URLError,TimeoutError)):
                    updater.generate(sources,[],'test-key')
                self.assertEqual(call.call_count,1)

    def test_empty_malformed_and_partial_model_drafts_are_bounded_revisions(self):
        sources, _ = self.fixture()
        for content in [None,'','{','{"cards":[]}','{"cards":[{}]}']:
            raw=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':content}}]}).encode()
            with self.subTest(content=content), patch.object(updater,'api_open',return_value=self.api_response(raw)) as call:
                with self.assertRaises(updater.ContentRejected):
                    updater.generate(sources,[],'test-key')
                self.assertEqual(call.call_count,updater.MAX_GENERATION_ATTEMPTS)

    def test_rejects_one_paragraph_or_four_paragraph_drafts(self):
        for count in [1,4]:
            sources, raw=self.fixture()
            raw['cards'][0]['answer']='\n\n'.join(['根據文章，較小架構可能適合資源有限的情境，但效益仍須依實際任務驗證。']*count)
            # Keep length within 80–320, isolate paragraph validation.
            if count==1: raw['cards'][0]['answer']=raw['cards'][0]['answer']*3
            with self.subTest(count=count), self.assertRaisesRegex(ValueError,'three paragraphs'):
                updater.validate_cards(raw,sources,[])

    def test_cache_miss_recovers_published_edition_before_generation(self):
        edition=self.edition()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'cards.json'
            target.write_text('{corrupt')
            response=self.api_response(json.dumps(edition).encode())
            response.url=updater.PUBLISHED_FEED
            with patch.object(updater,'urlopen',return_value=response):
                recovered=updater.load_previous(target)
            self.assertEqual(recovered['editionId'],'stable')
            self.assertEqual(recovered['cards'],edition['cards'])

    def test_valid_cached_ai_edition_does_not_fetch_published_copy(self):
        edition=self.edition()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'cards.json'
            target.write_text(json.dumps(edition))
            with patch.object(updater,'urlopen') as request:
                self.assertEqual(updater.load_previous(target),edition)
            request.assert_not_called()

    def test_corrupt_cache_and_offline_site_restore_checkout_seed(self):
        from urllib.error import URLError
        edition=self.edition()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data').mkdir()
            target=root/'data/cards.json'
            target.write_text('null')
            (root/'data/cards.seed.json').write_text(json.dumps(edition))
            with patch.object(updater,'ROOT',root),patch.object(updater,'urlopen',side_effect=URLError('offline')):
                self.assertEqual(updater.load_previous(target),edition)

    def test_corrupt_cache_seed_and_site_fall_back_to_curated_cards(self):
        from urllib.error import URLError
        concepts=json.loads((ROOT/'data/concepts.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data').mkdir()
            target=root/'data/cards.json'
            target.write_text('null')
            (root/'data/cards.seed.json').write_text('{broken')
            (root/'data/concepts.json').write_text(json.dumps(concepts))
            with patch.object(updater,'ROOT',root),patch.object(updater,'urlopen',side_effect=URLError('offline')):
                recovered=updater.load_previous(target)
            self.assertTrue(updater.valid_edition(recovered))

    def test_operational_failure_keeps_known_good_edition_atomic_and_truthful(self):
        from urllib.error import URLError
        edition=self.edition()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data').mkdir()
            target=root/'data/cards.json'
            target.write_text(json.dumps(edition))
            with patch.object(updater,'ROOT',root),patch.object(updater,'refresh',side_effect=URLError('offline')):
                self.assertEqual(updater.main(),1)
            after=json.loads(target.read_text())
            for field in ['cards','editionId','generatedAt','sourceHistory']:
                self.assertEqual(after[field],edition[field])
            self.assertEqual(after['status'],'update-failed')
            self.assertFalse(target.with_suffix('.tmp').exists())

    def test_invalid_cached_metadata_is_not_trusted(self):
        edition=self.edition()
        for change in [{'generatedAt':'not-a-date'},{'sourceHistory':'wrong'}, {'cards':[None]*5}]:
            with self.subTest(change=list(change)):
                self.assertFalse(updater.valid_edition({**edition,**change}))

    def test_redirect_is_rejected_before_api_key_can_be_forwarded(self):
        with self.assertRaises(updater.APIResponseError):
            updater.NoAPIRedirect().redirect_request(None,None,302,'redirect',{},'https://other.example')

    def test_pipeline_repair_publish_skip_then_network_rollback(self):
        from urllib.error import URLError
        sources, valid = self.fixture()
        body='<div class="blog-content news-article--content--body rich-text single-post__content news__body"><p>'+''.join(s['body'] for s in sources)*8+'</p></div>'
        feed='<rss><channel>'+''.join(
            '<item><title>'+s['title']+'</title><link>'+s['url']+'</link><pubDate>Sat, 10 Oct 2026 00:00:00 GMT</pubDate></item>' for s in sources)+'</channel></rss>'
        invalid=json.loads(json.dumps(valid))
        invalid['cards'][0]['answer']='過長的導讀'*100
        responses=[self.api_response(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(d)}}]}).encode()) for d in [invalid,valid]]
        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026,10,11,1,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data').mkdir()
            target=root/'data/cards.json'
            previous=self.edition()
            previous['sourceHistory']=[]
            target.write_text(json.dumps(previous))
            with patch.object(updater,'ROOT',root),patch.object(updater,'datetime',FrozenDateTime),patch.dict('os.environ',{'LLM_API_KEY':'test-key'}),patch.object(updater,'get_public',side_effect=lambda url: (feed if url in [s['feed'] for s in updater.SOURCES.values()] else body).encode()),patch.object(updater,'api_open',side_effect=responses) as api:
                self.assertEqual(updater.main(),0)
                published=json.loads(target.read_text())
                self.assertTrue(updater.valid_edition(published))
                self.assertNotEqual(published['editionId'],previous['editionId'])
                self.assertEqual(published['status'],'updated')
                self.assertEqual(api.call_count,2)
                self.assertEqual(updater.main(),0)
                self.assertEqual(json.loads(target.read_text())['status'],'already-generated-today')
                self.assertEqual(api.call_count,2)
                with patch.object(updater,'get_public',side_effect=URLError('offline')):
                    self.assertEqual(updater.main(),1)
                retained=json.loads(target.read_text())
                self.assertEqual(retained['editionId'],published['editionId'])
                self.assertEqual(retained['cards'],published['cards'])
                self.assertEqual(retained['generatedAt'],published['generatedAt'])
                self.assertEqual(retained['status'],'update-failed')

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
        with patch.object(updater,'collect_articles',return_value=sources), patch.object(updater,'generate') as generate:
            result, changed = updater.refresh(previous,datetime(2026,10,11,tzinfo=timezone.utc),'test-key')
        self.assertFalse(changed)
        self.assertEqual(result['cards'],['old'])
        self.assertEqual(result['status'],'no-new-articles')
        generate.assert_not_called()

    def test_at_most_one_generation_per_hong_kong_day(self):
        sources, _ = self.fixture()
        previous={'mode':'llm','promptVersion':updater.PROMPT_VERSION,'generatedAt':'2026-10-10T23:00:00+00:00','cards':['old']}
        with patch.object(updater,'collect_articles',return_value=sources), patch.object(updater,'generate') as generate:
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
            with patch.object(updater,'ROOT',root), patch.object(updater,'load_previous',return_value=previous), patch.dict('os.environ',{'LLM_API_KEY':''}), patch.object(updater,'get_public') as fetch:
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
        with patch.object(updater,'collect_articles',return_value=sources), patch.object(updater,'article_body',return_value=sources[0]['body']), patch.object(updater,'generate',return_value=cards) as generate:
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
        with patch.object(updater,'collect_articles',return_value=sources), patch.object(updater,'article_body',return_value=sources[0]['body']), patch.object(updater,'generate',return_value=cards) as generate:
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
        response.url=updater.API_URL
        response.read.return_value=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}).encode()
        with patch.object(updater,'api_open',return_value=response) as call:
            cards=updater.generate(sources,[],'test-key')
        request=call.call_args.args[0]
        self.assertEqual(request.full_url,updater.API_URL)
        payload=json.loads(request.data)
        self.assertEqual(payload['model'],'deepseek-flash')
        self.assertEqual(payload['response_format'],{'type':'json_object'})
        self.assertIn('教師模型',payload['messages'][0]['content'])
        self.assertIn('不能把發布平台當成研發者',payload['messages'][0]['content'])
        self.assertEqual(len(cards),5)
        response.read.return_value=json.dumps({'choices':[{'finish_reason':'length'}]}).encode()
        with patch.object(updater,'api_open',return_value=response) as call, self.assertRaises(updater.ContentRejected):
            updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,updater.MAX_GENERATION_ATTEMPTS)

    def test_length_repair_succeeds_with_one_revision(self):
        from unittest.mock import MagicMock
        sources, valid = self.fixture()
        invalid=json.loads(json.dumps(valid))
        invalid['cards'][0]['answer']='過長的導讀'*100
        responses=[]
        for draft in [invalid, valid]:
            response=MagicMock()
            response.__enter__.return_value=response
            response.url=updater.API_URL
            response.read.return_value=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(draft)}}]}).encode()
            responses.append(response)
        with patch.object(updater,'api_open',side_effect=responses) as call:
            result=updater.generate(sources,[],'test-key')
        self.assertEqual(len(result),5)
        self.assertEqual(call.call_count,2)
        repair=json.loads(call.call_args.args[0].data)['messages'][-1]['content']
        self.assertIn('80–320',repair)
        self.assertIn('"answer": 500',repair)

    def test_exhausted_generation_is_failure_without_overwriting_previous_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'data').mkdir()
            target=root/'data/cards.json'
            previous=self.edition()
            target.write_text(json.dumps(previous))
            reason='卡3：卡片導讀格式不正確：必須是 80–320 字的文字。'
            with patch.object(updater,'ROOT',root), patch.object(updater,'load_previous',return_value=previous), patch.object(updater,'refresh',side_effect=updater.ContentRejected(reason,attempts=6)), patch.object(updater,'report_failure') as report:
                self.assertEqual(updater.main(),1)
            result=json.loads(target.read_text())
            self.assertEqual(result['editionId'],previous['editionId'])
            self.assertEqual(result['cards'],previous['cards'])
            self.assertEqual(result['generatedAt'],previous['generatedAt'])
            self.assertEqual(result['status'],'generation-failed')
            self.assertEqual(result['generationAttempts'],6)
            self.assertEqual(result['updateReason'],reason)
            self.assertIsNotNone(updater.read_edition(target))
            report.assert_called_once_with(reason)

if __name__ == '__main__':
    unittest.main()
