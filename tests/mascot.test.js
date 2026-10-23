import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,statSync} from 'node:fs';
import {createMotion,beginDrag,moveDrag,endDrag,lookAt,playMotion,tapMotion,resetMotion,stepMotion,turnMotion} from '../assets/mascot/motion.js';
import {attachControls} from '../assets/mascot/controls.js';
import {applyPose,createNaiwa,disposeNaiwa} from '../assets/mascot/model.js';
import {mountNaiwa} from '../assets/mascot/scene.js';
import {LANGUAGES,t} from '../i18n.js';

function run(state,start,end,reduced=false) {
  let pose;
  for(let time=start;time<end;time+=1/60) pose=stepMotion(state,1/60,time,reduced);
  return pose;
}
class Button extends EventTarget {
  constructor() {
    super();this.classes=new Set();this.captures=new Set();this.focused=false;
    this.classList={add:name=>this.classes.add(name),remove:name=>this.classes.delete(name)};
  }
  getBoundingClientRect(){return {left:0,top:0,width:200,height:240};}
  setPointerCapture(id){this.captures.add(id);}
  hasPointerCapture(id){return this.captures.has(id);}
  releasePointerCapture(id){this.captures.delete(id);}
  focus(){this.focused=true;}
}
function dispatch(button,type,properties={}) {
  const event=new Event(type,{cancelable:true});Object.assign(event,properties);button.dispatchEvent(event);return event;
}
function controls() {
  const motion=createMotion(),button=new Button(),resetButton=new Button(),actions=[];
  let time=0,wakes=0,returns=0;
  const detach=attachControls({button,resetButton,motion,wake:()=>wakes++,onAction:name=>actions.push(name),scheduleReturn:()=>returns++,clock:()=>time});
  return {motion,button,resetButton,actions,detach,setTime:value=>time=value,get wakes(){return wakes;},get returns(){return returns;}};
}

