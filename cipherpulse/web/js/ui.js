"use strict";
/* CipherPulse console: data, panels, controls, voice. Shared via window.CP */
(function(){
const $=id=>document.getElementById(id);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const KEYS=["hr","spo2","temp","resp","radiation"];
const META={
  hr:{name:"Heart rate",unit:"bpm",lo:40,hi:140,safe:[50,105]},
  spo2:{name:"Blood oxygen",unit:"%",lo:85,hi:100,safe:[94,100]},
  temp:{name:"Temperature",unit:"\u00b0C",lo:35,hi:40,safe:[35.8,37.9]},
  resp:{name:"Breathing",unit:"/min",lo:8,hi:30,safe:[9,22]},
  radiation:{name:"Radiation",unit:"\u00b5Sv/h",lo:0,hi:10,safe:[0,3]}
};
const KIND={air_quality:"Possible cabin air problem",exertion:"Exertion",fever_pattern:"Fever pattern",radiation_event:"Radiation event",low_oxygen:"Low blood oxygen",ml_anomaly:"Unusual vitals (ML)",security:"Security block",
  trend_spo2:"Early warning: oxygen falling",trend_hr:"Early warning: heart rate rising",trend_temp:"Early warning: temperature rising",trend_radiation:"Early warning: radiation rising"};
const RT={forged_or_modified:"Forged or modified",replay:"Replayed",sensor_fault:"Impossible values (sensor fault)",stale:"Stale timestamp",unknown_device:"Unknown device",malformed:"Malformed"};
const COLHEX={ok:"#7fe9ff",warning:"#ffb547",critical:"#ff5c6c"};
const CREWCOL={A1:"#7fe9ff",A2:"#ffb547",A3:"#6cffc1",A4:"#c48bff"};
const S={crew:{},series:{},alerts:[],counts:{accepted:0,rejected:0},rtypes:{},rlog:[],link:true,queued:0,records:0,agents:null,
  phase:"orbit",phases:["orbit"],dose:{},doseBudget:2000,limits:{},defaults:{},sel:"A1",view:"crew",tab:"live",suit:"suit"};
const CP=window.CP={S,$,esc,clamp,META,KEYS,COLHEX,hooks:{}};
const kindName=k=>KIND[k]||(k||"").replace(/_/g," ");
CP.kindName=kindName;

/* ---------- feedback: toast, beep, speech ---------- */
function toast(msg,kind,ms){
  const box=$("toasts"); const d=document.createElement("div"); d.className="toast "+(kind||"info"); d.textContent=msg;
  box.appendChild(d); while(box.children.length>4) box.firstChild.remove();
  setTimeout(()=>d.remove(),ms||5000);
}
CP.toast=toast;
let actx=null;
addEventListener("pointerdown",()=>{
  if(!actx){try{actx=new (window.AudioContext||window.webkitAudioContext)();}catch(e){}}
  if(actx&&actx.state==="suspended") actx.resume();
});
function beep(kind){
  if(!actx||!$("optSound").checked) return;
  const seq={info:[660],warning:[520,440],critical:[880,660,880]}[kind]||[600], t=actx.currentTime;
  seq.forEach((fr,i)=>{const o=actx.createOscillator(),g=actx.createGain();o.type="sine";o.frequency.value=fr;
    g.gain.setValueAtTime(.0001,t+i*.14);g.gain.exponentialRampToValueAtTime(.07,t+i*.14+.02);g.gain.exponentialRampToValueAtTime(.0001,t+i*.14+.13);
    o.connect(g);g.connect(actx.destination);o.start(t+i*.14);o.stop(t+i*.14+.14);});
}
function speak(t,force){
  if(!(force||$("voiceOn").checked)||!(window.speechSynthesis&&window.SpeechSynthesisUtterance)) return;
  const u=new SpeechSynthesisUtterance(t); u.rate=1.03; speechSynthesis.cancel(); speechSynthesis.speak(u);
}
CP.speak=speak; CP.beep=beep;
const post=(url,body)=>fetch(url,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body||{})}).then(r=>r.json()).catch(()=>({}));
CP.post=post;

