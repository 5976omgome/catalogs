"use strict";
const $=id=>document.getElementById(id);
const FEED_BLOCK_CAP=200;
function pct(p,t){return t>0?Math.floor(100*p/t):0}

function initClock(){function tick(){$("clock").textContent=new Date().toLocaleTimeString("en",{hour12:false,hour:"2-digit",minute:"2-digit",second:"2-digit"})}tick();setInterval(tick,1000)}

let _timerStart=null,_timerInterval=null;
function _renderTimer(){if(_timerStart==null)return;const e=Math.max(0,Math.floor((Date.now()-_timerStart)/1000));$("timer").textContent=String(Math.floor(e/60)).padStart(2,"0")+":"+String(e%60).padStart(2,"0")}
function startTimer(){_timerStart=Date.now();if(!_timerInterval)_timerInterval=setInterval(_renderTimer,1000);_renderTimer()}
function stopTimer(){if(_timerInterval){clearInterval(_timerInterval);_timerInterval=null}}

function sys(text,cls){const log=$("sys-log");const ts=new Date().toLocaleTimeString("en",{hour12:false,hour:"2-digit",minute:"2-digit",second:"2-digit"});const d=document.createElement("div");d.className="sysline "+(cls||"");d.textContent=`[${ts}] ${text}`;log.append(d);log.scrollTop=log.scrollHeight;while(log.children.length>200)log.firstChild.remove()}

function initCollapsible(){document.querySelectorAll(".card-head[data-collapse]").forEach(head=>{head.style.cursor="pointer";head.addEventListener("click",e=>{if(e.target.closest(".ftoggle")||e.target.closest("#global-filters")||e.target.closest("button:not(.collapse-btn)")||e.target.closest("label")||e.target.closest("input"))return;const body=document.getElementById(head.dataset.collapse);if(!body)return;const card=head.closest(".card");const btn=head.querySelector(".collapse-btn");const collapsed=body.classList.toggle("collapsed");if(card)card.classList.toggle("is-collapsed",collapsed);if(btn)btn.textContent=collapsed?"\u25B6":"\u25BC"})})}

function initToolsDropdown(){const btn=$("tool-btn"),menu=$("tools-menu");if(!btn||!menu)return;btn.addEventListener("click",e=>{e.stopPropagation();menu.classList.toggle("open")});document.addEventListener("click",()=>menu.classList.remove("open"));menu.addEventListener("click",e=>e.stopPropagation())}

let totalProcessed=0,totalArtists=0,totalCreated=0;
let _statShowFraction=false,_cleanShowFraction=false;
function updateStats(){
  $("stat-pct").textContent=_statShowFraction?totalProcessed+"/"+totalArtists:pct(totalProcessed,totalArtists)+"% TOTAL";
  $("stat-clean").textContent=_cleanShowFraction?totalCreated+"/"+totalProcessed:pct(totalCreated,totalProcessed)+"% CLEAN";
}

function addToFeed(artist,week,type){
  const grid=$("feeds-grid");
  const block=document.createElement("div");block.className="ablock";
  const cat=type==="drafted"?"drafted":(type==="error"?"error":"skipped");
  block.dataset.cat=cat;
  if(!gFilters[cat])block.style.display="none";
  const head=document.createElement("div");head.className="ahead";
  const nm=document.createElement("span");nm.className="aname";nm.textContent=artist;
  const badge=document.createElement("span");
  badge.className="badge "+(type==="drafted"?"keep":"drop");
  badge.textContent=type==="drafted"?"DRAFTED":(type==="error"?"ERROR":"SKIPPED");
  head.append(nm,badge);block.append(head);
  if(week){const row=document.createElement("div");row.className="src";const lbl=document.createElement("div");lbl.className="src-name";lbl.textContent="WEEK";const vals=document.createElement("div");vals.className="src-vals";vals.textContent=week;row.append(lbl,vals);block.append(row)}
  grid.append(block);
  while(grid.children.length>FEED_BLOCK_CAP)grid.firstChild.remove();
  grid.scrollTop=grid.scrollHeight;
}

function startStream(){
  const es=new EventSource("/api/followup/stream");
  es.onmessage=msg=>{let d;try{d=JSON.parse(msg.data)}catch{return}handleEvent(d)};
  es.onerror=()=>{sys("Stream disconnected, reconnecting…","warn");es.close();setTimeout(startStream,2000)};
  sys("Connected.","info");
}

function handleEvent(ev){
  if(ev.type==="started"){startTimer();sys("Follow Upper running…","info")}
  else if(ev.type==="total"){totalArtists=ev.count;sys("Found "+ev.count+" threads to process.","info");updateStats()}
  else if(ev.type==="sys"){sys(ev.text,ev.cls||"")}
  else if(ev.type==="drafted"){totalProcessed++;totalCreated++;addToFeed(ev.artist,ev.week||"","drafted");sys("✓ "+ev.artist,"ok");updateStats()}
  else if(ev.type==="skip"){totalProcessed++;addToFeed("(existing draft)","","skip");updateStats()}
  else if(ev.type==="error_artist"){totalProcessed++;addToFeed(ev.artist||"Error","","error");sys("✗ "+ev.artist+": "+ev.error,"bad");updateStats()}
  else if(ev.type==="done"){stopTimer();sys("✓ Done: "+ev.created+" follow-up drafts, "+ev.skipped+" skipped.","ok")}
  else if(ev.type==="stopped"){stopTimer();sys("■ Stopped.","warn")}
  else if(ev.type==="error"){stopTimer();sys("✗ "+ev.message,"bad")}
}

