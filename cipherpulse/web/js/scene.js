"use strict";
/* CipherPulse 3D: realistic PBR astronaut + X-ray, Earth orbit with link beam, system pipeline. */
(function(){
const CP=window.CP,S=CP.S,$=CP.$,clamp=CP.clamp,META=CP.META;
const T=window.THREE;
if(!T){ $("gl").style.display="none"; CP.toast("The 3D library did not load. Check your internet connection and press Ctrl+F5.","critical",9000); return; }
const cv=$("gl");
let renderer;
try{ renderer=new T.WebGLRenderer({canvas:cv,antialias:true,powerPreference:"high-performance"}); }
catch(e){ CP.toast("Your browser could not start 3D graphics. Try Chrome or Edge.","critical",9000); return; }
const reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
const QUAL={high:{pr:2,shadow:2048},medium:{pr:1.5,shadow:1024},low:{pr:1,shadow:512}};
let qual="high", useBloom=true;
renderer.setPixelRatio(Math.min(devicePixelRatio,QUAL.high.pr));
renderer.outputEncoding=T.sRGBEncoding; renderer.toneMapping=T.ACESFilmicToneMapping; renderer.toneMappingExposure=1.05;
renderer.shadowMap.enabled=true; renderer.shadowMap.type=T.PCFSoftShadowMap;
const scene=new T.Scene(); scene.background=new T.Color(0x02050b);
const camera=new T.PerspectiveCamera(42,1,.1,400);

/* ---------- helpers ---------- */
function canvasTex(w,h,draw,srgb){ const c=document.createElement("canvas"); c.width=w; c.height=h; draw(c.getContext("2d"),w,h); const t=new T.CanvasTexture(c); if(srgb!==false) t.encoding=T.sRGBEncoding; t.anisotropy=4; return t; }
const glowTex=canvasTex(64,64,(g)=>{const r=g.createRadialGradient(32,32,0,32,32,32);r.addColorStop(0,"rgba(255,255,255,1)");r.addColorStop(.3,"rgba(255,255,255,.35)");r.addColorStop(1,"rgba(255,255,255,0)");g.fillStyle=r;g.fillRect(0,0,64,64);},false);
function sprite(color,size,op){ const s=new T.Sprite(new T.SpriteMaterial({map:glowTex,color,transparent:true,opacity:op==null?.6:op,blending:T.AdditiveBlending,depthWrite:false})); s.scale.set(size,size,1); return s; }
const col=hex=>new T.Color(hex);
const STATUS={ok:0x7fe9ff,warning:0xffb547,critical:0xff5c6c};

/* ---------- environment reflections (for visor, metal) ---------- */
try{
  const pm=new T.PMREMGenerator(renderer);
  const env=canvasTex(512,256,(g,w,h)=>{
    const gr=g.createLinearGradient(0,0,0,h); gr.addColorStop(0,"#16305a"); gr.addColorStop(.5,"#25476e"); gr.addColorStop(1,"#070c14"); g.fillStyle=gr; g.fillRect(0,0,w,h);
    g.fillStyle="#fff4de"; g.fillRect(70,40,110,46); g.fillStyle="#a8dcff"; g.fillRect(340,64,90,34); g.fillStyle="#ffd9a0"; g.fillRect(220,10,60,18); g.fillStyle="#6fe0ff"; g.fillRect(430,120,50,10);
  });
  env.mapping=T.EquirectangularReflectionMapping;
  scene.environment=pm.fromEquirectangular(env).texture; env.dispose(); pm.dispose();
}catch(e){ console.warn("Environment map skipped",e); }

/* ---------- space backdrop ---------- */
(function(){
  const n=1800,p=new Float32Array(n*3),c=new Float32Array(n*3),tmp=new T.Color();
  for(let i=0;i<n;i++){const r=120+Math.random()*120,t=Math.random()*6.283,u=Math.acos(2*Math.random()-1);
    p[i*3]=r*Math.sin(u)*Math.cos(t);p[i*3+1]=r*Math.cos(u);p[i*3+2]=r*Math.sin(u)*Math.sin(t);
    tmp.setHSL(.55+Math.random()*.15,.4,.7+Math.random()*.3); c[i*3]=tmp.r;c[i*3+1]=tmp.g;c[i*3+2]=tmp.b;}
  const g=new T.BufferGeometry(); g.setAttribute("position",new T.BufferAttribute(p,3)); g.setAttribute("color",new T.BufferAttribute(c,3));
  scene.add(new T.Points(g,new T.PointsMaterial({size:1.1,vertexColors:true,sizeAttenuation:false,transparent:true,opacity:.9,depthWrite:false,fog:false})));
  [[0x3b2f8a,-90,30,-150,170],[0x0e5a78,110,-20,-170,190],[0x6a2a6a,20,60,-190,160]].forEach(([c0,x,y,z,s])=>{const sp=sprite(c0,s,.16);sp.position.set(x,y,z);scene.add(sp);});
})();

/* ---------- lights ---------- */
const sun=new T.DirectionalLight(0xfff0d8,2.3); sun.position.set(6,7,5); sun.castShadow=true;
sun.shadow.mapSize.set(2048,2048); Object.assign(sun.shadow.camera,{left:-3.5,right:3.5,top:4,bottom:-1,near:1,far:25}); sun.shadow.bias=-.0004; sun.shadow.normalBias=.02;
scene.add(sun);
const rimL=new T.DirectionalLight(0x6fd3ff,1.5); rimL.position.set(-6,3,-5); scene.add(rimL);
const fillL=new T.HemisphereLight(0x8fb7ff,0x07121f,.5); scene.add(fillL);
const keyPoint=new T.PointLight(0x7fe9ff,.9,9); keyPoint.position.set(0,.4,2.2); scene.add(keyPoint);

const crewG=new T.Group(), orbitG=new T.Group(), sysG=new T.Group();
scene.add(crewG,orbitG,sysG); orbitG.visible=false; sysG.visible=false;

/* =====================================================================
   CREW VIEW: PBR spacesuit astronaut, X-ray skeleton and organs
   ===================================================================== */
const fabric=canvasTex(128,128,(g,w,h)=>{
  g.fillStyle="#808080"; g.fillRect(0,0,w,h);
  for(let i=0;i<5200;i++){const v=110+Math.random()*60|0;g.fillStyle=`rgb(${v},${v},${v})`;g.fillRect(Math.random()*w,Math.random()*h,1.6,1.6);}
  g.strokeStyle="rgba(0,0,0,.22)"; g.lineWidth=1; for(let i=0;i<w;i+=6){g.beginPath();g.moveTo(i,0);g.lineTo(i,h);g.stroke();g.beginPath();g.moveTo(0,i);g.lineTo(w,i);g.stroke();}
},false);
fabric.wrapS=fabric.wrapT=T.RepeatWrapping; fabric.repeat.set(5,5);
const suitMats=[];
function sm(o){ const m=new T.MeshStandardMaterial(o); m.userData.c=m.color.getHex(); suitMats.push(m); return m; }
const white=sm({color:0xe9edf1,roughness:.6,metalness:.04,bumpMap:fabric,bumpScale:.5});
const grey=sm({color:0x8e99a4,roughness:.5,metalness:.25,bumpMap:fabric,bumpScale:.3});
const dark=sm({color:0x1b232c,roughness:.55,metalness:.45});
const metal=sm({color:0xc9d1d9,roughness:.24,metalness:.95});
const accent=sm({color:0x1fd6bd,roughness:.45,metalness:.2,emissive:0x0a5a50,emissiveIntensity:.5});
const visorMat=new T.MeshPhysicalMaterial({color:0xd9a441,metalness:1,roughness:.05,clearcoat:1,clearcoatRoughness:.03,envMapIntensity:1.8,side:T.DoubleSide});
visorMat.userData.c=visorMat.color.getHex(); suitMats.push(visorMat);

// platform
const platform=new T.Group(); crewG.add(platform);
const pBase=new T.Mesh(new T.CylinderGeometry(1.7,1.85,.14,72),new T.MeshStandardMaterial({color:0x0b1824,metalness:.85,roughness:.3})); pBase.position.y=-.07; pBase.receiveShadow=true; platform.add(pBase);
const pRing=new T.Mesh(new T.TorusGeometry(1.66,.016,8,160),new T.MeshBasicMaterial({color:0x7fe9ff,toneMapped:false})); pRing.rotation.x=Math.PI/2; pRing.position.y=.002; platform.add(pRing);
[1.2,.8,.4].forEach(r=>{const m=new T.Mesh(new T.RingGeometry(r-.006,r,96),new T.MeshBasicMaterial({color:0x2aa6c4,transparent:true,opacity:.55,side:T.DoubleSide}));m.rotation.x=-Math.PI/2;m.position.y=.003;platform.add(m);});
const beam=new T.Mesh(new T.CylinderGeometry(1.55,1.55,3.4,48,1,true),new T.MeshBasicMaterial({color:0x7fe9ff,transparent:true,opacity:.035,side:T.DoubleSide,blending:T.AdditiveBlending,depthWrite:false}));
beam.position.y=1.7; platform.add(beam);

const A=new T.Group(); crewG.add(A); A.position.y=.05;
function mesh(geo,mat,x,y,z,parent){ const m=new T.Mesh(geo,mat); m.position.set(x,y,z); m.castShadow=true; m.receiveShadow=true; (parent||A).add(m); return m; }
function limb(r1,r2,len){ const pts=[new T.Vector2(.0001,-len/2)],n=8; for(let i=0;i<=n;i++){const t=i/n;pts.push(new T.Vector2((r2+(r1-r2)*t)*(1+.05*Math.sin(t*Math.PI)),-len/2+len*t));} pts.push(new T.Vector2(.0001,len/2)); return new T.LatheGeometry(pts,26); }
function ring(R,y,mat,x,z,tube){ const m=mesh(new T.TorusGeometry(R,tube||.013,10,36),mat,x||0,y,z||0); m.rotation.x=Math.PI/2; return m; }
const SPH=(r)=>new T.SphereGeometry(r,24,18);

[-1,1].forEach(s=>{
  const b=mesh(SPH(.13),grey,s*.15,.09,.07); b.scale.set(1,.75,1.8);
  mesh(new T.BoxGeometry(.2,.04,.42),dark,s*.15,.025,.075);
  mesh(limb(.105,.085,.46),white,s*.15,.42,0); ring(.1,.2,metal,s*.15,0,.016);
  mesh(SPH(.115),white,s*.15,.68,.01); ring(.12,.55,accent,s*.15,0,.012);
  mesh(limb(.14,.115,.46),white,s*.15,.92,0); ring(.145,1.03,accent,s*.15,0,.012);
  // arms
  mesh(SPH(.12),white,s*.39,1.66,0);
  const ua=mesh(limb(.1,.085,.30),white,s*.435,1.525,0); ua.rotation.z=s*.2; ring(.1,1.57,accent,s*.425,0,.012).rotation.z=s*.2;
  mesh(SPH(.09),white,s*.47,1.37,.01);
  const fa=mesh(limb(.085,.07,.28),white,s*.49,1.235,.05); fa.rotation.z=s*.07; fa.rotation.x=-.3;
  ring(.078,1.10,metal,s*.505,.11,.016);
  const gl=mesh(SPH(.085),grey,s*.51,1.02,.13); gl.scale.set(1,1.15,.85);
  mesh(SPH(.03),grey,s*.455,1.02,.17); [-.04,0,.04].forEach(dx=>mesh(SPH(.026),grey,s*.51+dx,.94,.16));
});
mesh(SPH(.26),white,0,1.17,0).scale.set(1.15,.7,.85); ring(.27,1.26,metal,0,0,.015);
// torso (lathe, squashed front-back)
const torso=new T.Mesh(new T.LatheGeometry([[.0001,1.22],[.27,1.22],[.29,1.32],[.335,1.46],[.345,1.56],[.325,1.68],[.23,1.76],[.14,1.80],[.0001,1.80]].map(p=>new T.Vector2(p[0],p[1])),40),white);
torso.scale.z=.84; torso.castShadow=torso.receiveShadow=true; A.add(torso);
ring(.15,1.80,metal,0,0,.02);
// helmet
const helmet=mesh(new T.SphereGeometry(.27,36,26),white,0,1.99,0); helmet.scale.set(1,1.04,1.06);
const visor=mesh(new T.SphereGeometry(.286,44,30,Math.PI/2-.95,1.9,.8,1.38),visorMat,0,1.99,0); visor.scale.set(1,1.04,1.06);
ring(.18,1.83,metal,0,0,.022);
[-1,1].forEach(s=>mesh(new T.BoxGeometry(.03,.05,.06),new T.MeshBasicMaterial({color:0xffffff,toneMapped:false}),s*.27,2.04,.06));
// life-support backpack
mesh(new T.BoxGeometry(.52,.62,.24),white,0,1.48,-.28);
mesh(new T.BoxGeometry(.4,.3,.02),dark,0,1.52,-.41);
[-1,1].forEach(s=>mesh(new T.CylinderGeometry(.06,.06,.5,20),metal,s*.17,1.46,-.45));
mesh(new T.CylinderGeometry(.008,.008,.36,8),metal,.2,1.9,-.3);
function hose(pts){ const c=new T.CatmullRomCurve3(pts.map(p=>new T.Vector3(p[0],p[1],p[2]))); const m=new T.Mesh(new T.TubeGeometry(c,28,.016,8,false),dark); m.castShadow=true; A.add(m); }
[-1,1].forEach(s=>hose([[s*.1,1.46,.3],[s*.28,1.38,.27],[s*.38,1.34,.06],[s*.28,1.4,-.26]]));

// chest bio-monitor with LIVE ECG screen
const ecgCv=document.createElement("canvas"); ecgCv.width=256; ecgCv.height=130; const ecgG=ecgCv.getContext("2d");
const ecgTex=new T.CanvasTexture(ecgCv); ecgTex.encoding=T.sRGBEncoding;
mesh(new T.BoxGeometry(.27,.2,.06),dark,0,1.52,.30);
const screen=new T.Mesh(new T.PlaneGeometry(.22,.112),new T.MeshBasicMaterial({map:ecgTex,toneMapped:false})); screen.position.set(0,1.54,.332); A.add(screen);
const leds=[-.07,0,.07].map(x=>{const m=new T.MeshBasicMaterial({color:0x6cffc1,toneMapped:false});mesh(new T.BoxGeometry(.028,.02,.012),m,x,1.445,.332);return m;});
let idTexVal="";
const idCv=document.createElement("canvas"); idCv.width=128; idCv.height=80; const idG=idCv.getContext("2d"); const idTex=new T.CanvasTexture(idCv); idTex.encoding=T.sRGBEncoding;
const idPatch=new T.Mesh(new T.PlaneGeometry(.12,.075),new T.MeshStandardMaterial({map:idTex,roughness:.8})); idPatch.position.set(-.185,1.645,.237); idPatch.rotation.y=-.62; A.add(idPatch);
const logoTex=canvasTex(128,80,(g,w,h)=>{g.fillStyle="#0f2a4a";g.fillRect(0,0,w,h);g.strokeStyle="#7fe9ff";g.lineWidth=4;g.strokeRect(3,3,w-6,h-6);g.strokeStyle="#6cffc1";g.lineWidth=5;g.lineJoin="round";g.beginPath();[[16,42],[40,42],[52,20],[68,62],[82,32],[92,42],[112,42]].forEach(([x,y],i)=>i?g.lineTo(x,y):g.moveTo(x,y));g.stroke();});
const logo=new T.Mesh(new T.PlaneGeometry(.12,.075),new T.MeshStandardMaterial({map:logoTex,roughness:.8})); logo.position.set(.185,1.645,.237); logo.rotation.y=.62; A.add(logo);

/* ---- skeleton + organs (X-ray) ---- */
const bones=new T.Group(), organs=new T.Group(); A.add(bones,organs);
const boneMat=new T.MeshStandardMaterial({color:0xcff6ff,emissive:0x3bb6d6,emissiveIntensity:.9,roughness:.45,transparent:true,opacity:0});
const xr={bone:[boneMat],organ:[]};
const ORG_MESHES=[];
function tagOrgan(m,n){ m.userData.organ=n; ORG_MESHES.push(m); return m; }
function bone(geo,x,y,z,rx,rz,sc){ const m=tagOrgan(new T.Mesh(geo,boneMat),"bones"); m.position.set(x,y,z); if(rx)m.rotation.x=rx; if(rz)m.rotation.z=rz; if(sc)m.scale.set(sc[0],sc[1],sc[2]); bones.add(m); return m; }
bone(new T.SphereGeometry(.105,20,16),0,1.99,0,0,0,[1,1.15,1.1]); bone(new T.SphereGeometry(.07,14,10),0,1.9,.05,0,0,[1,.55,.9]);
for(let i=0;i<20;i++){const t=i/19;bone(new T.CylinderGeometry(.026,.026,.017,10),0,1.78-t*.53,-.03-.04*Math.sin(t*3.1),0,0);}
for(let i=0;i<10;i++){const R=.12+.09*Math.sin((i+1)/10*Math.PI*.9),L=Math.PI*1.6;
  bone(new T.TorusGeometry(R,.007,6,34,L),0,1.69-i*.04,-.005,Math.PI/2,Math.PI/2-L/2,[1,.82,1]);}
bone(new T.BoxGeometry(.03,.17,.012),0,1.58,.17);
[-1,1].forEach(s=>{
  bone(new T.CylinderGeometry(.008,.008,.3,6),s*.15,1.72,.05,0,s*1.45);
  bone(SPH(.04),s*.39,1.66,0); bone(new T.CylinderGeometry(.018,.018,.30,8),s*.435,1.525,0,0,s*.2);
  bone(SPH(.03),s*.47,1.37,.01); bone(new T.CylinderGeometry(.013,.013,.28,8),s*.49,1.235,.05,-.3,s*.07);
  bone(new T.BoxGeometry(.07,.08,.02),s*.51,1.02,.12);
  bone(SPH(.045),s*.15,1.14,0); bone(new T.CylinderGeometry(.022,.022,.46,8),s*.15,.92,0);
  bone(SPH(.035),s*.15,.68,0); bone(new T.CylinderGeometry(.018,.018,.44,8),s*.15,.43,0);
  bone(new T.BoxGeometry(.07,.02,.2),s*.15,.06,.07); bone(SPH(.09),s*.13,1.2,0,0,0,[1,.8,.6]);
});
function omat(c,e,op){ const m=new T.MeshStandardMaterial({color:c,emissive:e,emissiveIntensity:.9,roughness:.5,transparent:true,opacity:0}); m.userData.op=op||.9; xr.organ.push(m); return m; }
function organ(geo,m,x,y,z,sc){ const o=new T.Mesh(geo,m); o.position.set(x,y,z); if(sc)o.scale.set(sc[0],sc[1],sc[2]); organs.add(o); return o; }
const heartMat=omat(0xff4c63,0xff1f3d);
const heart=tagOrgan(organ(SPH(.05),heartMat,.04,1.52,.11,[1,1.2,.9]),"heart"); heart.rotation.z=-.4;
const heartGlow=sprite(0xff5c6c,.34,0); heart.add(heartGlow);
const lungMat=omat(0x9fe8ff,0x2aa6c4,.55);
const lungL=tagOrgan(organ(SPH(.085),lungMat,-.12,1.55,.02,[1,1.9,.9]),"lungs"), lungR=tagOrgan(organ(SPH(.085),lungMat,.13,1.55,.02,[1,1.9,.9]),"lungs");
const brainGeo=SPH(.085); (function(){const p=brainGeo.attributes.position;for(let i=0;i<p.count;i++){const x=p.getX(i),y=p.getY(i),z=p.getZ(i),n=.008*Math.sin(x*70)*Math.sin(y*60+z*40);p.setXYZ(i,x*(1+n*6),y*(1+n*6),z*(1+n*6));}brainGeo.computeVertexNormals();})();
const brainMat=omat(0xffa0b4,0xff6a8a,.85); const brain=tagOrgan(organ(brainGeo,brainMat,0,2.03,-.01,[1,.82,1.12]),"brain");
organ(SPH(.07),omat(0x8a2d2d,0x3a0a0a,.7),.1,1.37,.06,[1.5,.7,.9]);
[-1,1].forEach(s=>tagOrgan(organ(SPH(.025),omat(0x8a3a3a,0x300808,.7),s*.08,1.3,-.06,[.8,1.4,.8]),"kidneys"));
const eyeMat=omat(0xdff6ff,0x6fe0ff,.95); [-1,1].forEach(s=>tagOrgan(organ(SPH(.02),eyeMat,s*.045,2.0,.085),"eyes"));
const muscleMat=omat(0xc8504a,0x5a1410,.5); [-1,1].forEach(s=>{tagOrgan(organ(SPH(.07),muscleMat,s*.15,.92,.04,[1,3.2,.9]),"muscles");tagOrgan(organ(SPH(.05),muscleMat,s*.15,.45,.0,[1,3.0,.9]),"muscles");});
const vesselMat=omat(0xff6a7a,0xff3050,.8), veinMat=omat(0x5aa8ff,0x1f5cff,.7);
function vessel(mat,pts,r){ const c=new T.CatmullRomCurve3(pts.map(p=>new T.Vector3(p[0],p[1],p[2]))); organs.add(new T.Mesh(new T.TubeGeometry(c,24,r||.006,6,false),mat)); }
vessel(vesselMat,[[.04,1.56,.1],[.03,1.72,.04],[.01,1.9,.0],[0,2.0,-.02]],.009);
[-1,1].forEach(s=>{vessel(vesselMat,[[.04,1.5,.1],[s*.15,1.48,.06],[s*.35,1.42,.03],[s*.5,1.2,.06],[s*.51,1.03,.12]]);
  vessel(veinMat,[[s*.03,1.5,.08],[s*.12,1.3,.04],[s*.14,1.0,.02],[s*.15,.6,.0],[s*.15,.1,.05]]);});
const radShell=new T.Mesh(new T.SphereGeometry(1.7,32,22),new T.MeshBasicMaterial({color:0xffb547,wireframe:true,transparent:true,opacity:0,blending:T.AdditiveBlending,depthWrite:false})); radShell.position.y=1.05; crewG.add(radShell);
const scanDisc=new T.Mesh(new T.RingGeometry(0,.8,56),new T.MeshBasicMaterial({color:0x7fe9ff,transparent:true,opacity:.1,side:T.DoubleSide,blending:T.AdditiveBlending,depthWrite:false}));
const scanRing=new T.Mesh(new T.TorusGeometry(.8,.01,6,80),new T.MeshBasicMaterial({color:0xbff6ff,transparent:true,opacity:.95,blending:T.AdditiveBlending,toneMapped:false}));
[scanDisc,scanRing].forEach(m=>{m.rotation.x=Math.PI/2;crewG.add(m);});

/* suit modes: suit (opaque) / xray (see-through, bones+organs glow) / holo (cyan wireframe) */
let suitMode="suit", suitAmt=1, xrAmt=0;
function setSuit(m){ suitMode=m; suitMats.forEach(mt=>{ mt.wireframe=m==="holo"; if(m==="holo") mt.color.setHex(0x44d6f0); else mt.color.setHex(mt.userData.c); mt.needsUpdate=true; }); }
function applySuitFade(dt){
  const tgt=suitMode==="suit"?1:suitMode==="xray"?.09:.5, xt=suitMode==="suit"?0:1;
  suitAmt+=(tgt-suitAmt)*Math.min(1,dt*5); xrAmt+=(xt-xrAmt)*Math.min(1,dt*5);
  suitMats.forEach(mt=>{const tr=suitAmt<.995; if(mt.transparent!==tr){mt.transparent=tr;mt.needsUpdate=true;} mt.opacity=suitAmt; mt.depthWrite=suitAmt>.6||suitMode==="suit";});
  boneMat.opacity=.92*xrAmt; xr.organ.forEach(m=>m.opacity=m.userData.op*xrAmt);
  heartGlow.material.opacity=Math.min(.6,heartGlow.material.opacity)*(xrAmt>.05?1:0);
  bones.visible=organs.visible=xrAmt>.02;
}

/* =====================================================================
   ORBIT VIEW: Earth, atmosphere, space station, ground control, data beam
   ===================================================================== */
const ER=3, earthGroup=new T.Group(); earthGroup.rotation.z=.41; orbitG.add(earthGroup);
const procEarth=canvasTex(1024,512,(g,w,h)=>{
  const o=g.createLinearGradient(0,0,0,h); o.addColorStop(0,"#0b2f66"); o.addColorStop(.5,"#0e4a8c"); o.addColorStop(1,"#0b2f66"); g.fillStyle=o; g.fillRect(0,0,w,h);
  for(let i=0;i<70;i++){const cx=Math.random()*w,cy=h*.15+Math.random()*h*.7,r=18+Math.random()*80;g.fillStyle=["#2f6b3a","#3f7d44","#8a7a4a","#58703a"][i%4];g.globalAlpha=.85;g.beginPath();
    for(let k=0;k<14;k++){const a=k/14*6.283,rr=r*(.55+Math.random()*.6);g.lineTo(cx+Math.cos(a)*rr*1.4,cy+Math.sin(a)*rr*.8);}g.closePath();g.fill();}
  g.globalAlpha=1; g.fillStyle="rgba(240,248,255,.92)"; g.fillRect(0,0,w,26); g.fillRect(0,h-34,w,34);
});
const earthMat=new T.MeshPhongMaterial({map:procEarth,specular:0x2a4a6a,shininess:14});
const earth=new T.Mesh(new T.SphereGeometry(ER,96,64),earthMat); earthGroup.add(earth);
const clouds=new T.Mesh(new T.SphereGeometry(ER*1.012,80,56),new T.MeshPhongMaterial({transparent:true,opacity:.85,depthWrite:false})); clouds.visible=false; earthGroup.add(clouds);
(function(){ // real NASA-style Earth maps from the three.js examples repo; silently keeps the procedural Earth if offline
  const L=new T.TextureLoader(); L.setCrossOrigin("anonymous"); const B="https://cdn.jsdelivr.net/gh/mrdoob/three.js@r128/examples/textures/planets/";
  const get=(n,cb)=>L.load(B+n,t=>{t.anisotropy=8;cb(t);},undefined,()=>{});
  get("earth_atmos_2048.jpg",t=>{t.encoding=T.sRGBEncoding;earthMat.map=t;earthMat.needsUpdate=true;});
  get("earth_specular_2048.jpg",t=>{earthMat.specularMap=t;earthMat.specular.setHex(0x6a8ca8);earthMat.needsUpdate=true;});
  get("earth_normal_2048.jpg",t=>{earthMat.normalMap=t;earthMat.normalScale.set(.8,.8);earthMat.needsUpdate=true;});
  get("earth_lights_2048.png",t=>{t.encoding=T.sRGBEncoding;earthMat.emissiveMap=t;earthMat.emissive.setHex(0xffcc88);earthMat.emissiveIntensity=.35;earthMat.needsUpdate=true;});
  get("earth_clouds_1024.png",t=>{clouds.material.map=t;clouds.material.needsUpdate=true;clouds.visible=true;});
})();
const atmVS="varying vec3 vN; void main(){ vN=normalize(normalMatrix*normal); gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }";
const atmOuter=new T.Mesh(new T.SphereGeometry(ER*1.1,64,48),new T.ShaderMaterial({vertexShader:atmVS,fragmentShader:"varying vec3 vN; void main(){ float i=pow(max(0.0,0.74-dot(vN,vec3(0.0,0.0,1.0))),3.0); gl_FragColor=vec4(0.28,0.58,1.0,1.0)*i*1.7; }",side:T.BackSide,blending:T.AdditiveBlending,transparent:true,depthWrite:false}));
const atmInner=new T.Mesh(new T.SphereGeometry(ER*1.025,64,48),new T.ShaderMaterial({vertexShader:atmVS,fragmentShader:"varying vec3 vN; void main(){ float i=pow(1.0-abs(dot(vN,vec3(0.0,0.0,1.0))),3.2); gl_FragColor=vec4(0.45,0.72,1.0,1.0)*i*0.7; }",blending:T.AdditiveBlending,transparent:true,depthWrite:false}));
orbitG.add(atmOuter,atmInner);
const sunGlow=sprite(0xfff1cf,46,.95); sunGlow.position.copy(sun.position).normalize().multiplyScalar(80); orbitG.add(sunGlow);

// space station
const station=new T.Group();
const foil=new T.MeshStandardMaterial({color:0xd8a845,metalness:1,roughness:.35});
const hull=new T.MeshStandardMaterial({color:0xe6eaee,metalness:.3,roughness:.45});
const trussM=new T.MeshStandardMaterial({color:0xb8c2cc,metalness:.9,roughness:.3});
const panelTex=canvasTex(256,128,(g,w,h)=>{g.fillStyle="#0c1f4a";g.fillRect(0,0,w,h);g.strokeStyle="#c8a24a";g.lineWidth=1.4;for(let x=0;x<=w;x+=16){g.beginPath();g.moveTo(x,0);g.lineTo(x,h);g.stroke();}for(let y=0;y<=h;y+=16){g.beginPath();g.moveTo(0,y);g.lineTo(w,y);g.stroke();}const gr=g.createLinearGradient(0,0,w,h);gr.addColorStop(0,"rgba(150,190,255,.25)");gr.addColorStop(1,"rgba(0,0,0,0)");g.fillStyle=gr;g.fillRect(0,0,w,h);});
const panelMat=new T.MeshStandardMaterial({map:panelTex,metalness:.55,roughness:.28,emissive:0x0a1a40,emissiveIntensity:.35});
function sbox(g,m,x,y,z){const o=new T.Mesh(g,m);o.position.set(x,y,z);station.add(o);return o;}
sbox(new T.BoxGeometry(5.4,.07,.07),trussM,0,0,0);
const cyl=(r,l,m,x,y,z,rx,rz)=>{const o=new T.Mesh(new T.CylinderGeometry(r,r,l,20),m);o.position.set(x,y,z);o.rotation.set(rx||0,0,rz||0);station.add(o);return o;};
cyl(.17,1.3,hull,0,0,0,0,Math.PI/2); cyl(.13,1.1,foil,0,0,.55,Math.PI/2,0); cyl(.13,.9,hull,0,0,-.5,Math.PI/2,0);
[-.68,.68].forEach(x=>sbox(new T.SphereGeometry(.21,20,16),hull,x,0,0));
const wings=[]; [-2.55,-1.75,1.75,2.55].forEach(x=>[-1,1].forEach(z=>{const w=sbox(new T.BoxGeometry(.58,.012,1.3),panelMat,x,0,z*.76);wings.push(w);}));
sbox(new T.BoxGeometry(.55,.012,.9),hull,0,.02,-1.1); sbox(new T.CylinderGeometry(.05,.13,.34,16),hull,0,0,1.25).rotation.x=Math.PI/2;
const navR=sprite(0xff3040,.35,.9),navG=sprite(0x40ff80,.35,.9); navR.position.set(-2.7,.05,0); navG.position.set(2.7,.05,0); station.add(navR,navG);
station.scale.setScalar(.5);
const orbitPlane=new T.Group(); orbitPlane.rotation.set(.55,0,.15); orbitG.add(orbitPlane);
const OR=4.9, stPivot=new T.Group(); orbitPlane.add(stPivot); stPivot.add(station);
(function(){const p=[];for(let i=0;i<=160;i++){const a=i/160*6.283;p.push(new T.Vector3(Math.cos(a)*OR,0,Math.sin(a)*OR));}
  orbitPlane.add(new T.Line(new T.BufferGeometry().setFromPoints(p),new T.LineBasicMaterial({color:0x7fe9ff,transparent:true,opacity:.28})));})();
// ground control pin on Earth (generic ground station)
const gs=new T.Group(); earth.add(gs);
(function(){const lat=28.5,lon=-80.6,ph=(90-lat)*Math.PI/180,th=(lon+180)*Math.PI/180;
  const p=new T.Vector3(-ER*Math.sin(ph)*Math.cos(th),ER*Math.cos(ph),ER*Math.sin(ph)*Math.sin(th));
  gs.position.copy(p); gs.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),p.clone().normalize());})();
