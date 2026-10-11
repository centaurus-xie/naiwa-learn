import { createSession, advance, dayKey } from './learning.js';

const $ = (id) => document.getElementById(id);
const KEY = 'naiwa-learning-v1';
let state;
let revealed = false;
let today = dayKey();
const cardTemplate = $('card').innerHTML;
const date = new Intl.DateTimeFormat('zh-Hant', {month:'long', day:'numeric', weekday:'short'}).format(new Date());
$('date-label').textContent = `${date} · DAILY DISCOVERY`;

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); }
  catch { $('storage-notice').hidden = false; }
}
function safeSource(value) {
  try { const u = new URL(value); return u.protocol === 'https:' ? u.href : null; }
  catch { return null; }
}
function render() {
  revealed = false;
  const count = state.completed.length;
  $('progress').replaceChildren(...Array.from({length:state.total}, (_, i) => {
    const dot = document.createElement('span');
    dot.className = i < count ? 'done' : i === count ? 'active' : '';
    return dot;
  }));
  $('progress').setAttribute('aria-label', `已讀 ${count} 張，共 ${state.total} 張`);
  $('counter').replaceChildren(document.createTextNode(String(Math.min(count + 1, state.total)).padStart(2,'0') + ' '));
  const denominator = document.createElement('span');
  denominator.textContent = `/ ${String(state.total).padStart(2,'0')}`;
  $('counter').append(denominator);
  $('actions').hidden = true;
  if (!$('question')) {
    $('card').innerHTML = cardTemplate;
    $('reveal').addEventListener('click', revealCard);
  }
  $('session-label').textContent='今天的小發現';
  $('card').classList.remove('is-revealed', 'entering', 'complete');
  void $('card').offsetWidth;
  $('card').classList.add('entering');
  if (!state.queue.length) {
    $('card').classList.add('complete');
    $('card').replaceChildren();
    const spark = document.createElement('span'); spark.className='card-spark'; spark.textContent='✳'; spark.setAttribute('aria-hidden','true');
    const heading = document.createElement('h2'); heading.textContent='今天完成了。';
    const copy = document.createElement('p'); copy.textContent='又多懂了一點點。\n好奇心，我們明天繼續。'; copy.style.whiteSpace='pre-line';
    $('card').append(spark, heading, copy);
    $('guide-message').textContent='做得好！明天我還在這裡。';
    $('session-label').textContent='今天的五個發現，都看過了';
    $('hint').textContent='休息一下，讓新知慢慢發芽。';
    return;
  }
  const card = state.cards.find(c => c.id === state.queue[0]);
  $('category').textContent=card.category;
  $('question').textContent=card.question;
  $('answer-text').textContent=card.answer;
  $('answer').hidden=true;
  $('source').hidden=true;
  $('reveal').hidden=false;
  $('reveal').disabled=false;
  $('kicker').textContent='值得關注的新進展';
  $('news-context').hidden=!card.newsTitle;
  $('news-title').textContent=card.newsTitle || '';
  $('hint').textContent='看看發生了什麼，再想想它意味著什麼。';
  const url=safeSource(card.sourceUrl);
  if(url) $('source').href=url; else $('source').removeAttribute('href');
  $('source').textContent=`${card.sourceName || '閱讀來源'}${card.publishedAt ? ' · '+card.publishedAt.slice(0,10) : ''} ↗`;
}
function revealCard() {
  if(revealed || !state?.queue.length) return;
  revealed=true;
  $('answer').hidden=false;
  $('source').hidden=!$('source').hasAttribute('href');
  $('reveal').hidden=true;
  $('actions').hidden=false;
  $('card').classList.add('is-revealed');
  $('kicker').textContent='進展、意義與觀察';
  $('guide-message').textContent='這件事，可能和你想的有點不一樣。';
  $('hint').textContent='感興趣可以讀原文，或留到稍後再看。';
  $('remember').focus({preventScroll:true});
}
$('reveal').addEventListener('click', revealCard);
$('card').addEventListener('click', (event) => {
  if (!event.target.closest('a, button')) revealCard();
});
function respond(remembered) {
  if(!revealed) return;
  state=advance(state, remembered); save(); render();
  if(state.queue.length) {
    $('guide-message').textContent=remembered ? '收下這個新發現，再來一張。' : '沒關係，我們等一下再見一次。';
    $('reveal').focus({preventScroll:true});
  }
}
$('again').addEventListener('click',()=>respond(false));
$('remember').addEventListener('click',()=>respond(true));

async function start() {
  today = dayKey();
  let saved;
  try { saved=JSON.parse(localStorage.getItem(KEY)); } catch { /* Invalid or unavailable storage is nonfatal. */ }
  let feed;
  try {
    const response=await fetch('./data/cards.json',{cache:'no-cache'});
    if(!response.ok) throw new Error('feed');
    feed=await response.json();
  } catch {
    if(saved?.day===today && saved.cards?.length) feed={cards:saved.cards,editionId:saved.editionId,offline:true};
    else {
      $('question').textContent='小卡暫時沒送到。';
      $('hint').textContent='檢查網路後，重新整理就可以再試一次。';
      $('reveal').hidden=true;
      return;
    }
  }
  try { state=createSession(feed.cards,today,saved,feed.editionId || null); }
  catch { $('question').textContent='小卡正在整理中。'; $('hint').textContent='請稍後重新整理。'; return; }
  save(); render();
  const format=(value)=>new Intl.DateTimeFormat('zh-Hant',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(value));
  let label=feed.generatedAt ? `新卡發布 ${format(feed.generatedAt)} · AI 整理，請參照原文`
    : '基礎概念卡 · 尚未生成 AI 新卡';
  if(feed.checkedAt) label+=` ｜ 檢查 ${format(feed.checkedAt)}`;
  if(feed.status==='no-new-articles') label+=' · 暫無新文章';
  if(feed.status==='already-generated-today') label+=' · 今日卡片已備妥';
  if(feed.status==='update-failed') label+=' · 更新未成功，保留原卡';
  if(feed.status==='content-retained') label+=' · 新內容仍在整理，沿用上一版';
  if(feed.offline) label='目前離線，繼續本機保存的卡片';
  $('feed-status').textContent=label;
}
start();
