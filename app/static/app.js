"use strict";
const $=id=>document.getElementById(id);

// ---------------------------------------------------------------------------
// CLOCK + TIMER + STATS
// ---------------------------------------------------------------------------
let _timerStart=null;let _timerInterval=null;

function initClock(){
  function tick(){
    const now=new Date();
    $("clock").textContent=now.toLocaleTimeString("en",{hour12:false,hour:"2-digit",minute:"2-digit",second:"2-digit"});
  }
  tick();setInterval(tick,1000);
}

function startTimer(){
  if(_timerInterval)return;
  _timerStart=Date.now();
  _timerInterval=setInterval(()=>{
    const elapsed=Math.floor((Date.now()-_timerStart)/1000);
    const m=String(Math.floor(elapsed/60)).padStart(2,"0");
    const s=String(elapsed%60).padStart(2,"0");
    $("timer").textContent=m+":"+s;
  },1000);
}

function stopTimer(){
  if(_timerInterval){clearInterval(_timerInterval);_timerInterval=null}
}

function updateStats(){
  // Count running items (slots used)
  const queueEl=$("queue");
  const items=queueEl?queueEl.querySelectorAll("li"):[];
  let running=0,totalProcessed=0,totalArtists=0,totalKeep=0;
  // We track from the qState
  Object.values(qState).forEach(li=>{
    const stat=li.querySelector(".stat");
    if(stat&&stat.classList.contains("running"))running++;
  });
  $("stat-slots").textContent=running+"/4";

  // Calculate totals from all feeds
  let allProcessed=0,allTotal=0,allKeep=0;
  Object.values(feeds).forEach(f=>{
    allKeep+=f.counts.keep||0;
    const total=(f.counts.keep||0)+(f.counts.review||0)+(f.counts.drop||0);
    allProcessed+=total;
  });

  // Total % finished (across all items)
  // We need total artists from queue items
  let queueTotal=0;
  Object.values(qState).forEach(li=>{
    const c=li.querySelector(".counts");
    if(c){const parts=c.textContent.split("/");if(parts[1])queueTotal+=parseInt(parts[1])||0}
  });
  const pct=queueTotal>0?Math.floor(100*allProcessed/queueTotal):0;
  $("stat-pct").textContent=pct+"%";

  // % clean (KEEP out of all processed)
  const cleanPct=allProcessed>0?Math.floor(100*allKeep/allProcessed):0;
  $("stat-clean").textContent=cleanPct+"% CLEAN";
}

// ---------------------------------------------------------------------------
// GLOBAL FILTERS — shared across all feeds
// ---------------------------------------------------------------------------
const gFilters={drop:true,review:true,keep:true,socials:true,debug:false};

function initGlobalFilters(){
  ["drop","review","keep","socials","debug"].forEach(key=>{
    const el=$("gf-"+key);
    el.classList.toggle("on",gFilters[key]);
    el.classList.toggle("off",!gFilters[key]);
    el.addEventListener("click",()=>{
      gFilters[key]=!gFilters[key];
      el.classList.toggle("on",gFilters[key]);
      el.classList.toggle("off",!gFilters[key]);
      applyAllFilters();
    });
  });
}

function applyAllFilters(){
  Object.keys(feeds).forEach(id=>{
    const feed=feeds[id];
    feed.log.querySelectorAll(".ablock").forEach(b=>{
      const s=b.dataset.status;
      if(s==="KEEP")b.style.display=gFilters.keep?"":"none";
      else if(s==="REVIEW")b.style.display=gFilters.review?"":"none";
      else b.style.display=gFilters.drop?"":"none";
    });
  });
}

// ---------------------------------------------------------------------------
// COLLAPSIBLE CARDS
// ---------------------------------------------------------------------------
function initCollapsible(){
  document.querySelectorAll(".card-head[data-collapse]").forEach(head=>{
    head.style.cursor="pointer";
    head.addEventListener("click",e=>{
      if(e.target.closest("button:not(.collapse-btn)")||e.target.closest("label")||e.target.closest("input"))return;
      const bodyId=head.dataset.collapse;
      const body=document.getElementById(bodyId);
      const btn=head.querySelector(".collapse-btn");
      if(body.style.display==="none"){body.style.display="";if(btn)btn.textContent="\u25BC"}
      else{body.style.display="none";if(btn)btn.textContent="\u25B6"}
    });
  });
}

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
// Status pills — turn red when key missing, clickable to set key
// ---------------------------------------------------------------------------
let _keyModalTarget=null;