const pin=new T.Mesh(new T.ConeGeometry(.035,.16,12),new T.MeshBasicMaterial({color:0x6cffc1,toneMapped:false})); pin.position.y=.08; gs.add(pin);
const pulseR=new T.Mesh(new T.TorusGeometry(.09,.006,6,32),new T.MeshBasicMaterial({color:0x6cffc1,transparent:true,opacity:.8,toneMapped:false})); pulseR.rotation.x=Math.PI/2; pulseR.position.y=.01; gs.add(pulseR);
// link beam: arc between station and ground, with beads that flow while the link is up
const BN=48, beamGeo=new T.BufferGeometry(); beamGeo.setAttribute("position",new T.BufferAttribute(new Float32Array((BN+1)*3),3));
const beamUp=new T.Line(beamGeo,new T.LineBasicMaterial({color:0x6cffc1,transparent:true,opacity:.85})), beamDown=new T.Line(beamGeo,new T.LineDashedMaterial({color:0xff5c6c,dashSize:.14,gapSize:.12,transparent:true,opacity:.9}));
[beamUp,beamDown].forEach(l=>{l.frustumCulled=false;orbitG.add(l);});
const bead=[]; for(let i=0;i<14;i++){const s=sprite(0xbfffe6,.22,.9);orbitG.add(s);bead.push(s);}
const cubes=[]; for(let i=0;i<24;i++){const m=new T.Mesh(new T.BoxGeometry(.05,.05,.05),new T.MeshBasicMaterial({color:0xffb547,toneMapped:false}));m.visible=false;orbitG.add(m);cubes.push(m);}
const arc=new T.QuadraticBezierCurve3(new T.Vector3(),new T.Vector3(),new T.Vector3());
const wp=new T.Vector3(), wq=new T.Vector3();
let stAng=.6;

