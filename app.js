import { createSession, advance, dayKey, validCards, feedInfo, completedCards, startReading, guideMessage, completionMessage, termsForCard, termSegments } from './learning.js?v=20261024-2';
import {LANGUAGE_KEY,languageOf,localeOf,t,translatedCard} from './i18n.js?v=20261024-2';

const $ = (id) => document.getElementById(id);
const KEY = 'naiwa-learning-v1';
let state;
let currentFeed;
let loadError=null;
let language='zh-Hant';
try { language=languageOf(localStorage.getItem(LANGUAGE_KEY)); } catch { /* Preference storage is optional. */ }
const say=(key,values)=>t(language,key,values);
let revealed = false;
let advancing = false;
let activeTermNote = null;
let noteSequence = 0;
let today = dayKey();
let mascot=null,mascotMode='loading',mascotHintKey='mascotLoading',mascotStatusKey=null,mascotHintTimer=0;
const cardTemplate = $('card').innerHTML;
function localizeStatic(root) {
  root.querySelectorAll('[data-i18n]').forEach(element=>element.textContent=say(element.dataset.i18n));
  root.querySelectorAll('[data-i18n-label]').forEach(element=>element.setAttribute('aria-label',say(element.dataset.i18nLabel)));
  root.querySelectorAll('[data-i18n-alt]').forEach(element=>element.alt=say(element.dataset.i18nAlt));
}
function applyLanguage() {
  document.documentElement.lang=language;
  document.title=say('brand')+' · AI Daily';
  document.querySelector('meta[name="description"]').content=say('description');
  localizeStatic(document);
  refreshMascotCopy();
  document.querySelectorAll('[data-language]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.language===language)));
  const date=new Intl.DateTimeFormat(localeOf(language),{timeZone:'Asia/Hong_Kong',month:'long',day:'numeric',weekday:'short'}).format(new Date());
  $('date-label').textContent=`${date} · DAILY DISCOVERY`;
}
function renderPlaceholder() {
  $('question').textContent=say(loadError==='unavailable' ? 'unavailableTitle' : loadError==='invalid' ? 'invalidTitle' : 'preparing');
  $('hint').textContent=say(loadError==='unavailable' ? 'unavailableHint' : loadError==='invalid' ? 'invalidHint' : 'previewHint');
  $('guide-message').textContent=say('hello');
}
document.querySelectorAll('[data-language]').forEach(button=>button.addEventListener('click',()=>{
  const selected=languageOf(button.dataset.language);
  if(selected===language) return;
  language=selected;
  try { localStorage.setItem(LANGUAGE_KEY,language); } catch { $('storage-notice').hidden=false; }
  applyLanguage();
  if(state) render({animate:false}); else renderPlaceholder();
  if(currentFeed) renderFeed(currentFeed);
}));
applyLanguage();
renderPlaceholder();

function refreshMascotCopy() {
  $('mascot-control').setAttribute('aria-label',say(mascotMode==='ready' ? 'mascotControl' : 'mascotAlt'));
  $('mascot-hint').textContent=say(mascotHintKey);
  if(mascotStatusKey) $('mascot-status').textContent=say(mascotStatusKey);
}
function mascotFallback() {
  mascotMode='fallback';mascotHintKey='mascotFallback';mascotStatusKey=null;
  clearTimeout(mascotHintTimer);$('mascot-status').textContent='';
  $('mascot-control').disabled=true;$('mascot-reset').hidden=true;
  $('guide-scene').dataset.renderer='fallback';refreshMascotCopy();
}
function startMascot() {
  import('./assets/mascot/scene.js?v=20261024-2').then(({mountNaiwa})=>{
    mascot=mountNaiwa({button:$('mascot-control'),resetButton:$('mascot-reset'),
      onFallback:mascotFallback,
      onReady(){
        mascotMode='ready';mascotHintKey='mascotHint';
        $('guide-scene').dataset.renderer='ready';$('mascot-control').disabled=false;
        $('mascot-reset').hidden=false;refreshMascotCopy();
      },
      onAction(action){
        mascotStatusKey=mascotHintKey='mascot.'+action;refreshMascotCopy();clearTimeout(mascotHintTimer);
        mascotHintTimer=setTimeout(()=>{mascotHintKey='mascotHint';refreshMascotCopy();},2100);
      }});
  }).catch(mascotFallback);
}
// News and reading controls load first. Failure of the optional 3D module is isolated.
const prepareMascot=()=>{
  if('requestIdleCallback' in window) window.requestIdleCallback(startMascot,{timeout:1500});
  else setTimeout(startMascot,100);
};
if('IntersectionObserver' in window) {
  const observer=new IntersectionObserver(entries=>{if(entries[0].isIntersecting) {observer.disconnect();prepareMascot();}});
  observer.observe($('mascot-control'));
} else prepareMascot();

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); }
  catch { $('storage-notice').hidden = false; }
}
function safeSource(value) {
  try { const u = new URL(value); return u.protocol === 'https:' ? u.href : null; }
  catch { return null; }
}
function closeTermNote(restoreFocus=true) {
  if(!activeTermNote) return;
  const {trigger,panel}=activeTermNote;
  panel.hidden=true;
  trigger.setAttribute('aria-expanded','false');
  activeTermNote=null;
  if(restoreFocus && trigger.isConnected) trigger.focus({preventScroll:true});
}
function annotate(element, text, terms, contentLanguage=language) {
  const segments=termSegments(text,terms);
  element.replaceChildren();
  if(!segments.some(segment=>segment.note)) { element.textContent=text; return; }
  const panel=document.createElement('aside');
  panel.className='term-note'; panel.id=`term-note-${++noteSequence}`;
  panel.lang=contentLanguage;
  panel.hidden=true; panel.tabIndex=-1; panel.setAttribute('role','note');
  panel.setAttribute('aria-labelledby',`${panel.id}-title`);
  element.after(panel);
  for(const segment of segments) {
    if(!segment.note) { element.append(document.createTextNode(segment.text)); continue; }
    const trigger=document.createElement('button');
    trigger.type='button'; trigger.className='term-trigger'; trigger.textContent=segment.text;
    trigger.setAttribute('aria-label',say('termOpen',{term:segment.text}));
    trigger.setAttribute('aria-expanded','false'); trigger.setAttribute('aria-controls',panel.id);
    trigger.addEventListener('click',()=>{
      const same=activeTermNote?.trigger===trigger;
      closeTermNote(false);
      if(same) { trigger.focus({preventScroll:true}); return; }
      const title=document.createElement('strong');
      title.id=`${panel.id}-title`; title.textContent=segment.note.term;
      const copy=document.createElement('p'); copy.textContent=segment.note.definition;
      const close=document.createElement('button');
      close.type='button'; close.className='term-close'; close.textContent='×';
      close.setAttribute('aria-label',say('termClose',{term:segment.note.term}));
      close.addEventListener('click',()=>closeTermNote());
      panel.replaceChildren(title,copy,close); panel.hidden=false;
      trigger.setAttribute('aria-expanded','true'); activeTermNote={trigger,panel};
      panel.focus({preventScroll:true});
      panel.scrollIntoView({block:'nearest',behavior:'auto'});
    });
    element.append(trigger);
  }
}
function renderParagraphs(container, text, terms) {
  container.replaceChildren();
  for(const paragraph of text.split(/\n\s*\n/)) {
    const copy=document.createElement('p'); container.append(copy);
    annotate(copy,paragraph,terms,container.lang || language);
  }
}
document.addEventListener('keydown',event=>{
  // A modal's native cancel event handles Escape without closing the review too.
  if(event.key==='Escape' && activeTermNote && !$('review-dialog').open) {
    event.preventDefault(); closeTermNote();
  }
});
function renderFeed(feed) {
  const info=feedInfo(feed,new Date(),language);
  $('feed-meta').hidden=false;
  $('feed-meta').dataset.tone=info.tone;
  $('feed-status').textContent=info.summary;
  $('feed-detail-label').textContent=info.detailLabel;
  $('feed-detail-text').textContent=info.details;
}
function updateGuide(phase='preview',reaction=null) {
  const card=state.cards.find(c=>c.id===state.queue[0]);
  const message=state.queue.length ? guideMessage(card,phase,language) : completionMessage(completedCards(state),language);
  if($('guide-message').textContent!==message) $('guide-message').textContent=message;
  if(reaction) mascot?.react(reaction);
}
function render({animate=true}={}) {
  closeTermNote(false);
  $('card').querySelectorAll('.term-note').forEach(panel=>panel.remove());
  revealed = false;
  document.body.classList.remove('has-reading-actions');
  const count = state.completed.length;
  $('review-entry').hidden=count===0;
  $('review-open').textContent=say('reviewCount',{count})+' ↗';
  $('progress').replaceChildren(...Array.from({length:state.total}, (_, i) => {
    const dot = document.createElement('span');
    dot.className = i < count ? 'done' : i === count ? 'active' : '';
    return dot;
  }));
  $('progress').setAttribute('aria-label',say('progress',{count,total:state.total}));
  $('counter').replaceChildren(document.createTextNode(String(Math.min(count + 1, state.total)).padStart(2,'0') + ' '));
  const denominator = document.createElement('span');
  denominator.textContent = `/ ${String(state.total).padStart(2,'0')}`;
  $('counter').append(denominator);
  $('actions').hidden = true;
  if (!$('question')) {
    $('card').innerHTML = cardTemplate;
    $('reveal').addEventListener('click', revealCard);
    localizeStatic($('card'));
  }
  $('session-label').textContent=say('session');
  $('card').classList.remove('is-revealed', 'entering', 'complete');
  void $('card').offsetWidth;
  if(animate) $('card').classList.add('entering');
  if (!state.queue.length) {
    $('card').classList.add('complete');
    $('card').replaceChildren();
    const spark = document.createElement('span'); spark.className='card-spark'; spark.textContent='✳'; spark.setAttribute('aria-hidden','true');
    const heading = document.createElement('h2'); heading.textContent=say('doneTitle'); heading.tabIndex=-1;
    const copy = document.createElement('p'); copy.textContent=say('doneCopy'); copy.style.whiteSpace='pre-line';
    $('card').append(spark, heading, copy);
    updateGuide();
    $('session-label').textContent=say('doneSession');
    $('hint').textContent=say('doneHint');
    return;
  }
  const display=translatedCard(state.cards.find(c=>c.id===state.queue[0]),language);
  const card=display.card;
  $('category').textContent=card.category;
  const terms=termsForCard(card,display.language);
  annotate($('question'),card.question,terms,display.language);
  ['category','question','answer-text'].forEach(id=>$(id).lang=display.language);
  $('translation-notice').hidden=!display.fallback;
  $('translation-notice').textContent=say('translationMissing');
  $('attribution').hidden=!card.actor;
  $('attribution').textContent=card.actor ? say('attribution',{actor:card.actor}) : '';
  renderParagraphs($('answer-text'),card.answer,terms);
  $('answer').hidden=true;
  $('source').hidden=true;
  $('reveal').hidden=false;
  $('reveal').disabled=false;
  $('kicker').textContent=say('previewKicker');
  $('news-context').hidden=!card.newsTitle;
  $('news-title').textContent=card.newsTitle || '';
  $('hint').textContent=say('previewHint');
  const url=safeSource(card.sourceUrl);
  if(url) $('source').href=url; else $('source').removeAttribute('href');
  $('source').textContent=`${card.sourceName || say('source')}${card.publishedAt ? ' · '+card.publishedAt.slice(0,10) : ''} ↗`;
  if(state.readingStarted) revealCard({focus:false});
  else updateGuide();
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
  $('kicker').textContent=say('readingKicker');
  updateGuide('reading',focus ? 'peek' : null);
  $('hint').textContent=say('readingHint');
  if(focus) $('question').focus({preventScroll:true});
}
$('reveal').addEventListener('click', revealCard);
$('card').addEventListener('click', (event) => {
  if (!event.target.closest('a, button, .term-note')) revealCard();
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
  updateGuide('reading',state.queue.length ? (remembered ? 'nod' : 'tilt') : 'settle');
  if(!remembered) $('hint').textContent=say('laterHint');
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
  closeTermNote(false);
  $('review-title').textContent=say('reviewCount',{count:state.completed.length});
  $('review-list').replaceChildren(...completedCards(state).map((original,index)=>{
    const display=translatedCard(original,language), card=display.card;
    const item=document.createElement('details');
    item.className='review-item'; item.open=index===0;
    const title=document.createElement('summary'); title.textContent=card.question; title.lang=display.language;
    const meta=document.createElement('p'); meta.className='attribution';
    meta.textContent=[card.category,card.actor || card.sourceName].filter(Boolean).join(' · ');
    const terms=termsForCard(card,display.language);
    const copy=document.createElement('div'); copy.className='review-copy'; copy.lang=display.language;
    item.append(title,meta,copy);
    if(display.fallback) {
      const notice=document.createElement('p'); notice.className='translation-notice'; notice.textContent=say('translationMissing'); meta.after(notice);
    }
    renderParagraphs(copy,card.answer,terms);
    // Keep interactive buttons out of the native summary toggle.
    const titleOnly=terms.filter(note=>!termSegments(card.answer,[note]).some(segment=>segment.note));
    if(titleOnly.length) {
      const labels=document.createElement('p'); labels.className='review-terms';
      copy.before(labels); annotate(labels,say('titleTerms')+titleOnly.map(note=>note.term).join(' · '),titleOnly,display.language);
    }
    item.addEventListener('toggle',()=>{
      if(!item.open && activeTermNote && item.contains(activeTermNote.trigger)) closeTermNote(false);
    });
    const url=safeSource(card.sourceUrl);
    if(url) {
      const source=document.createElement('a'); source.className='source'; source.href=url;
      source.target='_blank'; source.rel='noopener noreferrer';
      source.textContent=`${card.sourceName || say('source')}${card.publishedAt ? ' · '+card.publishedAt.slice(0,10) : ''} ↗`;
      item.append(source);
    }
    return item;
  }));
  $('review-dialog').showModal();
}
$('review-open').addEventListener('click',openReview);
$('review-close').addEventListener('click',()=>{ closeTermNote(false); $('review-dialog').close(); });
$('review-dialog').addEventListener('cancel',event=>{
  if(activeTermNote) { event.preventDefault(); closeTermNote(); }
});
$('review-dialog').addEventListener('close',()=>closeTermNote(false));

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
      loadError='unavailable'; renderPlaceholder();
      $('reveal').hidden=true;
      currentFeed={offline:true}; renderFeed(currentFeed);
      return;
    }
  } finally {
    clearTimeout(timer);
  }
  try { state=createSession(feed.cards,today,saved,feed.editionId || null); }
  catch { loadError='invalid'; renderPlaceholder(); return; }
  currentFeed=feed;
  save(); render();
  renderFeed(feed);
}
start();