async function refreshStatus(){
  try{
    const r=await fetch("/api/status");const s=await r.json();
    $("pill-itunes").className="pill ok clickable";
    $("pill-deezer").className="pill ok clickable";
    $("pill-groq").className="pill clickable "+(s.groq_set?"ok":"missing");
    $("pill-gemini").className="pill clickable "+(s.gemini_set?"ok":"missing");
    $("pill-genius").className="pill clickable "+(s.genius_set?"ok":"missing");
    if(!s.genius_set)sys("⚠ Genius — click pill to add key.","warn");
    if(!s.groq_set&&!s.gemini_set)sys("⚠ No AI keys — click pills to add.","warn");
    if(s.groq_set)sys("✓ Groq ready.","ok");
    if(s.gemini_set)sys("✓ Gemini ready.","ok");
    if(s.genius_set)sys("✓ Genius ready.","ok");
    sys("✓ iTunes + Deezer ready.","ok");
    sys("Virtual Scout ready.","info");
  }catch(e){sys("Server connection failed: "+e.message,"bad")}
}

function initKeyModal(){
  const modal=$("key-modal"),close=$("key-modal-close"),save=$("key-modal-save"),input=$("key-modal-input");
  close.addEventListener("click",()=>modal.classList.remove("open"));
  modal.addEventListener("click",e=>{if(e.target===modal)modal.classList.remove("open")});
  document.querySelectorAll(".pill.clickable").forEach(pill=>{
    pill.addEventListener("click",()=>{
      const key=pill.dataset.key;
      if(!key||key==="itunes"||key==="deezer")return;
      _keyModalTarget=key;
      const names={groq_api_key:"GROQ",gemini_api_key:"GEMINI",genius_token:"GENIUS"};
      $("key-modal-title").textContent="Set "+(names[key]||key)+" Key";
      input.value="";$("key-modal-msg").textContent="";
      modal.classList.add("open");input.focus();
    });
  });
  save.addEventListener("click",async()=>{
    const val=input.value.trim();
    if(!val){$("key-modal-msg").textContent="Paste a key first";return}
    const body={};body[_keyModalTarget]=val;
    const r=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    if(r.ok){$("key-modal-msg").textContent="✓ Saved";input.value="";
      setTimeout(()=>{modal.classList.remove("open");refreshStatus()},800)}
    else{$("key-modal-msg").textContent="Error"}
  });
  input.addEventListener("keydown",e=>{if(e.key==="Enter")save.click()});
}

// ---------------------------------------------------------------------------
// Queue
// ---------------------------------------------------------------------------
const qState={};
function renderItem(item){
  if(qState[item.id]){qState[item.id].remove();delete qState[item.id]}
  const li=document.createElement("li");li.dataset.id=item.id;
  const name=document.createElement("span");name.className="name";name.textContent=item.filename;
  const stat=document.createElement("span");stat.className="stat "+item.status;
  stat.textContent=item.status==="running"?`${Math.floor(100*item.processed/Math.max(item.total,1))}%`:item.status.toUpperCase();
  li.append(name);
  if(item.total>0&&item.status==="running"){const c=document.createElement("span");c.className="counts";c.textContent=`${item.processed}/${item.total}`;li.append(c)}
  if(item.has_output){const exp=document.createElement("span");exp.className="exports";
    const stem=item.filename.replace(/\.(csv|tsv)$/i,"");
    const mk=(l,c,u,f)=>{const b=document.createElement("button");b.type="button";b.textContent=l;b.className=c;b.addEventListener("click",()=>dl(b,u,f));return b};
    exp.append(mk("KEEP","btn-keep",`/api/export/${item.id}/keep`,`${stem}-keep.xlsx`),
      mk("DROPS","btn-drops",`/api/export/${item.id}/drops`,`${stem}-drops.xlsx`),
      mk("FULL","btn-full",`/api/download/${item.id}`,`${stem}.xlsx`));li.append(exp)}
  li.append(stat);$("queue").append(li);qState[item.id]=li;
}