/* ---------- navigation ---------- */
CP.setTab=function(t){
  S.tab=t;
  document.querySelectorAll(".tabs button").forEach(b=>b.classList.toggle("on",b.dataset.tab===t));
  document.querySelectorAll(".pane").forEach(p=>p.classList.toggle("on",p.id==="tab-"+t));
  if(t==="analytics"){renderAnalytics();drawChart();} if(t==="security") renderSecurity(); if(t==="settings") renderSettings();
};
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>CP.setTab(b.dataset.tab));
CP.setView=function(v){
  S.view=v;
  [["vCrew","crew"],["vOrbit","orbit"],["vSys","sys"]].forEach(([id,n])=>$(id).classList.toggle("on",n===v));
  $("suitModes").classList.toggle("hidden",v!=="crew");
  CP.hooks.setView&&CP.hooks.setView(v);
};
$("vCrew").onclick=()=>CP.setView("crew"); $("vOrbit").onclick=()=>CP.setView("orbit"); $("vSys").onclick=()=>CP.setView("sys");
CP.setSuit=function(m){
  S.suit=m; [["mSuit","suit"],["mXray","xray"],["mHolo","holo"]].forEach(([id,n])=>$(id).classList.toggle("on",n===m));
  CP.hooks.setSuit&&CP.hooks.setSuit(m);
};
$("mSuit").onclick=()=>CP.setSuit("suit"); $("mXray").onclick=()=>CP.setSuit("xray"); $("mHolo").onclick=()=>CP.setSuit("holo");
CP.select=function(a){
  if(!S.crew[a]) return; S.sel=a; renderCrew(); renderVitals(true); drawChart();
  CP.hooks.select&&CP.hooks.select(a);
};
$("btnReport").onclick=()=>window.open("/api/report","_blank");
$("btnCsv").onclick=()=>window.open("/api/export/"+S.sel+".csv","_blank");
$("btnTour").onclick=()=>CP.tour&&CP.tour.start(); $("btnTour2").onclick=()=>CP.tour&&CP.tour.start();

/* ---------- crew cards and vitals ---------- */
function renderCrew(){
  const box=$("crew"); box.innerHTML="";
  Object.keys(S.crew).forEach(a=>{
    const c=S.crew[a], v=c.vitals, dose=S.dose[a]||0, pct=clamp(dose/S.doseBudget*100,0,100), idx=c.index==null?100:c.index;
    const b=document.createElement("button");
    b.className="card "+c.status+(a===S.sel?" sel":"");
    b.title="Select "+a+" (shown in the 3D view and the Live tab)";
    b.innerHTML=`<div class="top"><b>${a}${c.buffered?'<span class="tagd">delayed data</span>':""}</b><span class="idx" style="color:${idx<60?"#ff5c6c":idx<85?"#ffb547":"#6cffc1"}">${idx}</span></div>
      <small>${v?`${v.hr} bpm, ${v.spo2}% O2, ${v.temp}\u00b0C`:"waiting for data"}</small>
      <small>${c.status==="ok"?"Normal":kindName(c.kind)}</small>
      <div class="bar ${idx<60?"bad":""}" title="Health index ${idx} of 100"><i style="width:${idx}%"></i></div>
      <small>Radiation dose ${Math.round(dose)} of ${S.doseBudget} \u00b5Sv</small><div class="bar dose"><i style="width:${pct}%"></i></div>`;
    b.onclick=()=>CP.select(a);
    box.appendChild(b);
  });
}
function ser(a){ return S.series[a]||(S.series[a]={hr:[],spo2:[],temp:[],resp:[],radiation:[],mark:[]}); }
function renderVitals(rebuild){
  const box=$("vitals"); $("vTitle").innerHTML="Vitals for "+S.sel+'<span class="origin" title="These readings come from the demo simulator, not from real astronauts">SIMULATED_DEMO</span>';
  if(rebuild||!box.children.length){
    box.innerHTML="";
    KEYS.forEach(k=>{const r=document.createElement("div");r.className="vital";
      r.innerHTML=`<span>${META[k].name}</span><canvas width="170" height="28" id="sp_${k}"></canvas><b id="vv_${k}">-</b>`;box.appendChild(r);});
  }
  const c=S.crew[S.sel]||{}, v=c.vitals, s=ser(S.sel);
  KEYS.forEach(k=>{
    const el=$("vv_"+k); if(el) el.textContent=v?`${v[k]} ${META[k].unit}`:"-";
    const cv=$("sp_"+k); if(cv) spark(cv,s[k],k,c.status||"ok");
  });
}
function lim(k){ const l=S.limits[k]; return l?[Math.max(l[0],META[k].lo),l[1]>=META[k].hi?META[k].hi:l[1]]:META[k].safe; }
function spark(cv,arr,k,status){
  const m=META[k],g=cv.getContext("2d"),w=cv.width,h=cv.height; g.clearRect(0,0,w,h);
  const y=x=>h-3-(clamp(x,m.lo,m.hi)-m.lo)/(m.hi-m.lo)*(h-6), sf=lim(k);
  g.fillStyle="rgba(108,255,193,.09)"; g.fillRect(0,y(sf[1]),w,Math.max(1,y(sf[0])-y(sf[1])));
  if(arr.length<2) return;
  g.beginPath(); arr.forEach((x,i)=>{const px=(i+90-arr.length)/89*w; i?g.lineTo(px,y(x)):g.moveTo(px,y(x));});
  g.strokeStyle=COLHEX[status]; g.lineWidth=1.6; g.stroke();
}

