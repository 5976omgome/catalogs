"use strict";
const $=id=>document.getElementById(id);

// ---------------------------------------------------------------------------
// Status pills
// ---------------------------------------------------------------------------
async function refreshStatus(){
  try{
    const r=await fetch("/api/status");const s=await r.json();
    const pd=$("pill-discogs");
    pd.textContent=s.discogs_set?"discogs":"discogs off";
    pd.className="pill "+(s.discogs_set?"ok":"bad");
    const pa=$("pill-ai");
    const ok=s.groq_set||s.gemini_set;
    let t="ai off";
    if(s.groq_set&&s.gemini_set)t="ai: groq+gemini";
    else if(s.groq_set)t="ai: groq";
    else if(s.gemini_set)t="ai: gemini";
    pa.textContent=t;pa.className="pill "+(ok?"ok":"bad");
  }catch(e){}
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
async function loadSettings(){
  try{
    const r=await fetch("/api/settings");const s=await r.json();
    const show=(id,info)=>{$(id).textContent=info.set?info.preview:"\u2014"};
    show("prev-discogs",s.discogs_token);
    show("prev-groq",s.groq_api_key);
    show("prev-gemini",s.gemini_api_key);
  }catch(e){}
}
async function saveKeys(){
  const body={};
  const d=$("key-discogs").value.trim();
  const g=$("key-groq").value.trim();
  const m=$("key-gemini").value.trim();
  if(d)body.discogs_token=d;if(g)body.groq_api_key=g;if(m)body.gemini_api_key=m;
  if(!Object.keys(body).length){$("keys-msg").textContent="nothing to save";return}
  $("keys-msg").textContent="saving\u2026";
  const r=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  if(r.ok){$("keys-msg").textContent="saved \u2713";$("key-discogs").value="";$("key-groq").value="";$("key-gemini").value="";
    loadSettings();refreshStatus();setTimeout(()=>$("keys-msg").textContent="",2000)}
  else $("keys-msg").textContent="error";
}
async function clearKeys(){
  if(!confirm("Clear ALL stored API keys?"))return;
  await fetch("/api/settings/clear",{method:"POST"});loadSettings();refreshStatus();
}

// ---------------------------------------------------------------------------
// Queue
// ---------------------------------------------------------------------------
const qState={};
function renderItem(item){
  if(qState[item.id]){qState[item.id].remove();delete qState[item.id]}
  const li=document.createElement("li");li.dataset.id=item.id;

  const head=document.createElement("div");head.className="qhead";
  const name=document.createElement("span");name.className="name";name.textContent=item.filename;
  const stat=document.createElement("span");stat.className="stat "+item.status;stat.textContent=item.status;
  head.append(name,stat);li.append(head);

  if(item.total>0){
    const bar=document.createElement("div");bar.className="qbar";
    const fill=document.createElement("span");
    fill.style.width=Math.floor(100*item.processed/item.total)+"%";
    bar.append(fill);li.append(bar);
    const counts=document.createElement("div");counts.className="qcounts";
    const pct=item.total?Math.floor(100*item.processed/item.total):0;
    const cpct=item.processed?Math.floor(100*item.keep/item.processed):0;
    counts.innerHTML=`${item.processed}/${item.total} processed \u00b7 ${pct}% | ${item.keep} keep \u00b7 ${item.review} review \u00b7 ${item.drop} drop \u00b7 ${cpct}% clean`;
    li.append(counts);
  }

  if(item.has_output){
    const exp=document.createElement("div");exp.className="qexports";
    const stem=item.filename.replace(/\.(csv|tsv)$/i,"");
    const mk=(label,cls,url,fname)=>{const b=document.createElement("button");b.type="button";b.textContent=label;b.className=cls;
      b.addEventListener("click",()=>dl(b,url,fname));return b};
    exp.append(
      mk("KEEP","btn-keep",`/api/export/${item.id}/keep`,`${stem}-keep.xlsx`),
      mk("REVIEW","btn-review",`/api/export/${item.id}/review`,`${stem}-review.xlsx`),
      mk("DROPS","btn-drops",`/api/export/${item.id}/drops`,`${stem}-drops.xlsx`),
      mk("ALL","",`/api/export/${item.id}/all`,`${stem}-all.xlsx`),
      mk("FULL","btn-full",`/api/download/${item.id}`,`${stem}.xlsx`),
    );
    if(item.status==="running"){
      exp.append(mk("STOP & EXPORT","btn-stop-export",`/api/queue/stop_and_export/${item.id}`,`${stem}.xlsx`));
    }
    li.append(exp);
  }
  $("queue").append(li);qState[item.id]=li;
}

// ---------------------------------------------------------------------------
// Download helper (blob → save-as)
// ---------------------------------------------------------------------------
async function dl(btn,url,suggestedName){
  const orig=btn.textContent;btn.disabled=true;btn.textContent="\u2026";
  try{
    const r=await fetch(url);
    if(!r.ok){let msg=`${r.status}`;try{const j=await r.json();if(j.error)msg=j.error}catch(e){}
      btn.textContent=orig;btn.disabled=false;sysLine("download error: "+msg,"bad");alert("Download: "+msg);return}
    const blob=await r.blob();
    const cd=r.headers.get("Content-Disposition")||"";
    const m=/filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd);
    const filename=(m&&decodeURIComponent(m[1].replace(/"$/,"")))||suggestedName;
    if(window.showSaveFilePicker){
      try{const h=await window.showSaveFilePicker({suggestedName:filename,
        types:[{description:"Excel",accept:{"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":[".xlsx"]}}]});
        const w=await h.createWritable();await w.write(blob);await w.close();
        btn.textContent="\u2713";sysLine("saved "+filename,"ok");setTimeout(()=>{btn.textContent=orig;btn.disabled=false},1500);return;
      }catch(e){if(e.name==="AbortError"){btn.textContent=orig;btn.disabled=false;return}}
    }
    const u=URL.createObjectURL(blob);const a=document.createElement("a");a.href=u;a.download=filename;a.style.display="none";
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);
    btn.textContent="\u2713";sysLine("downloaded "+filename,"ok");setTimeout(()=>{btn.textContent=orig;btn.disabled=false},1500);
  }catch(err){btn.textContent=orig;btn.disabled=false;sysLine("download error: "+err.message,"bad")}
}

// ---------------------------------------------------------------------------
// Live log
// ---------------------------------------------------------------------------
function sysLine(text,cls){
  const log=$("log");const d=document.createElement("div");d.className="sysline "+(cls||"");d.textContent=text;
  log.append(d);log.scrollTop=log.scrollHeight;
}
function artistBlock(ev){
  const log=$("log");const block=document.createElement("div");block.className="ablock";

  // Header: name + badge
  const head=document.createElement("div");head.className="ahead";
  const nm=document.createElement("span");nm.className="aname";nm.textContent=ev.artist;
  const badge=document.createElement("span");
  let bc="drop";if(ev.status==="KEEP")bc="keep";else if(ev.status==="REVIEW")bc="review";
  badge.className="badge "+bc;badge.textContent=ev.status;
  head.append(nm,badge);
  if(ev.earliest_year){const yr=document.createElement("span");yr.className="counter";yr.textContent="since "+ev.earliest_year;head.append(yr)}
  block.append(head);

  // Per-source rows
  const order=["Chartmetric","iTunes","Deezer","Discogs"];
  for(const src of order){
    const items=(ev.sources&&ev.sources[src])||[];
    const row=document.createElement("div");row.className="src";
    const lbl=document.createElement("div");lbl.className="src-name";lbl.textContent=src;
    const vals=document.createElement("div");vals.className="src-vals";
    if(!items.length){const e=document.createElement("span");e.className="empty";e.textContent="no data";vals.append(e)}
    else{for(const it of items){
      const line=document.createElement("span");line.className="entry";
      const txt=document.createTextNode(it.label||"(empty)");line.append(txt);
      if(it.classification){const tag=document.createElement("span");tag.className="tag "+it.classification;tag.textContent=it.classification;line.append(tag)}
      vals.append(line);
    }}
    row.append(lbl,vals);block.append(row);
  }

  // Reason
  if(ev.status_reason){
    const reason=document.createElement("div");reason.className="reason";
    reason.innerHTML='<span class="arrow">\u2192</span>'+ev.status_reason.replace(/</g,"&lt;");
    block.append(reason);
  }
  log.append(block);log.scrollTop=log.scrollHeight;
}

// ---------------------------------------------------------------------------
// Counters
// ---------------------------------------------------------------------------
let _totalProcessed=0,_totalTotal=0,_totalKeep=0;
function updateCounters(ev){
  _totalProcessed=ev.processed;_totalTotal=ev.total;_totalKeep=ev.keep;
  const pct=_totalTotal?Math.floor(100*_totalProcessed/_totalTotal):0;
  $("counter-progress").textContent=`${_totalProcessed}/${_totalTotal} \u00b7 ${pct}%`;
  const cpct=_totalProcessed?Math.floor(100*_totalKeep/_totalProcessed):0;
  $("counter-clean").textContent=`${_totalKeep} clean \u00b7 ${cpct}%`;
}

// ---------------------------------------------------------------------------
// SSE
// ---------------------------------------------------------------------------
function startStream(){
  const es=new EventSource("/api/stream");
  es.onmessage=msg=>{let d;try{d=JSON.parse(msg.data)}catch{return}handleEvent(d)};
  es.onerror=()=>{sysLine("stream reconnecting\u2026","warn");es.close();setTimeout(startStream,2000)};
}
function handleEvent(ev){
  if(ev.type==="snapshot"){$("queue").innerHTML="";Object.keys(qState).forEach(k=>delete qState[k]);
    (ev.items||[]).forEach(renderItem)}
  else if(ev.type==="item_added"){renderItem(ev.item);sysLine("+ "+ev.item.filename,"info")}
  else if(ev.type==="item_started"){renderItem(ev.item);sysLine("\u25b6 "+ev.item.filename,"info");_totalProcessed=0;_totalTotal=0;_totalKeep=0}
  else if(ev.type==="artist_done"){artistBlock(ev);updateCounters(ev);
    const li=qState[ev.item_id];if(li){const fill=li.querySelector(".qbar>span");if(fill)fill.style.width=Math.floor(100*ev.processed/ev.total)+"%";
      const c=li.querySelector(".qcounts");if(c){const pct=ev.total?Math.floor(100*ev.processed/ev.total):0;const cpct=ev.processed?Math.floor(100*ev.keep/ev.processed):0;
        c.innerHTML=`${ev.processed}/${ev.total} \u00b7 ${pct}% | ${ev.keep} keep \u00b7 ${ev.review} review \u00b7 ${ev.drop} drop \u00b7 ${cpct}% clean`}}}
  else if(ev.type==="item_done"){renderItem(ev.item);sysLine("\u2713 done \u00b7 "+ev.item.filename,"ok")}
  else if(ev.type==="item_stopped"){renderItem(ev.item);sysLine("\u25a0 stopped \u00b7 "+ev.item.filename,"warn")}
  else if(ev.type==="item_error"){renderItem(ev.item);sysLine("\u2715 error \u00b7 "+(ev.item.error||ev.item.filename),"bad")}
  else if(ev.type==="queue_done"){sysLine("queue done","info")}
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------
async function uploadFile(file){
  const fd=new FormData();fd.append("file",file);
  const r=await fetch("/api/upload",{method:"POST",body:fd});
  if(!r.ok){const e=await r.json().catch(()=>({error:r.statusText}));alert("Upload: "+(e.error||"failed"))}
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded",()=>{
  $("file-input").addEventListener("change",e=>{for(const f of e.target.files)uploadFile(f);e.target.value=""});
  $("btn-run").addEventListener("click",()=>fetch("/api/queue/start",{method:"POST"}));
  $("btn-stop").addEventListener("click",()=>{fetch("/api/queue/stop",{method:"POST"});sysLine("stop requested","warn")});
  $("btn-clear").addEventListener("click",()=>{fetch("/api/queue/clear",{method:"POST"})});
  $("btn-clear-log").addEventListener("click",()=>{$("log").innerHTML=""});
  $("btn-save-keys").addEventListener("click",saveKeys);
  $("btn-clear-keys").addEventListener("click",clearKeys);
  $("btn-toggle-keys").addEventListener("click",()=>{
    const b=$("keys-body");b.style.display=b.style.display==="none"?"":"none"});
  refreshStatus();loadSettings();startStream();
});
