import {languageOf,localeOf,t} from './i18n.js?v=20261024-1';

export function dayKey(date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Hong_Kong',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
}

export function validCards(cards) {
  return Array.isArray(cards) && cards.length===5 && new Set(cards.map(c=>c?.id)).size===5
    && cards.every(c=>c && ['id','question','answer','category'].every(k=>typeof c[k]==='string' && c[k].trim() && c[k].length<=2000)
      && ['sourceUrl','sourceName','publishedAt','newsTitle','evidence','actor'].every(k=>c[k]===undefined || typeof c[k]==='string'));
}

function termPattern(term) {
  const escaped=term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  // An acronym must not turn part of an unrelated English word into a link.
  return `${/^[a-z0-9_]/i.test(term) ? '(?<![a-z0-9_])' : ''}${escaped}${/[a-z0-9_]$/i.test(term) ? '(?![a-z0-9_])' : ''}`;
}

export function termsForCard(card,language='zh-Hant') {
  if(!Array.isArray(card?.terms)) return [];
  const text=[card.question,card.answer].filter(value=>typeof value==='string').join('\n');
  const notes=[], seen=new Set();
  for(const entry of card.terms.slice(0,12)) {
    if(typeof entry?.term!=='string' || typeof entry?.definition!=='string') continue;
    const term=entry.term.replace(/\s+/g,' ').trim(), definition=entry.definition.replace(/\s+/g,' ').trim();
    const english=languageOf(language)==='en';
    if(term.length<2 || term.length>(english ? 80 : 40) || definition.length<12 || definition.length>(english ? 280 : 120)
      || !(english ? /[a-z]/i : /[\u4e00-\u9fff]/u).test(definition) || /[<>]|https?:\/\/|www\./i.test(term+' '+definition)
      || seen.has(term.toLowerCase()) || !new RegExp(termPattern(term),'iu').test(text)) continue;
    notes.push({term,definition}); seen.add(term.toLowerCase());
    if(notes.length===3) break;
  }
  return notes;
}

export function termSegments(text, terms=[]) {
  if(!terms.length) return [{text}];
  // Match literal text only, with longer terms taking precedence over overlaps.
  const sorted=[...terms].sort((a,b)=>b.term.length-a.term.length);
  const pattern=new RegExp(sorted.map(note=>`(${termPattern(note.term)})`).join('|'),'giu');
  const segments=[]; let end=0;
  for(const match of text.matchAll(pattern)) {
    if(match.index>end) segments.push({text:text.slice(end,match.index)});
    segments.push({text:match[0],note:sorted[match.slice(1).findIndex(value=>value!==undefined)]});
    end=match.index+match[0].length;
  }
  if(end<text.length) segments.push({text:text.slice(end)});
  return segments.length ? segments : [{text}];
}