/* ---------- alerts ---------- */
function renderAlerts(){
  const box=$("alerts");
  if(!S.alerts.length){box.innerHTML='<p class="empty">No alerts yet. Start a scenario below and watch the agents work.</p>';return;}
  box.innerHTML=S.alerts.slice(0,14).map(a=>`
    <div class="alert ${a.severity} ${a.kind&&a.kind.startsWith("trend_")?"trend":""} ${a.kind==="security"?"security":""}">
      <h3><span>${a.astro}: ${kindName(a.kind)}</span><em>${a.provider||"..."}${a.engine&&a.engine!=="gateway"?" via "+a.engine:""}</em></h3>
      <div>${esc(a.explanation||"")}</div>
      ${(a.actions&&a.actions.length)?"<ul>"+a.actions.map(x=>`<li>${esc(x)}</li>`).join("")+"</ul>":""}
    </div>`).join("");
}
function upsertAlert(m){
  const rec={id:m.id,astro:m.astro,kind:m.kind,severity:m.severity,explanation:m.explanation,actions:m.actions,provider:m.provider,engine:m.engine,eta:m.eta,t:m.t||Date.now()};
  const i=S.alerts.findIndex(a=>a.id===m.id);
  if(i>=0) S.alerts[i]={...S.alerts[i],...rec,t:S.alerts[i].t}; else S.alerts.unshift(rec);
  renderAlerts(); if(S.tab==="analytics") renderAnalytics();
}

