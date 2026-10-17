import test from 'node:test';
import assert from 'node:assert/strict';
import {termsForCard,termSegments,validCards,createSession,advance} from '../learning.js';

const definition='這是本機測試用的術語說明，不代表真實新聞。';
const note=term=>({term,definition});
const sample={question:'術語甲與 VLA 的本機介面預覽',answer:'教師模型與模型；術語甲在這裡再次出現。'};
const cards=Array.from({length:5},(_,i)=>({...sample,id:String(i),category:'介面測試',terms:[note('術語甲')]}));

test('legacy cards and malformed optional notes stay readable',()=>{
  for(const terms of [undefined,null,42,{},'terms',[null,{},42]]) {
    const feed=cards.map(card=>({...card,terms}));
    assert.ok(validCards(feed));
    assert.deepEqual(termsForCard(feed[0]),[]);
    assert.equal(createSession(feed,'2026-10-17').queue.length,5);
  }
});
test('notes are normalized, bounded, deduplicated, and tied to visible text',()=>{
  const terms=[null,note('不在正文'),{term:'VLA',definition:'太短'},note('<script>'),
    {term:'術語甲',definition:'請看 https://example.com/說明'},
    {term:' 術語甲 ',definition:' '+definition+'\n'},note('VLA'),note('vla'),note('教師模型'),note('模型')];
  assert.deepEqual(termsForCard({...sample,terms}),[note('術語甲'),note('VLA'),note('教師模型')]);
  assert.deepEqual(termsForCard({...sample,terms:[{term:'術語甲',definition:'中'.repeat(121)}]}),[]);
  assert.deepEqual(termsForCard({...sample,terms:[{term:'VLA',definition:'English definitions are not accepted.'}]}),[]);
});
test('ASCII terms match whole words but can touch Chinese characters',()=>{
  const text='chair AI ai模型 NVLA VLA的用途 VLA2 _VLA';
  const segments=termSegments(text,[note('AI'),note('VLA')]);
  assert.deepEqual(segments.filter(s=>s.note).map(s=>s.text),['AI','ai','VLA']);
  assert.equal(segments.map(s=>s.text).join(''),text);
  assert.deepEqual(termsForCard({question:'chair NVLA',terms:[note('AI'),note('VLA')]}),[]);
});
test('longest overlapping term wins, with every repeated occurrence annotated',()=>{
  const text='教師模型參考模型，再更新教師模型。';
  const segments=termSegments(text,[note('模型'),note('教師模型')]);
  assert.deepEqual(segments.filter(s=>s.note).map(s=>s.note.term),['教師模型','模型','教師模型']);
  assert.equal(segments.map(s=>s.text).join(''),text);
});
test('regex punctuation is literal and does not alter plain text',()=>{
  const text='C++ 與 a(b) 不是 C 或 ab，<b>保留為文字</b>。';
  const segments=termSegments(text,[note('C++'),note('a(b)')]);
  assert.deepEqual(segments.filter(s=>s.note).map(s=>s.text),['C++','a(b)']);
  assert.equal(segments.map(s=>s.text).join(''),text);
  assert.deepEqual(termSegments('',[]),[{text:''}]);
  assert.deepEqual(termSegments('沒有術語',[note('VLA')]),[{text:'沒有術語'}]);
});
test('annotations participate in fallback edition signatures',()=>{
  const saved=advance(createSession(cards,'2026-10-17'),true);
  const changed=cards.map(card=>({...card,terms:[{term:'術語甲',definition:definition+'補充內容。'}]}));
  const next=createSession(changed,'2026-10-17',saved);
  assert.notEqual(next.editionId,saved.editionId);
  assert.deepEqual(next.completed,[]);
});
test('tampered local notes cannot override online notes under the same edition ID',()=>{
  const saved=advance(createSession(cards,'2026-10-17',null,'edition'),true);
  saved.cards=JSON.parse(JSON.stringify(saved.cards));
  saved.cards[0].terms[0].definition+='本機改動。';
  const next=createSession(cards,'2026-10-17',saved,'edition');
  assert.deepEqual(next.completed,[]);
  assert.deepEqual(next.cards[0].terms,[note('術語甲')]);
});
test('unchanged annotations preserve reading progress and use current feed metadata',()=>{
  const saved=advance(createSession(cards,'2026-10-17',null,'edition'),true);
  const fresh=cards.map(card=>({...card,sourceName:'新版來源顯示名'}));
  const next=createSession(fresh,'2026-10-17',saved,'edition');
  assert.deepEqual(next.completed,['0']);
  assert.equal(next.cards[0].sourceName,'新版來源顯示名');
});
