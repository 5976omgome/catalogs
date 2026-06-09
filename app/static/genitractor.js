"use strict";
const $=id=>document.getElementById(id);

// Max rendered feed blocks (mirrors the 200-line console cap).
const FEED_BLOCK_CAP=200;
// Safe percentage — never divides by zero (renders 0% instead of NaN%).
function pct(p,t){return t>0?Math.floor(100*p/t):0}

// ---------------------------------------------------------------------------
// CLOCK
// ---------------------------------------------------------------------------
function initClock(){
  function tick(){$("clock").textContent=new Date().toLocaleTimeString("en",{hour12:false,hour:"2-digit",minute:"2-digit",second:"2-digit"})}
  tick();setInterval(tick,1000);
}

// ---------------------------------------------------------------------------
// TIMER
// ---------------------------------------------------------------------------
let _timerStart=null,_timerInterval=null;
function _renderTimer(){
  if(_timerStart==null)return;
  const e=Math.max(0,Math.floor((Date.now()-_timerStart)/1000));
  $("timer").textContent=String(Math.floor(e/60)).padStart(2,"0")+":"+String(e%60).padStart(2,"0");
}
function startTimer(){
  _timerStart=Date.now();
  if(!_timerInterval)_timerInterval=setInterval(_renderTimer,1000);
  _renderTimer();
}
function resumeTimer(startedAtSec){
  if(startedAtSec==null)return;
  _timerStart=startedAtSec*1000;
  if(!_timerInterval)_timerInterval=setInterval(_renderTimer,1000);
  _renderTimer();
}
function stopTimer(){if(_timerInterval){clearInterval(_timerInterval);_timerInterval=null}}

// ---------------------------------------------------------------------------
// SYSTEM CONSOLE
// ---------------------------------------------------------------------------
function sys(text,cls){
  const log=$("sys-log");
  const ts=new Date().toLocaleTimeString("en",{hour12:false,hour:"2-digit",minute:"2-digit",second:"2-digit"});
  const d=document.createElement("div");d.className="sysline "+(cls||"");
  d.textContent=`[${ts}] ${text}`;
  log.append(d);log.scrollTop=log.scrollHeight;
  while(log.children.length>200)log.firstChild.remove();
}

// ---------------------------------------------------------------------------
// COLLAPSIBLE — class-driven (no scrollHeight, no inline maxHeight, no timers)
// ---------------------------------------------------------------------------
function initCollapsible(){
  document.querySelectorAll(".card-head[data-collapse]").forEach(head=>{
    head.style.cursor="pointer";
    head.addEventListener("click",e=>{
      if(e.target.closest("button:not(.collapse-btn)"))return;
      const body=document.getElementById(head.dataset.collapse);
      if(!body)return;
      const card=head.closest(".card");
      const btn=head.querySelector(".collapse-btn");
      const collapsed=body.classList.toggle("collapsed");
      if(card)card.classList.toggle("is-collapsed",collapsed);
      if(btn)btn.textContent=collapsed?"\u25B6":"\u25BC";
    });
  });
}

// ---------------------------------------------------------------------------
// STATUS — only Genius pill
// ---------------------------------------------------------------------------
async function refreshStatus(){
  try{
    const r=await fetch("/api/status");const s=await r.json();
    $("pill-genius").className="pill clickable "+(s.genius_set?"ok":"missing");
    if(!s.genius_set)sys("\u26a0 Genius not configured \u2014 click pill to add key.","warn");
    else sys("\u2713 Genius ready.","ok");
    sys("Genitractor ready.","info");
  }catch(e){sys("Server connection failed: "+e.message,"bad")}
}