// ---------------------------------------------------------------------------
// Download
// ---------------------------------------------------------------------------
async function dl(btn,url,name){
  const orig=btn.textContent;btn.disabled=true;btn.textContent="\u2026";
  try{const r=await fetch(url);
    if(!r.ok){let msg=`${r.status}`;try{const j=await r.json();if(j.error)msg=j.error}catch(e){}
      btn.textContent=orig;btn.disabled=false;sys("Download error: "+msg,"bad");return}
    const blob=await r.blob();const cd=r.headers.get("Content-Disposition")||"";
    const m=/filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd);
    const filename=(m&&decodeURIComponent(m[1].replace(/"$/,"")))||name;
    if(window.showSaveFilePicker){try{const h=await window.showSaveFilePicker({suggestedName:filename,
      types:[{description:"Excel",accept:{"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":[".xlsx"]}}]});
      const w=await h.createWritable();await w.write(blob);await w.close();btn.textContent="\u2713";sys("Saved: "+filename,"ok");
      setTimeout(()=>{btn.textContent=orig;btn.disabled=false},1500);return}catch(e){if(e.name==="AbortError"){btn.textContent=orig;btn.disabled=false;return}}}
    const u=URL.createObjectURL(blob);const a=document.createElement("a");a.href=u;a.download=filename;a.style.display="none";
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);
    btn.textContent="\u2713";sys("Downloaded: "+filename,"ok");setTimeout(()=>{btn.textContent=orig;btn.disabled=false},1500);
  }catch(err){btn.textContent=orig;btn.disabled=false;sys("Download error: "+err.message,"bad")}}

// ---------------------------------------------------------------------------
// FEEDS — each CSV gets its own panel, system console always present
// ---------------------------------------------------------------------------
const feeds={};

function ensureFeed(itemId,filename){
  if(feeds[itemId])return feeds[itemId];
  const panel=document.createElement("div");panel.className="feed-panel";panel.dataset.id=itemId;
  const header=document.createElement("div");header.className="feed-header";
  const title=document.createElement("span");title.className="feed-title";title.textContent=filename;
  const bar=document.createElement("div");bar.className="feed-bar";
  const barFill=document.createElement("span");barFill.style.width="0%";bar.append(barFill);
  const pct=document.createElement("span");pct.className="feed-pct";pct.textContent="0%";
  header.append(title,bar,pct);
  const log=document.createElement("div");log.className="feed-log";
  panel.append(header,log);
  $("feeds-grid").append(panel);
  const feed={el:panel,log,barFill,pct,counts:{drop:0,review:0,keep:0}};
  feeds[itemId]=feed;
  updateGridLayout();
  return feed;
}

function removeFeed(itemId){if(feeds[itemId]){feeds[itemId].el.remove();delete feeds[itemId];updateGridLayout()}}

function updateGridLayout(){
  const grid=$("feeds-grid");
  const n=Object.keys(feeds).length;
  grid.className="feeds-grid";
  if(n<=1)grid.classList.add("cols-1");
  else if(n===2)grid.classList.add("cols-2");
  else if(n===3)grid.classList.add("cols-3");
  else grid.classList.add("cols-4");
  $("feeds-title").textContent=n>1?"FEEDS":"FEED";
}

function addArtistToFeed(ev){
  const feed=ensureFeed(ev.item_id,"");
  const block=document.createElement("div");block.className="ablock";
  let cat="drop";if(ev.status==="KEEP")cat="keep";else if(ev.status==="REVIEW")cat="review";
  block.dataset.status=ev.status;
  feed.counts[cat]++;
  // Apply global filter
  if(!gFilters[cat])block.style.display="none";

  const head=document.createElement("div");head.className="ahead";
  const nm=document.createElement("span");nm.className="aname";nm.textContent=ev.artist;
  const badge=document.createElement("span");badge.className="badge "+cat;badge.textContent=ev.status;
  head.append(nm,badge);
  if(ev.earliest_year){const yr=document.createElement("span");yr.className="counter";yr.textContent=""+ev.earliest_year;head.append(yr)}
  block.append(head);

  const order=["Chartmetric","iTunes","Deezer"];
  for(const src of order){
    const items=(ev.sources&&ev.sources[src])||[];
    const row=document.createElement("div");row.className="src";
    const lbl=document.createElement("div");lbl.className="src-name";lbl.textContent=src.toUpperCase();
    const vals=document.createElement("div");vals.className="src-vals";
    if(!items.length){const e=document.createElement("span");e.className="empty";e.textContent="\u2014";vals.append(e)}
    else{for(const it of items){const line=document.createElement("span");line.className="entry";
      line.append(document.createTextNode(it.label||""));
      if(it.classification){const tag=document.createElement("span");tag.className="tag "+it.classification;tag.textContent=it.classification;line.append(tag)}
      vals.append(line)}}
    row.append(lbl,vals);block.append(row)}

  if(ev.status_reason){const reason=document.createElement("div");reason.className="reason";
    reason.innerHTML='<span class="arrow">\u2192</span>'+ev.status_reason.replace(/</g,"&lt;");block.append(reason)}
  // Genius socials — render as a proper source row alongside Chartmetric/iTunes/Deezer
  if(gFilters.socials){
    const row=document.createElement("div");row.className="src";
    const lbl=document.createElement("div");lbl.className="src-name";lbl.textContent="GENIUS";
    const vals=document.createElement("div");vals.className="src-vals";
    if(ev.socials&&(ev.socials.instagram||ev.socials.twitter||ev.socials.facebook||ev.socials.youtube)){
      if(ev.socials.instagram){const a=document.createElement("a");a.href="https://instagram.com/"+ev.socials.instagram;a.target="_blank";a.rel="noopener";a.className="social-link";a.textContent="IG: @"+ev.socials.instagram;vals.append(a)}
      if(ev.socials.twitter){const a=document.createElement("a");a.href="https://x.com/"+ev.socials.twitter;a.target="_blank";a.rel="noopener";a.className="social-link";a.textContent="X: @"+ev.socials.twitter;vals.append(a)}
      if(ev.socials.facebook){const a=document.createElement("a");a.href="https://facebook.com/"+ev.socials.facebook;a.target="_blank";a.rel="noopener";a.className="social-link";a.textContent="FB: "+ev.socials.facebook;vals.append(a)}
      if(ev.socials.youtube){const a=document.createElement("a");a.href=ev.socials.youtube;a.target="_blank";a.rel="noopener";a.className="social-link";a.textContent="YT: "+ev.socials.youtube.replace(/https?:\/\/(www\.)?youtube\.com\/?/,"");vals.append(a)}
    }else{const e=document.createElement("span");e.className="empty";e.textContent="\u2014";vals.append(e)}
    row.append(lbl,vals);block.append(row)
  }
  if(ev.debug&&gFilters.debug){const dbg=document.createElement("div");dbg.className="debug-info";
    dbg.textContent=ev.debug.steps.join(" | ");block.append(dbg)}

  feed.log.append(block);feed.log.scrollTop=feed.log.scrollHeight;
  const p=ev.total?Math.floor(100*ev.processed/ev.total):0;
  feed.barFill.style.width=p+"%";feed.pct.textContent=p+"%";
  sys(`${ev.status==="KEEP"?"\u2713":ev.status==="REVIEW"?"\u26a0":"\u2717"} ${ev.artist} \u2192 ${ev.status}`,cat==="keep"?"ok":cat==="review"?"warn":"bad");
}

// ---------------------------------------------------------------------------
// SSE
// ---------------------------------------------------------------------------
function startStream(){
  const es=new EventSource("/api/stream");
  es.onmessage=msg=>{let d;try{d=JSON.parse(msg.data)}catch{return}handleEvent(d)};
  es.onerror=()=>{sys("Stream disconnected, reconnecting\u2026","warn");es.close();setTimeout(startStream,2000)};
  sys("Connected to server.","info");
}
function handleEvent(ev){
  if(ev.type==="snapshot"){$("queue").innerHTML="";Object.keys(qState).forEach(k=>delete qState[k]);
    (ev.items||[]).forEach(i=>{renderItem(i);if(i.status==="running")ensureFeed(i.id,i.filename)})}
  else if(ev.type==="item_added"){renderItem(ev.item);sys("+ "+ev.item.filename,"info")}
  else if(ev.type==="item_started"){renderItem(ev.item);ensureFeed(ev.item.id,ev.item.filename);updateStats();sys("\u25b6 "+ev.item.filename,"info")}
  else if(ev.type==="artist_done"){addArtistToFeed(ev);updateStats();
    const li=qState[ev.item_id];if(li){const stat=li.querySelector(".stat");if(stat)stat.textContent=`${Math.floor(100*ev.processed/ev.total)}%`;
      const c=li.querySelector(".counts");if(c)c.textContent=`${ev.processed}/${ev.total}`}}
  else if(ev.type==="item_done"){renderItem(ev.item);updateStats();sys("\u2713 Done: "+ev.item.filename,"ok");checkAllDone()}
  else if(ev.type==="item_stopped"){renderItem(ev.item);updateStats();sys("\u25a0 Stopped: "+ev.item.filename,"warn")}
  else if(ev.type==="item_error"){renderItem(ev.item);sys("\u2717 Error: "+(ev.item.error||ev.item.filename),"bad")}
  else if(ev.type==="genius_progress"){
    const s=ev.socials||{};const parts=[];
    if(s.instagram)parts.push("IG");if(s.facebook)parts.push("FB");
    const found=parts.length?parts.join("+"):"—";
    sys(`[genius] ${ev.artist} → ${found} (${ev.total_found} found / ${ev.processed} checked)`,ev.found?"ok":"")
  }
  else if(ev.type==="genius_done"){
    sys(`[genius] ✓ Complete: ${ev.found} socials from ${ev.processed} artists.`,"ok");
    $("btn-genius").disabled=false;$("btn-genius").textContent="GENIUS";$("btn-genius-stop").style.display="none";
  }
}

function checkAllDone(){
  // Stop timer when no running items remain
  let anyRunning=false;
  Object.values(qState).forEach(li=>{
    const stat=li.querySelector(".stat");
    if(stat&&stat.classList.contains("running"))anyRunning=true;
  });
  if(!anyRunning)stopTimer();
}

// ---------------------------------------------------------------------------
// Upload + Init
// ---------------------------------------------------------------------------
async function uploadFile(file){const fd=new FormData();fd.append("file",file);
  const r=await fetch("/api/upload",{method:"POST",body:fd});
  if(!r.ok){const e=await r.json().catch(()=>({error:"failed"}));sys("Upload error: "+(e.error||""),"bad")}}

// ---------------------------------------------------------------------------
// GENIUS SEPARATE PASS
// ---------------------------------------------------------------------------
async function startGeniusPass(){
  const btn=$("btn-genius");
  btn.disabled=true;btn.textContent="RUNNING…";
  $("btn-genius-stop").style.display="";
  sys("Genius pass starting (1 artist / 2 sec)…","info");
  try{
    const r=await fetch("/api/genius/run",{method:"POST"});
    const d=await r.json();
    if(!r.ok){sys("Genius error: "+(d.error||""),"bad");btn.disabled=false;btn.textContent="GENIUS";$("btn-genius-stop").style.display="none"}
  }catch(e){sys("Genius start failed: "+e.message,"bad");btn.disabled=false;btn.textContent="GENIUS";$("btn-genius-stop").style.display="none"}
}

async function stopGeniusPass(){
  await fetch("/api/genius/stop",{method:"POST"});
  sys("Genius pass stopped.","warn");
  $("btn-genius").disabled=false;$("btn-genius").textContent="GENIUS";
  $("btn-genius-stop").style.display="none";
}

// ---------------------------------------------------------------------------
// FEEDBACK SYSTEM
// ---------------------------------------------------------------------------
const fbState={category:null,rawText:"",cleanedText:"",isClean:false};

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

  $("fb-text").addEventListener("input",e=>{
    fbState.rawText=e.target.value.trim();fbState.isClean=false;fbState.cleanedText="";
    $("fb-preview-wrap").style.display="none";$("fb-ai-status").textContent="";
    updateFbSubmit()});

  $("fb-ai-clean").addEventListener("click",handleFbClean);
  $("fb-submit").addEventListener("click",handleFbSubmit);
}

