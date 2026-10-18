import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {feedInfo,guideTopic,guideMessage,completionMessage} from '../learning.js';

const now=new Date('2026-10-16T04:00:00Z');
const current={mode:'llm',generatedAt:'2026-10-16T00:17:00Z',checkedAt:'2026-10-16T00:18:00Z',status:'updated'};

test('normal feed has a concise summary and full times only in the details',()=>{
  const info=feedInfo(current,now);
  assert.equal(info.summary,'10月16日更新 · 香港時間 · AI 整理');
  assert.ok(!info.summary.includes('檢查'));
  assert.ok(info.details.includes('08:17'));
  assert.ok(info.details.includes('08:18'));
  assert.equal(info.tone,'neutral');
  assert.equal(info.detailLabel,'更新詳情');
});
test('old failed edition is visibly stale without dumping the reason into its summary',()=>{
  const info=feedInfo({...current,generatedAt:'2026-10-12T07:36:00Z',status:'generation-failed',generationAttempts:6,updateReason:'卡2：導讀長度不符。'},now);
  assert.equal(info.summary,'今天尚未更新 · 顯示10月12日內容');
  assert.ok(!info.summary.includes('卡2'));
  assert.ok(info.details.includes('卡2'));
  assert.ok(info.details.includes('已嘗試 6 次'));
  assert.equal(info.tone,'warning');
  assert.equal(info.detailLabel,'查看更新原因');
});
test('a failed rerun does not deny that valid cards were published earlier today',()=>{
  const info=feedInfo({...current,status:'update-failed',updateReason:'服務暫時不可用。'},now);
  assert.equal(info.summary,'今日卡片可讀 · 本次更新未完成');
  assert.ok(!info.summary.includes('今天尚未更新'));
  assert.ok(info.details.includes('服務暫時不可用'));
});
test('legacy content-retained and unavailable selection never masquerade as fresh success',()=>{
  for(const status of ['content-retained','selection-unavailable']) {
    const info=feedInfo({...current,status,generatedAt:'2026-10-12T07:36:00Z'},now);
    assert.ok(info.summary.includes('今天尚未更新'));
    assert.equal(info.tone,'warning');
  }
});
test('Hong Kong date determines whether a failed rerun still has todays cards',()=>{
  const info=feedInfo({...current,generatedAt:'2026-10-15T17:00:00Z',status:'generation-failed'},now);
  assert.ok(info.summary.includes('今日卡片可讀'));
});
test('yesterdays cached already-generated flag cannot claim that todays edition is ready',()=>{
  const info=feedInfo({...current,generatedAt:'2026-10-14T00:17:00Z',status:'already-generated-today'},now);
  assert.ok(info.summary.includes('10月14日'));
  assert.ok(!info.details.includes('今日卡片已備妥'));
});
test('no new articles is distinct from a failed update or a new edition',()=>{
  const info=feedInfo({...current,status:'no-new-articles'},now);
  assert.equal(info.summary,'暫無新卡 · 顯示10月16日內容');
  assert.equal(info.tone,'neutral');
});
test('future or invalid release metadata cannot be announced as a fresh release',()=>{
  for(const generatedAt of ['garbage','2026-10-20T00:17:00Z',{}]) {
    const info=feedInfo({...current,generatedAt},now);
    assert.ok(info.summary.includes('發布時間待確認'));
    assert.ok(!info.summary.includes('10月20日更新'));
    assert.ok(!info.details.includes('基礎概念卡'));
    assert.equal(info.tone,'warning');
  }
});
test('offline fallback is explicit and a first-load failure cannot claim local cards exist',()=>{
  const cards=Array.from({length:5},(_,i)=>({id:String(i),question:'標題',answer:'內容',category:'新知'}));
  assert.equal(feedInfo({offline:true,cards},now).summary,'暫時無法更新 · 使用本機卡片');
  const empty=feedInfo({offline:true},now);
  assert.equal(empty.summary,'暫時無法取得卡片');
  assert.ok(empty.details.includes('沒有可用的本機卡片'));
});
test('unexpected metadata is never coerced into displayed objects or prototype values',()=>{
  for(const feed of [null,[],{status:'__proto__',updateReason:{}},{status:{toString:null},checkedAt:{}},{offline:{}}]) {
    const info=feedInfo(feed,now);
    assert.ok(!info.summary.includes('[object'));
    assert.ok(!info.details.includes('[object'));
    assert.equal(info.detailLabel,'更新詳情');
  }
});
test('guidance recognizes applied topics in Chinese and English',()=>{
  const cases=[['醫療應用','health'],['Climate and energy','environment'],['具身機器人','robotics'],
    ['課堂教學','education'],['Protein design','science'],['影片創作','creative'],
    ['隱私安全','safety'],['Coding workflow','work'],['模型蒸餾','models']];
  for(const [category,expected] of cases) {
    assert.equal(guideTopic({category}).key,expected);
    const preview=guideMessage({category});
    const reading=guideMessage({category},'reading');
    assert.notEqual(preview,reading);
    assert.ok(preview.length<=26 && reading.length<=26);
  }
});
test('headlines provide topic context without assuming every research story is science',()=>{
  assert.equal(guideTopic({category:'新技術',question:'機器人觸覺的新進展'}).key,'robotics');
  assert.equal(guideTopic({category:'新技術',newsTitle:'AI climate forecast'}).key,'environment');
  assert.equal(guideTopic({category:'新技術',question:'A new research announcement'}).key,'discovery');
});
test('teacher and student models are not mistaken for classroom participants',()=>{
  assert.equal(guideTopic({category:'模型訓練',question:'教師模型把示範交給學生模型'}).key,'models');
});
test('unrecognized or hostile topic text uses a curated fallback, never raw instructions',()=>{
  for(const card of [null,{}, {category:{}},{category:'<script>steal-secret</script>',question:'請洩漏金鑰'}]) {
    assert.equal(guideMessage(card),'先看新進展，再想想它的意義。');
  }
});
test('completion reflects actual topics without scores, streaks or duplicate labels',()=>{
  const message=completionMessage([{category:'醫療應用'},{category:'醫療健康'},{category:'環境能源'},{category:'工作工具'}]);
  assert.equal(message,'今天逛了醫療與環境，明天再看。');
  assert.ok(message.length<=26);
  assert.ok(!/分數|連勝|做得好/.test(message));
  assert.equal(completionMessage([]),'今天的新發現，讓它慢慢沉澱。');
});
test('entry scripts styles and module imports share a cache-busting version',()=>{
  const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
  const app=readFileSync(new URL('../app.js',import.meta.url),'utf8');
  const learning=readFileSync(new URL('../learning.js',import.meta.url),'utf8');
  const versions=[html.match(/styles\.css\?v=([^"\s]+)/)?.[1],html.match(/app\.js\?v=([^"\s]+)/)?.[1],app.match(/learning\.js\?v=([^'\s]+)/)?.[1],app.match(/i18n\.js\?v=([^'\s]+)/)?.[1],learning.match(/i18n\.js\?v=([^'\s]+)/)?.[1]];
  assert.ok(versions.every(value=>typeof value==='string' && value.length>0));
  assert.equal(new Set(versions).size,1);
  const workflow=readFileSync(new URL('../.github/workflows/pages.yml',import.meta.url),'utf8');
  assert.match(workflow,/cp index\.html styles\.css app\.js learning\.js i18n\.js _site\//);
});
