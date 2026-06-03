"use strict";
const $=id=>document.getElementById(id);

// ---------------------------------------------------------------------------
// Status pills
// ---------------------------------------------------------------------------
async function refreshStatus(){
  try{
    const r=await fetch("/api/status");const s=await r.json();
    $("pill-itunes").className="pill ok";
    $("pill-deezer").className="pill ok";
    const pa=$("pill-ai");
    const ok=s.groq_set||s.gemini_set;
    let t="ai off";
    if(s.groq_set&&s.gemini_set)t="groq+gemini";
    else if(s.groq_set)t="groq";
    else if(s.gemini_set)t="gemini";
    pa.textContent=t;pa.className="pill "+(ok?"ok":"");
  }catch(e){}
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
async function loadSettings(){
  try{
    const r=await fetch("/api/settings");const s=await r.json();
    $("prev-groq").textContent=s.groq_api_key.set?s.groq_api_key.preview:"\u2014";
    $("prev-gemini").textContent=s.gemini_api_key.set?s.gemini_api_key.preview:"\u2014";
  }catch(e){}
}
async function saveKeys(){
  const body={};
  const g=$("key-groq").value.trim();
  const m=$("key-gemini").value.trim();
  if(g)body.groq_api_key=g;if(m)body.gemini_api_key=m;
  if(!Object.keys(body).length){$("keys-msg").textContent="nothing to save";return}
  $("keys-msg").textContent="saving\u2026";
  const r=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  if(r.ok){$("keys-msg").textContent="saved \u2713";$("key-groq").value="";$("key-gemini").value="";
    loadSettings();refreshStatus();setTimeout(()=>$("keys-msg").textContent="",2000)}
  else $("keys-msg").textContent="error";
}
async function clearKeys(){
  if(!confirm("Clear ALL stored API keys?"))return;
  await fetch("/api/settings/clear",{method:"POST"});loadSettings();refreshStatus();
}

// ---------------------------------------------------------------------------
// Queue (compact — just filename + status + exports)
// ---------------------------------------------------------------------------
const qState={};
function renderItem(item){
  if(qState[item.id]){qState[item.id].remove();delete qState[item.id]}
  const li=document.createElement("li");li.dataset.id=item.id;

  const name=document.createElement("span");name.className="name";name.textContent=item.filename;
  const stat=document.createElement("span");stat.className="stat "+item.status;
  stat.textContent=item.status==="running"?`${Math.floor(100*item.processed/Math.max(item.total,1))}%`:item.status;
  li.append(name);

  if(item.total>0&&item.status==="running"){
    const counts=document.createElement("span");counts.className="counts";
    counts.textContent=`${item.processed}/${item.total}`;
    li.append(counts);
  }

  if(item.has_output){
    const exp=document.createElement("span");exp.className="exports";
    const stem=item.filename.replace(/\.(csv|tsv)$/i,"");
    const mk=(label,cls,url,fname)=>{const b=document.createElement("button");b.type="button";b.textContent=label;b.className=cls;
      b.addEventListener("click",()=>dl(b,url,fname));return b};
    exp.append(
      mk("KEEP","btn-keep",`/api/export/${item.id}/keep`,`${stem}-keep.xlsx`),
      mk("DROPS","btn-drops",`/api/export/${item.id}/drops`,`${stem}-drops.xlsx`),
      mk("FULL","btn-full",`/api/download/${item.id}`,`${stem}.xlsx`),
    );
    li.append(exp);
  }

  li.append(stat);
  $("queue").append(li);qState[item.id]=li;
}

// ---------------------------------------------------------------------------
// Download helper
// ---------------------------------------------------------------------------
async function dl(btn,url,suggestedName){
  const orig=btn.textContent;btn.disabled=true;btn.textContent="\u2026";
  try{
    const r=await fetch(url);
    if(!r.ok){let msg=`${r.status}`;try{const j=await r.json();if(j.error)msg=j.error}catch(e){}
      btn.textContent=orig;btn.disabled=false;alert("Download: "+msg);return}
    const blob=await r.blob();
    const cd=r.headers.get("Content-Disposition")||"";
    const m=/filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd);
    const filename=(m&&decodeURIComponent(m[1].replace(/"$/,"")))||suggestedName;
    if(window.showSaveFilePicker){
      try{const h=await window.showSaveFilePicker({suggestedName:filename,
        types:[{description:"Excel",accept:{"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":[".xlsx"]}}]});
        const w=await h.createWritable();await w.write(blob);await w.close();
        btn.textContent="\u2713";setTimeout(()=>{btn.textContent=orig;btn.disabled=false},1500);return;
      }catch(e){if(e.name==="AbortError"){btn.textContent=orig;btn.disabled=false;return}}
    }
    const u=URL.createObjectURL(blob);const a=document.createElement("a");a.href=u;a.download=filename;a.style.display="none";
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);
    btn.textContent="\u2713";setTimeout(()=>{btn.textContent=orig;btn.disabled=false},1500);
  }catch(err){btn.textContent=orig;btn.disabled=false}
}

// ---------------------------------------------------------------------------
// FEEDS — multi-panel grid with per-feed filter toggles
// ---------------------------------------------------------------------------
const feeds={};  // item_id → {el, log, filters:{drop:true,review:true,keep:true}, counts:{drop:0,review:0,keep:0}}

function ensureFeed(itemId, filename){
  if(feeds[itemId]) return feeds[itemId];

  const panel=document.createElement("div");panel.className="feed-panel";panel.dataset.id=itemId;

  // Header: title + progress bar + percentage
  const header=document.createElement("div");header.className="feed-header";
  const title=document.createElement("span");title.className="feed-title";title.textContent=filename;
  const bar=document.createElement("div");bar.className="feed-bar";
  const barFill=document.createElement("span");barFill.style.width="0%";bar.append(barFill);
  const pct=document.createElement("span");pct.className="feed-pct";pct.textContent="0%";
  header.append(title,bar,pct);

  // Filter toggles
  const filters=document.createElement("div");filters.className="feed-filters";
  const state={drop:true,review:true,keep:true};
  const counts={drop:0,review:0,keep:0};

  function mkToggle(key,label,cls){
    const el=document.createElement("span");
    el.className=`ftoggle ${cls} on`;el.dataset.key=key;
    el.textContent=`${label} (0)`;
    el.addEventListener("click",()=>{
      state[key]=!state[key];
      el.classList.toggle("on",state[key]);
      el.classList.toggle("off",!state[key]);
      applyFilters(itemId);
    });
    return el;
  }
  const tDrop=mkToggle("drop","Flagged","f-drop");
  const tReview=mkToggle("review","Review","f-review");
  const tKeep=mkToggle("keep","Clean","f-keep");
  filters.append(tDrop,tReview,tKeep);

  // Log area
  const log=document.createElement("div");log.className="feed-log";

  panel.append(header,filters,log);
  $("feeds-grid").append(panel);

  const feed={el:panel,log,barFill,pct,filters:state,counts,toggles:{drop:tDrop,review:tReview,keep:tKeep}};
  feeds[itemId]=feed;
  updateGridLayout();
  return feed;
}

function removeFeed(itemId){
  if(feeds[itemId]){
    feeds[itemId].el.remove();
    delete feeds[itemId];
    updateGridLayout();
  }
}

function updateGridLayout(){
  const grid=$("feeds-grid");
  const n=Object.keys(feeds).length;
  grid.className="feeds-grid";
  if(n<=1) grid.classList.add("cols-1");
  else if(n===2) grid.classList.add("cols-2");
  else if(n===3) grid.classList.add("cols-3");
  else grid.classList.add("cols-4");
}

function applyFilters(itemId){
  const feed=feeds[itemId];if(!feed)return;
  const blocks=feed.log.querySelectorAll(".ablock");
  blocks.forEach(b=>{
    const status=b.dataset.status;
    if(status==="KEEP") b.style.display=feed.filters.keep?"":"none";
    else if(status==="REVIEW") b.style.display=feed.filters.review?"":"none";
    else b.style.display=feed.filters.drop?"":"none";
  });
}

function updateFeedCounts(itemId){
  const feed=feeds[itemId];if(!feed)return;
  feed.toggles.drop.textContent=`Flagged (${feed.counts.drop})`;
  feed.toggles.review.textContent=`Review (${feed.counts.review})`;
  feed.toggles.keep.textContent=`Clean (${feed.counts.keep})`;
}

function addArtistToFeed(ev){
  const feed=ensureFeed(ev.item_id, "");
  const block=document.createElement("div");block.className="ablock";
  let statusCat="drop";
  if(ev.status==="KEEP")statusCat="keep";
  else if(ev.status==="REVIEW")statusCat="review";
  block.dataset.status=ev.status;

  // Count
  feed.counts[statusCat]++;
  updateFeedCounts(ev.item_id);

  // Visibility based on filter
  if(!feed.filters[statusCat]) block.style.display="none";

  // Header
  const head=document.createElement("div");head.className="ahead";
  const nm=document.createElement("span");nm.className="aname";nm.textContent=ev.artist;
  const badge=document.createElement("span");
  badge.className="badge "+statusCat;badge.textContent=ev.status;
  head.append(nm,badge);
  if(ev.earliest_year){const yr=document.createElement("span");yr.className="counter";yr.textContent=""+ev.earliest_year;head.append(yr)}
  block.append(head);

  // Sources
  const order=["Chartmetric","iTunes","Deezer"];
  for(const src of order){
    const items=(ev.sources&&ev.sources[src])||[];
    const row=document.createElement("div");row.className="src";
    const lbl=document.createElement("div");lbl.className="src-name";lbl.textContent=src;
    const vals=document.createElement("div");vals.className="src-vals";
    if(!items.length){const e=document.createElement("span");e.className="empty";e.textContent="\u2014";vals.append(e)}
    else{for(const it of items){
      const line=document.createElement("span");line.className="entry";
      line.append(document.createTextNode(it.label||""));
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

  feed.log.append(block);
  feed.log.scrollTop=feed.log.scrollHeight;

  // Update progress bar
  const p=ev.total?Math.floor(100*ev.processed/ev.total):0;
  feed.barFill.style.width=p+"%";
  feed.pct.textContent=p+"%";
}

// ---------------------------------------------------------------------------
// SSE
// ---------------------------------------------------------------------------
function startStream(){
  const es=new EventSource("/api/stream");
  es.onmessage=msg=>{let d;try{d=JSON.parse(msg.data)}catch{return}handleEvent(d)};
  es.onerror=()=>{es.close();setTimeout(startStream,2000)};
}
function handleEvent(ev){
  if(ev.type==="snapshot"){
    $("queue").innerHTML="";Object.keys(qState).forEach(k=>delete qState[k]);
    (ev.items||[]).forEach(i=>{renderItem(i);if(i.status==="running")ensureFeed(i.id,i.filename)});
  }
  else if(ev.type==="item_added"){renderItem(ev.item)}
  else if(ev.type==="item_started"){renderItem(ev.item);ensureFeed(ev.item.id,ev.item.filename)}
  else if(ev.type==="artist_done"){
    addArtistToFeed(ev);
    // Update queue item
    const li=qState[ev.item_id];
    if(li){
      const stat=li.querySelector(".stat");
      if(stat)stat.textContent=`${Math.floor(100*ev.processed/ev.total)}%`;
      const counts=li.querySelector(".counts");
      if(counts)counts.textContent=`${ev.processed}/${ev.total}`;
    }
  }
  else if(ev.type==="item_done"){renderItem(ev.item)}
  else if(ev.type==="item_stopped"){renderItem(ev.item)}
  else if(ev.type==="item_error"){renderItem(ev.item)}
}

// ---------------------------------------------------------------------------
// Upload + Init
// ---------------------------------------------------------------------------
async function uploadFile(file){
  const fd=new FormData();fd.append("file",file);
  await fetch("/api/upload",{method:"POST",body:fd});
}

document.addEventListener("DOMContentLoaded",()=>{
  $("file-input").addEventListener("change",e=>{for(const f of e.target.files)uploadFile(f);e.target.value=""});
  $("btn-run").addEventListener("click",()=>fetch("/api/queue/start",{method:"POST"}));
  $("btn-stop").addEventListener("click",()=>fetch("/api/queue/stop",{method:"POST"}));
  $("btn-clear").addEventListener("click",()=>{
    fetch("/api/queue/clear",{method:"POST"});
    // Remove finished feed panels
    Object.keys(feeds).forEach(id=>{
      const li=qState[id];
      if(!li||!li.querySelector(".stat.running"))removeFeed(id);
    });
  });
  $("btn-save-keys").addEventListener("click",saveKeys);
  $("btn-clear-keys").addEventListener("click",clearKeys);
  $("btn-toggle-keys").addEventListener("click",()=>{
    const b=$("keys-body");b.style.display=b.style.display==="none"?"":"none"});
  refreshStatus();loadSettings();startStream();
});