function resetFb(){
  fbState.category=null;fbState.rawText="";fbState.cleanedText="";fbState.isClean=false;
  document.querySelectorAll(".fb-cat").forEach(b=>b.classList.remove("active"));
  $("fb-text").value="";$("fb-preview-wrap").style.display="none";
  $("fb-ai-status").textContent="";$("fb-ai-status").className="fb-ai-status";
  $("fb-submit-status").textContent="";$("fb-submit-status").className="fb-submit-status";
  $("fb-submit").disabled=true;$("fb-ai-clean").disabled=true;
}

function updateFbSubmit(){
  $("fb-submit").disabled=!(fbState.category&&fbState.rawText);
  $("fb-ai-clean").disabled=!fbState.rawText;
}

async function handleFbClean(){
  if(!fbState.rawText)return;
  const btn=$("fb-ai-clean"),status=$("fb-ai-status");
  btn.disabled=true;status.textContent="Processing...";status.className="fb-ai-status";
  try{
    const r=await fetch("/api/feedback/clean",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({text:fbState.rawText,category:fbState.category||"OTHER"})});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||"API error");
    fbState.cleanedText=d.cleaned;fbState.isClean=true;
    $("fb-preview").textContent=d.cleaned;$("fb-preview-wrap").style.display="";
    status.textContent="Enhanced \u2713";status.className="fb-ai-status ok";
  }catch(e){status.textContent=e.message;status.className="fb-ai-status bad"}
  finally{btn.disabled=!fbState.rawText}
}