test('Naiwa is a real volumetric mesh with green eyes, a belly and articulated arms',()=>{
  const model=createNaiwa();
  const position=model.body.geometry.getAttribute('position');
  assert.ok(position.count>3000);
  const z=[...Array(position.count)].map((_,i)=>position.getZ(i));
  assert.ok(Math.max(...z)>.65 && Math.min(...z)<-.65);
  assert.ok(model.body.geometry.getAttribute('color').count===position.count);
  assert.equal(model.eyes.length,2);assert.equal(model.arms.length,2);
  assert.ok(model.arms.every(arm=>arm.getObjectByName('Three-fingered hand')));
  let vertices=0;model.root.traverse(object=>{if(object.isMesh){vertices+=object.geometry.getAttribute('position').count;assert.equal(object.material.map,null);}});
  assert.ok(vertices<50000);
  disposeNaiwa(model);
});
test('pose changes the 3D arm, eye and body transforms rather than a CSS image',()=>{
  const model=createNaiwa();
  const motion=createMotion();playMotion(motion,'wave',0);
  const pose=stepMotion(motion,1/60,.65);applyPose(model,pose);
  assert.ok(model.arms[0].rotation.z>1.5);
  assert.ok(Math.abs(model.root.rotation.z)>0);
  playMotion(motion,'hop',1);applyPose(model,stepMotion(motion,1/60,1.4));
  assert.ok(model.root.position.y>.15);
  disposeNaiwa(model);
});
test('shared geometry and materials are disposed only once',()=>{
  const model=createNaiwa(),resources=new Set();
  for(const group of [model.root,model.shadow]) group.traverse(object=>{if(object.geometry)resources.add(object.geometry);if(object.material)resources.add(object.material);});
  const counts=new Map([...resources].map(resource=>[resource,0]));
  for(const resource of resources) resource.addEventListener('dispose',()=>counts.set(resource,counts.get(resource)+1));
  disposeNaiwa(model);
  assert.ok([...counts.values()].every(count=>count===1));
});
test('idle state has no continuous render requirement',()=>{
  const pose=stepMotion(createMotion(),1/60,100);
  assert.equal(pose.active,false);assert.equal(pose.yaw,0);assert.equal(pose.lift,0);
});
test('a full-width drag turns 360 degrees and vertical tilt stays bounded',()=>{
  const state=createMotion();beginDrag(state,7,0,0,0);moveDrag(state,7,200,10000,200,240,.1);
  assert.equal(state.targetYaw,Math.PI*2);assert.equal(state.targetPitch,.3);
  assert.equal(state.pointer.moved,true);
  moveDrag(state,7,0,-10000,200,240,.2);assert.equal(state.targetPitch,-.3);
  moveDrag(state,7,1,1,0,0,.3);assert.ok(Number.isFinite(state.velocity));
});
test('a second finger cannot take over the captured drag',()=>{
  const state=createMotion();assert.equal(beginDrag(state,1,10,10,0),true);
  assert.equal(beginDrag(state,2,10,10,0),false);
  assert.equal(moveDrag(state,2,100,100,200,240,.1),false);
  assert.equal(endDrag(state,2,.2),null);assert.equal(state.pointer.id,1);
});
test('pointer cancellation releases pressure without launching an action or inertia',()=>{
  const state=createMotion();beginDrag(state,1,0,0,0);moveDrag(state,1,80,40,200,240,.1);
  const result=endDrag(state,1,.11,true);
  assert.equal(result.cancelled,true);assert.equal(state.velocity,0);assert.equal(state.targetPress,0);
  assert.equal(state.pointer,null);assert.equal(state.action,null);
});
test('release settles to the nearest front and eventually stops rendering',()=>{
  const state=createMotion();beginDrag(state,1,0,0,0);moveDrag(state,1,80,40,200,240,.1);endDrag(state,1,.11);
  const pose=run(state,.12,12);
  assert.ok(Math.abs(Math.sin(pose.yaw))<.002);assert.ok(Math.cos(pose.yaw)>.99);
  assert.ok(Math.abs(pose.pitch)<.001);assert.equal(pose.active,false);
});
test('tap responses cycle, complete, and do not become an idle animation',()=>{
  const state=createMotion();
  assert.deepEqual([0,1,2,3].map(time=>tapMotion(state,time)),['wave','hop','nod','wave']);
  assert.equal(playMotion(state,'__proto__',4),false);
  assert.equal(run(state,4,8).active,false);
});
test('reduced motion disables playful animation and inertia but allows direct rotation',()=>{
  const state=createMotion();tapMotion(state,0);
  const quiet=stepMotion(state,1/60,.5,true);
  assert.equal(quiet.wave,0);assert.equal(quiet.lift,0);assert.equal(quiet.active,false);
  beginDrag(state,1,0,0,1);moveDrag(state,1,50,0,200,240,1.1);
  assert.equal(stepMotion(state,1/60,1.1,true).yaw,state.targetYaw);
  endDrag(state,1,1.2);run(state,1.21,5,true);assert.equal(state.velocity,0);
});
test('home reset never spins a long way back through multiple revolutions',()=>{
  const state=createMotion();state.yaw=state.targetYaw=Math.PI*8+1;
  turnMotion(state,0,.2,0);lookAt(state,2,-2);resetMotion(state);
  assert.ok(Math.abs(state.targetYaw-state.yaw)<=Math.PI);
  assert.equal(state.targetPitch,0);assert.equal(state.targetLookX,0);
});
test('mouse drag uses pointer capture and suppresses the trailing click',()=>{
  const c=controls();
  dispatch(c.button,'pointerdown',{pointerId:1,clientX:10,clientY:10,button:0,pointerType:'mouse'});
  assert.ok(c.button.captures.has(1));
  c.setTime(.1);dispatch(c.button,'pointermove',{pointerId:1,clientX:80,clientY:20,pointerType:'mouse'});
  dispatch(c.button,'pointerup',{pointerId:1});dispatch(c.button,'click',{detail:1});
  assert.deepEqual(c.actions,['turn']);assert.equal(c.motion.sequence,0);
  assert.equal(c.button.captures.size,0);assert.equal(c.returns,1);c.detach();
});
test('a touch tap responds on release even when Safari does not send a click',()=>{
  const c=controls();
  dispatch(c.button,'pointerdown',{pointerId:4,clientX:40,clientY:50,pointerType:'touch',isPrimary:true,button:0});
  assert.deepEqual(c.actions,[]);
  c.setTime(.1);dispatch(c.button,'pointerup',{pointerId:4,clientX:40,clientY:50});
  assert.deepEqual(c.actions,['wave']);assert.equal(c.motion.action.name,'wave');
  assert.ok(stepMotion(c.motion,1/60,.6).wave>1);c.detach();
});
test('normal finger jitter neither rotates Naiwa nor prevents a tap',()=>{
  const c=controls();
  dispatch(c.button,'pointerdown',{pointerId:4,clientX:40,clientY:50,pointerType:'touch',button:0});
  c.setTime(.05);dispatch(c.button,'pointermove',{pointerId:4,clientX:47,clientY:54,pointerType:'touch'});
  assert.equal(c.motion.targetYaw,0);assert.equal(c.motion.targetPitch,0);assert.equal(c.motion.velocity,0);
  c.setTime(.1);dispatch(c.button,'pointerup',{pointerId:4,clientX:48,clientY:55});
  assert.deepEqual(c.actions,['wave']);assert.equal(c.motion.velocity,0);c.detach();
});
test('touch release and its compatibility click execute only one action',()=>{
  for(const click of [{detail:1,pointerType:'touch'},{detail:1},{detail:0}]) {
    const c=controls();
    dispatch(c.button,'pointerdown',{pointerId:4,clientX:40,clientY:50,pointerType:'touch',button:0});
    c.setTime(.1);dispatch(c.button,'pointerup',{pointerId:4,clientX:40,clientY:50});
    c.setTime(.4);dispatch(c.button,'click',click);
    assert.deepEqual(c.actions,['wave']);assert.equal(c.motion.sequence,1);c.detach();
  }
});
test('keyboard activation immediately after a pointer tap remains available',()=>{
  const c=controls();
  dispatch(c.button,'pointerdown',{pointerId:4,clientX:40,clientY:50,pointerType:'touch',button:0});
  dispatch(c.button,'pointerup',{pointerId:4,clientX:40,clientY:50});
  dispatch(c.button,'keydown',{key:'Enter'});dispatch(c.button,'click',{detail:0});
  assert.deepEqual(c.actions,['wave','hop']);c.detach();
});
test('rapid taps without compatibility clicks still cycle one action per release',()=>{
  const c=controls();
  for(let i=0;i<3;i++) {
    c.setTime(i*.15);
    dispatch(c.button,'pointerdown',{pointerId:i+1,clientX:40,clientY:50,pointerType:'touch',button:0});
    dispatch(c.button,'pointerup',{pointerId:i+1,clientX:40,clientY:50});
  }
  assert.deepEqual(c.actions,['wave','hop','nod']);assert.equal(c.motion.sequence,3);c.detach();
});
test('mouse and pen taps also activate on release without duplicate clicks',()=>{
  for(const pointerType of ['mouse','pen']) {
    const c=controls();
    dispatch(c.button,'pointerdown',{pointerId:1,clientX:40,clientY:50,pointerType,button:0});
    c.setTime(.1);dispatch(c.button,'pointerup',{pointerId:1,clientX:40,clientY:50});
    dispatch(c.button,'click',{pointerType,detail:1});
    assert.deepEqual(c.actions,['wave']);c.detach();
  }
});
test('a touch drag rotates but never triggers a tap action on release',()=>{
  const c=controls();
  dispatch(c.button,'pointerdown',{pointerId:4,clientX:40,clientY:50,pointerType:'touch',button:0});
  c.setTime(.1);dispatch(c.button,'pointermove',{pointerId:4,clientX:90,clientY:65,pointerType:'touch'});
  const velocity=c.motion.velocity;
  c.setTime(.11);dispatch(c.button,'pointerup',{pointerId:4,clientX:90,clientY:65});
  dispatch(c.button,'lostpointercapture',{pointerId:4});dispatch(c.button,'click',{detail:1,pointerType:'touch'});
  assert.ok(c.motion.targetYaw>0);assert.equal(c.motion.velocity,velocity);
  assert.deepEqual(c.actions,['turn']);assert.equal(c.motion.sequence,0);c.detach();
});
test('release coordinates catch a drag even when the last pointermove is missing',()=>{
  const c=controls();
  dispatch(c.button,'pointerdown',{pointerId:4,clientX:40,clientY:50,pointerType:'touch',button:0});
  c.setTime(.1);dispatch(c.button,'pointerup',{pointerId:4,clientX:90,clientY:65});
  assert.deepEqual(c.actions,['turn']);assert.ok(c.motion.targetYaw>0);c.detach();
});
test('lifting just outside the control cancels a tap even within the jitter tolerance',()=>{
  const c=controls();
  dispatch(c.button,'pointerdown',{pointerId:4,clientX:198,clientY:50,pointerType:'touch',button:0});
  c.setTime(.1);dispatch(c.button,'pointerup',{pointerId:4,clientX:201,clientY:50});
  dispatch(c.button,'click',{detail:1});
  assert.deepEqual(c.actions,[]);assert.equal(c.motion.pointer,null);c.detach();
});
test('assistive clicks work without any pointer sequence and after the deduplication window',()=>{
  const c=controls();dispatch(c.button,'click',{detail:0});
  assert.deepEqual(c.actions,['wave']);
  dispatch(c.button,'pointerdown',{pointerId:4,clientX:40,clientY:50,pointerType:'touch',button:0});
  dispatch(c.button,'pointerup',{pointerId:4,clientX:40,clientY:50});
  c.setTime(2);dispatch(c.button,'click',{detail:0});
  assert.deepEqual(c.actions,['wave','hop','nod']);c.detach();
});
test('cancelled touch, lost capture and focus loss never become an accidental tap',()=>{
  for(const type of ['pointercancel','lostpointercapture','blur']) {
    const c=controls();dispatch(c.button,'pointerdown',{pointerId:1,clientX:40,clientY:50,pointerType:'touch',button:0});
    dispatch(c.button,type,{pointerId:1});dispatch(c.button,'click',{detail:1});
    assert.equal(c.motion.pointer,null);assert.equal(c.motion.targetPress,0);
    assert.deepEqual(c.actions,[]);assert.equal(c.button.classes.size,0);c.detach();
  }
});
test('nonprimary touches and nonleft mouse buttons are ignored',()=>{
  const c=controls();
  dispatch(c.button,'pointerdown',{pointerId:2,clientX:0,clientY:0,button:0,isPrimary:false});
  dispatch(c.button,'pointerdown',{pointerId:3,clientX:0,clientY:0,button:2});
  assert.equal(c.motion.pointer,null);assert.equal(c.wakes,0);c.detach();
});
test('keyboard turns and reset prevent page scrolling and return focus to Naiwa',()=>{
  const c=controls();
  const event=dispatch(c.button,'keydown',{key:'ArrowRight'});
  assert.equal(event.defaultPrevented,true);assert.equal(c.motion.targetYaw,.25);
  dispatch(c.button,'keydown',{key:'Home'});assert.equal(c.motion.targetYaw,0);
  dispatch(c.resetButton,'click');assert.equal(c.button.focused,true);
  assert.deepEqual(c.actions,['turn','reset','reset']);c.detach();
});
test('detaching controls removes handlers and releases the gesture state',()=>{
  const c=controls();dispatch(c.button,'pointerdown',{pointerId:1,clientX:40,clientY:50,button:0});
  c.detach();dispatch(c.button,'click',{detail:0});
  assert.deepEqual(c.actions,[]);assert.equal(c.motion.pointer,null);
  assert.equal(c.button.captures.size,0);
});
test('failure to create WebGL leaves the caller a clean static fallback',()=>{
  const previous={matchMedia:globalThis.matchMedia,cancelAnimationFrame:globalThis.cancelAnimationFrame};
  let fallback=0;
  globalThis.matchMedia=()=>({matches:false});globalThis.cancelAnimationFrame=()=>{};
  try {
    const result=mountNaiwa({button:new Button(),resetButton:new Button(),onFallback:()=>fallback++});
    assert.equal(result,null);assert.equal(fallback,1);
  } finally {
    for(const key of Object.keys(previous)) {
      if(previous[key]===undefined) delete globalThis[key];else globalThis[key]=previous[key];
    }
  }
});
test('interactive copy exists in all three languages and engine stays local and bounded',()=>{
  for(const language of LANGUAGES) for(const key of ['mascotControl','mascotReset','mascotHint','mascotLoading','mascotFallback','mascot.wave','mascot.hop','mascot.nod','mascot.turn','mascot.reset']) assert.ok(t(language,key));
  assert.ok(statSync(new URL('../assets/mascot/three.min.js',import.meta.url)).size<650000);
  assert.match(readFileSync(new URL('../assets/mascot/THREE-LICENSE.txt',import.meta.url),'utf8'),/MIT License/);
  const source=readFileSync(new URL('../assets/mascot/scene.js',import.meta.url),'utf8');
  assert.ok(!source.includes('https://'));assert.ok(!source.includes('setInterval'));
  const workflow=readFileSync(new URL('../.github/workflows/pages.yml',import.meta.url),'utf8');
  assert.ok(workflow.includes('cp -R assets _site/'));
});
