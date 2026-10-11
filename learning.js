export function dayKey(date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
}
export function createSession(cards, day, saved, editionId = null) {
  const valid=Array.isArray(cards) ? cards.filter(c=>c && ['id','question','answer','category'].every(k=>typeof c[k]==='string' && c[k].trim())) : [];
  if(!valid.length) throw new Error('No valid cards');
  if(saved?.day===day && (saved.editionId || null)===editionId && Array.isArray(saved.cards) && Array.isArray(saved.queue) && Array.isArray(saved.completed)
    && saved.total===saved.cards.length && saved.total>0 && saved.total<=5
    && saved.cards.every(c=>c && ['id','question','answer','category'].every(k=>typeof c[k]==='string' && c[k].trim()))
    && new Set([...saved.queue,...saved.completed]).size===saved.total
    && saved.queue.length+saved.completed.length===saved.total
    && [...saved.queue,...saved.completed].every(id=>saved.cards.some(c=>c.id===id))) return saved;
  const unique=[...new Map(valid.map(c=>[c.id,c])).values()].slice(0,5);
  return {day,editionId,cards:unique,queue:unique.map(c=>c.id),completed:[],total:unique.length};
}
export function advance(state,remembered) {
  if(!state.queue.length) return state;
  const [id,...remaining]=state.queue;
  return {...state,queue:remembered?remaining:[...remaining,id],completed:remembered?[...state.completed,id]:state.completed};
}
