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
        self.assertIn('60–800',updater.failure_reason(ValueError('Invalid card field: answer')))
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
                  'evidence':sources[i]['body']} for i in range(5)]
        for i, card in enumerate(cards):
            card['translations']={
                'zh-Hans':{'category':'模型效率','question':f'第{i}篇文章介绍以更小架构改善模型效率',
                           'paragraphs':[actors[i]+' 团队在文章中说明，模型采用更小的架构来提升运作效率；这并不代表所有任务都有相同表现。',
                                         '这可能意味着，资源有限的部署情境值得重新评估较小模型的适用性。',
                                         '文章摘录未提供具体测试条件，实际效益仍需依任务验证。'],'terms':[]},
                'en':{'category':'Model efficiency','question':f'Article {i}: smaller architectures may improve model efficiency',
                      'paragraphs':[actors[i]+' describes a smaller model architecture intended to improve efficiency. This does not establish the same benefit for every task.',
                                    'In a setting with limited compute, this may make smaller models worth considering again.',
                                    'The excerpt does not give specific test conditions. The benefit still needs to be checked on the target task.'],'terms':[]}}
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

    def responder(self, sources, valid, overrides=None):
        """Respond to the actual source/task, with independently scripted failures."""
        counts={i:0 for i in range(5)}
        def respond(request, timeout):
            context=json.loads(json.loads(request.data)['messages'][-1]['content'])
            source=context['article'] or context['lockedCard']
            index=next(i for i,item in enumerate(sources) if item['sourceName']==source['sourceName'])
            replies=(overrides or {}).get(index,[{'card':valid['cards'][index]}])
            reply=replies[min(counts[index],len(replies)-1)]
            counts[index]+=1
            if isinstance(reply,dict):return self.completion(reply)
            return self.api_response(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':reply}}]}).encode())
        return respond

    def text_card(self, card):
        parts=[]
        for prefix,version in [('',card),*[(language+'.',value) for language,value in card.get('translations',{}).items()]]:
            for key in ['actor','category','question','answer']:
                value=version.get(key)
                if key=='answer' and value is None:value='\n\n'.join(version.get('paragraphs',[]))
                if value:parts.append('['+prefix+key+']\n'+value)
        return '\n'.join(parts)

    def test_five_small_requests_bind_missing_or_fabricated_evidence_and_source_ids_in_code(self):
        sources, valid=self.fixture();raw=json.loads(json.dumps(valid))
        for index,card in enumerate(raw['cards']):
            card.pop('sourceIndex');card.pop('evidence')
            card.update({'sourceUrl':'https://evil.example','evidenceIndex':999})
            if index==1:card['evidence']='not an original quote'
        with patch.object(updater,'api_open',side_effect=self.responder(sources,raw)) as call:
            cards=updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,5)
        self.assertEqual(cards,updater.validate_cards(valid,sources,[]))
        for index,item in enumerate(call.call_args_list):
            request=json.loads(item.args[0].data)
            context=json.loads(request['messages'][-1]['content'])
            self.assertEqual(context['article']['body'],cards[index]['evidence'])
            self.assertEqual(request['max_tokens'],4096)
            self.assertEqual(cards[index]['sourceUrl'],sources[index]['url'])

    def test_json_cosmetic_errors_are_recovered_without_modifying_quotes_or_prose(self):
        sources, valid=self.fixture();card=valid['cards'][0]
        raw=json.dumps({'card':card},ensure_ascii=False)
        raw=raw.replace('\\n','\n')[:-1]+',}'
        decorated='\ufeff```json\n'+raw+'\n```'
        self.assertEqual(updater.parse_model_json(decorated),{'card':card})
        literal={'text':'comma,} stays literal, including a quote " and backslash \\'}
        self.assertEqual(updater.parse_model_json(json.dumps(literal)),literal)
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,{0:[decorated]})) as call:
            self.assertEqual(len(updater.generate(sources,[],'test-key')),5)
        self.assertEqual(call.call_count,5)

    def test_broken_json_on_three_cards_recovers_through_independent_text_retries(self):
        sources, valid=self.fixture()
        bad={0:'',2:'{"card":{"question":"不能直接嵌入"引號""}}',3:'{"card": {"answer": "unfinished'}
        overrides={index:[broken,self.text_card(valid['cards'][index])] for index,broken in bad.items()}
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,overrides)) as call:
            cards=updater.generate(sources,[],'test-key')
        self.assertEqual(cards,updater.validate_cards(valid,sources,[]))
        self.assertEqual(call.call_count,8)
        self.assertTrue(all(json.loads(item.args[0].data)['response_format']=={'type':'text'} for item in call.call_args_list[5:]))

    def test_every_card_can_fail_twice_and_still_publish_within_the_total_budget(self):
        sources, valid=self.fixture()
        overrides={index:['','{',self.text_card(card)] for index,card in enumerate(valid['cards'])}
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,overrides)) as call:
            cards=updater.generate(sources,[],'test-key')
        self.assertEqual(cards,updater.validate_cards(valid,sources,[]))
        self.assertEqual(call.call_count,15)

    def test_missing_translations_cannot_discard_five_valid_new_cards(self):
        sources, valid=self.fixture();raw=json.loads(json.dumps(valid))
        for card in raw['cards']:card['translations'].pop('en')
        with patch.object(updater,'api_open',side_effect=self.responder(sources,raw)) as call:
            cards=updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,15)
        self.assertTrue(all(set(card['translations'])=={'zh-Hans'} for card in cards))
        self.assertEqual([card['answer'] for card in cards],[card['answer'] for card in valid['cards']])
        self.assertTrue(updater.valid_edition({'cards':cards}))

    def test_translation_repairs_cannot_overwrite_core_or_an_already_valid_language(self):
        sources, valid=self.fixture();initial=json.loads(json.dumps(valid['cards'][1]));initial['translations']['en']['paragraphs']=[]
        repair={'actor':'Invented name','question':'不能覆寫繁體標題','translations':{
            'zh-Hans':{'question':'不能覆寫簡體標題'},'en':valid['cards'][1]['translations']['en']}}
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,{1:[{'card':initial},{'card':repair}]})) as call:
            cards=updater.generate(sources,[],'test-key')
        context=json.loads(json.loads(call.call_args.args[0].data)['messages'][-1]['content'])
        self.assertIsNone(context['article'])
        self.assertEqual(context['missingLanguages'],['en'])
        self.assertNotIn(valid['cards'][1]['question'],context['previousQuestions'])
        self.assertEqual(cards,updater.validate_cards(valid,sources,[]))
        self.assertEqual(call.call_count,6)

    def test_valid_translation_is_retained_when_the_other_language_keeps_failing(self):
        sources, valid=self.fixture();initial={**valid['cards'][0],'translations':{}}
        second={'translations':{'zh-Hans':valid['cards'][0]['translations']['zh-Hans']}}
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,{0:[{'card':initial},{'card':second},'']})) as call:
            cards=updater.generate(sources,[],'test-key')
        last=json.loads(json.loads(call.call_args.args[0].data)['messages'][-1]['content'])
        self.assertEqual(last['missingLanguages'],['en'])
        self.assertEqual(set(cards[0]['translations']),{'zh-Hans'})
        self.assertEqual(call.call_count,7)

    def test_wrong_attribution_still_blocks_publication_and_other_cards_are_not_regenerated(self):
        sources, valid=self.fixture();wrong={**valid['cards'][1],'actor':'Invented Lab'}
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,{1:[{'card':wrong}]})) as call:
            with self.assertRaises(updater.ContentRejected) as raised:updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,7)
        self.assertEqual(raised.exception.attempts,7)
        self.assertIn('卡2',str(raised.exception))
        self.assertIn('具名',str(raised.exception))

    def test_duplicate_article_can_be_replaced_without_rewriting_accepted_cards(self):
        sources, valid=self.fixture();duplicate={**valid['cards'][4],'question':'香港科技大學介紹更小架構改善運作效率'}
        alternative={**sources[4],'url':sources[4]['url']+'-alternative'}
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,{4:[{'card':duplicate},{'card':duplicate},{'card':valid['cards'][4]}]})) as call,patch.object(updater,'article_body',return_value=sources[4]['body']) as read:
            cards=updater.generate(sources,[duplicate['question']],'test-key',alternatives=[sources[4],alternative])
        read.assert_called_once_with(alternative['url'])
        self.assertEqual(cards[4]['sourceUrl'],alternative['url'])
        self.assertEqual(cards[:4],updater.validate_cards(valid,sources,[])[:4])
        self.assertEqual(call.call_count,7)

    def test_failed_alternate_reads_are_bounded_and_never_repeated(self):
        sources, valid=self.fixture();wrong={**valid['cards'][0],'actor':'Unknown Lab'}
        candidates=[{**sources[0],'url':sources[0]['url']+f'-{i}'} for i in range(6)]
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,{0:[{'card':wrong}]})),patch.object(updater,'article_body',side_effect=ValueError('unavailable')) as read:
            with self.assertRaises(updater.ContentRejected):updater.generate(sources,[],'test-key',alternatives=[sources[0],*candidates])
        urls=[item.args[0] for item in read.call_args_list]
        self.assertEqual(len(urls),4)
        self.assertEqual(len(set(urls)),4)
        self.assertNotIn(sources[0]['url'],urls)

    def test_locked_titles_and_benchmark_slots_still_apply_to_other_cards(self):
        sources, valid=self.fixture();raw=json.loads(json.dumps(valid))
        raw['cards'][0]['question']='第一個模型在新基準評測中的排名進展'
        raw['cards'][0]['translations']['en']['paragraphs']=[]
        raw['cards'][1]['question']=raw['cards'][0]['question']
        second={**valid['cards'][1],'question':'另一個模型在新基準評測中的排名進展'}
        overrides={0:[{'card':raw['cards'][0]}],1:[{'card':raw['cards'][1]},{'card':second},{'card':valid['cards'][1]}]}
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,overrides)) as call:
            cards=updater.generate(sources,[],'test-key')
        repairs=[json.loads(json.loads(item.args[0].data)['messages'][-1]['content']) for item in call.call_args_list[5:]]
        source_repairs=[context for context in repairs if context['article']]
        self.assertTrue(all(context['remainingBenchmarkSlots']==0 for context in source_repairs))
        self.assertIn(raw['cards'][0]['question'],source_repairs[0]['previousQuestions'])
        self.assertEqual(sum(bool(updater.BENCHMARK.search(card['question'])) for card in cards),1)

    def test_ambiguous_json_fields_text_sections_and_multi_card_sources_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            updater.parse_model_json('{"actor":"MIT","actor":"Google"}')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            updater.parse_text_card('[actor]\nMIT\n[actor]\nGoogle')
        sources, valid=self.fixture()
        unindexed=[{key:value for key,value in card.items() if key!='sourceIndex'} for card in valid['cards']]
        with patch.object(updater,'api_open',return_value=self.completion({'cards':unindexed})) as call:
            with self.assertRaises(updater.ContentRejected):updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,15)

    def test_source_excerpt_is_literal_bounded_and_is_the_only_generation_material(self):
        sources, valid=self.fixture()
        sources[0]['body']+=' The model has an important limitation.'*100
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid)) as call:
            cards=updater.generate(sources,[],'test-key')
        context=json.loads(json.loads(call.call_args_list[0].args[0].data)['messages'][-1]['content'])
        self.assertGreater(len(cards[0]['evidence']),180)
        self.assertLessEqual(len(cards[0]['evidence']),1800)
        self.assertIn(cards[0]['evidence'],sources[0]['body'])
        self.assertEqual(context['article']['body'],cards[0]['evidence'])

    def test_plain_text_quotes_terms_and_line_breaks_round_trip_without_json_escaping(self):
        sources, valid=self.fixture();card=valid['cards'][0]
        card['answer']=card['answer'].replace('模型','「模型」',1)
        content=self.text_card(card)+'\n[terms]\n模型 | 本篇指的是用來處理資料與產生結果的運算系統。'
        parsed=updater.parse_text_card(content)['card']
        self.assertEqual(parsed['answer'],card['answer'])
        self.assertEqual(parsed['terms'][0]['term'],'模型')
        parsed['evidence']=sources[0]['body']
        self.assertEqual(set(updater.validate_one(parsed,sources[0],[],require_translations=True)['translations']),{'zh-Hans','en'})

    def test_text_repair_accepts_fenced_sections_and_case_variants_without_leaking_fences(self):
        sources, valid=self.fixture()
        text='```text\n'+self.text_card(valid['cards'][0]).replace('[actor]','[Actor]').replace('[en.','[EN.')+'\n```'
        with patch.object(updater,'api_open',side_effect=self.responder(sources,valid,{0:['',text]})):
            cards=updater.generate(sources,[],'test-key')
        self.assertEqual(cards,updater.validate_cards(valid,sources,[]))

    def test_json_prompt_example_is_readable_and_passes_current_core_and_language_rules(self):
        sources,_=self.fixture()
        example=json.loads(updater.JSON_FORMAT.splitlines()[2])['card']
        source={**sources[0],'body':'Example Lab demonstrates a fictional small model that organizes documents.'}
        example['evidence']=source['body']
        self.assertEqual(set(updater.validate_one(example,source,[],require_translations=True)['translations']),{'zh-Hans','en'})

    def test_new_edition_is_published_even_when_one_translation_cannot_be_completed(self):
        sources, valid=self.fixture();valid['cards'][0]['question']='MIT 嘗試用更小架構協助處理醫療資料'
        valid['cards'][0]['translations'].pop('en')
        previous=self.edition();previous['sourceHistory']=[]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir()
            target=root/'data/cards.json';target.write_text(json.dumps(previous))
            with patch.object(updater,'ROOT',root),patch.object(updater,'load_previous',return_value=previous),patch.object(updater,'collect_articles',return_value=sources),patch.object(updater,'select_sources',return_value=sources),patch.dict('os.environ',{'LLM_API_KEY':'test-key'}),patch.object(updater,'api_open',side_effect=self.responder(sources,valid)):
                self.assertEqual(updater.main(),0)
            published=json.loads(target.read_text())
        self.assertEqual(published['status'],'updated')
        self.assertNotEqual(published['editionId'],previous['editionId'])
        self.assertNotEqual(published['generatedAt'],previous['generatedAt'])
        self.assertEqual(set(published['cards'][0]['translations']),{'zh-Hans'})
        self.assertTrue(updater.valid_edition(published))

    def test_service_failure_during_optional_translation_keeps_new_originals(self):
        from urllib.error import URLError
        sources, valid=self.fixture();raw=json.loads(json.dumps(valid));raw['cards'][0]['translations'].pop('en')
        first=self.responder(sources,raw)
        def respond(request,timeout):
            context=json.loads(json.loads(request.data)['messages'][-1]['content'])
            if context['lockedCard']:raise URLError('temporarily offline')
            return first(request,timeout)
        with patch.object(updater,'api_open',side_effect=respond) as call:
            cards=updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,6)
        self.assertEqual(cards,updater.validate_cards(raw,sources,[]))

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


    def test_evidence_options_stay_literal_and_bounded_for_long_chinese_and_english(self):
        for body in [('原文證據與適用限制。'*1200)+'結束',('The research team reports a grounded mechanism. '*400)+'End.']:
            options=updater.evidence_options(body)
            self.assertTrue(options)
            self.assertLessEqual(len(options),24)
            self.assertTrue(all(10<=len(e)<=180 and updater.normalize(e) in updater.normalize(body) for e in options))

    def test_invalid_legacy_evidence_indices_and_nontext_paragraphs_do_not_bypass_validation(self):
        for kind in ['index','paragraphs']:
            sources, raw=self.structured_fixture()
            if kind=='index': raw['cards'][0]['evidenceIndex']=999
            else: raw['cards'][0]['paragraphs']=[None]
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


    def test_notes_use_the_same_generation_call_with_a_bounded_output_budget(self):
        sources, raw=self.fixture()
        for card in raw['cards']:
            card['terms']=[{'term':'模型','definition':'本篇用來處理資料、產生結果的運算系統。'}]
        with patch.object(updater,'api_open',return_value=self.completion(raw)) as call:
            generated=updater.generate(sources,[],'test-key')
        self.assertEqual(call.call_count,5)
        self.assertEqual(json.loads(call.call_args.args[0].data)['max_tokens'],4096)
        self.assertTrue(all(len(card['terms'])==1 for card in generated))

    def test_generation_requires_complete_translations_but_legacy_cards_still_validate(self):
        sources, raw=self.fixture()
        draft={key:value for key,value in raw['cards'][0].items() if key!='translations'}
        self.assertEqual(updater.validate_one(draft,sources[0],[])['translations'],{})
        with self.assertRaisesRegex(ValueError,'Invalid card translations'):
            updater.validate_one(draft,sources[0],[],require_translations=True)


    def test_translation_feedback_reports_all_bad_fields_without_echoing_prose(self):
        sources, raw=self.fixture();draft=raw['cards'][0]
        draft['translations']['en'].update({'category':'x','question':'short',
            'paragraphs':['A brief first paragraph.','Another brief paragraph.','A brief final paragraph.']})
        with self.assertRaises(updater.TranslationRejected) as raised:
            updater.validate_one(draft,sources[0],[],require_translations=True)
        issues=raised.exception.issues
        self.assertTrue(all(issue['language']=='en' for issue in issues))
        self.assertEqual({issue['field'] for issue in issues},{'category','question','answer','paragraphs[0]'})
        reason=updater.failure_reason(raised.exception)
        self.assertIn('英文譯文 question',reason)
        self.assertIn('長度 5',reason)
        self.assertIn('6–240',reason)
        self.assertIn('首段須保留具名主體',reason)
        self.assertNotIn('brief first',reason)
        self.assertEqual(updater.draft_issue(0,raised.exception,draft,sources[0])['translationIssues'],issues)

    def test_both_invalid_languages_are_reported_and_not_silently_accepted(self):
        sources, raw=self.fixture();raw['cards'][0]['translations']={}
        with self.assertRaises(updater.TranslationRejected) as raised:
            updater.validate_one(raw['cards'][0],sources[0],[],require_translations=True)
        self.assertEqual({issue['language'] for issue in raised.exception.issues},{'zh-Hans','en'})
        self.assertEqual(updater.card_translations(raw['cards'][0]),{})


    def test_translations_share_original_metadata_and_support_english_notes(self):
        sources, raw=self.fixture();draft=raw['cards'][0]
        draft['translations']['en'].update({'id':'fake','actor':'fake','sourceUrl':'https://evil.example/',
            'terms':[{'term':'model','definition':'The computational system discussed in this fictional testing fixture.'}]})
        result=updater.validate_one(draft,sources[0],[],require_translations=True)
        version=result['translations']['en']
        self.assertEqual(version['terms'],draft['translations']['en']['terms'])
        self.assertEqual(len(version['answer'].split('\n\n')),3)
        for field in ['id','actor','sourceUrl','evidence']:
            self.assertNotIn(field,version)
        self.assertEqual(result['actor'],'MIT')
        self.assertEqual(result['sourceUrl'],sources[0]['url'])

    def test_chinese_masquerading_as_english_or_missing_named_actor_is_rejected(self):
        sources, raw=self.fixture()
        for paragraphs in [['AI '+ '中文內容'*30]*3,['A team describes this fictional sample development in plain English.']*3]:
            draft=json.loads(json.dumps(raw['cards'][0]));draft['translations']['en']['paragraphs']=paragraphs
            with self.subTest(paragraphs=paragraphs),self.assertRaisesRegex(ValueError,'Invalid card translations'):
                updater.validate_one(draft,sources[0],[],require_translations=True)


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
                raw['cards'][0]['evidence']=sources[0]['body']
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

    def test_readable_one_two_or_four_paragraph_drafts_are_accepted_without_truncation(self):
        for count in [1,2,4]:
            sources, raw=self.fixture()
            text='MIT 團隊在文章中說明較小架構可能適合資源有限的情境，但效益仍須依實際任務驗證，摘錄未提供所有條件，不能視作已在各種工作中普遍有效。'
            raw['cards'][0]['answer']='\n\n'.join([text]*count)
            raw['cards'][0]['translations']['zh-Hans']['paragraphs']=[text]*count
            with self.subTest(count=count):
                card=updater.validate_one(raw['cards'][0],sources[0],[],require_translations=True)
                self.assertEqual(card['answer'],raw['cards'][0]['answer'])

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
        valid['cards'][0]['question']='MIT 嘗試用更小架構協助處理醫療資料'
        invalid={**valid['cards'][0],'answer':'過長的導讀'*200}
        responses=self.responder(sources,valid,{0:[{'card':invalid},{'card':valid['cards'][0]}]})
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
                self.assertEqual(api.call_count,6)
                self.assertEqual(updater.main(),0)
                self.assertEqual(json.loads(target.read_text())['status'],'already-generated-today')
                self.assertEqual(api.call_count,6)
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

    def test_prompt_upgrade_preserves_used_articles_and_prefers_new_candidates(self):
        sources,raw=self.fixture();cards=updater.validate_cards(raw,sources,[])
        history=[sources[0]['url'],'https://news.mit.edu/2026/older-1001']
        previous={**self.edition(),'promptVersion':'old-protocol','sourceHistory':history}
        with patch.object(updater,'collect_articles',return_value=sources),patch.object(updater,'select_sources',return_value=sources) as select,patch.object(updater,'generate',return_value=cards):
            payload,changed=updater.refresh(previous,datetime(2026,10,11,tzinfo=timezone.utc),'test-key')
        self.assertTrue(changed)
        self.assertEqual(select.call_args.args[1],history)
        self.assertTrue(set(history)<=set(payload['sourceHistory']))

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
