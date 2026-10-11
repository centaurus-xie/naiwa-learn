export function dayKey(date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
}

export function validCards(cards) {
  return Array.isArray(cards) && cards.length===5 && new Set(cards.map(c=>c?.id)).size===5
    && cards.every(c=>c && ['id','question','answer','category'].every(k=>typeof c[k]==='string' && c[k].trim() && c[k].length<=2000)
      && ['sourceUrl','sourceName','publishedAt','newsTitle','evidence'].every(k=>c[k]===undefined || typeof c[k]==='string'));
}

export function feedStatus(feed) {
  if(feed.offline) return '暫時無法取得新卡，繼續本機保存的卡片';
  const format=(value)=>{
    if(typeof value!=='string') return null;
    const date=new Date(value);
    return Number.isNaN(date.getTime()) ? null : new Intl.DateTimeFormat('zh-Hant',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(date);
  };
  const published=format(feed.generatedAt), checked=format(feed.checkedAt);
  let label=published ? `新卡發布 ${published} · AI 整理，請參照原文` : '基礎概念卡 · 尚未生成 AI 新卡';
  if(checked) label+=` ｜ 檢查 ${checked}`;
  const states={
    'no-new-articles':'暫無新文章',
    'already-generated-today':'今日卡片已備妥',
    'update-failed':'更新未成功，保留原卡',
    'content-retained':'本次新卡未通過校驗，沿用上一版'
  };
  if(typeof feed.status==='string' && Object.hasOwn(states,feed.status)) label+=' · '+states[feed.status];
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
    && [...saved.queue,...saved.completed].every(id=>cards.some(c=>c.id===id))) return saved;
  return {day,editionId:version,cards,queue:cards.map(c=>c.id),completed:[],total:5};
}
export function advance(state,remembered) {
  if(!state.queue.length) return state;
  const [id,...remaining]=state.queue;
  return {...state,queue:remembered?remaining:[...remaining,id],completed:remembered?[...state.completed,id]:state.completed};
}
