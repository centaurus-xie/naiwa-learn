import {beginDrag,endDrag,lookAt,moveDrag,resetMotion,tapMotion,turnMotion} from './motion.js?v=20261024-2';

// Pointer Events handle mouse, pen, and touch through the same bounded gestures.
export function attachControls({button,resetButton,motion,wake,onAction=()=>{},scheduleReturn=()=>{},clock=()=>performance.now()/1000}) {
  const abort=new AbortController(),options={signal:abort.signal};
  let pointerClickUntil=-Infinity;
  const activate=()=>{onAction(tapMotion(motion));wake();};
  const release=id=>{if(button.hasPointerCapture?.(id)) button.releasePointerCapture(id);};
  const reset=()=>{
    const id=motion.pointer?.id; resetMotion(motion); if(id!==undefined) release(id);
    button.classList.remove('is-dragging'); wake(); onAction('reset');
  };
  button.addEventListener('pointerdown',event=>{
    if(event.isPrimary===false || (event.button!==undefined && event.button!==0)) return;
    if(!beginDrag(motion,event.pointerId,event.clientX,event.clientY,clock(),event.pointerType)) return;
    button.setPointerCapture?.(event.pointerId);
    button.classList.add('is-dragging'); wake();
  },options);
  button.addEventListener('pointermove',event=>{
    const rect=button.getBoundingClientRect();
    if(moveDrag(motion,event.pointerId,event.clientX,event.clientY,rect.width,rect.height,clock())) wake();
    else if(!motion.pointer && event.pointerType!=='touch') {
      lookAt(motion,(event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2); wake();
    }
  },options);
  const finish=(event,cancel)=>{
    const pointer=motion.pointer;
    if(!pointer || pointer.id!==event.pointerId) return;
    const rect=button.getBoundingClientRect();
    const hasPosition=Number.isFinite(event.clientX) && Number.isFinite(event.clientY);
    const inside=!hasPosition || (event.clientX>=rect.left && event.clientX<=rect.left+rect.width
      && event.clientY>=rect.top && event.clientY<=rect.top+rect.height);
    // The final coordinates may arrive only on pointerup. Do not zero inertia for
    // an unchanged position, or depend on a later compatibility click to tap.
    if(!cancel && hasPosition && (event.clientX!==pointer.lastX || event.clientY!==pointer.lastY)) {
      moveDrag(motion,event.pointerId,event.clientX,event.clientY,rect.width,rect.height,clock());
    }
    const result=endDrag(motion,event.pointerId,clock(),cancel);
    pointerClickUntil=clock()+1;
    button.classList.remove('is-dragging'); release(event.pointerId);
    if(result.moved && !cancel) onAction('turn');
    else if(!cancel && inside) activate();
    lookAt(motion,0,0); wake(); scheduleReturn();
  };
  button.addEventListener('pointerup',event=>finish(event,false),options);
  button.addEventListener('pointercancel',event=>finish(event,true),options);
  button.addEventListener('lostpointercapture',event=>finish(event,true),options);
  button.addEventListener('blur',()=>{if(motion.pointer) finish({pointerId:motion.pointer.id},true);},options);
  button.addEventListener('pointerleave',()=>{if(!motion.pointer) {lookAt(motion,0,0);wake();}},options);
  button.addEventListener('click',event=>{
    if(motion.pointer) return;
    // Pointer activation already ran on release. Keep click for keyboard/assistive
    // activation, including browsers that omit pointerType on synthetic clicks.
    if(event.pointerType || event.detail>0 || clock()<=pointerClickUntil) {
      pointerClickUntil=-Infinity;return;
    }
    activate();
  },options);
  button.addEventListener('keydown',event=>{
    if(motion.pointer) return;
    if(event.key==='Enter' || event.key===' ') pointerClickUntil=-Infinity;
    const steps={ArrowLeft:[-.25,0],ArrowRight:[.25,0],ArrowUp:[0,-.08],ArrowDown:[0,.08]};
    if(Object.hasOwn(steps,event.key)) {
      event.preventDefault(); turnMotion(motion,...steps[event.key],clock());
      wake(); scheduleReturn(); onAction('turn');
    } else if(event.key==='Home' || event.key==='Escape') {
      event.preventDefault(); event.stopPropagation(); reset();
    }
    // Native button Enter/Space activation generates the same click handler.
  },options);
  resetButton.addEventListener('click',()=>{reset();button.focus({preventScroll:true});},options);
  return ()=>{
    const id=motion.pointer?.id;abort.abort();resetMotion(motion);
    if(id!==undefined) release(id);
    button.classList.remove('is-dragging');
  };
}