/* =====================================================================
   SYSTEM VIEW: live data pipeline
   ===================================================================== */
const NODES={
  sensor:{t:"Wearables",p:[-5.2,0,0]}, verify:{t:"Verifier",p:[-3.1,.9,.9]}, reject:{t:"Rejected log",p:[-3.1,-2.1,-.4]},
  vault:{t:"Encrypted vault",p:[-.7,2.2,-.6]}, detect:{t:"Analysis engine",p:[-.7,-.9,.9]}, memory:{t:"Crew memory",p:[1,-2.7,-.5]},
  agents:{t:"AI agents",p:[2.1,-.1,0]}, llm:{t:"Claude, Groq, Gemini",p:[3.3,1.9,-.8]}, dash:{t:"Dashboard and voice",p:[5.1,.5,.4]}, mcp:{t:"MCP and A2A",p:[3.6,-2.2,.6]}
};
const EDGES=[["sensor","verify"],["verify","vault"],["verify","detect"],["verify","reject"],["detect","agents"],["agents","dash"],["detect","dash"],["agents","memory"],["agents","llm"],["dash","mcp"]];
Object.entries(NODES).forEach(([id,n])=>{
  n.pos=new T.Vector3(...n.p); n.pulse=0; n.base=col(id==="reject"?0xff5c6c:id==="vault"?0x6cffc1:id==="agents"||id==="llm"||id==="memory"?0xc48bff:0x7fe9ff); n.flash=n.base.clone();
  const g=new T.Group(); g.position.copy(n.pos);
  n.shell=new T.Mesh(new T.IcosahedronGeometry(.4,1),new T.MeshBasicMaterial({color:n.base.clone(),wireframe:true,transparent:true,opacity:.85,blending:T.AdditiveBlending}));
  n.core=new T.Mesh(new T.SphereGeometry(.17,24,16),new T.MeshStandardMaterial({color:0x10202c,emissive:n.base.clone(),emissiveIntensity:1.6,metalness:.3,roughness:.3}));
  n.ring=new T.Mesh(new T.TorusGeometry(.56,.008,6,64),new T.MeshBasicMaterial({color:n.base.clone(),transparent:true,opacity:.6,toneMapped:false})); n.ring.rotation.x=1.2;
  n.glow=sprite(n.base.clone(),2,.45); g.add(n.shell,n.core,n.ring,n.glow); n.group=g; sysG.add(g);
});
EDGES.forEach(([a,b])=>{ const m=new T.Mesh(new T.TubeGeometry(new T.LineCurve3(NODES[a].pos,NODES[b].pos),1,.014,6,false),new T.MeshBasicMaterial({color:b==="reject"?0xff5c6c:0x2aa6c4,transparent:true,opacity:.5})); sysG.add(m); });
const packets=[], pGeo=new T.SphereGeometry(.075,10,8);
function flow(chain,color){ if(packets.length>44) return; const m=new T.Mesh(pGeo,new T.MeshBasicMaterial({color,blending:T.AdditiveBlending,toneMapped:false})); m.add(sprite(color,.5,.7)); m.position.copy(NODES[chain[0]].pos); sysG.add(m); packets.push({m,chain,i:0,t:0}); }
function pulse(id,color){ const n=NODES[id]; if(!n) return; n.pulse=1; n.flash.setHex(color==null?0xffffff:color); }
let lastFlow=0;
function flowVitals(){ const t=performance.now(); if(t-lastFlow<450) return; lastFlow=t; flow(["sensor","verify","vault"],0x7fe9ff); flow(["sensor","verify","detect","dash"],0x6cffc1); }
const flowReject=()=>flow(["sensor","verify","reject"],0xff5c6c);
const flowAlert=sev=>{ const c=sev==="critical"?0xff5c6c:0xffb547; flow(["detect","agents","llm","dash"],c); flow(["agents","memory"],0xc48bff); };