// ---------------------------------------------------------------------------
// KEY MODAL
// ---------------------------------------------------------------------------
function initKeyModal(){
  const modal=$("key-modal"),close=$("key-modal-close"),save=$("key-modal-save"),input=$("key-modal-input");
  close.addEventListener("click",()=>modal.classList.remove("open"));
  modal.addEventListener("click",e=>{if(e.target===modal)modal.classList.remove("open")});
  $("pill-genius").addEventListener("click",()=>{
    input.value="";$("key-modal-msg").textContent="";
    modal.classList.add("open");input.focus();
  });
  save.addEventListener("click",async()=>{
    const val=input.value.trim();
    if(!val){$("key-modal-msg").textContent="Paste token first";return}
    const r=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({genius_token:val})});
    if(r.ok){$("key-modal-msg").textContent="\u2713 Saved";input.value="";
      setTimeout(()=>{modal.classList.remove("open");refreshStatus()},800)}
    else{$("key-modal-msg").textContent="Error"}
  });
  input.addEventListener("keydown",e=>{if(e.key==="Enter")save.click()});
}

// ---------------------------------------------------------------------------
// CONFIRM MODAL
// ---------------------------------------------------------------------------
let _confirmCb=null;
function initConfirmModal(){
  const modal=$("confirm-modal"),close=$("confirm-close"),yes=$("confirm-yes"),no=$("confirm-no");
  close.addEventListener("click",()=>modal.classList.remove("open"));
  no.addEventListener("click",()=>modal.classList.remove("open"));
  modal.addEventListener("click",e=>{if(e.target===modal)modal.classList.remove("open")});
  yes.addEventListener("click",()=>{modal.classList.remove("open");if(_confirmCb)_confirmCb()});
}
function showConfirm(title,msg,cb){
  $("confirm-title").textContent=title;$("confirm-msg").textContent=msg;_confirmCb=cb;
  $("confirm-modal").classList.add("open");
}

// ---------------------------------------------------------------------------
// TOOLS DROPDOWN
// ---------------------------------------------------------------------------
function initToolsDropdown(){
  const btn=$("tool-btn"),menu=$("tools-menu");
  if(!btn||!menu)return;
  btn.addEventListener("click",e=>{e.stopPropagation();menu.classList.toggle("open")});
  document.addEventListener("click",()=>menu.classList.remove("open"));
  menu.addEventListener("click",e=>e.stopPropagation());
}