const gFilters={drafted:true,skipped:true,error:true};
function initFilters(){
  [["gf-drafted","drafted"],["gf-skipped","skipped"],["gf-error","error"]].forEach(([id,key])=>{
    const el=$(id);if(!el)return;
    el.addEventListener("click",()=>{gFilters[key]=!gFilters[key];el.classList.toggle("on",gFilters[key]);el.classList.toggle("off",!gFilters[key]);applyFilters()});
  });
}
function applyFilters(){document.querySelectorAll("#feeds-grid .ablock").forEach(b=>{b.style.display=gFilters[b.dataset.cat]?"":"none"})}

// Confirm modal
let _confirmCb=null;
function initConfirmModal(){const modal=$("confirm-modal");if(!modal)return;const close=$("confirm-close"),yes=$("confirm-yes"),no=$("confirm-no");close.addEventListener("click",()=>modal.classList.remove("open"));no.addEventListener("click",()=>modal.classList.remove("open"));modal.addEventListener("click",e=>{if(e.target===modal)modal.classList.remove("open")});yes.addEventListener("click",()=>{modal.classList.remove("open");if(_confirmCb)_confirmCb()})}
function showConfirm(title,msg,cb){const modal=$("confirm-modal");if(!modal){if(cb)cb();return}$("confirm-title").textContent=title;$("confirm-msg").textContent=msg;_confirmCb=cb;modal.classList.add("open")}

// Feedback
const fbState={category:null,rawText:""};
function initFeedback(){const btn=$("btn-feedback"),modal=$("feedback-modal"),close=$("feedback-close");if(!btn||!modal)return;btn.addEventListener("click",()=>{resetFb();modal.classList.add("open")});close.addEventListener("click",()=>modal.classList.remove("open"));modal.addEventListener("click",e=>{if(e.target===modal)modal.classList.remove("open")});document.querySelectorAll(".fb-cat").forEach(b=>{b.addEventListener("click",()=>{document.querySelectorAll(".fb-cat").forEach(x=>x.classList.remove("active"));b.classList.add("active");fbState.category=b.dataset.cat;updateFbSubmit()})});$("fb-text").addEventListener("input",e=>{fbState.rawText=e.target.value.trim();updateFbSubmit()});$("fb-submit").addEventListener("click",handleFbSubmit)}
function resetFb(){fbState.category=null;fbState.rawText="";document.querySelectorAll(".fb-cat").forEach(b=>b.classList.remove("active"));$("fb-text").value="";$("fb-submit").disabled=true;$("fb-submit-status").textContent=""}
function updateFbSubmit(){$("fb-submit").disabled=!(fbState.category&&fbState.rawText)}
async function handleFbSubmit(){if(!fbState.category||!fbState.rawText)return;$("fb-submit").disabled=true;$("fb-submit-status").textContent="Submitting...";try{const r=await fetch("/api/feedback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({category:fbState.category,text:fbState.rawText,raw_text:"",ai_enhanced:false})});const d=await r.json();if(!r.ok)throw new Error(d.error||"Failed");$("fb-submit-status").textContent="\u2713 "+d.file;$("fb-submit-status").className="fb-submit-status ok";sys("Feedback: "+d.file,"ok");setTimeout(()=>{$("feedback-modal").classList.remove("open");resetFb()},1200)}catch(e){$("fb-submit-status").textContent=e.message;$("fb-submit-status").className="fb-submit-status bad";$("fb-submit").disabled=false}}

async function checkAuth(){
  const r=await fetch("/api/drafter/auth-check");const d=await r.json();
  $("pill-gmail").className="pill "+(d.ready?"ok":"missing");
  if(d.ready)sys("✓ Gmail authorized.","ok");
  else sys("⚠ Gmail not connected — add credentials.json to project root.","warn");
}

document.addEventListener("DOMContentLoaded",()=>{
  sys("Follow Upper starting…","info");
  initClock();initCollapsible();initToolsDropdown();initFilters();initConfirmModal();initFeedback();
  startStream();checkAuth();

  $("stat-pct").addEventListener("click",()=>{_statShowFraction=!_statShowFraction;updateStats()});
  $("stat-clean").addEventListener("click",()=>{_cleanShowFraction=!_cleanShowFraction;updateStats()});

  $("btn-run").addEventListener("click",()=>{fetch("/api/followup/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({})});sys("RUN","info")});
  $("btn-stop").addEventListener("click",()=>showConfirm("Stop follow-ups?","This halts Gmail follow-up drafting.",()=>{fetch("/api/followup/stop",{method:"POST"});sys("STOP","warn")}));
  $("btn-clear").addEventListener("click",()=>showConfirm("Clear feed?","This clears the feed and console.",()=>{$("feeds-grid").innerHTML="";$("sys-log").innerHTML="";totalProcessed=0;totalArtists=0;totalCreated=0;updateStats();sys("Cleared.","info")}));
});
