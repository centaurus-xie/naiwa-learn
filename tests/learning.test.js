import test from 'node:test';
import assert from 'node:assert/strict';
import {createSession,advance,validCards,feedStatus,completedCards} from '../learning.js';
const cards=Array.from({length:5},(_,i)=>({id:String(i),question:'Q',answer:'A',category:'AI'}));
test('review returns card to end without awarding progress',()=>{
  const s=advance(createSession(cards,'2026-10-11'),false);
  assert.deepEqual(s.queue,['1','2','3','4','0']);
  assert.equal(s.completed.length,0);
});
test('five remembered cards complete the session and survive reload',()=>{
  let s=createSession(cards,'2026-10-11');
  for(let i=0;i<5;i++) s=advance(s,true);
  assert.equal(s.queue.length,0);
  assert.equal(s.completed.length,5);
  assert.deepEqual(createSession(cards,'2026-10-11',JSON.parse(JSON.stringify(s))),s);
  assert.equal(createSession(cards,'2026-10-12',s).queue.length,5);
});
test('a new edition replaces stale same-day cards',()=>{
  const s=advance(createSession(cards,'2026-10-11',null,'old'),true);
  const fresh=createSession(cards.map(c=>({...c,id:'new-'+c.id})),'2026-10-11',s,'new');
  assert.deepEqual(fresh.queue,['new-0','new-1','new-2','new-3','new-4']);
  assert.deepEqual(fresh.completed,[]);
});
test('checking the same edition preserves progress',()=>{
  const s=advance(createSession(cards,'2026-10-11',null,'same'),true);
  assert.deepEqual(createSession(cards,'2026-10-11',s,'same'),s);
});
test('corrupt storage resets safely',()=>{
  const s=createSession(cards,'2026-10-11');
  s.queue=['bad'];
  assert.equal(createSession(cards,'2026-10-11',s).queue.length,5);
});
test('corrupt saved card content cannot replace a valid online edition',()=>{
  const s=createSession(cards,'2026-10-11',null,'edition');
  s.cards=cards.map(c=>({...c}));
  s.cards[0].answer='wrong saved content';
  assert.equal(createSession(cards,'2026-10-11',s,'edition').cards[0].answer,'A');
});
test('legacy editions without metadata still refresh when content changes',()=>{
  const s=advance(createSession(cards,'2026-10-11'),true);
  const fresh=createSession(cards.map(c=>({...c,answer:'new answer'})),'2026-10-11',s);
  assert.equal(fresh.completed.length,0);
  assert.equal(fresh.cards[0].answer,'new answer');
});
test('reject damaged feeds rather than silently showing fewer cards',()=>{
  for(const damaged of [null,[],cards.slice(0,4),[...cards.slice(0,4),null],cards.map(c=>({...c,id:'duplicate'})),cards.map(c=>({...c,publishedAt:42}))]){
    assert.equal(validCards(damaged),false);
    assert.throws(()=>createSession(damaged,'2026-10-11'));
  }
});
test('bad timestamps never interrupt reading or claim a new release',()=>{
  const status=feedStatus({generatedAt:'garbage',checkedAt:{},status:'content-retained'});
  assert.ok(!status.includes('新卡發布'));
  assert.ok(status.includes('沿用上一版'));
});
test('fallback status and successful publication are distinct',()=>{
  assert.ok(feedStatus({offline:true,generatedAt:'2026-10-11T00:00:00Z'}).includes('本機保存'));
  assert.ok(feedStatus({generatedAt:'2026-10-11T00:00:00Z',checkedAt:'2026-10-11T01:00:00Z'}).includes('新卡發布'));
  assert.ok(feedStatus({status:'update-failed'}).includes('更新未成功'));
});
test('unexpected status metadata cannot crash the page or expose prototype values',()=>{
  for(const status of [{toString:null},[],42,'__proto__','toString']) {
    assert.equal(feedStatus({status}),'基礎概念卡 · 尚未生成 AI 新卡');
  }
});
test('read history follows completion order and never changes progress',()=>{
  let state=createSession(cards,'2026-10-12');
  state=advance(state,false);
  state=advance(state,true);
  state=advance(state,true);
  const before=JSON.stringify(state);
  assert.deepEqual(completedCards(state).map(c=>c.id),['1','2']);
  assert.equal(JSON.stringify(state),before);
});
test('all five completed cards remain available to reread after reload',()=>{
  let state=createSession(cards,'2026-10-12');
  for(let i=0;i<5;i++) state=advance(state,true);
  state=createSession(cards,'2026-10-12',JSON.parse(JSON.stringify(state)));
  assert.equal(completedCards(state).length,5);
  assert.equal(state.queue.length,0);
  assert.deepEqual(completedCards(createSession(cards,'2026-10-13',state)),[]);
});