// ---------------------------------------------------------------------------
// FEEDBACK
// ---------------------------------------------------------------------------
const fbState={category:null,rawText:""};
function initFeedback(){
  const btn=$("btn-feedback"),modal=$("feedback-modal"),close=$("feedback-close");
  btn.addEventListener("click",()=>{resetFb();modal.classList.add("open")});
  close.addEventListener("click",()=>modal.classList.remove("open"));
  modal.addEventListener("click",e=>{if(e.target===modal)modal.classList.remove("open")});
  document.querySelectorAll(".fb-cat").forEach(b=>{
    b.addEventListener("click",()=>{
      document.querySelectorAll(".fb-cat").forEach(x=>x.classList.remove("active"));
      b.classList.add("active");fbState.category=b.dataset.cat;updateFbSubmit()});
  });
  $("fb-text").addEventListener("input",e=>{fbState.rawText=e.target.value.trim();updateFbSubmit()});
  $("fb-submit").addEventListener("click",handleFbSubmit);
}
function resetFb(){fbState.category=null;fbState.rawText="";document.querySelectorAll(".fb-cat").forEach(b=>b.classList.remove("active"));$("fb-text").value="";$("fb-submit").disabled=true;$("fb-submit-status").textContent=""}
function updateFbSubmit(){$("fb-submit").disabled=!(fbState.category&&fbState.rawText)}
async function handleFbSubmit(){
  if(!fbState.category||!fbState.rawText)return;
  $("fb-submit").disabled=true;$("fb-submit-status").textContent="Submitting...";
  try{
    const r=await fetch("/api/feedback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({category:fbState.category,text:fbState.rawText,raw_text:"",ai_enhanced:false})});
    const d=await r.json();if(!r.ok)throw new Error(d.error||"Failed");
    $("fb-submit-status").textContent="\u2713 "+d.file;$("fb-submit-status").className="fb-submit-status ok";
    sys("Feedback: "+d.file,"ok");setTimeout(()=>{$("feedback-modal").classList.remove("open");resetFb()},1200);
  }catch(e){$("fb-submit-status").textContent=e.message;$("fb-submit-status").className="fb-submit-status bad";$("fb-submit").disabled=false}
}

// ---------------------------------------------------------------------------
// QUEUE + GENIUS CONTACT EXTRACTION (SSE)
// ---------------------------------------------------------------------------
const qState={};
function renderItem(item){
  if(qState[item.id]){qState[item.id].remove();delete qState[item.id]}
  const li=document.createElement("li");li.dataset.id=item.id;
  const name=document.createElement("span");name.className="name";name.textContent=item.filename;
  const stat=document.createElement("span");stat.className="stat "+item.status;
  stat.textContent=item.status==="running"?`${pct(item.processed,item.total)}%`:item.status.toUpperCase();
  li.append(name);
  if(item.total>0&&item.status==="running"){const c=document.createElement("span");c.className="counts";c.textContent=`${item.processed}/${item.total}`;li.append(c)}
  li.append(stat);$("queue").append(li);qState[item.id]=li;
}

let totalProcessed=0,totalArtists=0,totalFound=0;
let _statShowFraction=false;
let _cleanShowFraction=false;

function updateStats(){
  const elPct=$("stat-pct");
  if(_statShowFraction){
    elPct.textContent=totalProcessed+"/"+totalArtists;
  }else{
    elPct.textContent=pct(totalProcessed,totalArtists)+"% TOTAL";
  }

  const elClean=$("stat-clean");
  if(_cleanShowFraction){
    elClean.textContent=totalFound+"/"+totalProcessed;
  }else{
    elClean.textContent=pct(totalFound,totalProcessed)+"% FOUND";
  }
}

function addContactToFeed(ev){
  const grid=$("feeds-grid");
  const block=document.createElement("div");block.className="ablock";
  const head=document.createElement("div");head.className="ahead";
  const nm=document.createElement("span");nm.className="aname";nm.textContent=ev.artist;
  const badge=document.createElement("span");
  const socials=ev.socials||{};
  const hasAnything=socials.instagram||socials.facebook||socials.twitter;
  badge.className="badge "+(hasAnything?"found":"empty");
  badge.textContent=hasAnything?"FOUND":"NONE";
  head.append(nm,badge);block.append(head);

  const rows=[
    ["IG",socials.instagram?"https://instagram.com/"+socials.instagram:""],
    ["FB",socials.facebook?(socials.facebook.startsWith("http")?socials.facebook:"https://facebook.com/"+socials.facebook):""],
    ["X",socials.twitter?"https://x.com/"+socials.twitter:""]
  ];
  for(const[label,url] of rows){
    const row=document.createElement("div");row.className="src";
    const lbl=document.createElement("div");lbl.className="src-name";lbl.textContent=label;
    const vals=document.createElement("div");vals.className="src-vals";
    if(url){const a=document.createElement("a");a.href=url;a.target="_blank";a.rel="noopener";a.textContent=url;vals.append(a)}
    else{const s=document.createElement("span");s.className="empty";s.textContent="\u2014";vals.append(s)}
    row.append(lbl,vals);block.append(row);
  }
  grid.append(block);
  while(grid.children.length>FEED_BLOCK_CAP)grid.firstChild.remove();
  grid.scrollTop=grid.scrollHeight;

  totalProcessed++;
  if(hasAnything)totalFound++;
  updateStats();
  sys(`${hasAnything?"\u2713":"\u2014"} ${ev.artist}`,hasAnything?"ok":"");
}

// ---------------------------------------------------------------------------
// SSE
// ---------------------------------------------------------------------------
function startStream(){
  const es=new EventSource("/api/genitractor/stream");
  es.onmessage=msg=>{let d;try{d=JSON.parse(msg.data)}catch{return}handleEvent(d)};
  es.onerror=()=>{sys("Stream disconnected, reconnecting\u2026","warn");es.close();setTimeout(startStream,2000)};
  sys("Connected.","info");
}

function handleEvent(ev){
  if(ev.type==="snapshot"){$("queue").innerHTML="";Object.keys(qState).forEach(k=>delete qState[k]);
    totalArtists=0;totalProcessed=0;totalFound=0;
    let resumeStart=null;
    (ev.items||[]).forEach(i=>{
      renderItem(i);
      totalArtists+=(i.total||0);
      totalProcessed+=(i.processed||0);
      totalFound+=(i.found||0);
      if(i.status==="running"&&i.started_at!=null)resumeStart=(resumeStart==null?i.started_at:Math.min(resumeStart,i.started_at));
    });
    updateStats();
    if(resumeStart!=null)resumeTimer(resumeStart);else stopTimer();
  }
  else if(ev.type==="item_added"){renderItem(ev.item);sys("+ "+ev.item.filename,"info")}
  else if(ev.type==="item_started"){renderItem(ev.item);totalArtists+=(ev.item.total||0);updateStats();if(ev.item.started_at!=null)resumeTimer(ev.item.started_at);sys("\u25b6 "+ev.item.filename,"info")}
  else if(ev.type==="contact_done"){addContactToFeed(ev);
    const li=qState[ev.item_id];if(li){const s=li.querySelector(".stat");if(s)s.textContent=`${pct(ev.processed,ev.total)}%`;
      const c=li.querySelector(".counts");if(c)c.textContent=`${ev.processed}/${ev.total}`}}
  else if(ev.type==="item_done"){renderItem(ev.item);sys("\u2713 Done: "+ev.item.filename,"ok");checkAllDone()}
  else if(ev.type==="item_stopped"){renderItem(ev.item);sys("\u25a0 Stopped.","warn")}
  else if(ev.type==="item_error"){renderItem(ev.item);sys("\u2717 Error: "+(ev.item.error||""),"bad")}
}

function checkAllDone(){
  let any=false;Object.values(qState).forEach(li=>{const s=li.querySelector(".stat");if(s&&s.classList.contains("running"))any=true});
  if(!any)stopTimer();
}

// ---------------------------------------------------------------------------
// CROSS-TOOL PROGRESS BAR — polls Chartporter status
// ---------------------------------------------------------------------------
let _ctbStartedAt=null,_ctbTimerInterval=null;
function _renderCtbTimer(){
  const el=$("ctb-timer");if(!el)return;
  if(_ctbStartedAt==null){el.textContent="00:00";return}
  const e=Math.max(0,Math.floor((Date.now()-_ctbStartedAt*1000)/1000));
  el.textContent=String(Math.floor(e/60)).padStart(2,"0")+":"+String(e%60).padStart(2,"0");
}
function initCrossToolBar(){
  if(!_ctbTimerInterval)_ctbTimerInterval=setInterval(_renderCtbTimer,1000);
  setInterval(async()=>{
    try{
      const r=await fetch("/api/cross-status");const d=await r.json();
      const cp=d.chartporter;
      const bar=$("cross-tool-bar");
      if(cp.running&&cp.total>0){
        bar.classList.add("visible");
        const p=pct(cp.processed,cp.total);
        $("ctb-fill").style.width=p+"%";
        $("ctb-stats").textContent=cp.processed+"/"+cp.total;
        _ctbStartedAt=(cp.started_at!=null?cp.started_at:_ctbStartedAt);
        _renderCtbTimer();
      }else{
        bar.classList.remove("visible");
        _ctbStartedAt=null;
      }
    }catch(e){}
  },10000);
}

// ---------------------------------------------------------------------------
// UPLOAD + INIT
// ---------------------------------------------------------------------------
async function uploadFile(file){
  const fd=new FormData();fd.append("file",file);
  const r=await fetch("/api/genitractor/upload",{method:"POST",body:fd});
  if(!r.ok){const e=await r.json().catch(()=>({error:"failed"}));sys("Upload error: "+(e.error||""),"bad")}
}

// Persistent in-UI export message (does not scroll away like the console).
function showExportMsg(text,cls){
  const el=$("export-msg");if(!el)return;
  el.textContent=text||"";
  el.className="export-msg"+(text?" show":"")+(cls?" "+cls:"");
}

// EXPORT — fetch + blob download; never navigates the page to a JSON body.
async function exportContacts(){
  showExportMsg("");
  try{
    const r=await fetch("/api/genitractor/export");
    if(!r.ok){let msg=`${r.status}`;try{const j=await r.json();if(j.error)msg=j.error}catch(e){}
      sys("Export error: "+msg,"bad");showExportMsg("Export unavailable: "+msg,"bad");return}
    const blob=await r.blob();
    const cd=r.headers.get("Content-Disposition")||"";
    const m=/filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd);
    const filename=(m&&decodeURIComponent(m[1].replace(/"$/,"")))||"Genitractor_Contacts.csv";
    const u=URL.createObjectURL(blob);const a=document.createElement("a");a.href=u;a.download=filename;a.style.display="none";
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);
    sys("Downloaded: "+filename,"ok");
  }catch(e){sys("Export error: "+e.message,"bad");showExportMsg("Export failed: "+e.message,"bad")}
}

// CLEAR — reset the queue server-side and the client feed/stat state.
function clearAll(){
  fetch("/api/genitractor/clear",{method:"POST"}).then(()=>{
    totalProcessed=0;totalArtists=0;totalFound=0;
    Object.keys(qState).forEach(k=>{if(qState[k])qState[k].remove();delete qState[k]});
    $("feeds-grid").innerHTML="";
    updateStats();showExportMsg("");
    sys("Queue cleared.","info");
  }).catch(e=>sys("Clear failed: "+e.message,"bad"));
}

function _safeInit(name,fn){try{fn()}catch(e){sys(name+" init failed: "+(e&&e.message||e),"bad")}}

document.addEventListener("DOMContentLoaded",()=>{
  sys("Genitractor starting\u2026","info");
  _safeInit("clock",initClock);
  _safeInit("collapsible",initCollapsible);
  _safeInit("keyModal",initKeyModal);
  _safeInit("confirmModal",initConfirmModal);
  _safeInit("toolsDropdown",initToolsDropdown);
  _safeInit("feedback",initFeedback);
  _safeInit("crossToolBar",initCrossToolBar);
  _safeInit("controls",()=>{
    $("file-input").addEventListener("change",e=>{for(const f of e.target.files)uploadFile(f);e.target.value=""});
    $("stat-pct").addEventListener("click",()=>{_statShowFraction=!_statShowFraction;updateStats()});
    $("stat-clean").addEventListener("click",()=>{_cleanShowFraction=!_cleanShowFraction;updateStats()});
    $("btn-run").addEventListener("click",()=>{fetch("/api/genitractor/start",{method:"POST"});sys("RUN","info");showExportMsg("");startTimer()});
    $("btn-stop").addEventListener("click",()=>{showConfirm("Stop extraction?","This will halt Genius lookups.",()=>{fetch("/api/genitractor/stop",{method:"POST"});sys("STOP","warn");stopTimer()})});
    $("btn-export-all").addEventListener("click",()=>{showConfirm("Export contacts?","This will download all found contacts as CSV.",exportContacts)});
    const bc=$("btn-clear");if(bc)bc.addEventListener("click",()=>showConfirm("Clear queue?","This removes finished/errored items and resets the feed & stats. Running items are kept.",clearAll));
  });
  _safeInit("stream",startStream);
  _safeInit("status",refreshStatus);
});
