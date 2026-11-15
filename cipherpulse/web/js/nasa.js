"use strict";
/* NASA tab: real NASA data with provenance labels. Everything here comes from /api/nasa/* (keys stay on the server). */
(function(){
const CP=window.CP,$=CP.$,esc=CP.esc;
const LBL={NASA_OBSERVED:"#6cffc1",NASA_RESEARCH:"#7fe9ff",NASA_DERIVED:"#c48bff",EXTERNAL_RESEARCH:"#ffb547",SIMULATED_DEMO:"#ff9aa4",UNAVAILABLE:"#ff5c6c"};
const chip=(l,t)=>`<span class="lbl" style="--c:${LBL[l]||"#fff"}" title="${esc(t||"")}">${l}</span>`;
let defs={}, booted=false;
async function api(url,opt){
  try{
    const r=await fetch(url,opt); const j=await r.json().catch(()=>({}));
    if(!r.ok){const d=j.detail||j; return {error:(d.error||JSON.stringify(d)).toString().slice(0,300),status:r.status,label:"UNAVAILABLE"};}
    return j;
  }catch(e){return {error:"Could not reach the gateway: "+e.message,label:"UNAVAILABLE"};}
}
const err=r=>`<p class="empty">${chip("UNAVAILABLE","Could not be retrieved")} ${esc(r.error)}</p>`;
const link=(u,t)=>u?`<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t||u)}</a>`:"";

function card(i){
  const h=i.human?'<span class="lbl" style="--c:#6cffc1">HUMAN</span>':`<span class="lbl" style="--c:#85a8b7">${esc(i.organism||"unknown organism")}</span>`;
  return `<div class="ncard"><div class="row2">${i.accession?`<b>${esc(i.accession)}</b>`:"<b>no OSDR accession</b>"}${h}${chip(i.label)}</div>
   <div>${esc(i.title||"")}</div>
   <small>${esc([i.assay,i.material_type,i.mission,i.project_type,i.release_date].filter(Boolean).join(" | "))}</small>
   ${i.external_accession?`<small>${chip("EXTERNAL_RESEARCH","Referenced in an external repository. Not an OSDR accession.")} ${esc(i.external_accession)} (external repository id)</small>`:""}
   <div class="row2">${i.accession?`<button class="btn" data-files="${esc(i.accession)}">Files and data</button> ${link(i.source_url,"OSDR page")}`:""}</div></div>`;
}
function ntrsCard(i){return `<div class="ncard"><div class="row2">${chip(i.label)}<b>${esc(i.type||"report")}</b></div><div>${esc(i.title||"")}</div><small>${esc((i.abstract||"").slice(0,220))}</small><div>${link(i.url,"NTRS record")}</div></div>`;}
function imgCard(i){return `<figure class="nimg">${i.thumb?`<img loading="lazy" src="${esc(i.thumb)}" alt="${esc(i.title||"NASA image")}">`:""}<figcaption><b>${esc((i.title||"").slice(0,60))}</b><small>${esc(i.nasa_id||"")} | credit: ${esc(i.credit||"NASA")}</small>${link(i.page_url,"NASA page")}</figcaption></figure>`;}

/* ---- OSDR explorer ---- */
async function searchOsdr(){
  const out=$("nOsdrOut"); out.innerHTML='<p class="empty">Searching NASA OSDR...</p>';
  const p=new URLSearchParams({q:$("nQ").value.trim(),topic:$("nTopic").value,human:$("nHuman").checked,size:15});
  const r=await api("/api/nasa/osdr/search?"+p);
  if(r.error) return out.innerHTML=err(r);
  out.innerHTML=`<p class="hint">${r.total_matches??"?"} matching studies. Showing ${r.returned}${r.human_only?" (human studies only)":""}. Retrieved ${esc(r.meta.retrieved_at)}${r.meta.from_cache?" (cached)":""}.</p>`+(r.items.map(card).join("")||'<p class="empty">No studies matched. Try another topic or untick "human only".</p>');
  out.querySelectorAll("[data-files]").forEach(b=>b.onclick=()=>openDataset(b.dataset.files));
}
async function openDataset(acc){
  const box=$("nDetail"); box.classList.remove("hidden"); box.innerHTML=`<p class="empty">Loading ${esc(acc)}...</p>`; box.scrollIntoView({block:"nearest"});
  const r=await api("/api/nasa/osdr/"+encodeURIComponent(acc));
  if(r.error) return box.innerHTML=err(r);
  const m=r.metadata,f=r.files;
  box.innerHTML=`<h2>${esc(m.accession)}: ${esc(m.title||"")}</h2><div class="row2">${chip("NASA_RESEARCH")}<span class="lbl" style="--c:${m.organism==="Homo sapiens"?"#6cffc1":"#85a8b7"}">${esc(m.organism||"organism not stated")}</span></div>
   <small>${esc([m.assay,m.technology,m.material_type,m.mission,m.release_date].filter(Boolean).join(" | "))}</small>
   ${m.external_accession?`<small>${chip("EXTERNAL_RESEARCH")} external id ${esc(m.external_accession)} (not an OSDR accession)</small>`:""}
   <p class="hint">${esc((m.description||"").slice(0,420))}</p>
   <h2>Files (${f.count}, ${f.processable} can be parsed here)</h2>
   <div class="flist">${f.files.slice(0,40).map(x=>`<div class="frow"><span title="${esc(x.name)}">${esc(x.name.length>46?x.name.slice(0,43)+"...":x.name)}</span><small>${esc(x.format)}</small>
      ${x.processable?`<button class="btn" data-dl="${esc(x.name)}">Download and process</button>`:`<small title="${esc(x.parser||"")}">needs ${esc(x.parser||"a specialised tool")}</small>`}</div>`).join("")}${f.count>40?`<small>${f.count-40} more files not shown</small>`:""}</div>
   <div id="nDlOut"></div><div>${link(m.source_url,"Open this study on NASA OSDR")}</div>`;
  box.querySelectorAll("[data-dl]").forEach(b=>b.onclick=()=>download(acc,b.dataset.dl,b));
}
async function download(acc,file,btn){
  const out=$("nDlOut"); btn.disabled=true; out.innerHTML='<p class="empty">Checking size, downloading and inspecting...</p>';
  const r=await api(`/api/nasa/osdr/${encodeURIComponent(acc)}/download`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({file})});
  btn.disabled=false;
  if(r.error) return out.innerHTML=err(r);
  if(r.status==="skipped_too_large") return out.innerHTML=`<p class="empty">Skipped: file is ${r.size_mb} MB, over the ${r.limit_mb} MB limit.</p>`;
  if(r.status==="unsupported_format") return out.innerHTML=`<p class="empty">Not downloaded: ${esc(r.format)}. Needs ${esc(r.suggested_parser||"a specialised parser")}.</p>`;
  const t=(r.tables||[]).map(t=>`<div class="ncard"><b>${esc(t.name)}</b><small>${t.rows} rows, ${t.n_columns} columns, ${t.usable_records} rows with numeric values</small>
     <small>Columns: ${esc(t.columns.slice(0,10).join(", "))}${t.n_columns>10?" ...":""}</small>
     <small>Units from file headers: ${Object.keys(t.units).length?esc(JSON.stringify(t.units)):"none documented"}</small>
     <small>Columns with missing values: ${Object.keys(t.missing).length}</small><small>Processed copy: ${esc(t.processed_csv)}</small></div>`).join("");
  out.innerHTML=`<div class="row2">${chip(r.label)}<b>${esc(r.status)}</b></div><small>${esc(r.file)}, ${r.download?(r.download.bytes/1024).toFixed(1)+" KB":""}, sha256 ${esc((r.download&&r.download.sha256||"").slice(0,12))}</small>
    <small>Source: ${link(r.source_url,"original NASA download URL")}</small>${t||'<p class="empty">No tables found in this file.</p>'}${r.error?`<p class="empty">${esc(r.error)}</p>`:""}`;
}

/* ---- DONKI ---- */
async function loadDonki(){
  const out=$("nDonkiOut"); out.innerHTML='<p class="empty">Loading NASA DONKI events...</p>';
  const r=await api("/api/nasa/donki?types=FLR,CME,SEP,GST&days=30");
  if(r.error) return out.innerHTML=err(r);
  const errs=Object.entries(r.by_type).filter(([,v])=>v.error).map(([t,v])=>`${t}: ${v.error}`);
  out.innerHTML=`<p class="hint">${chip("NASA_OBSERVED")} ${r.count} events, ${esc(r.start)} to ${esc(r.end)}. ${esc(r.note)}<br>API key: ${esc(r.key_status)}</p>`+
    (errs.length?`<p class="empty">${chip("UNAVAILABLE")} ${esc(errs.join(" | "))}</p>`:"")+
    r.events.slice(0,40).map(e=>`<div class="ncard"><div class="row2"><b>${esc(e.type)}</b><small>${esc(e.time||"")}</small></div><div>${esc(e.summary)}</div>${link(e.link,"DONKI record")}</div>`).join("")||'<p class="empty">No events in this period.</p>';
}
/* ---- Images, NTRS, HRR, EDA ---- */
async function loadImages(){const out=$("nImgOut");out.innerHTML='<p class="empty">Searching NASA Image Library...</p>';const r=await api("/api/nasa/images?page_size=12&q="+encodeURIComponent($("nImgQ").value||"astronaut health"));
  out.innerHTML=r.error?err(r):`<p class="hint">${chip("NASA_OBSERVED")} ${r.returned} of ${r.total_hits??"?"} images. Credit shown with each image.</p><div class="ngrid">${r.items.map(imgCard).join("")}</div>`;}
async function loadNtrs(){const out=$("nRepOut");out.innerHTML='<p class="empty">Searching NASA Technical Reports Server...</p>';const r=await api("/api/nasa/ntrs?size=8&q="+encodeURIComponent($("nRepQ").value||"spaceflight astronaut health"));
  out.innerHTML=r.error?err(r):`<p class="hint">${r.total??"?"} reports. Showing ${r.returned}.</p>`+r.items.map(ntrsCard).join("");}
async function loadHrr(){const out=$("nRepOut");out.innerHTML='<p class="empty">Reading Human Research Roadmap...</p>';const r=await api("/api/nasa/hrr");
  out.innerHTML=r.error?err(r):`<p class="hint">${esc(r.note)}</p>`+r.items.slice(0,30).map(i=>`<div class="ncard">${chip(i.label)} ${link(i.url,i.title)}</div>`).join("");}
async function loadEda(){const out=$("nEdaOut");out.innerHTML='<p class="empty">Checking the Environmental Data App...</p>';const r=await api("/api/nasa/eda");
  out.innerHTML=r.error?err(r):`<div class="row2">${chip(r.label)}<b>${r.missions_listed.length} missions listed</b></div><small>${esc(r.missions_listed.join(", "))}</small><small>Parameters: ${esc(r.parameters_documented.join("; "))}</small><p class="hint">${esc(r.note)}</p>${link(r.page,"Open the Environmental Data App")}`;}
async function loadStatus(){
  const r=await api("/api/nasa/status"); if(r.error) return $("nStatus").innerHTML=err(r);
  defs=r.label_definitions;
  $("nLegend").innerHTML=Object.keys(defs).map(l=>chip(l,defs[l])).join(" ");
  const c=r.record_counts||{};
  $("nStatus").innerHTML=`<small>NASA API key: ${esc(r.nasa_api_key)}</small><small>Stored provenance records: ${Object.keys(c).length?esc(JSON.stringify(c)):"none yet"}</small>`;
  const t=$("nTopic"); if(!t.options.length) t.innerHTML='<option value="">Any topic</option>'+r.topics.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join("");
}
/* ---- organ click from the 3D body ---- */
CP.openOrgan=async function(organ){
  CP.setTab("nasa"); boot();
  const box=$("nOrgan"); box.classList.remove("hidden"); box.innerHTML=`<h2>${esc(organ)}: NASA research</h2><p class="empty">Looking up NASA studies, reports and images...</p>`;
  const r=await api("/api/nasa/organ/"+encodeURIComponent(organ));
  if(r.error) return box.innerHTML=`<h2>${esc(organ)}</h2>${err(r)}`;
  const sect=(t,x,fn)=>`<h2>${t}</h2>`+(x&&x.error?err(x):(x&&x.items&&x.items.length?x.items.slice(0,5).map(fn).join(""):'<p class="empty">Nothing returned.</p>'));
  box.innerHTML=`<h2>${esc(organ)} (${esc(r.system)}): NASA research</h2><ul class="lim">${r.limitations.map(l=>`<li>${esc(l)}</li>`).join("")}</ul>`+
    sect("Human studies (OSDR)",r.osdr_human,card)+sect("All organisms (OSDR)",r.osdr_all,card)+sect("Technical reports (NTRS)",r.ntrs,ntrsCard)+
    sect("NASA images",r.images,imgCard);
  box.querySelectorAll("[data-files]").forEach(b=>b.onclick=()=>openDataset(b.dataset.files));
  box.scrollIntoView({block:"start"});
};
function boot(){ if(booted) return; booted=true; loadStatus(); }
$("nSearch").onclick=searchOsdr; $("nQ").addEventListener("keydown",e=>{if(e.key==="Enter")searchOsdr();});
$("nDonki").onclick=loadDonki; $("nImg").onclick=loadImages; $("nNtrs").onclick=loadNtrs; $("nHrr").onclick=loadHrr; $("nEda").onclick=loadEda;
document.querySelector('[data-tab="nasa"]').addEventListener("click",boot);
})();