export function feedStatus(feed,language='zh-Hant') {
  const say=(key,values)=>t(language,key,values);
  if(feed.offline===true) return say('feedOffline');
  const format=(value)=>{
    if(typeof value!=='string') return null;
    const date=new Date(value);
    return Number.isNaN(date.getTime()) ? null : new Intl.DateTimeFormat(localeOf(language),{timeZone:'Asia/Hong_Kong',hourCycle:'h23',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(date);
  };
  const published=format(feed.generatedAt), checked=format(feed.checkedAt);
  let label=published ? say('feedPublished',{date:published}) : say(feed.mode==='llm' ? 'feedUnknown' : 'feedSeed');
  if(checked) label+=' ｜ '+say('checked',{date:checked});
  if(published || checked) label+=' · '+say('timezone');
  if(['no-new-articles','already-generated-today','update-failed','content-retained','generation-failed','selection-unavailable'].includes(feed.status)) label+=' · '+say('status.'+feed.status);
  if(feed.status==='generation-failed' && Number.isInteger(feed.generationAttempts) && feed.generationAttempts>0) label+=say('attempts',{count:feed.generationAttempts});
  if(['generation-failed','selection-unavailable','update-failed'].includes(feed.status) && typeof feed.updateReason==='string') label+=' · '+say('diagnostic',{reason:feed.updateReason.slice(0,260)});
  return label;
}

export function feedInfo(feed, now = new Date(), language='zh-Hant') {
  const say=(key,values)=>t(language,key,values);
  const data=feed && typeof feed==='object' && !Array.isArray(feed) ? feed : {};
  const offline=data.offline===true;
  const date=typeof data.generatedAt==='string' ? new Date(data.generatedAt) : null;
  const future=date && date.getTime()>now.getTime()+300000;
  const published=date && !Number.isNaN(date.getTime()) && !future ? date : null;
  const today=published && dayKey(published)===dayKey(now);
  const stamp=published ? new Intl.DateTimeFormat(localeOf(language),{timeZone:'Asia/Hong_Kong',month:'long',day:'numeric'}).format(published) : null;
  const failed=['update-failed','content-retained','generation-failed','selection-unavailable'].includes(data.status);
  const unknownDate=data.mode==='llm' && !published;
  let summary=stamp ? say('updated',{date:stamp}) : say('seedSummary');
  let details=feedStatus(data,language);
  if(data.status==='already-generated-today' && !today) details=feedStatus({...data,status:'updated'},language);
  if(future) {
    summary=say('unknownSummary');
    details=say('futureDetails')+(typeof data.updateReason==='string' ? ' '+say('diagnostic',{reason:data.updateReason.slice(0,260)}) : '');
  } else if(data.mode==='llm' && !published) summary=say('unknownSummary');
  if(data.status==='no-new-articles') summary=stamp ? say('noNew',{date:stamp}) : say('noNewSeed');
  if(failed) summary=today ? say('failedToday') : stamp ? say('failedOld',{date:stamp}) : say('failedNoDate');
  if(offline) {
    const cached=validCards(data.cards);
    summary=say(cached ? 'offlineCached' : 'offlineEmpty');
    if(!cached) details=say('offlineDetails');
  }
  return {summary,details,tone:failed || offline || future || unknownDate ? 'warning' : 'neutral',
    detailLabel:say(failed || offline || future || unknownDate ? 'updateReason' : 'updateDetails')};
}

// Curated questions guide attention, never invent facts about the article.
const GUIDE_TOPICS = [
  {key:'health',label:'醫療',match:/醫療|医疗|健康|診斷|诊断|臨床|临床|病理|藥物|药物|health|medic|clinic|diagnos|drug/i,
    preview:'AI 在醫療裡，能幫上什麼忙？',reading:'看看用途，也留意醫療上的限制。'},
  {key:'environment',label:'環境',match:/環境|环境|氣候|气候|能源|天氣|天气|電網|电网|climate|weather|energy|environment|geospatial/i,
    preview:'看看 AI 與環境的新連結。',reading:'留意 AI 怎麼理解環境變化。'},
  {key:'robotics',label:'機器人',match:/機器人|机器人|具身|交通|物流|駕駛|驾驶|robot|embodied|driving|transit|logistics/i,
    preview:'這次看 AI 怎麼走進真實世界。',reading:'看看它怎麼感知、怎麼行動。'},
  {key:'education',label:'教學',match:/教育|教學|教学|課堂|课堂|輔導|辅导|education|classroom|tutor/i,
    preview:'AI 能怎麼幫助教與學？',reading:'留意誰在學，以及 AI 幫了哪一步。'},
  {key:'science',label:'科學',match:/科學|科学|科研|蛋白|分子|材料|物理|化學|化学|protein|molecul|material|physics|chemistry|scientific/i,
    preview:'一起看看 AI 怎麼協助科學探索。',reading:'分清楚新發現，和仍待驗證的推測。'},
  {key:'creative',label:'創作',match:/創作|创作|創意|创意|設計|设计|影像|影片|視頻|视频|音樂|音乐|3D|design|creative|video|music|image generation/i,
    preview:'看看 AI 帶來哪些創作新方法。',reading:'留意創作者多了什麼選擇。'},
  {key:'safety',label:'安全',match:/安全|隱私|隐私|風險|风险|詐騙|诈骗|security|safety|privacy|fraud/i,
    preview:'這次多留意，AI 的風險與界線。',reading:'看看它保護了什麼，又有哪些限制。'},
  {key:'work',label:'工作',match:/工作|辦公|办公|工具|程式|代碼|代码|編程|编程|助手|無障礙|无障碍|workflow|coding|software|workplace|accessib/i,
    preview:'這個進展，能用在哪些工作裡？',reading:'看看它改變了工作中的哪一步。'},
  {key:'models',label:'模型',match:/模型|訓練|训练|推論|推理|蒸餾|蒸馏|智能體|智能体|model|training|inference|distill|agent|LLM/i,
    preview:'先別管術語，看看它改變了什麼。',reading:'先抓住關鍵機制，再看實際取捨。'},
];
const DEFAULT_GUIDE={key:'discovery',label:'新知',preview:'先看新進展，再想想它的意義。',reading:'看看它為什麼值得關注。'};

export function guideTopic(card) {
  const text=['category','question','newsTitle'].map(key=>typeof card?.[key]==='string' ? card[key].slice(0,2000) : '').join(' ');
  return GUIDE_TOPICS.find(topic=>topic.match.test(text)) || DEFAULT_GUIDE;
}

export function guideMessage(card, phase='preview', language='zh-Hant') {
  const topic=guideTopic(card);
  return t(language,`guide.${topic.key}.${phase==='reading' ? 'reading' : 'preview'}`);
}

export function completionMessage(cards,language='zh-Hant') {
  const topics=[...new Set(cards.map(card=>guideTopic(card).key).filter(key=>key!=='discovery'))];
  return topics.length>=2 ? t(language,'completion',{first:t(language,'topic.'+topics[0]),second:t(language,'topic.'+topics[1])}) : t(language,'completionDefault');
}

export function createSession(cards, day, saved, editionId = null) {
  if(!validCards(cards)) throw new Error('Expected five complete, unique cards');
  // Legacy data without an edition ID still changes when its card content changes.
  const version=typeof editionId==='string' && editionId ? editionId : JSON.stringify(cards.map(c=>[c.id,c.question,c.answer,termsForCard(c)]));
  if(saved?.day===day && saved.editionId===version && validCards(saved.cards)
    && saved.cards.every((c,i)=>c.id===cards[i].id && c.question===cards[i].question && c.answer===cards[i].answer
      && JSON.stringify(termsForCard(c))===JSON.stringify(termsForCard(cards[i])))
    && Array.isArray(saved.queue) && Array.isArray(saved.completed) && saved.total===5
    && new Set([...saved.queue,...saved.completed]).size===5
    && saved.queue.length+saved.completed.length===5
    && [...saved.queue,...saved.completed].every(id=>cards.some(c=>c.id===id))) {
    return {...saved,cards,readingStarted:saved.readingStarted===true || saved.completed.length>0};
  }
  return {day,editionId:version,cards,queue:cards.map(c=>c.id),completed:[],total:5,readingStarted:false};
}

export function startReading(state) {
  return state.queue.length ? {...state,readingStarted:true} : state;
}
export function advance(state,remembered) {
  if(!state.queue.length) return state;
  const [id,...remaining]=state.queue;
  return {...state,readingStarted:true,queue:remembered?remaining:[...remaining,id],completed:remembered?[...state.completed,id]:state.completed};
}

export function completedCards(state) {
  return state.completed.map(id=>state.cards.find(card=>card.id===id)).filter(Boolean);
}
