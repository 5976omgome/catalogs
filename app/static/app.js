"use strict";
const $=id=>document.getElementById(id);

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
// Status pills + startup diagnostics
// ---------------------------------------------------------------------------
async function refreshStatus(){
  try{
    const r=await fetch("/api/status");const s=await r.json();
    $("pill-itunes").className="pill ok";
    $("pill-deezer").className="pill ok";
    const pa=$("pill-ai");
    const ok=s.groq_set||s.gemini_set;
    let t="AI OFF";
    if(s.groq_set&&s.gemini_set)t="GROQ+GEMINI";
    else if(s.groq_set)t="GROQ";
    else if(s.gemini_set)t="GEMINI";
    pa.textContent=t;pa.className="pill "+(ok?"ok":"");
    let pg=document.getElementById("pill-genius");
    if(!pg){pg=document.createElement("span");pg.id="pill-genius";pg.className="pill";document.querySelector(".pills").append(pg)}
    pg.textContent=s.genius_set?"GENIUS":"GENIUS OFF";pg.className="pill "+(s.genius_set?"ok":"");
    if(!s.genius_set)sys("\u26a0 Genius token not configured \u2014 socials will not be pulled.","warn");
    if(!ok)sys("\u26a0 No AI keys configured \u2014 AI bridge disabled.","warn");
    if(s.genius_set)sys("\u2713 Genius API ready.","ok");
    if(ok)sys("\u2713 AI bridge ready ("+t+").","ok");
    sys("\u2713 iTunes + Deezer ready.","ok");
    sys("Ready. Drop CSV files and click RUN.","info");
  }catch(e){sys("Failed to connect: "+e.message,"bad")}
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
async function loadSettings(){
  try{const r=await fetch("/api/settings");const s=await r.json();
    $("prev-groq").textContent=s.groq_api_key.set?s.groq_api_key.preview:"\u2014";
    $("prev-gemini").textContent=s.gemini_api_key.set?s.gemini_api_key.preview:"\u2014";
    $("prev-genius").textContent=s.genius_token.set?s.genius_token.preview:"\u2014";
  }catch(e){}}
async function saveKeys(){
  const body={};const g=$("key-groq").value.trim();const m=$("key-gemini").value.trim();const gn=$("key-genius").value.trim();
  if(g)body.groq_api_key=g;if(m)body.gemini_api_key=m;if(gn)body.genius_token=gn;
  if(!Object.keys(body).length){$("keys-msg").textContent="NOTHING TO SAVE";return}
  const r=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  if(r.ok){$("keys-msg").textContent="SAVED \u2713";$("key-groq").value="";$("key-gemini").value="";$("key-genius").value="";
    loadSettings();refreshStatus();setTimeout(()=>$("keys-msg").textContent="",2000)}
  else{$("keys-msg").textContent="ERROR";sys("Failed to save keys","bad")}}
async function clearKeys(){if(!confirm("Clear ALL API keys?"))return;
  await fetch("/api/settings/clear",{method:"POST"});loadSettings();sys("Keys cleared.","warn");refreshStatus()}

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
  // Total panels = system console + feed panels
  const feedCount=Object.keys(feeds).length;
  const totalPanels=1+feedCount; // 1 for system console
  grid.className="feeds-grid";
  if(totalPanels<=1)grid.classList.add("cols-1");
  else if(totalPanels===2)grid.classList.add("cols-2");
  else if(totalPanels===3)grid.classList.add("cols-3");
  else grid.classList.add("cols-4");
  // Update header title
  $("feeds-title").textContent=feedCount>1?"FEEDS":"FEED";
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
  if(ev.socials&&gFilters.socials){const soc=document.createElement("div");soc.className="socials";const parts=[];
    if(ev.socials.instagram)parts.push("IG: @"+ev.socials.instagram);
    if(ev.socials.twitter)parts.push("X: @"+ev.socials.twitter);
    if(ev.socials.facebook)parts.push("FB: "+ev.socials.facebook);
    if(parts.length)soc.textContent=parts.join(" \u00b7 ");block.append(soc)}
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
  else if(ev.type==="item_started"){renderItem(ev.item);ensureFeed(ev.item.id,ev.item.filename);sys("\u25b6 "+ev.item.filename,"info")}
  else if(ev.type==="artist_done"){addArtistToFeed(ev);
    const li=qState[ev.item_id];if(li){const stat=li.querySelector(".stat");if(stat)stat.textContent=`${Math.floor(100*ev.processed/ev.total)}%`;
      const c=li.querySelector(".counts");if(c)c.textContent=`${ev.processed}/${ev.total}`}}
  else if(ev.type==="item_done"){renderItem(ev.item);sys("\u2713 Done: "+ev.item.filename,"ok")}
  else if(ev.type==="item_stopped"){renderItem(ev.item);sys("\u25a0 Stopped: "+ev.item.filename,"warn")}
  else if(ev.type==="item_error"){renderItem(ev.item);sys("\u2717 Error: "+(ev.item.error||ev.item.filename),"bad")}
}

// ---------------------------------------------------------------------------
// Upload + Init
// ---------------------------------------------------------------------------
async function uploadFile(file){const fd=new FormData();fd.append("file",file);
  const r=await fetch("/api/upload",{method:"POST",body:fd});
  if(!r.ok){const e=await r.json().catch(()=>({error:"failed"}));sys("Upload error: "+(e.error||""),"bad")}}

document.addEventListener("DOMContentLoaded",()=>{
  sys("Catalog Audit v4 starting\u2026","info");
  initGlobalFilters();
  initCollapsible();
  $("file-input").addEventListener("change",e=>{for(const f of e.target.files)uploadFile(f);e.target.value=""});
  $("btn-run").addEventListener("click",()=>{fetch("/api/queue/start",{method:"POST"});sys("RUN","info")});
  $("btn-stop").addEventListener("click",()=>{fetch("/api/queue/stop",{method:"POST"});sys("STOP","warn")});
  $("btn-export-all").addEventListener("click",()=>dl($("btn-export-all"),"/api/export_all","AllCombinedOutput.xlsx"));
  $("btn-clear").addEventListener("click",()=>{fetch("/api/queue/clear",{method:"POST"});Object.keys(feeds).forEach(id=>removeFeed(id));sys("Cleared.","info")});
  $("btn-save-keys").addEventListener("click",saveKeys);
  $("btn-clear-keys").addEventListener("click",clearKeys);
  loadSettings();startStream();refreshStatus();
});
