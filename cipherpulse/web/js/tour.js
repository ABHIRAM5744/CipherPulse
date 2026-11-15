"use strict";
/* Guided tour: a narrated, video-style walkthrough that drives the real system. */
(function(){
const CP=window.CP,S=CP.S,$=CP.$;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const STEPS=[
 {t:"Welcome to CipherPulse",view:"orbit",suit:"suit",tab:"live",spot:null,cam:{yaw:.8,pitch:.3,dist:15,target:[0,0,0]},
  x:"Welcome. CipherPulse is a mission console that watches astronaut health in real time and keeps that data safe. You are looking at a space station orbiting Earth. Astronauts out there cannot always reach a doctor, and their medical data is private. This tour shows how CipherPulse solves both problems. Everything you see is simulated, and it is all running live."},
 {t:"The link to Earth",view:"orbit",spot:"#linkBadge",cam:{yaw:1.3,pitch:.2,dist:11,target:[1.4,.6,0]},
  x:"The glowing line is the radio link between the station and ground control. Green beads mean the link is up and data is flowing. Soon we will cut it, to show what happens when contact is lost."},
 {t:"Meet the crew",view:"crew",suit:"suit",spot:"#crew",sel:"A2",
  x:"Each astronaut wears a sensor suit that measures five vitals every second: heart rate, blood oxygen, temperature, breathing and radiation. These cards show the crew. The big number is a health index from zero to one hundred, and higher is healthier. The orange bar shows radiation dose against a mission budget."},
 {t:"A live body scan",view:"crew",suit:"suit",spot:"#center",cam:{yaw:.25,pitch:.08,dist:3.6,target:[0,1.3,0]},
  x:"This is the selected astronaut's spacesuit. The screen on the chest is a live heart monitor, drawn from the real data stream. Floating labels show each vital. You can drag to rotate the view and scroll to zoom."},
 {t:"X-ray view",view:"crew",suit:"xray",spot:"#center",cam:{yaw:.1,pitch:.05,dist:4.2,target:[0,1.2,0]},
  x:"Switch to X-ray and the suit turns see-through. The heart beats at the astronaut's real heart rate. The lungs breathe at the real breathing rate, and they turn red if blood oxygen drops. The brain changes colour if body temperature rises."},
 {t:"Live vitals and safe zones",view:"crew",suit:"suit",tab:"live",spot:"#vitals",cam:{yaw:.5,pitch:.12,dist:5.6,target:[0,1.05,0]},
  x:"On the right, every vital has a live chart. The green band is the safe range. When a line leaves the band, the system pays attention."},
 {t:"Every packet is signed",view:"sys",spot:null,cam:{yaw:0,pitch:.1,dist:13.5,target:[0,-.2,0]},
  x:"Now the system view. Each reading travels as a packet from the wearable to the verifier. The wearable signs every packet with a secret key, like a signature that cannot be forged. Watch the glowing packets flow through the pipeline: verifier, vault, analysis, AI agents, and finally this dashboard."},
 {t:"Blocking fake data",view:"sys",tab:"security",spot:"#right",
  x:"Let us attack it. I am sending a forged packet, then a replay of an old one, then a packet whose values were changed after signing. The verifier checks the signature, the sequence number, the timestamp, and whether the values are humanly possible. Bad packets go to the red rejected log and never reach the crew.",
  run:async c=>{await sleep(2500);if(!c.ok())return;CP.act("spoof","forge");await sleep(3500);if(!c.ok())return;CP.act("spoof","replay");await sleep(3500);if(!c.ok())return;CP.act("spoof","modify");}},
 {t:"Tamper-proof storage",view:"sys",tab:"security",spot:"#chain",
  x:"Good packets are encrypted and stored in a vault. Each record holds a fingerprint of the record before it, like links in a chain. Now I will sneak in and edit one stored record. Watch the chain button: it pinpoints exactly which record was changed.",
  run:async c=>{await sleep(4500);if(!c.ok())return;CP.act("tamper");}},
 {t:"AI detection: a CO2 leak",view:"crew",suit:"xray",tab:"live",spot:"#alerts",cam:{yaw:.2,pitch:.08,dist:4.4,target:[0,1.25,0]},
  x:"Now a real emergency. First I repair the vault. Then I simulate a carbon dioxide leak on the selected astronaut. Oxygen falls while heart rate and breathing climb. The detector combines safe limits, the astronaut's own baseline, a machine learning model, and a pattern check that tells this apart from ordinary exercise.",
  run:async c=>{CP.act("restore");await sleep(2000);if(!c.ok())return;CP.act("scenario","co2");},
  wait:()=>S.alerts.some(a=>a.astro===S.sel&&a.kind!=="security"&&a.t>Date.now()-30000&&a.explanation&&!/analysing/.test(a.explanation)),waitMs:22000},
 {t:"AI agents explain what happened",view:"crew",suit:"xray",tab:"live",spot:"#alerts",
  x:"When an alert fires, a team of AI agents wakes up. They recall earlier events from memory, ask a language model to explain the situation in plain words, apply safety rules, and suggest what to do. If no AI key is set, built in rules write the explanation instead. Critical alerts are also spoken aloud."},
 {t:"Early warnings and analytics",view:"crew",suit:"suit",tab:"analytics",spot:"#right",
  x:"The analytics tab compares the whole crew on one chart, and the dots mark alerts. The system also forecasts. If a vital is heading toward its limit within about forty five seconds, you get an early warning before anything is actually wrong. Radiation budgets are tracked here too."},
 {t:"When contact is lost",view:"orbit",tab:"live",spot:"#linkBadge",cam:{yaw:1.0,pitch:.25,dist:11,target:[1.4,.6,0]},
  x:"Now we cut the link. The beam breaks and turns red. The wearables keep recording, keep signing, and queue every reading locally. Those amber cubes around the station are the queued packets. Nothing is lost.",
  run:async c=>{await sleep(2500);if(!c.ok())return;CP.act("link",false);}},
 {t:"Reconnecting",view:"orbit",spot:"#crew",
  x:"Contact is back. The queued readings are sent in order, verified like any other packet, and marked as delayed data on the crew cards. This is called offline first design, and it is essential for space.",
  run:async c=>{await sleep(1500);if(!c.ok())return;CP.act("link",true);}},
 {t:"Mission phases and settings",view:"crew",suit:"suit",tab:"settings",spot:"#phaseSel",cam:{yaw:.35,pitch:.1,dist:5.6,target:[0,1.05,0]},
  x:"What counts as normal changes. During a spacewalk the heart works harder. Choose a mission phase here and the alert limits adapt, so you do not get false alarms. In the settings tab you can also edit every limit, switch sound, and lower graphics quality on a slower computer."},
 {t:"Talk to it",view:"crew",tab:"live",spot:".say",
  x:"You can talk to the console. Press Talk and ask who is most at risk, or say show X-ray, or verify integrity. Other AI tools can connect through the MCP server and the agent to agent endpoint. The Mission report button builds a printable summary, and Export CSV downloads the data."},
 {t:"Your turn",view:"crew",suit:"suit",tab:"learn",spot:null,cam:{yaw:.35,pitch:.1,dist:5.6,target:[0,1.05,0]},
  x:"That is the whole system: sense, sign, verify, store safely, detect, explain, and keep working offline. Now try the buttons yourself. The Learn tab explains every term in simple words. Thank you for watching."}
];
let idx=-1, playing=false, token=0, stepStart=0, dur=1, ticker=null, speed=1;
const el={box:$("tour"),title:$("tourTitle"),step:$("tourStep"),text:$("tourText"),fill:$("tourFill"),bar:$("tourBar"),play:$("tPlay"),sel:$("tChapters"),spd:$("tSpeed"),voice:$("tVoice"),spot:$("spot")};
STEPS.forEach((s,i)=>{const o=document.createElement("option");o.value=i;o.textContent=`${i+1}. ${s.t}`;el.sel.appendChild(o);const t=document.createElement("i");t.className="tick";t.style.left=(i/STEPS.length*100)+"%";el.bar.appendChild(t);});

function spot(sel){
  if(!sel){el.spot.classList.add("hidden");return;}
  const n=document.querySelector(sel); if(!n){el.spot.classList.add("hidden");return;}
  const r=n.getBoundingClientRect(),p=8; el.spot.classList.remove("hidden");
  Object.assign(el.spot.style,{left:(r.left-p)+"px",top:(r.top-p)+"px",width:(r.width+2*p)+"px",height:(r.height+2*p)+"px"});
}
function say(text,speedX,onDone){
  if(!el.voice.checked||!(window.speechSynthesis&&window.SpeechSynthesisUtterance)){return false;}
  try{ speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(text); u.rate=Math.min(1.5,speedX*1.02); u.onend=onDone; u.onerror=onDone; speechSynthesis.speak(u); return true; }catch(e){return false;}
}
function waitFor(cond,ms,my){ return new Promise(res=>{const t0=Date.now();(function p(){ if(my!==token||cond()||Date.now()-t0>ms) return res(); setTimeout(p,400);})();}); }
async function play(i){
  if(i<0) i=0; if(i>=STEPS.length){finish();return;}
  const my=++token, s=STEPS[i]; idx=i; playing=true; el.play.textContent="Pause"; el.sel.value=String(i);
  el.title.textContent=s.t; el.step.textContent=`Chapter ${i+1} of ${STEPS.length}`; el.text.textContent=s.x;
  if(s.sel) CP.select(s.sel);
  if(s.view) CP.setView(s.view); if(s.suit) CP.setSuit(s.suit); if(s.tab) CP.setTab(s.tab);
  if(s.cam&&CP.hooks.cam) setTimeout(()=>{ if(my===token) CP.hooks.cam(s.cam); },60);
  setTimeout(()=>{ if(my===token) spot(s.spot); },80);
  dur=Math.max(7000,s.x.length*66); stepStart=Date.now();
  const ctx={ok:()=>my===token&&playing};
  if(s.run) s.run(ctx).catch(()=>{});
  const narrDone=new Promise(res=>{ if(!say(s.x,speed,res)) setTimeout(res,dur/speed); else setTimeout(res,dur*1.8/speed); });
  await Promise.all([narrDone,sleep(Math.min(dur/speed,9000))]);
  if(my!==token) return;
  if(s.wait) await waitFor(s.wait,s.waitMs||20000,my);
  if(my!==token) return;
  await sleep(900); if(my!==token) return;
  play(i+1);
}
function finish(){ playing=false; el.play.textContent="Replay"; el.fill.style.width="100%"; el.spot.classList.add("hidden"); try{speechSynthesis.cancel();}catch(e){} }
function start(){
  el.box.classList.remove("hidden"); CP.act("link",true); CP.act("restore"); CP.setTab("live");
  if(!ticker) ticker=setInterval(()=>{ if(playing&&idx>=0){ const f=Math.min(1,(Date.now()-stepStart)/(dur/speed)); el.fill.style.width=((idx+f)/STEPS.length*100)+"%"; } },120);
  play(0);
}
function close(){
  token++; playing=false; el.box.classList.add("hidden"); el.spot.classList.add("hidden"); try{speechSynthesis.cancel();}catch(e){}
  CP.act("link",true); CP.act("restore");
}
function pause(){ if(playing){ token++; playing=false; el.play.textContent="Play"; try{speechSynthesis.cancel();}catch(e){} } else play(idx<0?0:(idx>=STEPS.length-1&&el.play.textContent==="Replay"?0:idx)); }
el.play.onclick=pause; $("tNext").onclick=()=>play(Math.min(STEPS.length-1,idx+1)); $("tPrev").onclick=()=>play(Math.max(0,idx-1)); $("tClose").onclick=close;
el.sel.onchange=()=>play(parseInt(el.sel.value,10)); el.spd.onchange=()=>{speed=parseFloat(el.spd.value)||1;};
el.bar.onclick=e=>{const r=el.bar.getBoundingClientRect(); play(Math.floor((e.clientX-r.left)/r.width*STEPS.length));};
addEventListener("keydown",e=>{
  if(el.box.classList.contains("hidden")) return; const tg=(e.target.tagName||"").toLowerCase(); if(tg==="input"||tg==="select"||tg==="textarea") return;
  if(e.key===" "){e.preventDefault();pause();} else if(e.key==="ArrowRight") $("tNext").click(); else if(e.key==="ArrowLeft") $("tPrev").click(); else if(e.key==="Escape") close();
});
addEventListener("resize",()=>{ if(idx>=0&&!el.box.classList.contains("hidden")) spot(STEPS[idx].spot); });
CP.tour={start,close,steps:STEPS};
})();
