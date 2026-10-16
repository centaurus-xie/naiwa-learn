export function dayKey(date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Hong_Kong',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
}

export function validCards(cards) {
  return Array.isArray(cards) && cards.length===5 && new Set(cards.map(c=>c?.id)).size===5
    && cards.every(c=>c && ['id','question','answer','category'].every(k=>typeof c[k]==='string' && c[k].trim() && c[k].length<=2000)
      && ['sourceUrl','sourceName','publishedAt','newsTitle','evidence','actor'].every(k=>c[k]===undefined || typeof c[k]==='string'));
}

export function feedStatus(feed) {
  if(feed.offline) return '暫時無法取得新卡，繼續本機保存的卡片';
  const format=(value)=>{
    if(typeof value!=='string') return null;
    const date=new Date(value);
    return Number.isNaN(date.getTime()) ? null : new Intl.DateTimeFormat('zh-Hant',{timeZone:'Asia/Hong_Kong',hourCycle:'h23',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(date);
  };
  const published=format(feed.generatedAt), checked=format(feed.checkedAt);
  let label=published ? `新卡發布 ${published} · AI 整理，請參照原文` : '基礎概念卡 · 尚未生成 AI 新卡';
  if(checked) label+=` ｜ 檢查 ${checked}`;
  if(published || checked) label+=' · 香港時間（UTC+8）';
  const states={
    'no-new-articles':'暫無新文章',
    'already-generated-today':'今日卡片已備妥',
    'update-failed':'更新未成功，保留原卡',
    'content-retained':'本次更新未完成，顯示的是先前版本',
    'generation-failed':'新卡生成失敗，請查看更新原因',
    'selection-unavailable':'可讀來源或題材不足，尚未發布新卡'
  };
  if(typeof feed.status==='string' && Object.hasOwn(states,feed.status)) label+=' · '+states[feed.status];
  if(feed.status==='generation-failed' && Number.isInteger(feed.generationAttempts) && feed.generationAttempts>0) label+=`（已嘗試 ${feed.generationAttempts} 次）`;
  if(['generation-failed','selection-unavailable','update-failed'].includes(feed.status) && typeof feed.updateReason==='string') label+=' · '+feed.updateReason.slice(0,260);
  return label;
}

export function createSession(cards, day, saved, editionId = null) {
  if(!validCards(cards)) throw new Error('Expected five complete, unique cards');
  // Legacy data without an edition ID still changes when its card content changes.
  const version=typeof editionId==='string' && editionId ? editionId : JSON.stringify(cards.map(c=>[c.id,c.question,c.answer]));
  if(saved?.day===day && saved.editionId===version && validCards(saved.cards)
    && saved.cards.every((c,i)=>c.id===cards[i].id && c.question===cards[i].question && c.answer===cards[i].answer)
    && Array.isArray(saved.queue) && Array.isArray(saved.completed) && saved.total===5
    && new Set([...saved.queue,...saved.completed]).size===5
    && saved.queue.length+saved.completed.length===5
    && [...saved.queue,...saved.completed].every(id=>cards.some(c=>c.id===id))) {
    return {...saved,readingStarted:saved.readingStarted===true || saved.completed.length>0};
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
