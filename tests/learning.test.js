import test from 'node:test';
import assert from 'node:assert/strict';
import {createSession,advance} from '../learning.js';
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
test('midday feed changes cannot replace the current session',()=>{
  const s=advance(createSession(cards,'2026-10-11'),true);
  assert.deepEqual(createSession([{...cards[0],id:'new'}],'2026-10-11',s),s);
});
test('corrupt storage resets safely',()=>{
  const s=createSession(cards,'2026-10-11');
  s.queue=['bad'];
  assert.equal(createSession(cards,'2026-10-11',s).queue.length,5);
});
