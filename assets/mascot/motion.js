const TAU=Math.PI*2;
export const clamp=(value,low,high)=>Math.min(high,Math.max(low,value));
const ease=(dt,speed)=>1-Math.exp(-dt*speed);
const nearestFront=angle=>angle+Math.atan2(-Math.sin(angle),Math.cos(angle));
const DURATIONS={wave:1.35,hop:.85,nod:.85,peek:.8,tilt:.85,settle:1.1};

export function createMotion() {
  return {yaw:0,pitch:0,targetYaw:0,targetPitch:0,velocity:0,lookX:0,lookY:0,
    targetLookX:0,targetLookY:0,press:0,targetPress:0,pointer:null,action:null,sequence:0,returnAt:0};
}
export function beginDrag(state,id,x,y,now,pointerType='mouse') {
  if(state.pointer) return false;
  state.pointer={id,x,y,lastX:x,lastY:y,lastAt:now,yaw:state.targetYaw,pitch:state.targetPitch,
    threshold:pointerType==='touch' ? 12 : 5,moved:false};
  state.velocity=0; state.targetPress=1; state.action=null;
  return true;
}
export function moveDrag(state,id,x,y,width,height,now) {
  const pointer=state.pointer;
  if(!pointer || pointer.id!==id) return false;
  const dx=x-pointer.x,dy=y-pointer.y;
  pointer.moved ||= Math.hypot(dx,dy)>pointer.threshold;
  // Finger jitter is still a tap: do not rotate or add inertia before a drag starts.
  if(pointer.moved) {
    state.targetYaw=pointer.yaw+dx/Math.max(1,width)*TAU;
    state.targetPitch=clamp(pointer.pitch+dy/Math.max(1,height)*.85,-.3,.3);
    state.velocity=clamp((x-pointer.lastX)/Math.max(.008,now-pointer.lastAt)/Math.max(1,width)*TAU,-6,6);
  }
  pointer.lastX=x; pointer.lastY=y; pointer.lastAt=now;
  return true;
}
export function endDrag(state,id,now,cancel=false) {
  if(!state.pointer || state.pointer.id!==id) return null;
  const moved=state.pointer.moved;
  if(cancel || !moved || now-state.pointer.lastAt>.12) state.velocity=0;
  state.pointer=null; state.targetPress=0; state.returnAt=now+2.4;
  return {moved,cancelled:cancel};
}
export function lookAt(state,x,y) {
  state.targetLookX=clamp(x,-1,1); state.targetLookY=clamp(y,-1,1);
}
export function resetMotion(state) {
  state.pointer=null; state.targetPress=0; state.velocity=0;
  state.targetYaw=nearestFront(state.yaw); state.targetPitch=0;
  lookAt(state,0,0); state.action=null; state.returnAt=0;
}
export function turnMotion(state,dx,dy,now) {
  state.targetYaw+=dx; state.targetPitch=clamp(state.targetPitch+dy,-.3,.3);
  state.returnAt=now+2.4;
}
export function playMotion(state,name,now) {
  if(!Object.hasOwn(DURATIONS,name)) return false;
  state.action={name,started:now,duration:DURATIONS[name]};
  return true;
}
export function tapMotion(state,now) {
  const name=['wave','hop','nod'][state.sequence++%3];
  playMotion(state,name,now); return name;
}

export function stepMotion(state,dt,now,reduced=false) {
  dt=clamp(dt,0,.05);
  if(!state.pointer) {
    if(reduced) state.velocity=0;
    state.targetYaw+=state.velocity*dt;
    state.velocity*=Math.exp(-dt*7);
    if(now>=state.returnAt) {
      state.targetYaw=reduced ? nearestFront(state.targetYaw) : state.targetYaw+(nearestFront(state.targetYaw)-state.targetYaw)*ease(dt,3.5);
      state.targetPitch=reduced ? 0 : state.targetPitch*Math.exp(-dt*5);
    }
  }
  for(const [key,target,speed] of [['yaw','targetYaw',16],['pitch','targetPitch',14],['lookX','targetLookX',12],['lookY','targetLookY',12],['press','targetPress',16]]) {
    state[key]=reduced ? state[target] : state[key]+(state[target]-state[key])*ease(dt,speed);
  }
  if(reduced) state.action=null;
  const action=state.action;
  const p=action ? clamp((now-action.started)/action.duration,0,1) : 0;
  const envelope=action && p<1 ? Math.sin(p*Math.PI) : 0;
  const name=action?.name;
  const quiet=reduced ? 0 : 1;
  const wave=name==='wave' ? envelope*(2.05+Math.sin(p*5*Math.PI)*.15)*quiet : 0;
  const jump=name==='hop' || name==='settle' ? envelope*(name==='hop' ? .23 : .1)*quiet : 0;
  const nod=name==='nod' || name==='peek' ? Math.sin(p*TAU)*envelope*.14*quiet : 0;
  const roll=name==='tilt' ? envelope*.14*quiet : wave*.035;
  const blink=(name==='nod' || name==='wave') && p>.38 && p<.53 ? .22 : 1;
  if(action && p>=1) state.action=null;
  return {yaw:state.yaw,pitch:state.pitch+nod,roll:roll-state.lookX*.025*quiet,
    lift:jump,scaleY:1-state.press*.035*quiet-(name==='hop' ? Math.sin(p*TAU)*.045*quiet : 0),
    wave,blink:reduced ? 1 : blink,lookX:state.lookX,lookY:state.lookY,
    active:!!state.action || Math.abs(state.velocity)>.002 || ['yaw','pitch','lookX','lookY','press'].some(key=>Math.abs(state[key]-state['target'+key[0].toUpperCase()+key.slice(1)])>.0005)
      || (!state.pointer && now>=state.returnAt && (Math.abs(Math.sin(state.targetYaw))>.001 || Math.abs(state.targetPitch)>.001))};
}
