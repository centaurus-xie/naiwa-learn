import { createSession, advance, dayKey } from './learning.js';

const $ = (id) => document.getElementById(id);
const KEY = 'naiwa-learning-v1';
let state;
let revealed = false;
const today = dayKey();
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
  $('progress').setAttribute('aria-label', `已記住 ${count} 張，共 ${state.total} 張`);
  $('counter').replaceChildren(document.createTextNode(String(Math.min(count + 1, state.total)).padStart(2,'0') + ' '));
  const denominator = document.createElement('span');
  denominator.textContent = `/ ${String(state.total).padStart(2,'0')}`;
  $('counter').append(denominator);
  $('actions').hidden = true;
  $('card').classList.remove('is-revealed', 'entering');
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
    $('session-label').textContent='今天的五張，都記住了';
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
  $('kicker').textContent='一個小問題';
  $('news-context').hidden=!card.newsTitle;
  $('news-title').textContent=card.newsTitle || '';
  $('hint').textContent='不用急著知道答案，好奇就是開始。';
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
  $('kicker').textContent='原來如此';
  $('guide-message').textContent='懂一點點，就很棒了。';
  $('hint').textContent='「再看看」會把這張留到稍後複習。';
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
  let saved;
  try { saved=JSON.parse(localStorage.getItem(KEY)); } catch { /* Invalid or unavailable storage is nonfatal. */ }
  let feed;
  try {
    const response=await fetch('./data/cards.json',{cache:'no-cache'});
    if(!response.ok) throw new Error('feed');
    feed=await response.json();
  } catch {
    if(saved?.day===today && saved.cards?.length) feed={cards:saved.cards};
    else {
      $('question').textContent='小卡暫時沒送到。';
      $('hint').textContent='檢查網路後，重新整理就可以再試一次。';
      $('reveal').hidden=true;
      return;
    }
  }
  try { state=createSession(feed.cards,today,saved); }
  catch { $('question').textContent='小卡正在整理中。'; $('hint').textContent='請稍後重新整理。'; return; }
  save(); render();
  $('feed-status').textContent=feed.fetchedAt
    ? `資訊更新 ${new Intl.DateTimeFormat('zh-Hant',{month:'numeric',day:'numeric'}).format(new Date(feed.fetchedAt))} · 新聞搭配概念卡`
    : 'AI 基礎卡 · 每天一點練習';
}
start();