/* =====================================================================
   labels, camera, interaction
   ===================================================================== */
const tagsBox=$("tags"), vOff={hr:[104,-8],spo2:[-118,-14],temp:[104,-4],resp:[-112,26],radiation:[110,18]};
function mkTag(cls,html){ const d=document.createElement("div"); d.className="tag3d "+cls; d.innerHTML=html||""; tagsBox.appendChild(d); return d; }
const vtags={}; Object.keys(vOff).forEach(k=>vtags[k]=mkTag("v"));
const ntags={}; Object.entries(NODES).forEach(([id,n])=>ntags[id]=mkTag("n",`<b>${n.t}</b><small></small>`));
const otag={st:mkTag("o","Space station"),gs:mkTag("o","Ground control"),lk:mkTag("o","")};
const anchors={hr:heart,spo2:lungR,temp:brain,resp:lungL}; const radAnchor=new T.Object3D(); radAnchor.position.set(.22,1.05,.1); A.add(radAnchor); anchors.radiation=radAnchor;
const tv=new T.Vector3();
function proj(obj,off){ if(obj.isObject3D) obj.getWorldPosition(tv); else tv.copy(obj); if(off) tv.add(off); tv.project(camera); return [(tv.x*.5+.5)*innerWidth,(-tv.y*.5+.5)*innerHeight,tv.z<1]; }
function place(el,x,y,ok,ox,oy){ el.style.transform=`translate(${x+(ox||0)}px,${y+(oy||0)}px) translate(-50%,-50%)`; el.style.display=ok?"":"none"; }