/* ---------- analytics ---------- */
function renderAnalytics(){
  const sel=$("anVital"); if(!sel.options.length){KEYS.forEach(k=>{const o=document.createElement("option");o.value=k;o.textContent=META[k].name;sel.appendChild(o);}); sel.onchange=drawChart;}
  $("anLegend").innerHTML=Object.keys(S.crew).map(a=>`<span><i style="background:${CREWCOL[a]||"#fff"}"></i>${a}</span>`).join("")+'<span>Dots mark alerts</span>';
  $("anIndex").innerHTML=Object.keys(S.crew).map(a=>{const i=S.crew[a].index==null?100:S.crew[a].index;
    return `<div class="mini"><span>${a}</span><div class="bar ${i<60?"bad":""}"><i style="width:${i}%"></i></div><span>${i}</span></div>`}).join("");
  $("anDose").innerHTML=Object.keys(S.crew).map(a=>{const d=S.dose[a]||0,p=clamp(d/S.doseBudget*100,0,100);
    return `<div class="mini"><span>${a}</span><div class="bar dose ${p>80?"bad":""}"><i style="width:${p}%"></i></div><span>${Math.round(d)} \u00b5Sv</span></div>`}).join("");
  const w=S.alerts.filter(a=>a.kind&&a.kind.startsWith("trend_")).slice(0,5);
  $("anWarn").innerHTML=w.length?w.map(a=>`<div class="alert trend"><h3><span>${a.astro}: ${kindName(a.kind)}</span><em>${a.eta?"limit in about "+a.eta+" s":""}</em></h3><div>${esc(a.explanation||"")}</div></div>`).join(""):'<p class="empty">None yet. The system predicts when a vital will cross its limit.</p>';
}
function drawChart(){
  if(S.tab!=="analytics") return;
  const cv=$("anChart"); if(!cv) return; const g=cv.getContext("2d"),w=cv.width,h=cv.height; g.clearRect(0,0,w,h);
  const k=$("anVital").value||"hr", m=META[k], P={l:40,r:10,t:10,b:18};
  const y=x=>h-P.b-(clamp(x,m.lo,m.hi)-m.lo)/(m.hi-m.lo)*(h-P.t-P.b), X=(i,n)=>P.l+(i+90-n)/89*(w-P.l-P.r), sf=lim(k);
  g.fillStyle="rgba(108,255,193,.1)"; g.fillRect(P.l,y(sf[1]),w-P.l-P.r,Math.max(1,y(sf[0])-y(sf[1])));
  g.strokeStyle="rgba(127,233,255,.12)"; g.fillStyle="#85a8b7"; g.font="20px Chakra Petch, sans-serif"; g.lineWidth=1;
  for(let i=0;i<=4;i++){const v=m.lo+(m.hi-m.lo)*i/4,yy=y(v);g.beginPath();g.moveTo(P.l,yy);g.lineTo(w-P.r,yy);g.stroke();g.fillText(String(Math.round(v*10)/10),2,yy+6);}
  Object.keys(S.crew).forEach(a=>{
    const s=ser(a),arr=s[k]; if(arr.length<2) return;
    g.beginPath(); arr.forEach((v,i)=>{const px=X(i,arr.length);i?g.lineTo(px,y(v)):g.moveTo(px,y(v));});
    g.strokeStyle=CREWCOL[a]||"#fff"; g.lineWidth=a===S.sel?3:1.6; g.globalAlpha=a===S.sel?1:.7; g.stroke(); g.globalAlpha=1;
    s.mark.forEach((mk,i)=>{ if(mk&&i<arr.length){g.beginPath();g.arc(X(i,arr.length),y(arr[i]),5,0,6.283);g.fillStyle=mk===2?"#ff5c6c":"#ffb547";g.fill();}});
  });
}

/* ---------- security ---------- */
function renderSecurity(){
  $("secAcc").textContent=S.counts.accepted; $("secRej").textContent=S.counts.rejected; $("secRec").textContent=S.records;
  const e=Object.entries(S.rtypes), mx=Math.max(1,...e.map(x=>x[1]));
  $("secTypes").innerHTML=e.length?e.map(([k,n])=>`<div class="mini"><span style="grid-column:span 1;white-space:normal">${RT[k]||k}</span><div class="bar bad"><i style="width:${n/mx*100}%"></i></div><span>${n}</span></div>`).join(""):'<p class="empty">Nothing blocked yet. Try an attack from the bottom bar.</p>';
  $("secLog").innerHTML=S.rlog.length?S.rlog.slice(0,8).map(r=>`<div>${r.astro}: ${esc(r.reason)}</div>`).join(""):'<span class="empty">None.</span>';
}