async function handleFbSubmit(){
  if(!fbState.category||!fbState.rawText)return;
  const btn=$("fb-submit"),status=$("fb-submit-status");
  btn.disabled=true;status.textContent="Submitting...";status.className="fb-submit-status";
  const payload={
    category:fbState.category,
    text:fbState.isClean?fbState.cleanedText:fbState.rawText,
    raw_text:fbState.isClean?fbState.rawText:"",
    ai_enhanced:fbState.isClean
  };
  try{
    const r=await fetch("/api/feedback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||"Submit failed");
    status.textContent="Submitted \u2713 "+d.file;status.className="fb-submit-status ok";
    sys("Feedback submitted: "+d.file,"ok");
    setTimeout(()=>{$("feedback-modal").classList.remove("open");resetFb()},1500);
  }catch(e){status.textContent=e.message;status.className="fb-submit-status bad";btn.disabled=false}
}

document.addEventListener("DOMContentLoaded",()=>{
  sys("Virtual Scout starting\u2026","info");
  initClock();
  initGlobalFilters();
  initCollapsible();
  initFeedback();
  $("file-input").addEventListener("change",e=>{for(const f of e.target.files)uploadFile(f);e.target.value=""});
  $("btn-run").addEventListener("click",()=>{fetch("/api/queue/start",{method:"POST"});sys("RUN","info");startTimer()});
  $("btn-stop").addEventListener("click",()=>{fetch("/api/queue/stop",{method:"POST"});sys("STOP","warn");stopTimer()});
  $("btn-export-all").addEventListener("click",()=>dl($("btn-export-all"),"/api/export_all","AllCombinedOutput.xlsx"));
  $("btn-genius").addEventListener("click",startGeniusPass);
  $("btn-genius-stop").addEventListener("click",stopGeniusPass);
  $("btn-clear").addEventListener("click",()=>{fetch("/api/queue/clear",{method:"POST"});Object.keys(feeds).forEach(id=>removeFeed(id));sys("Cleared.","info")});
  initKeyModal();
  startStream();refreshStatus();
});