const VIEWS={crew:{yaw:.35,pitch:.1,dist:5.6,target:[0,1.05,0],min:2.6,max:10},orbit:{yaw:.7,pitch:.3,dist:15,target:[0,0,0],min:7,max:34},sys:{yaw:0,pitch:.1,dist:13.5,target:[0,-.2,0],min:6,max:26}};
const cam={yaw:.35,pitch:.1,dist:5.6,target:new T.Vector3(0,1.05,0)}, camT={yaw:.35,pitch:.1,dist:5.6,target:new T.Vector3(0,1.05,0),min:2.6,max:10};
let drag=null, auto=!reduce, autoTimer=0;
function goView(v,keepYaw){ const d=VIEWS[v]; camT.yaw=keepYaw?camT.yaw:d.yaw; camT.pitch=d.pitch; camT.dist=d.dist; camT.min=d.min; camT.max=d.max; camT.target.set(...d.target); }
let downAt=null;
cv.addEventListener("pointerdown",e=>{drag={x:e.clientX,y:e.clientY};downAt={x:e.clientX,y:e.clientY};auto=false;clearTimeout(autoTimer);cv.setPointerCapture(e.pointerId);});
cv.addEventListener("pointermove",e=>{if(!drag)return;camT.yaw-=(e.clientX-drag.x)*.006;camT.pitch=clamp(camT.pitch+(e.clientY-drag.y)*.004,-.2,1.2);drag={x:e.clientX,y:e.clientY};});
const ray=new T.Raycaster(), ndc=new T.Vector2();
function pickOrgan(e){
  if(S.view!=="crew") return;
  if(xrAmt<.5){ CP.toast("Switch to X-ray view, then click an organ to see NASA research.","info",3500); return; }
  ndc.set(e.clientX/innerWidth*2-1,-(e.clientY/innerHeight)*2+1); ray.setFromCamera(ndc,camera);
  const hit=ray.intersectObjects(ORG_MESHES.filter(m=>m.parent&&m.parent.visible),false)[0];
  if(!hit) return;
  const name=hit.object.userData.organ, mats=ORG_MESHES.filter(m=>m.userData.organ===name).map(m=>m.material);
  mats.forEach(m=>{m.userData.keep=m.emissiveIntensity;m.emissiveIntensity=3;}); setTimeout(()=>mats.forEach(m=>{m.emissiveIntensity=m.userData.keep||.9;}),700);
  CP.openOrgan&&CP.openOrgan(name);
}
cv.addEventListener("pointerup",e=>{ const moved=downAt?Math.hypot(e.clientX-downAt.x,e.clientY-downAt.y):99; drag=null; downAt=null; autoTimer=setTimeout(()=>{auto=!reduce},4500); if(moved<5) pickOrgan(e); });
cv.addEventListener("wheel",e=>{camT.dist=clamp(camT.dist+e.deltaY*.005*camT.dist/6,camT.min,camT.max);e.preventDefault();},{passive:false});
function updateCam(dt){
  if(auto&&!drag) camT.yaw+=dt*(S.view==="sys"?.05:.1);
  const k=Math.min(1,dt*4);
  cam.yaw+=(camT.yaw-cam.yaw)*k; cam.pitch+=(camT.pitch-cam.pitch)*k; cam.dist+=(camT.dist-cam.dist)*k; cam.target.lerp(camT.target,k);
  camera.position.set(cam.target.x+Math.sin(cam.yaw)*Math.cos(cam.pitch)*cam.dist, cam.target.y+Math.sin(cam.pitch)*cam.dist, cam.target.z+Math.cos(cam.yaw)*Math.cos(cam.pitch)*cam.dist);
  camera.lookAt(cam.target);
}

