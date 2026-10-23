import {BufferAttribute,CatmullRomCurve3,Color,Group,LatheGeometry,Mesh,
  MeshStandardMaterial,SphereGeometry,TubeGeometry,Vector2,Vector3} from './three.min.js?v=0.186.1';

// A code-built interpretation of the supplied character, not its original mesh.
// All surfaces, eyes, fingers, and limbs have actual depth; no image billboard.
export function createNaiwa() {
  const root=new Group(); root.name='Naiwa';
  const sphereGeometry=new SphereGeometry(1,32,24);
  const skin=new MeshStandardMaterial({color:'#f4cf51',roughness:.72});
  const green=new MeshStandardMaterial({color:'#8caf78',roughness:.58});
  const pupilMaterial=new MeshStandardMaterial({color:'#111b12',roughness:.38});
  const hands=new MeshStandardMaterial({color:'#786d45',roughness:.8});
  const mouthMaterial=new MeshStandardMaterial({color:'#69552e',roughness:.9});
  const shine=new MeshStandardMaterial({color:'#fff8d9',roughness:.3});
  function sphere(parent,name,material,position,scale) {
    const mesh=new Mesh(sphereGeometry,material); mesh.name=name;
    mesh.position.set(...position); mesh.scale.set(...scale); parent.add(mesh); return mesh;
  }
  function tube(parent,name,points,radius,material=skin) {
    const curve=new CatmullRomCurve3(points.map(point=>new Vector3(...point)));
    const mesh=new Mesh(new TubeGeometry(curve,40,radius,12,false),material);
    mesh.name=name; parent.add(mesh); return mesh;
  }
  const profile=new CatmullRomCurve3([
    [.001,.25,0],[.45,.24,0],[.64,.36,0],[.84,.68,0],[.91,1.07,0],
    [.86,1.43,0],[.71,1.85,0],[.54,2.18,0],[.44,2.55,0],
    [.44,2.87,0],[.39,3.08,0],[.25,3.23,0],[.001,3.27,0]
  ].map(point=>new Vector3(...point)));
  const geometry=new LatheGeometry(profile.getPoints(80).map(point=>new Vector2(Math.max(.001,point.x),point.y)),64);
  geometry.scale(1,1,.78);
  const position=geometry.getAttribute('position'), colors=[];
  const yellow=new Color('#f4cf51'),cream=new Color('#ede0c7');
  const smooth=(a,b,x)=>{const q=Math.min(1,Math.max(0,(x-a)/(b-a)));return q*q*(3-2*q);};
  for(let i=0;i<position.count;i++) {
    const x=position.getX(i),y=position.getY(i),z=position.getZ(i);
    const ellipse=(x/.72)**2+((y-1.14)/.92)**2;
    const belly=(1-smooth(.83,1.12,ellipse))*smooth(.12,.45,z);
    const color=yellow.clone().lerp(cream,belly);
    colors.push(color.r,color.g,color.b);
  }
  geometry.setAttribute('color',new BufferAttribute(new Float32Array(colors),3));
  const body=new Mesh(geometry,new MeshStandardMaterial({vertexColors:true,roughness:.76}));
  body.name='Pear-shaped body'; root.add(body);
  for(const side of [-1,1]) sphere(root,'Foot',skin,[side*.35,.16,.07],[.3,.16,.36]);

  const eyes=[];
  for(const side of [-1,1]) {
    const eye=new Group(); eye.name='Green eye';
    eye.position.set(side*.255,2.93,.285); eye.rotation.y=side*.18; root.add(eye);
    sphere(eye,'Green iris',green,[0,0,0],[.136,.176,.083]);
    const pupil=sphere(eye,'Pupil',pupilMaterial,[0,-.016,.074],[.076,.104,.036]);
    sphere(pupil,'Eye highlight',shine,[-.24,.35,.85],[.13,.12,.14]);
    eyes.push({eye,pupil});
  }
  tube(root,'Smile',[[-.18,2.69,.319],[-.09,2.66,.344],[0,2.65,.35],[.09,2.66,.344],[.18,2.69,.319]],.014,mouthMaterial);

  const arms=[];
  for(const side of [-1,1]) {
    const arm=new Group(); arm.name=side===-1 ? 'Waving arm' : 'Resting arm';
    arm.position.set(side*.64,2.04,0); root.add(arm);
    const points=[[0,0,.04],[side*.30,-.37,.28],[side*.24,-.58,.60],[-side*.23,-.43,.78],[-side*.95,-.12,.64]];
    if(side===1) for(const point of points) point[1]-=.06;
    tube(arm,'Folded arm',points,.19);
    sphere(arm,'Shoulder',skin,points[0],[.2,.22,.2]);
    sphere(arm,'Wrist',skin,points.at(-1),[.19,.18,.18]);
    const hand=new Group(); hand.name='Three-fingered hand'; hand.position.set(...points.at(-1));
    hand.position.z+=.1; hand.rotation.z=-side*.13; arm.add(hand);
    sphere(hand,'Palm',hands,[0,0,0],[.16,.095,.09]);
    for(let i=0;i<3;i++) sphere(hand,'Finger',hands,[-side*.065,(i-1)*.064,.055],[.15,.041,.055]);
    arms.push(arm);
  }
  const shadow=sphere(new Group(),'Ground shadow',new MeshStandardMaterial({color:'#9da78d',transparent:true,opacity:.16,depthWrite:false,roughness:1}),[0,.005,0],[.96,.008,.55]);
  return {root,body,eyes,arms,shadow};
}

export function applyPose(model,pose) {
  model.root.rotation.set(pose.pitch,pose.yaw,pose.roll);
  model.root.position.y=pose.lift;
  const width=1/Math.sqrt(pose.scaleY);
  model.root.scale.set(width,pose.scaleY,width);
  model.arms[0].rotation.z=pose.wave;
  for(const {eye,pupil} of model.eyes) {
    eye.scale.y=pose.blink;
    pupil.position.x=pose.lookX*.022;
    pupil.position.y=-.016+pose.lookY*.018;
  }
  const spread=1+pose.lift*.35;
  model.shadow.scale.set(.96*spread,.008,.55*spread);
  model.shadow.material.opacity=.16-pose.lift*.2;
}

export function disposeNaiwa(model) {
  const geometries=new Set(),materials=new Set();
  for(const group of [model.root,model.shadow]) group.traverse(object=>{
    if(object.geometry) geometries.add(object.geometry);
    if(object.material) materials.add(object.material);
  });
  geometries.forEach(geometry=>geometry.dispose());
  materials.forEach(material=>material.dispose());
}
