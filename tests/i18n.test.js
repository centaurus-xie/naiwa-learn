import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {LANGUAGES,languageOf,t,translatedCard} from '../i18n.js';
import {createSession,advance,termsForCard,termSegments,feedInfo,feedStatus,guideMessage,completionMessage} from '../learning.js';

const english={category:'Test preview',question:'A local preview of Sample term',answer:'Sample term appears in this fictional interface preview. These words test language switching and do not report a real discovery.',terms:[{term:'Sample term',definition:'A fictional phrase used to test the English note, not a real technical definition.'}]};
const simplified={category:'测试预览',question:'用来检查术语甲的本机界面预览',answer:'术语甲用于本机界面预览。这些文字不是真实新闻，不报告新的发现，也不提供事实建议。',terms:[{term:'术语甲',definition:'这个虚构的词语只用来检查简体中文注释。'}]};
const card={id:'one',category:'測試預覽',question:'用來檢查術語甲的本機介面預覽',answer:'術語甲用於本機介面預覽。這些文字不是真實新聞。',actor:'原文機構',sourceUrl:'https://example.com/original',translations:{en:english,'zh-Hans':simplified}};

test('only the three supported language preferences are accepted',()=>{
  for(const language of LANGUAGES) assert.equal(languageOf(language),language);
  for(const language of [null,undefined,{},[],42,'__proto__','toString','en-US','zh']) assert.equal(languageOf(language),'zh-Hant');
});
test('every static interface binding has curated copy in all three languages',()=>{
  const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
  const keys=[...html.matchAll(/data-i18n(?:-label|-alt)?="([^"]+)"/g)].map(match=>match[1]);
  for(const language of LANGUAGES) for(const key of keys) {
    assert.ok(t(language,key).length>0,language+' '+key);
    assert.ok(!/[{}]/.test(t(language,key)));
  }
  assert.equal(t('en','brand'),'Naiwa Daily');
  assert.equal(t('zh-Hans','brand'),'奶蛙小课堂');
  assert.equal((html.match(/data-language=/g)||[]).length,3);
  assert.match(html,/>繁<\/button>[\s\S]*>简<\/button>[\s\S]*>En<\/button>/);
});
test('copy interpolation never coerces objects or prototype keys',()=>{
  assert.equal(t('en','reviewCount',{count:2}),'Read today · 2');
  assert.equal(t('en','reviewCount',{count:{toString(){throw new Error('must not run');}}}),'Read today · ');
  assert.throws(()=>t('en','__proto__'));
});
test('localized prose cannot override canonical identity attribution or source links',()=>{
  const input={...card,translations:{en:{...english,id:'evil',actor:'fake',sourceUrl:'https://evil.example/',evidence:'fake'}}};
  const result=translatedCard(input,'en');
  assert.equal(result.fallback,false);
  assert.equal(result.language,'en');
  assert.equal(result.card.question,english.question);
  assert.equal(result.card.id,card.id);
  assert.equal(result.card.actor,card.actor);
  assert.equal(result.card.sourceUrl,card.sourceUrl);
  assert.equal(result.card.evidence,undefined);
});
test('missing damaged or fake-English editions explicitly fall back as a whole',()=>{
  for(const translations of [null,{}, {en:null},{en:{...english,answer:42}},{en:{...english,question:''}},
    {en:{...english,answer:'AI '+ '中文內容'.repeat(40)}},Object.create({en:english})]) {
    const original={...card,translations};
    const result=translatedCard(original,'en');
    assert.equal(result.card,original);
    assert.equal(result.language,'zh-Hant');
    assert.equal(result.fallback,true);
  }
  assert.equal(translatedCard(card,'zh-Hant').fallback,false);
});
test('switching all three languages never mutates progress queue IDs or stored source cards',()=>{
  const cards=Array.from({length:5},(_,i)=>({...card,id:String(i)}));
  const state=advance(createSession(cards,'2026-10-18',null,'edition'),true);
  const snapshot=JSON.stringify(state);
  for(const language of ['en','zh-Hans','zh-Hant']) {
    for(const original of state.cards) assert.equal(translatedCard(original,language).card.id,original.id);
    assert.equal(JSON.stringify(state),snapshot);
  }
  assert.deepEqual(createSession(cards,'2026-10-18',state,'edition').completed,['0']);
});
test('fresh localized prose replaces stale saved translations without resetting progress',()=>{
  const cards=Array.from({length:5},(_,i)=>({...card,id:String(i)}));
  const state=advance(createSession(cards,'2026-10-18',null,'edition'),true);
  const fresh=cards.map(original=>({...original,translations:{en:{...english,question:'A corrected English headline for this preview'}}}));
  const restored=createSession(fresh,'2026-10-18',state,'edition');
  assert.deepEqual(restored.completed,['0']);
  assert.equal(translatedCard(restored.cards[0],'en').card.question,'A corrected English headline for this preview');
});
test('English and simplified term notes match their own visible prose',()=>{
  for(const language of ['en','zh-Hans']) {
    const display=translatedCard(card,language);
    const notes=termsForCard(display.card,display.language);
    assert.equal(notes.length,1);
    assert.ok(termSegments(display.card.answer,notes).some(segment=>segment.note));
  }
  assert.deepEqual(termsForCard({...english,terms:[{term:'Sample term',definition:'A'.repeat(281)}]},'en'),[]);
  assert.equal(termsForCard({...english,terms:[{term:'Sample term',definition:'A'.repeat(200)}]},'en').length,1);
});
test('all bundled starter cards have complete simplified and English editions',()=>{
  const feed=JSON.parse(readFileSync(new URL('../data/cards.json',import.meta.url),'utf8'));
  for(const original of feed.cards) for(const language of LANGUAGES) assert.equal(translatedCard(original,language).fallback,false);
});
test('feed times remain Hong Kong time regardless of selected language',()=>{
  const feed={mode:'llm',status:'updated',generatedAt:'2026-10-18T00:17:00Z',checkedAt:'2026-10-18T00:18:00Z'};
  assert.ok(feedStatus(feed,'en').includes('08:17'));
  assert.ok(feedStatus(feed,'en').includes('Hong Kong time (UTC+8)'));
  assert.ok(feedStatus(feed,'zh-Hans').includes('新卡发布'));
  for(const language of LANGUAGES) {
    const info=feedInfo({...feed,status:'generation-failed',generatedAt:'2026-10-12T00:17:00Z'},new Date('2026-10-18T01:00:00Z'),language);
    assert.equal(info.tone,'warning');
    assert.ok(!info.summary.includes('today’s cards are ready'));
  }
  assert.match(feedInfo({offline:true},new Date(),'en').details,/no saved cards/);
});
test('Naiwa guidance and completion follow the selected language',()=>{
  assert.match(guideMessage({category:'醫療'},'preview','en'),/healthcare/);
  assert.match(guideMessage({category:'醫療'},'preview','zh-Hans'),/医疗/);
  assert.equal(guideMessage({},'reading','en'),'Let’s see why this matters.');
  assert.equal(completionMessage([{category:'醫療'},{category:'環境'}],'en'),'Today: health + climate. More tomorrow.');
});
