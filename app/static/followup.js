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

function initCollapsible(){document.querySelectorAll(".card-head[data-collapse]").forEach(head=>{head.style.cursor="pointer";head.addEventListener("click",e=>{if(e.target.closest("button:not(.collapse-btn)"))return;const body=document.getElementById(head.dataset.collapse);if(!body)return;const card=head.closest(".card");const btn=head.querySelector(".collapse-btn");const collapsed=body.classList.toggle("collapsed");if(card)card.classList.toggle("is-collapsed",collapsed);if(btn)btn.textContent=collapsed?"\u25B6":"\u25BC"})})}

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
  const head=document.createElement("div");head.className="ahead";
  const nm=document.createElement("span");nm.className="aname";nm.textContent=artist;
  const badge=document.createElement("span");
  badge.className="badge "+(type==="drafted"?"keep":"drop");
  badge.textContent=type==="drafted"?"DRAFTED":"SKIPPED";
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
  else if(ev.type==="error_artist"){totalProcessed++;sys("✗ "+ev.artist+": "+ev.error,"bad");updateStats()}
  else if(ev.type==="done"){stopTimer();sys("✓ Done: "+ev.created+" follow-up drafts, "+ev.skipped+" skipped.","ok")}
  else if(ev.type==="stopped"){stopTimer();sys("■ Stopped.","warn")}
  else if(ev.type==="error"){stopTimer();sys("✗ "+ev.message,"bad")}
}

async function checkAuth(){
  const r=await fetch("/api/drafter/auth-check");const d=await r.json();
  $("pill-gmail").className="pill "+(d.ready?"ok":"missing");
  if(d.ready)sys("✓ Gmail authorized.","ok");
  else sys("⚠ Gmail not connected — add credentials.json to project root.","warn");
}

document.addEventListener("DOMContentLoaded",()=>{
  sys("Follow Upper starting…","info");
  initClock();initCollapsible();initToolsDropdown();
  startStream();checkAuth();

  $("stat-pct").addEventListener("click",()=>{_statShowFraction=!_statShowFraction;updateStats()});
  $("stat-clean").addEventListener("click",()=>{_cleanShowFraction=!_cleanShowFraction;updateStats()});

  $("btn-run").addEventListener("click",()=>{fetch("/api/followup/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({})});sys("RUN","info")});
  $("btn-stop").addEventListener("click",()=>{fetch("/api/followup/stop",{method:"POST"});sys("STOP","warn")});
  $("btn-clear").addEventListener("click",()=>{$("feeds-grid").innerHTML="";$("sys-log").innerHTML="";totalProcessed=0;totalArtists=0;totalCreated=0;updateStats();sys("Cleared.","info")});
});
