/* Haunted course: a local, read-only scenery renderer. No trainer or recording commands. */
import * as THREE from './vendor/three.module.js';
import {GLTFLoader} from './vendor/GLTFLoader.js';
import {clone as cloneRig} from './vendor/SkeletonUtils.js';

if(new URLSearchParams(location.search).get('scene')==='haunted') init().catch(error=>{
 console.error('Haunted scenery',error);
 const message=document.createElement('p');message.setAttribute('role','status');
 message.style.cssText='position:absolute;inset:35% 15% auto;z-index:4;background:#12212b;padding:24px;border-radius:16px;color:white';
 message.textContent='The 3D scenery could not load on this browser. Choose Real map or Animal game in the scenery menu. Your workout has not changed.';document.body.append(message);
});
async function init(){
 const renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'high-performance'});
 renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.5));renderer.setSize(innerWidth,innerHeight);
 renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.3;
 renderer.domElement.id='haunted-world';renderer.domElement.setAttribute('aria-label','A winding 3D cycling path through a moonlit graveyard');
 renderer.domElement.style.cssText='position:absolute;inset:0;width:100%;height:100%;pointer-events:none';
 document.getElementById('cv').style.display='none';document.body.prepend(renderer.domElement);
 const scene=new THREE.Scene();scene.background=new THREE.Color('#142738');scene.fog=new THREE.FogExp2('#24343c',.008);
 const camera=new THREE.PerspectiveCamera(58,innerWidth/innerHeight,.1,400);
 scene.add(new THREE.HemisphereLight('#c4e3ff','#35453b',2));
 const moonlight=new THREE.DirectionalLight('#aacdff',3);moonlight.position.set(-60,100,-70);scene.add(moonlight);
 const ground=new THREE.Mesh(new THREE.PlaneGeometry(1100,1100),new THREE.MeshStandardMaterial({color:'#283e37',roughness:1}));ground.rotation.x=-Math.PI/2;ground.position.set(0,-.35,-130);scene.add(ground);
 const route=new THREE.CatmullRomCurve3([[0,0,0],[45,0,-85],[110,0,-165],[85,0,-255],[-15,0,-315],[-115,0,-220],[-135,0,-110],[-85,0,-20]].map(p=>new THREE.Vector3(...p)),true,'centripetal');
 const length=route.getLength(),point=d=>route.getPointAt(((d%length)+length)%length/length);
 const tangent=d=>route.getTangentAt(((d%length)+length)%length/length);
 const normal=d=>new THREE.Vector3().crossVectors(tangent(d),new THREE.Vector3(0,1,0)).normalize();
 const beside=(d,offset)=>point(d).addScaledVector(normal(d),offset);
 const random=n=>{const x=Math.sin(n*91.733)*19731.117;return x-Math.floor(x);};
 function ribbon(width,y,color){
  const pos=[],uv=[],idx=[];for(let i=0;i<=700;i++){const d=i/700*length,p=point(d),n=normal(d);for(const side of [-1,1]){const v=p.clone().addScaledVector(n,side*width/2);pos.push(v.x,y,v.z);uv.push(side===-1?0:1,d/5);}if(i<700){const a=i*2;idx.push(a,a+2,a+1,a+1,a+2,a+3);}}
  const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));geo.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));geo.setIndex(idx);geo.computeVertexNormals();
  const mesh=new THREE.Mesh(geo,new THREE.MeshStandardMaterial({color,roughness:.97,side:THREE.DoubleSide}));scene.add(mesh);return mesh;
 }
 ribbon(7.8,-.18,'#625f4e');const road=ribbon(6.4,-.12,'#474c50');
 // Procedural cobbles: no external textures or services.
 const texCanvas=document.createElement('canvas');texCanvas.width=texCanvas.height=256;const ctx=texCanvas.getContext('2d');ctx.fillStyle='#454a4c';ctx.fillRect(0,0,256,256);
 for(let y=0;y<8;y++)for(let x=-1;x<8;x++){const shade=76+Math.floor(random(y*8+x+9)*22);ctx.fillStyle=`rgb(${shade},${shade+4},${shade+6})`;ctx.fillRect(x*37+(y%2)*18+2,y*32+2,33,27);}
 const tex=new THREE.CanvasTexture(texCanvas);tex.wrapS=tex.wrapT=THREE.RepeatWrapping;tex.colorSpace=THREE.SRGBColorSpace;road.material.map=tex;road.material.color.set('#a0aaab');
 // An actual moon and stars, rendered in the same world as the road.
 const moon=new THREE.Mesh(new THREE.SphereGeometry(13,24,16),new THREE.MeshBasicMaterial({color:'#d0e0cf'}));moon.position.set(-95,105,-210);scene.add(moon);
 const stars=[];for(let i=0;i<220;i++)stars.push((random(i)*2-1)*500,100+random(i+700)*220,(random(i+300)*2-1)*500);
 const starGeo=new THREE.BufferGeometry();starGeo.setAttribute('position',new THREE.Float32BufferAttribute(stars,3));scene.add(new THREE.Points(starGeo,new THREE.PointsMaterial({color:'#c9dbde',size:.6,sizeAttenuation:true})));
 const loader=new GLTFLoader(),assets=new Map();
 const names=['gravestone-cross-large','gravestone-round','gravestone-decorative','gravestone-broken','crypt','crypt-large','crypt-large-roof','pine-crooked','pine','trunk','rocks','rocks-tall','iron-fence','iron-fence-border-gate','lightpost-single','fire-basket','coffin','character-ghost','character-skeleton','character-keeper','character-vampire','character-zombie'];
 await Promise.all(names.map(async name=>{assets.set(name,await loader.loadAsync('/web/graveyard/'+name+'.glb'));}));
 function model(name,pos,height,rotation=0,rig=false){
  const source=assets.get(name),node=rig?cloneRig(source.scene):source.scene.clone(true),box=new THREE.Box3().setFromObject(node),size=box.getSize(new THREE.Vector3());
  const scale=height/(size.y||1);node.scale.multiplyScalar(scale);node.position.copy(pos);node.position.y-=box.min.y*scale;node.rotation.y=rotation;scene.add(node);return node;
 }
 const graves=['gravestone-cross-large','gravestone-round','gravestone-decorative','gravestone-broken'];
 for(let i=0;i<150;i++){const d=i/150*length,side=i%2?1:-1,p=beside(d,side*(9+random(i)*22));model(graves[i%4],p,.85+random(i+5)*1.3,Math.atan2(tangent(d).x,tangent(d).z)+random(i)*.4);}
 for(let i=0;i<65;i++){const d=i/65*length,p=beside(d,(i%2?1:-1)*(24+random(i)*28));model(i%3?'pine-crooked':'pine',p,6+random(i+17)*10,random(i)*6.28);}
 for(let i=0;i<25;i++){const d=i/25*length;model(i%2?'rocks':'rocks-tall',beside(d,(i%2?1:-1)*(11+random(i)*12)),1.2+random(i)*2.5,random(i)*6.28);}
 const flames=[];
 function torch(d,side){const p=beside(d,side*4.7);model('fire-basket',p,1.15);const fire=new THREE.Mesh(new THREE.ConeGeometry(.24,.8,6),new THREE.MeshBasicMaterial({color:'#ffa65a'}));fire.position.copy(p).y=1.3;scene.add(fire);flames.push(fire);}
 for(let i=0;i<30;i++){torch(i/30*length,1);torch(i/30*length,-1);}
 for(let i=0;i<8;i++){const d=30+i*length/8,angle=Math.atan2(tangent(d).x,tangent(d).z);model('crypt-large',beside(d,15),7,angle-Math.PI/2);model('crypt-large-roof',beside(d,15).add(new THREE.Vector3(0,7,0)),2,angle-Math.PI/2);model('crypt',beside(d,-16),5,angle+Math.PI/2);}
 // Stone gate towers frame the path while leaving the full road open.
 const stone=new THREE.MeshStandardMaterial({color:'#58636a',roughness:1});
 for(const d of [60,300,570]){const gate=new THREE.Group();gate.position.copy(point(d));gate.rotation.y=Math.atan2(tangent(d).x,tangent(d).z);scene.add(gate);for(const side of [-1,1]){const tower=new THREE.Mesh(new THREE.BoxGeometry(3.5,10,4),stone);tower.position.set(side*6,4.7,0);gate.add(tower);for(let i=-1;i<=1;i++){const tooth=new THREE.Mesh(new THREE.BoxGeometry(.8,1.1,1.2),stone);tooth.position.set(side*6+i,10.2,0);gate.add(tooth);}}const arch=new THREE.Mesh(new THREE.BoxGeometry(9,1.5,2),stone);arch.position.y=8;gate.add(arch);}
 // Scripted encounters are scenery only. Characters cannot alter the workout.
 const actors=[];
 function actor(name,d,offset,clip,height=2){const node=model(name,beside(d,offset),height,0,true),mixer=new THREE.AnimationMixer(node);const animation=assets.get(name).animations.find(a=>a.name===clip)||assets.get(name).animations.find(a=>a.name==='idle');if(animation)mixer.clipAction(animation).play();const a={node,mixer,d,offset,phase:random(d)*6.28,name};actors.push(a);return a;}
 for(let i=0;i<9;i++){const d=18+i*length/9;const keeper=actor('character-keeper',d,8,'attack-melee-right');const monster=actor(i%2?'character-skeleton':'character-vampire',d+2,11,'attack-melee-left');keeper.node.lookAt(monster.node.position);monster.node.lookAt(keeper.node.position);}
 for(let i=0;i<14;i++)actor('character-ghost',35+i*length/14,(i%2?1:-1)*(7+random(i)*10),'idle',1.7);
 for(let i=0;i<6;i++)actor('character-zombie',90+i*length/6,-12,'walk',2);
 // Rider follows the road. Wheel and pedal animation use cadence, not elapsed ride time.
 const bike=new THREE.Group();scene.add(bike);const bikeMat=new THREE.MeshStandardMaterial({color:'#d9b578',metalness:.65,roughness:.3}),rubber=new THREE.MeshStandardMaterial({color:'#171c21'});
 const wheels=[];for(const z of [-.85,.85]){const wheel=new THREE.Mesh(new THREE.TorusGeometry(.52,.055,8,24),rubber);wheel.rotation.y=Math.PI/2;wheel.position.set(0,.53,z);bike.add(wheel);wheels.push(wheel);for(let i=0;i<6;i++){const spoke=new THREE.Mesh(new THREE.CylinderGeometry(.008,.008,.96,4),bikeMat);spoke.rotation.z=i*Math.PI/3;wheel.add(spoke);}}
 function bar(a,b,radius,material,parent=bike){const av=new THREE.Vector3(...a),bv=new THREE.Vector3(...b),mesh=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,av.distanceTo(bv),8),material);mesh.position.copy(av).add(bv).multiplyScalar(.5);mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),bv.sub(av).normalize());parent.add(mesh);return mesh;}
 for(const [a,b] of [[[0,.53,-.85],[0,.75,0]],[[0,.75,0],[0,1.25,-.25]],[[0,1.25,-.25],[0,.53,-.85]],[[0,1.25,-.25],[0,1.32,.55]],[[0,1.32,.55],[0,.75,0]],[[0,1.32,.55],[0,.53,.85]]])bar(a,b,.035,bikeMat);
 const jersey=new THREE.MeshStandardMaterial({color:'#48a8aa'}),skin=new THREE.MeshStandardMaterial({color:'#d6b995'});
 bar([0,1.45,-.2],[0,2,.3],.19,jersey);const head=new THREE.Mesh(new THREE.SphereGeometry(.18,12,8),skin);head.position.set(0,2.18,.42);bike.add(head);const helmet=new THREE.Mesh(new THREE.SphereGeometry(.2,12,8,0,Math.PI*2,0,Math.PI/2),bikeMat);helmet.position.copy(head.position).y+=.04;bike.add(helmet);
 for(const side of [-1,1]){bar([side*.2,1.9,.25],[side*.26,1.43,.67],.065,skin);}
 const legs=[new THREE.Group(),new THREE.Group()];legs.forEach((leg,i)=>{leg.position.set(i?.15:-.15,1.4,-.2);bar([0,0,0],[0,-.65,.22],.075,jersey,leg);bar([0,-.65,.22],[0,-.95,.08],.055,skin,leg);bike.add(leg);});
 let last=0,pedal=0,previewDistance=0,exploring=false,disposed=false;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const tourStyle=document.createElement('style');tourStyle.textContent='.scenery-tour .ov,.scenery-tour .ctl{display:none!important}';document.head.append(tourStyle);
 const explore=document.getElementById('explore-haunted');explore.hidden=false;explore.onclick=()=>{exploring=true;document.body.classList.add('scenery-tour');document.getElementById('start').hidden=true;notice.hidden=false;};
 const notice=document.createElement('button');notice.type='button';notice.hidden=true;notice.textContent='Scenery tour · no workout recording · Exit';notice.style.cssText='position:absolute;bottom:18px;left:50%;transform:translateX(-50%);z-index:12;background:#152c37e8;color:#c7e3e0;border:1px solid #719697;border-radius:18px;padding:10px 16px';notice.onclick=()=>{exploring=false;document.body.classList.remove('scenery-tour');notice.hidden=true;document.getElementById('start').hidden=false;};document.body.append(notice);
 window.HauntedWorld={update({time,distance,cadence,active,paused}){
  if(disposed||document.hidden)return;const dt=Math.min(.05,Math.max(0,(time-last)/1000));last=time;
  if(active&&exploring){exploring=false;document.body.classList.remove('scenery-tour');notice.hidden=true;}if(exploring&&!reduced)previewDistance+=dt*5;
  const d=active?distance:previewDistance,p=point(d),angle=Math.atan2(tangent(d).x,tangent(d).z);bike.position.copy(p);bike.rotation.y=angle;
  const rpm=active&&!paused?cadence:exploring?60:0;pedal+=dt*rpm/60*Math.PI*2;legs.forEach((leg,i)=>leg.rotation.x=Math.sin(pedal+i*Math.PI)*.45);wheels.forEach(w=>w.rotation.z=pedal);
  const eye=point(d-8);eye.y=4.4;const look=point(d+12);look.y=1.6;camera.position.lerp(eye,1-Math.exp(-dt*5));camera.lookAt(look);
  for(const a of actors){if(a.node.position.distanceTo(p)<95){a.mixer.update(reduced?0:dt);if(a.name==='character-ghost')a.node.position.y=.5+Math.sin(time/1300+a.phase)*.5;if(a.sword)a.sword.rotation.x=Math.sin(time/350+a.phase)*.8;}}
  for(const fire of flames)fire.scale.y=reduced?1:1+Math.sin(time/130+fire.position.x)*.15;
  renderer.render(scene,camera);
 },diagnostics:()=>({renderer:'3D',routeLength:Math.round(length),actors:actors.length,models:assets.size,preview:exploring,recording:false,drawCalls:renderer.info.render.calls}),dispose(){disposed=true;scene.traverse(o=>{o.geometry?.dispose();if(o.material)for(const m of [].concat(o.material))m.dispose();});tex.dispose();renderer.dispose();renderer.domElement.remove();notice.remove();}};
 camera.position.copy(point(-8));camera.position.y=4.4;camera.lookAt(point(12).add(new THREE.Vector3(0,1.6,0)));
 addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
 addEventListener('pagehide',()=>window.HauntedWorld.dispose(),{once:true});
}