/* ---------- post-processing (bloom) with safe fallback ---------- */
let composer=null, bloom=null;
function buildComposer(){
  if(!(T.EffectComposer&&T.RenderPass&&T.UnrealBloomPass&&T.ShaderPass&&T.GammaCorrectionShader)){ console.info("Bloom scripts not loaded; using plain rendering"); return; }
  try{
    composer=new T.EffectComposer(renderer); composer.addPass(new T.RenderPass(scene,camera));
    bloom=new T.UnrealBloomPass(new T.Vector2(innerWidth,innerHeight),.5,.65,.82); composer.addPass(bloom);
    composer.addPass(new T.ShaderPass(T.GammaCorrectionShader));
  }catch(e){ console.warn("Bloom disabled",e); composer=null; }
}
buildComposer();
function resize(){ const w=innerWidth,h=innerHeight; renderer.setSize(w,h,false); camera.aspect=w/h; camera.updateProjectionMatrix(); if(composer) composer.setSize(w,h); }
addEventListener("resize",resize); resize();

/* ---------- per-view animation ---------- */
const ecg={buf:new Array(130).fill(0),ph:0,acc:0,n:0};
const pq=(p)=>{const g=(c,w,a)=>a*Math.exp(-Math.pow((p-c)/w,2));return g(.12,.035,.12)+g(.205,.012,-.15)+g(.235,.014,1)+g(.265,.012,-.28)+g(.42,.05,.26);};
function drawChest(v,st,idx,dt){
  ecg.acc+=dt*70; while(ecg.acc>=1){ecg.acc--;ecg.ph=(ecg.ph+(v.hr/60)/70)%1;ecg.buf.push(pq(ecg.ph)+(Math.random()-.5)*.03);ecg.buf.shift();}
  if((ecg.n++)%2) return;
  const g=ecgG,w=256,h=130,c="#"+STATUS[st].toString(16).padStart(6,"0");
  g.fillStyle="#02141c"; g.fillRect(0,0,w,h); g.strokeStyle="rgba(127,233,255,.12)"; g.lineWidth=1;
  for(let x=0;x<w;x+=16){g.beginPath();g.moveTo(x,0);g.lineTo(x,h);g.stroke();} for(let y=0;y<h;y+=16){g.beginPath();g.moveTo(0,y);g.lineTo(w,y);g.stroke();}
  g.beginPath(); ecg.buf.forEach((s,i)=>{const x=i/129*w,y=88-s*44;i?g.lineTo(x,y):g.moveTo(x,y);}); g.strokeStyle=c; g.lineWidth=2.4; g.stroke();
  g.fillStyle=c; g.font="600 24px Arial"; g.fillText(S.sel,8,26); g.textAlign="right"; g.fillText(Math.round(v.hr)+" bpm",w-8,26);
  g.fillStyle="#d6eef6"; g.font="20px Arial"; g.textAlign="left"; g.fillText("SpO2 "+Math.round(v.spo2)+"%",8,h-8); g.textAlign="right"; g.fillText("HI "+idx,w-8,h-8); g.textAlign="left";
  ecgTex.needsUpdate=true;
}
function updateIdPatch(){ if(idTexVal===S.sel) return; idTexVal=S.sel; idG.fillStyle="#1fd6bd"; idG.fillRect(0,0,128,80); idG.fillStyle="#04222b"; idG.font="700 44px Arial"; idG.textAlign="center"; idG.fillText(S.sel,64,50); idG.font="600 13px Arial"; idG.fillText("CREW",64,70); idTex.needsUpdate=true; }
let hrPh=0,rsPh=0,tt=0,last=performance.now(); const tmpC=new T.Color(), lungOk=col(0x9fe8ff), lungBad=col(0xff5c6c), brOk=col(0xffa0b4), brHot=col(0xff8a3d);
function frameCrew(dt,c,v,st){
  updateIdPatch();
  hrPh+=dt*(v.hr/60)*6.283; rsPh+=dt*(v.resp/60)*6.283;
  const beat=Math.pow(Math.max(0,Math.sin(hrPh)),6), br=.5+.5*Math.sin(rsPh);
  heart.scale.setScalar(1+.4*beat); heartGlow.material.opacity=(.25+.55*beat); heartMat.emissiveIntensity=.7+1.4*beat; vesselMat.emissiveIntensity=.6+1.2*beat;
  [lungL,lungR].forEach(l=>l.scale.set(1+.1*br,1.9+.14*br,.9+.08*br));
  tmpC.copy(lungOk).lerp(lungBad,clamp((97-v.spo2)/9,0,1)); lungMat.color.copy(tmpC); lungMat.emissive.copy(tmpC).multiplyScalar(.6);
  tmpC.copy(brOk).lerp(brHot,clamp((v.temp-36.8)/2,0,1)); brainMat.color.copy(tmpC);
  torso.scale.set(1+.012*br,1,.84*(1+.02*br));
  A.position.y=.05+Math.sin(tt*.9)*.014; A.rotation.y=Math.sin(tt*.35)*.06;
  const sc=STATUS[st]; pRing.material.color.setHex(sc); beam.material.color.setHex(sc);
  leds[0].color.setHex(st==="ok"?0x6cffc1:0x333b40); leds[1].color.setHex(st==="warning"?0xffb547:0x333b40); leds[2].color.setHex(st==="critical"?0xff5c6c:0x333b40);
  radShell.material.opacity=clamp(v.radiation/10,0,1)*.28; radShell.rotation.y+=dt*.3;
  const sy=.1+(.5+.5*Math.sin(tt*.7))*2.15; scanDisc.position.y=scanRing.position.y=sy; scanRing.material.opacity=.5+.4*Math.sin(tt*3);
  applySuitFade(dt); drawChest(v,st,c.index==null?100:c.index,dt);
  Object.keys(vtags).forEach(k=>{
    const [x,y,ok]=proj(anchors[k]), d=vtags[k], o=vOff[k], lo=CP.S.limits[k]||[META[k].safe[0],META[k].safe[1]], bad=v[k]<lo[0]&&lo[0]>-1||v[k]>lo[1];
    d.className="tag3d v"+(bad?" warning":"")+(S.view==="crew"?"":" hidden"); d.textContent=`${META[k].name} ${v[k]} ${META[k].unit}`; place(d,x,y,ok,o[0],o[1]);
  });
}
function frameOrbit(dt){
  stAng+=dt*(reduce?.02:.16); earthGroup.rotation.y+=dt*.02; clouds.rotation.y+=dt*.006;
  stPivot.position.set(Math.cos(stAng)*OR,0,Math.sin(stAng)*OR); station.rotation.y=-stAng+Math.PI/2; station.rotation.z=Math.sin(tt*.3)*.05;
  wings.forEach(w=>w.rotation.x=Math.sin(tt*.2)*.12);
  navR.material.opacity=navG.material.opacity=.4+.5*Math.abs(Math.sin(tt*2.2));
  stPivot.getWorldPosition(wp); gs.getWorldPosition(wq);
  const mid=wp.clone().add(wq).multiplyScalar(.5); mid.setLength(Math.max(mid.length()+2.4,6)); arc.v0.copy(wp); arc.v1.copy(mid); arc.v2.copy(wq);
  const pa=beamGeo.attributes.position; for(let i=0;i<=BN;i++){arc.getPoint(i/BN,tv);pa.setXYZ(i,tv.x,tv.y,tv.z);} pa.needsUpdate=true; beamGeo.computeBoundingSphere();
  const up=S.link; beamUp.visible=up; beamDown.visible=!up; if(!up) beamDown.computeLineDistances();
  bead.forEach((b,i)=>{ b.visible=up; if(up){arc.getPoint(((tt*.35+i/bead.length)%1),b.position);} });
  const n=up?0:clamp(Math.floor(((Date.now()-(S.cutAt||Date.now()))/1000)*Math.max(1,Object.keys(S.crew).length)/6),1,24);
  cubes.forEach((m,i)=>{ m.visible=i<n; if(i<n){const a=tt*1.2+i*.9; m.position.copy(wp).add(new T.Vector3(Math.cos(a)*.6,Math.sin(a*1.3)*.25,Math.sin(a)*.6)); m.rotation.set(a,a*.7,0);} });
  pulseR.scale.setScalar(1+((tt*.8)%1)*1.6); pulseR.material.opacity=.8*(1-((tt*.8)%1)); pin.material.color.setHex(up?0x6cffc1:0xff5c6c); pulseR.material.color.setHex(up?0x6cffc1:0xff5c6c);
  let [x,y,ok]=proj(wp,new T.Vector3(0,.55,0)); place(otag.st,x,y,ok,0,0); otag.st.textContent=`Space station, ${Object.keys(S.crew).length} crew`;
  [x,y,ok]=proj(wq,new T.Vector3(0,.0,0)); place(otag.gs,x,y,ok,0,22);
  [x,y,ok]=proj(arc.getPoint(.5,tv).clone()); place(otag.lk,x,y,ok,0,0);
  otag.lk.style.borderColor=up?"#6cffc1":"#ff5c6c"; otag.lk.style.color=up?"#6cffc1":"#ff9aa4";
  otag.lk.textContent=up?`Link up, ${S.counts.accepted} packets verified`:`Link down, buffering about ${n*6} packets`;
}
function frameSys(dt){
  const a=S.agents||{engine:"agents",llm:["rules"],memory:"local"}, st=S.counts;
  const set=(id,t)=>{const s=ntags[id].querySelector("small"); if(s.textContent!==t) s.textContent=t;};
  set("sensor",`${Object.keys(S.crew).length} crew, Ed25519 signed`); set("verify",`${st.accepted} verified, ${st.rejected} blocked`); set("vault",`${S.records} records, AES-256-GCM`);
  set("detect","limits, z-score, ML, forecast"); set("agents",`${a.engine}`); set("llm",a.llm.join(" > ")); set("memory",a.memory); set("dash","live charts, voice, report"); set("reject",`${st.rejected} blocked`); set("mcp","other AI tools connect here");
  Object.entries(NODES).forEach(([id,n])=>{
    n.shell.rotation.y+=dt*.6; n.shell.rotation.x+=dt*.2; n.ring.rotation.z+=dt*.8; n.pulse=Math.max(0,n.pulse-dt*2.2);
    n.group.scale.setScalar(1+.45*n.pulse); n.shell.material.color.copy(n.base).lerp(n.flash,n.pulse); n.core.material.emissive.copy(n.shell.material.color);
    const [x,y,ok]=proj(n.pos,new T.Vector3(0,-.75,0)); place(ntags[id],x,y,ok,0,0);
  });
  for(let i=packets.length-1;i>=0;i--){ const p=packets[i],a2=NODES[p.chain[p.i]].pos,b2=NODES[p.chain[p.i+1]].pos; p.t+=dt*1.6; p.m.position.lerpVectors(a2,b2,Math.min(1,p.t));
    if(p.t>=1){p.i++;p.t=0;pulse(p.chain[p.i]); if(p.i>=p.chain.length-1){sysG.remove(p.m);p.m.material.dispose();packets.splice(i,1);}} }
}
function frame(now){
  const dt=Math.min(.05,(now-last)/1000); last=now; tt+=dt; updateCam(dt);
  const c=S.crew[S.sel]||{}, v=c.vitals||{hr:66,spo2:98,temp:36.6,resp:14,radiation:.3}, st=c.status||"ok";
  if(S.view==="crew") frameCrew(dt,c,v,st); else if(S.view==="orbit") frameOrbit(dt); else frameSys(dt);
  if(composer&&useBloom) composer.render(); else renderer.render(scene,camera);
  requestAnimationFrame(frame);
}