/* ---------- settings + learn ---------- */
function renderSettings(){
  const t=$("limTable"); if(!Object.keys(S.limits).length) return;
  if(t.dataset.built!=="1"||t.dataset.stamp!==JSON.stringify(S.limits)){
    t.innerHTML="<tr><th></th><th>Warn low</th><th>Warn high</th><th>Crit low</th><th>Crit high</th></tr>"+KEYS.map(k=>
      `<tr><td>${META[k].name}</td>${[0,1,2,3].map(i=>`<td><input class="in" type="number" step="any" id="lim_${k}_${i}" value="${S.limits[k][i]}" aria-label="${META[k].name} limit ${i+1}"></td>`).join("")}</tr>`).join("");
    t.dataset.built="1"; t.dataset.stamp=JSON.stringify(S.limits);
  }
}
$("btnLimSave").onclick=async()=>{
  const out={}; KEYS.forEach(k=>out[k]=[0,1,2,3].map(i=>parseFloat($(`lim_${k}_${i}`).value)));
  const r=await post("/api/limits",{limits:out}); if(r.limits){S.limits=r.limits; toast("Alert limits saved. New readings use them immediately.","info");}
};
$("btnLimReset").onclick=async()=>{const r=await post("/api/limits",{reset:true}); if(r.limits){S.limits=r.limits; renderSettings(); toast("Limits reset to defaults.","info");}};
function fillPhases(){
  [$("phaseSel"),$("phaseSel2")].forEach(sel=>{
    if(sel.options.length!==S.phases.length){sel.innerHTML=S.phases.map(p=>`<option value="${p}">${{orbit:"Orbit (normal)",launch:"Launch",eva:"Spacewalk (EVA)",sleep:"Sleep"}[p]||p}</option>`).join("");}
    sel.value=S.phase;
    sel.onchange=()=>post("/api/phase",{name:sel.value});
  });
}
$("optBloom").onchange=e=>CP.hooks.setBloom&&CP.hooks.setBloom(e.target.checked);
$("optQuality").onchange=e=>CP.hooks.setQuality&&CP.hooks.setQuality(e.target.value);
const GLOSS=[
 ["Heart rate and SpO2","Heart rate is how many times the heart beats per minute. SpO2 is the percentage of oxygen in the blood; below about 94% needs attention."],
 ["Digital signature (Ed25519)","Each wearable has a secret key. It signs every reading like a tamper-proof stamp. The gateway checks the stamp with the matching public key. Fake or edited packets fail the check."],
 ["Replay attack","An attacker records a real, correctly signed packet and sends it again later. We block it because every packet has a sequence number that must always go up."],
 ["Encryption at rest (AES-256-GCM)","Stored data is scrambled with a secret key. Without the key it is unreadable, and GCM also detects if anyone changes even one byte."],
 ["Hash chain","Each stored record includes a fingerprint of the previous record, like links in a chain. Change or delete one record and every fingerprint after it stops matching, so the exact spot is found."],
 ["Anomaly detection","Four layers: safe limits, comparison with the person's own recent baseline (z-score), an Isolation Forest machine-learning model for unusual combinations, and a pattern check that tells CO2 problems from normal exercise."],
 ["Early warning (forecast)","The system fits a trend line to the last 25 seconds. If a vital is heading toward its limit within about 45 seconds, it warns you before the limit is crossed."],
 ["Health index","A 0 to 100 score per astronaut. It drops the further vitals drift from their safe range, plus a penalty when the ML model sees something unusual."],
 ["Mission phases","What is normal changes: during launch or a spacewalk the heart works harder. Choosing the phase relaxes warning limits so you do not get false alarms."],
 ["Offline-first","Space links drop. The wearable keeps recording, stores signed readings in a queue, and sends them in order when contact returns. They show as delayed data."],
 ["AI agents (LangGraph)","When an alert fires, a small team of steps runs: recall past events, ask a language model to explain, apply safety rules, then remember the event. If no AI key is set, built-in rules explain it."],
 ["MCP and A2A","MCP lets other AI tools (like Claude Desktop) read this system's data safely. A2A lets other AI agents talk to this one. Both are included."],
 ["Radiation budget","Radiation adds up over time. The bars show each astronaut's dose against a demo budget. One real second here equals one simulated hour."]
];
$("learnList").innerHTML=GLOSS.map(([t,p])=>`<details><summary>${t}</summary><p>${p}</p></details>`).join("");

/* ---------- stats / badges ---------- */
function renderStats(){
  ["sAcc","secAcc"].forEach(i=>$(i)&&($(i).textContent=S.counts.accepted)); ["sRej","secRej"].forEach(i=>$(i)&&($(i).textContent=S.counts.rejected));
  ["sRec","secRec"].forEach(i=>$(i)&&($(i).textContent=S.records));
  const b=$("linkBadge"); b.className="badge "+(S.link?"ok":"down");
  b.textContent=S.link?"Link to Earth is up":`Link down, buffering${S.queued?" ("+S.queued+" queued)":""}`;
  if(S.agents) $("agentBadge").textContent=`Agents: ${S.agents.engine}, models: ${S.agents.llm.join(" > ")}, memory: ${S.agents.memory}`;
}

