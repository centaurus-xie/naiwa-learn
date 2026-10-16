import { createSession, advance, dayKey, validCards, feedStatus, completedCards, startReading } from './learning.js';

const $ = (id) => document.getElementById(id);
const KEY = 'naiwa-learning-v1';
let state;
let revealed = false;
let advancing = false;
let today = dayKey();
const cardTemplate = $('card').innerHTML;
const date = new Intl.DateTimeFormat('zh-Hant', {timeZone:'Asia/Hong_Kong',month:'long', day:'numeric', weekday:'short'}).format(new Date());
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
  document.body.classList.remove('has-reading-actions');
  const count = state.completed.length;
  $('review-entry').hidden=count===0;
  $('review-open').textContent=`今日已讀 · ${count} ↗`;
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
    const heading = document.createElement('h2'); heading.textContent='今天完成了。'; heading.tabIndex=-1;
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
  $('attribution').hidden=!card.actor;
  $('attribution').textContent=card.actor ? `本篇提及 · ${card.actor}` : '';
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
  if(state.readingStarted) revealCard({focus:false});
}
function revealCard({focus=true}={}) {
  if(revealed || !state?.queue.length) return;
  if(!state.readingStarted) { state=startReading(state); save(); }
  revealed=true;
  $('answer').hidden=false;
  $('source').hidden=!$('source').hasAttribute('href');
  $('reveal').hidden=true;
  $('actions').hidden=false;
  document.body.classList.add('has-reading-actions');
  $('card').classList.add('is-revealed');
  $('kicker').textContent='進展、意義與觀察';
  $('guide-message').textContent='這件事，可能和你想的有點不一樣。';
  $('hint').textContent='感興趣可以讀原文，或留到稍後再看。';
  if(focus) $('question').focus({preventScroll:true});
}
$('reveal').addEventListener('click', revealCard);
$('card').addEventListener('click', (event) => {
  if (!event.target.closest('a, button')) revealCard();
});
function respond(remembered) {
  if(!revealed || advancing) return;
  // Continuous reading keeps the next button in place. Ignore a double tap
  // while the replacement card arrives, so it cannot mark two cards read.
  advancing=true;
  $('again').disabled=true;
  $('remember').disabled=true;
  setTimeout(()=>{
    advancing=false;
    $('again').disabled=false;
    $('remember').disabled=false;
  },280);
  state=advance(state, remembered); save(); render();
  if(state.queue.length) {
    $('guide-message').textContent=remembered ? '收下這個新發現，再來一張。' : '沒關係，我們等一下再見一次。';
  }
  // Read the next heading rather than focusing a hidden reveal button. Bring
  // the new card back into view after advancing from the end of a long card.
  $('card').querySelector('h2').focus({preventScroll:true});
  const anchor=$('session-heading');
  const top=anchor.getBoundingClientRect().top;
  if(top<16 || top>window.innerHeight/2) anchor.scrollIntoView({block:'start',behavior:'auto'});
}
$('again').addEventListener('click',()=>respond(false));
$('remember').addEventListener('click',()=>respond(true));

function openReview() {
  if(!state?.completed.length) return;
  $('review-title').textContent=`今日已讀 · ${state.completed.length}`;
  $('review-list').replaceChildren(...completedCards(state).map((card,index)=>{
    const item=document.createElement('details');
    item.className='review-item'; item.open=index===0;
    const title=document.createElement('summary'); title.textContent=card.question;
    const meta=document.createElement('p'); meta.className='attribution';
    meta.textContent=[card.category,card.actor || card.sourceName].filter(Boolean).join(' · ');
    const copy=document.createElement('p'); copy.className='review-copy'; copy.textContent=card.answer;
    item.append(title,meta,copy);
    const url=safeSource(card.sourceUrl);
    if(url) {
      const source=document.createElement('a'); source.className='source'; source.href=url;
      source.target='_blank'; source.rel='noopener noreferrer';
      source.textContent=`${card.sourceName || '閱讀原文'}${card.publishedAt ? ' · '+card.publishedAt.slice(0,10) : ''} ↗`;
      item.append(source);
    }
    return item;
  }));
  $('review-dialog').showModal();
}
$('review-open').addEventListener('click',openReview);
$('review-close').addEventListener('click',()=>$('review-dialog').close());

async function start() {
  today = dayKey();
  let saved;
  try { saved=JSON.parse(localStorage.getItem(KEY)); } catch { /* Invalid or unavailable storage is nonfatal. */ }
  let feed;
  let timer;
  const controller=new AbortController();
  try {
    timer=setTimeout(()=>controller.abort(),15000);
    const response=await fetch('./data/cards.json',{cache:'no-cache',signal:controller.signal});
    if(!response.ok) throw new Error('feed');
    feed=await response.json();
    if(!feed || !validCards(feed.cards)) throw new Error('invalid-feed');
  } catch {
    if(validCards(saved?.cards)) feed={cards:saved.cards,editionId:saved.editionId,offline:true};
    else {
      $('question').textContent='小卡暫時沒送到。';
      $('hint').textContent='檢查網路後，重新整理就可以再試一次。';
      $('reveal').hidden=true;
      return;
    }
  } finally {
    clearTimeout(timer);
  }
  try { state=createSession(feed.cards,today,saved,feed.editionId || null); }
  catch { $('question').textContent='小卡正在整理中。'; $('hint').textContent='請稍後重新整理。'; return; }
  save(); render();
  $('feed-status').textContent=feedStatus(feed);
}
start();