/* ---------- hooks used by the console and the tour ---------- */
const H=CP.hooks;
H.setView=function(v){
  crewG.visible=v==="crew"; orbitG.visible=v==="orbit"; sysG.visible=v==="sys"; sun.castShadow=v==="crew"; keyPoint.visible=v==="crew";
  Object.values(vtags).forEach(d=>d.classList.toggle("hidden",v!=="crew")); Object.values(ntags).forEach(d=>d.classList.toggle("hidden",v!=="sys")); Object.values(otag).forEach(d=>d.classList.toggle("hidden",v!=="orbit"));
  if(bloom) bloom.strength=v==="crew"?.42:v==="orbit"?.6:.85;
  goView(v);
};
H.setSuit=setSuit; H.vitals=()=>{ flowVitals(); }; H.reject=()=>flowReject(); H.alert=m=>flowAlert(m.severity); H.pulseNode=pulse; H.select=()=>{};
H.link=m=>{ if(!m.up) S.cutAt=Date.now(); };
H.cam=function(o){ if(o.yaw!=null)camT.yaw=o.yaw; if(o.pitch!=null)camT.pitch=o.pitch; if(o.dist!=null)camT.dist=o.dist; if(o.target)camT.target.set(o.target[0],o.target[1],o.target[2]); auto=false; clearTimeout(autoTimer); autoTimer=setTimeout(()=>{auto=!reduce},6000); };
H.setBloom=on=>{ useBloom=!!on; };
H.setQuality=q=>{ qual=q; const Q=QUAL[q]||QUAL.high; renderer.setPixelRatio(Math.min(devicePixelRatio,Q.pr)); resize();
  sun.shadow.mapSize.set(Q.shadow,Q.shadow); if(sun.shadow.map){sun.shadow.map.dispose();sun.shadow.map=null;} renderer.shadowMap.enabled=q!=="low"; suitMats.forEach(m=>m.needsUpdate=true);
  if(q==="low"){ useBloom=false; $("optBloom").checked=false; } };
H.setView(S.view||"crew"); setSuit("suit");
requestAnimationFrame(frame);
})();