/* ---------- controls ---------- */
document.querySelectorAll("[data-s]").forEach(b=>b.onclick=()=>post("/api/control",{cmd:"scenario",astro:S.sel,name:b.dataset.s}));
document.querySelectorAll("[data-a]").forEach(b=>b.onclick=()=>post("/api/control",{cmd:"spoof",astro:S.sel,kind:b.dataset.a}));
$("tamper").onclick=()=>post("/api/control",{cmd:"tamper"});
$("restore").onclick=()=>post("/api/control",{cmd:"restore"});
$("cut").onclick=()=>post("/api/control",{cmd:"link",up:false});
$("mend").onclick=()=>post("/api/control",{cmd:"link",up:true});
$("chain").onclick=()=>post("/api/integrity/verify");
CP.act=(name,arg)=>{
  if(name==="scenario") return post("/api/control",{cmd:"scenario",astro:S.sel,name:arg});
  if(name==="spoof") return post("/api/control",{cmd:"spoof",astro:S.sel,kind:arg});
  if(name==="link") return post("/api/control",{cmd:"link",up:!!arg});
  if(name==="tamper") return post("/api/control",{cmd:"tamper"});
  if(name==="restore") return post("/api/control",{cmd:"restore"});
  if(name==="verify") return post("/api/integrity/verify");
  if(name==="phase") return post("/api/phase",{name:arg});
};
function showIntegrity(m){
  const b=$("chain"); b.className="chain "+(m.ok?"ok":"bad");
  b.textContent=m.ok?`Chain intact: ${m.checked} records verified`:`Chain broken at record ${m.broken_at}: ${m.reason}`;
  if(!m.ok){speak("Warning. Stored data has been tampered with.");toast("Tamper detected in the vault at record "+m.broken_at,"critical",7000);beep("critical");}
  CP.hooks.pulseNode&&CP.hooks.pulseNode("vault",m.ok?0x6cffc1:0xff5c6c);
}

/* ---------- voice and chat ---------- */
function localCommand(t){
  const q=t.toLowerCase();
  if(/(start|begin|play|open).*(tour|tutorial|walkthrough|demo)|guide me/.test(q)){CP.tour&&CP.tour.start();return "Starting the guided tour.";}
  if(/(stop|close|end).*(tour|tutorial)/.test(q)){CP.tour&&CP.tour.close();return "Tour closed.";}
  if(/x-?ray|bones|organs/.test(q)){CP.setView("crew");CP.setSuit("xray");return "X-ray view on. You can see the skeleton and organs responding to live vitals.";}
  if(/holo|wireframe/.test(q)){CP.setView("crew");CP.setSuit("holo");return "Hologram view on.";}
  if(/(suit|normal) view|spacesuit/.test(q)){CP.setView("crew");CP.setSuit("suit");return "Suit view on.";}
  if(/orbit|earth|station/.test(q)&&/show|go|open|view/.test(q)){CP.setView("orbit");return "Showing the station in orbit and the link to Earth.";}
  if(/system|pipeline|architecture/.test(q)&&/show|go|open|view/.test(q)){CP.setView("sys");return "Showing how data flows through the system.";}
  if(/(show|select|open|go to)\s+a([1-9])/.test(q)){const a=("A"+q.match(/a([1-9])/)[1]);if(S.crew[a]){CP.setView("crew");CP.select(a);return "Showing "+a+".";}}
  if(/report/.test(q)&&/(open|show|make|generate|create)/.test(q)){window.open("/api/report","_blank");return "Opening the mission report. Press Control P to save it as a PDF.";}
  return null;
}
async function ask(text){
  if(!text) return; $("reply").textContent="Thinking...";
  const local=localCommand(text); if(local){$("reply").textContent=local;speak(local);return;}
  try{const j=await post("/api/chat",{text}); const r=j.reply||"No answer."; $("reply").textContent=r; speak(r);}
  catch(e){$("reply").textContent="Could not reach the gateway. Is CipherPulse still running?";}
}
CP.ask=ask;
$("send").onclick=()=>{ask($("q").value);$("q").value=""};
$("q").addEventListener("keydown",e=>{if(e.key==="Enter"){ask($("q").value);$("q").value=""}});
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
$("mic").onclick=()=>{
  if(!SR){$("reply").textContent="Voice input needs Chrome or Edge. You can type instead.";return;}
  const r=new SR(); r.lang="en-US"; r.interimResults=false;
  r.onresult=e=>{const t=e.results[0][0].transcript;$("reply").textContent="You said: "+t;ask(t)};
  r.onend=()=>$("mic").classList.remove("on"); r.onerror=()=>$("mic").classList.remove("on");
  $("mic").classList.add("on"); r.start();
};

