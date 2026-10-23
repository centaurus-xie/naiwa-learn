import {ACESFilmicToneMapping,DirectionalLight,HemisphereLight,OrthographicCamera,Scene,WebGLRenderer} from './three.min.js?v=0.186.1';
import {applyPose,createNaiwa,disposeNaiwa} from './model.js?v=20261023-2';
import {createMotion,playMotion,resetMotion,stepMotion} from './motion.js?v=20261023-2';
import {attachControls} from './controls.js?v=20261023-2';

export function mountNaiwa({button,resetButton,onReady=()=>{},onFallback=()=>{},onAction=()=>{}}) {
  let renderer,model,resizeObserver,visibilityObserver,detach=()=>{};
  const motion=createMotion(),reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const abort=new AbortController();
  let frame=0,returnTimer=0,last=0,visible=true,disposed=false;
  const now=()=>performance.now()/1000;
  const scene=new Scene();
  const camera=new OrthographicCamera(-2,2,3.6,-.3,.1,30);
  camera.position.set(0,2.25,7); camera.lookAt(0,1.66,0);
  const stop=()=>{cancelAnimationFrame(frame);frame=0;last=0;};
  function draw(stamp) {
    frame=0;
    if(disposed || !visible || document.hidden) return;
    const seconds=stamp/1000,dt=last ? seconds-last : 1/60; last=seconds;
    const pose=stepMotion(motion,dt,seconds,reduced.matches);
    applyPose(model,pose); renderer.render(scene,camera);
    if(pose.active) frame=requestAnimationFrame(draw); else last=0;
  }
  function wake() {
    if(!disposed && visible && !document.hidden && !frame) frame=requestAnimationFrame(draw);
  }
  function scheduleReturn() {
    clearTimeout(returnTimer);
    returnTimer=setTimeout(wake,2450);
  }
  function resize() {
    if(disposed) return;
    const rect=button.getBoundingClientRect(),width=Math.max(1,rect.width),height=Math.max(1,rect.height);
    const half=1.95,aspect=width/height;
    camera.left=-half*aspect;camera.right=half*aspect;camera.top=half;camera.bottom=-half;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1,2));
    renderer.setSize(width,height,false); wake();
  }
  function dispose() {
    if(disposed) return;
    disposed=true; stop(); clearTimeout(returnTimer); abort.abort(); detach();
    resizeObserver?.disconnect();visibilityObserver?.disconnect();
    if(model) disposeNaiwa(model);
    renderer?.dispose();renderer?.domElement.remove();
  }
  function fallback() {dispose();onFallback();}
  try {
    renderer=new WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});
    renderer.setClearColor(0x000000,0);renderer.toneMapping=ACESFilmicToneMapping;renderer.toneMappingExposure=1;
    renderer.domElement.setAttribute('aria-hidden','true');renderer.domElement.className='mascot-canvas';
    model=createNaiwa();scene.add(model.root,model.shadow);
    scene.add(new HemisphereLight(0xfffbeb,0xb4b698,1.8));
    const key=new DirectionalLight(0xfff2cf,2.4);key.position.set(-3,5,5);scene.add(key);
    const fill=new DirectionalLight(0xe8f2ff,.8);fill.position.set(4,3,2);scene.add(fill);
    button.append(renderer.domElement);
    resize();
    // First render must succeed before hiding the reference image.
    applyPose(model,stepMotion(motion,0,now(),reduced.matches));renderer.render(scene,camera);
    renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();fallback();},{signal:abort.signal});
    resizeObserver=new ResizeObserver(resize);resizeObserver.observe(button);
    visibilityObserver=new IntersectionObserver(entries=>{
      visible=entries[0].isIntersecting;
      if(visible) wake(); else stop();
    });visibilityObserver.observe(button);
    document.addEventListener('visibilitychange',()=>{if(document.hidden) stop();else wake();},{signal:abort.signal});
    window.addEventListener('pagehide',event=>{stop();if(!event.persisted) dispose();},{signal:abort.signal});
    window.addEventListener('pageshow',wake,{signal:abort.signal});
    reduced.addEventListener('change',()=>{resetMotion(motion);wake();},{signal:abort.signal});
    detach=attachControls({button,resetButton,motion,wake,onAction,scheduleReturn,clock:now});
    onReady();
    return {react(name){if(!disposed && !reduced.matches && !motion.pointer) {playMotion(motion,name,now());wake();}},dispose};
  } catch {
    fallback();return null;
  }
}