/* ---------- websocket ---------- */
let lastSpoke=0, lastCrewRender=0, lastAn=0;
function applySnapshot(m){
  S.crew=m.crew; S.counts=m.counts; S.link=m.link_up; S.records=m.records; S.agents=m.agents; S.phase=m.phase; S.phases=m.phases||S.phases;
  S.dose=m.dose||{}; S.doseBudget=m.dose_budget||2000; S.rtypes=m.rtypes||{}; S.limits=m.limits||{}; S.defaults=m.defaults||{};
  S.alerts=(m.alerts||[]).map(a=>({id:a.id,astro:a.astro,kind:a.kind,severity:a.severity,explanation:a.explanation,actions:a.actions,provider:a.provider,engine:a.engine,t:(a.at||0)*1000}));
  if(!S.crew[S.sel]) S.sel=Object.keys(S.crew)[0];
  fillPhases(); renderCrew(); renderVitals(true); renderAlerts(); renderStats(); renderSecurity();
  CP.hooks.select&&CP.hooks.select(S.sel);
}
function connect(){
  const ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws/dashboard");
  ws.onmessage=ev=>{
    const m=JSON.parse(ev.data), now=Date.now();
    if(m.type==="snapshot") applySnapshot(m);
    else if(m.type==="vitals"){
      const c=S.crew[m.astro]||(S.crew[m.astro]={});
      Object.assign(c,{vitals:m.vitals,status:m.status,kind:m.kind,buffered:m.buffered,index:m.index});
      S.dose[m.astro]=m.dose; S.counts=m.counts; S.records++;
      const s=ser(m.astro); KEYS.forEach(k=>{s[k].push(m.vitals[k]); if(s[k].length>90) s[k].shift();});
      s.mark.push(0); if(s.mark.length>90) s.mark.shift();
      renderStats();
      if(m.astro===S.sel) renderVitals(false);
      if(now-lastCrewRender>700){lastCrewRender=now;renderCrew();}
      if(now-lastAn>600){lastAn=now; if(S.tab==="analytics"){renderAnalytics();drawChart();} if(S.tab==="security") renderSecurity();}
      CP.hooks.vitals&&CP.hooks.vitals(m);
    }else if(m.type==="alert"){
      const s=ser(m.astro); if(s.mark.length) s.mark[s.mark.length-1]=m.severity==="critical"?2:1;
      upsertAlert({...m,t:now});
      if($("optToast").checked) toast(`${m.astro}: ${kindName(m.kind)}`,m.severity==="critical"?"critical":"warning");
      beep(m.severity==="critical"?"critical":"warning");
      CP.hooks.alert&&CP.hooks.alert(m);
    }else if(m.type==="agent"){
      upsertAlert(m);
      if(m.severity==="critical"&&now-lastSpoke>8000){lastSpoke=now;speak(`${m.astro}. ${m.explanation}`);}
    }else if(m.type==="reject"){
      S.counts=m.counts; S.rtypes=m.rtypes||S.rtypes; S.rlog.unshift({astro:m.astro,reason:m.reason}); S.rlog=S.rlog.slice(0,20);
      renderStats(); if(S.tab==="security") renderSecurity(); CP.hooks.reject&&CP.hooks.reject(m);
    }else if(m.type==="link"){S.link=m.up;S.queued=m.queued||0;renderStats();CP.hooks.link&&CP.hooks.link(m);
      toast(m.up?"Link restored. Buffered data is syncing.":"Link to Earth lost. Wearables are buffering.",m.up?"info":"warning");
    }else if(m.type==="integrity") showIntegrity(m);
    else if(m.type==="phase"){S.phase=m.name;fillPhases();toast("Mission phase: "+m.name,"info");}
    else if(m.type==="limits"){S.limits=m.limits;renderSettings();}
  };
  ws.onclose=()=>{$("agentBadge").textContent="Reconnecting to gateway..."; setTimeout(connect,1500)};
}
connect();
CP.render={crew:renderCrew,vitals:renderVitals,analytics:renderAnalytics,drawChart};
})();
