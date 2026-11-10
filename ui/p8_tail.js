
// ---------- data loading (profiles and radars are separate files) ----------
D.players={};D.radars={};D.viewboxes={};
const IDX=()=>Object.fromEntries(D.index.map(e=>[e.steamid,e]));
async function loadRadar(map){if(D.viewboxes[map])return;try{const r=await fetch(`radars/${map}.json`);if(!r.ok)return;const j=await r.json();
  Object.entries(j.levels).forEach(([k,u])=>D.radars[`${map}:${k}`]=u);D.viewboxes[map]=j.viewbox}catch(e){}}
async function loadPlayer(id,force){if(!force&&D.players[id])return D.players[id];
  const r=await fetch(`players/${id}.json`+(force?`?t=${Date.now()}`:""));if(!r.ok)throw new Error(tl("profile not found"));
  const p=await r.json();D.players[id]=p;const maps=new Set([...p.matches.map(m=>m.map),...((p.cross||{}).maps||[]).map(m=>m.map)]);
  await Promise.all([...maps].map(loadRadar));return p}

// ---------- view: players ----------
let jq="",jsort="n",jshow=24;   // 24 profiles at a time (the list had 22 screens)
function renderPlayers(){
  const v=$("#v-players");
  const list=D.index.filter(e=>!jq||e.name.toLowerCase().includes(jq)||e.steamid.includes(jq)||(e.archetype||"").toLowerCase().includes(jq)||Object.keys(e.maps||{}).some(m=>MAPN(m).toLowerCase().includes(jq)))
    .sort((a,b)=>(b.steamid===D.own)-(a.steamid===D.own)||(jsort==="n"?b.n-a.n:jsort==="kd"?(b.kd||0)-(a.kd||0):jsort==="adr"?(b.adr||0)-(a.adr||0):(b.last||"").localeCompare(a.last||"")));
  const shown=list.slice(0,jshow);
  v.innerHTML=`<div class="head"><div style="display:grid;gap:4px"><span class="eyebrow">${tln(D.index.length,"{n} profile · data built {date}","{n} profiles · data built {date}",{date:fmtDate(D.generated)})}</span><h2>${tl("Players")}</h2></div></div>
  <div class="btns" style="align-items:center"><input id="jf" type="search" value="${esc(jq)}" placeholder="${tl("Filter by name, SteamID, map or archetype")}" aria-label="${tl("Filter players")}" style="font:14px var(--f-body);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:3px;padding:6px 10px;min-width:260px">
    ${[["n",tl("Most demos")],["kd","K/D"],["adr","ADR"],["last",tl("Most recent")]].map(([k,t])=>`<button type="button" data-sort="${k}" aria-pressed="${jsort===k}">${t}</button>`).join("")}</div>
  ${jq?`<p class="note">${tln(list.length,"{n} profile matches.","{n} profiles match.")}</p>`:""}
  <div class="players">${shown.map(e=>`<button type="button" class="pcard" data-pid="${e.steamid}" aria-pressed="${e.steamid===S.player}">
    <b>${esc(e.name)}</b><span class="num note">${e.steamid}${e.rank?` · ${SKILL[e.rank]||""}`:""}</span>${e.archetype?`<span class="arch-tag" style="margin:0">${esc(e.archetype)}</span>`:""}
    <span>${e.minimal?tl("Minimal profile (public rankings, no demo)"):e.light?tl("Leetify-only profile (no demo)"):`${tln(e.n,"{n} demo","{n} demos")} · K/D ${e.kd==null?"—":e.kd} · ADR ${e.adr==null?"—":Math.round(e.adr)} · ${tl("{w}W {d}D {l}L",{w:e.record.win,d:e.record.draw,l:e.record.loss})}`}</span>
    <span class="note">${Object.entries(e.maps||{}).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([m,n])=>`${MAPN(m)} ${n}`).join(" · ")}</span>
    ${e.top_rule?`<span class="note">${tl("Priority: {what}",{what:esc(e.top_rule)})}</span>`:""}</button>`).join("")||`<div class="empty">${tl("No player matches.")}</div>`}</div>
  ${list.length>shown.length?`<div class="btns"><button type="button" id="jmore">${tl("Show {n} more ({left} left)",{n:Math.min(24,list.length-shown.length),left:list.length-shown.length})}</button></div>`:""}
  <div class="card"><h3>${tl("Analyze any player")}</h3>
    <p>${D.local?tl("Paste their Steam profile link, SteamID64 or custom URL name in the search bar at the top: the analysis runs on your PC."):tl("In the local version (double-click <code>Wily.bat</code>), paste their Steam profile link or SteamID64 in the search bar at the top. This published page can only show players already analyzed.")}</p>
    <p class="note">${tl("Demo sources: the ones already downloaded, their recent matchmaking matches via Leetify (about a month), their share codes (<code>--sharecode</code>) or their whole history with their authentication code (<code>--authcode</code>). Without demos, a light profile is built from their Leetify stats.")}</p></div>`;
  const jf=$("#jf",v);jf.oninput=()=>{jq=jf.value.trim().toLowerCase();jshow=24;const pos=jf.selectionStart;renderPlayers();const n=$("#jf");n.focus();n.setSelectionRange(pos,pos)};
  $$("[data-sort]",v).forEach(b=>b.onclick=()=>{jsort=b.dataset.sort;jshow=24;renderPlayers()});
  const jm=$("#jmore",v);if(jm)jm.onclick=()=>{const y=scrollY;jshow+=24;renderPlayers();scrollTo(0,y)};
  $$("[data-pid]",v).forEach(b=>b.onclick=()=>{setPlayer(b.dataset.pid).then(()=>go(b.dataset.pid===D.own?"review":"analysis"))});
}

// ---------- view: pros ----------
let PROS=null,pq="",proSel=null;
async function loadPros(){if(PROS)return PROS;try{const r=await fetch("pros.json");PROS=r.ok?await r.json():[]}catch(e){PROS=[]}return PROS}
function proDetail(x){const st=x.stats;const n=(v,s="")=>v==null?"—":String(v)+s;
  return `<article class="card prodetail"><div class="arch-h"><span class="ic" aria-hidden="true">${x.icon}</span><span class="nm">${esc(x.handle)}</span>
    ${x.prole==="igl"?`<span class="probadge">IGL</span>`:""}<span class="note">${esc(x.real_name||"")}${x.team?` · ${esc(x.team)}`:""} · ${esc(x.role_name)}</span>
    <a href="${esc(x.hltv)}" target="_blank" rel="noopener" style="color:var(--ct);font-size:13px">${tl("See on HLTV")}</a></div>
    ${x.traits.length?`<div class="traits">${x.traits.map(t=>`<span title="${esc(t.text)}">${esc(tEN(t.label))}</span>`).join("")}</div>`:""}
    <div class="kv"><div><b>${n(st.kpr)}</b><span>${tl("kills per round")}</span></div><div><b>${n(st.hs,"%")}</b><span>${tl("headshot kills")}</span></div>
      <div><b>${n(st.open_win,"%")}</b><span>${tl("opening duels won")}</span></div><div><b>${n(st.trade_rate)}</b><span>${tl("trades per round")}</span></div>
      <div><b>${n(st.iso_T==null?null:Math.round(st.iso_T)," u")}</b><span>${tl("distance to teammate as T")}</span></div><div><b>${n(st.util_pr)}</b><span>${tl("grenades per round")}</span></div>
      <div><b>${n(st.late_share,"%")}</b><span>${tl("kills after 0:55")}</span></div><div><b>${st.first_duel_t==null?"—":clock(st.first_duel_t)}</b><span>${tl("first duel of the round")}</span></div></div>
    <div><span class="lbl4" style="color:var(--muted)">${tl("Weapons (share of kills)")}</span>
      <div class="wbar">${Object.entries(x.weapons).filter(([k,v])=>v>0).map(([k,v])=>`<i style="width:${v}%;background:${WCOL[k]||"var(--muted)"}" title="${esc(k)} ${v}%"></i>`).join("")}</div>
      <div class="wleg">${Object.entries(x.weapons).filter(([k,v])=>v>0).map(([k,v])=>`<span><b style="background:${WCOL[k]||"var(--muted)"}"></b>${esc(k)} ${v}%</span>`).join("")}</div>
      ${x.top_weapons.length?`<p class="note">${tl("Favorites: {list}",{list:x.top_weapons.slice(0,3).map(w=>`${esc(w.weapon)} (${w.kills})`).join(", ")})}</p>`:""}</div>
    <span class="lbl4" style="color:var(--muted)">${tl("Zones played per map ({maps}, {rounds} rounds)",{maps:tln(x.maps,"{n} map","{n} maps"),rounds:x.rounds})}</span>
    <div class="zmaps">${Object.entries(x.zones).map(([m,sd])=>`<div><b>${MAPN(m)}</b>${["T","CT"].filter(k=>sd[k]).map(k=>`<br><span class="note">${k}:</span> ${sd[k].map(z=>`${esc(z.zone)} ${z.share}%`).join(" · ")}`).join("")}</div>`).join("")}</div>
  </article>`}
async function renderPros(){const v=$("#v-pros");const ps=await loadPros();
  const list=ps.filter(x=>!pq||[x.handle,x.real_name,x.team,x.role_name].some(t=>(t||"").toLowerCase().includes(pq)));
  const sel=ps.find(x=>x.steamid===proSel);
  v.innerHTML=`<div class="head"><div style="display:grid;gap:4px"><span class="eyebrow">${tl("{n} pro players analyzed on their recent match demos (HLTV)",{n:ps.length})}</span><h2>${tl("Pros")}</h2></div></div>
   ${sel?proDetail(sel):""}
   <div class="btns" style="align-items:center"><input id="pf" type="search" value="${esc(pq)}" placeholder="${tl("Filter by handle, name, team or role")}" aria-label="${tl("Filter pros")}" style="font:14px var(--f-body);background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:3px;padding:6px 10px;min-width:260px"></div>
   <div class="players">${list.map(x=>`<button type="button" class="pcard" data-pro="${x.steamid}" aria-pressed="${x.steamid===proSel}"><b>${esc(x.handle)}${x.prole==="igl"?`<span class="probadge">IGL</span>`:""}</b>
     <span class="note">${esc(x.team||"")}${x.real_name?` · ${esc(x.real_name)}`:""}</span><span class="arch-tag" style="margin:0">${x.icon} ${esc(x.role_name)}</span>
     <span class="note">${x.traits.slice(0,3).map(t=>esc(tEN(t.label))).join(" · ")}</span></button>`).join("")||`<div class="empty">${tl("No pro matches.")}</div>`}</div>
   <p class="note">${tl("Pros without a recent demo (team absent from the downloaded matches) don't show up yet. Pros' Steam profiles: public community guides on Steam.")}</p>`;
  const pf=$("#pf",v);pf.oninput=()=>{pq=pf.value.trim().toLowerCase();const pos=pf.selectionStart;renderPros().then(()=>{const n=$("#pf");n.focus();n.setSelectionRange(pos,pos)})};
  $$("[data-pro]",v).forEach(b=>b.onclick=()=>{proSel=b.dataset.pro;renderPros();window.scrollTo(0,0)});
}
function openPro(sid){proSel=sid;go("pros")}

// ---------- search ----------
function playerOptions(){}
function findKnown(q){const t=q.trim(),low=t.toLowerCase().replace(/\/+$/,"");const id=(t.match(/7656\d{13}/)||[])[0];const I=IDX();if(id)return I[id]?id:null;
  const van=(low.match(/\/id\/([^\/?#]+)/)||[])[1]||(!/[\/:]/.test(low)?low:null);
  for(const e of D.index){if((e.name||"").toLowerCase()===low||(van&&(e.vanity||"").toLowerCase()===van))return e.steamid}
  return null}
// the analysis's progress (16/10, the user: "beaucoup plus visuel et ux" than the server's log, then "fais-lui prendre
// moins de place"): one line (what runs, how far, the time) over a thin bar of one segment per step (its name, result and
// time on hover); the server's log behind "Details"
const STEP_PLAN={import:["extract","matches","profile","plan","page"],sync:["history","download","extract","matches","profile","plan","page"],search:["lookup","download","extract","matches","profile","plan","page"],
  again:["extract","matches","profile","plan","page"]};
const stepName=k=>({history:tl("Steam history"),lookup:tl("Finding the player and their matches"),download:tl("Downloading the demos"),
  extract:tl("Reading the demos"),matches:tl("Analyzing the matches"),profile:tl("Cross-match analysis"),plan:tl("Coaching plan"),page:tl("Profile page")})[k]||k;
const durTxt=s=>{s=Math.max(0,Math.round(s));return s<60?tl("{s} s",{s}):tl("{m} min {s} s",{m:Math.floor(s/60),s:s%60})};
let jobLogOpen=false;
function jobSteps(j){
  if(!Array.isArray(j.steps))return null;   // a server from before the steps (an app not restarted yet): its log only
  const kind=/^Steam sync/.test(j.query||"")?"sync":/^Demo import/.test(j.query||"")?"import":j.view==="matches"?"again":"search";
  const got=j.steps,by={};got.forEach(s=>by[s.key]=s);
  const plan=[...STEP_PLAN[kind]];got.forEach((s,i)=>{if(!plan.includes(s.key))plan.splice(i?plan.indexOf(got[i-1].key)+1:0,0,s.key)});
  const cur=got.length?got[got.length-1].key:null,ci=plan.indexOf(cur);
  const state=(k,i)=>by[k]?(by[k].t1||!j.running?"done":"run"):(i<ci||!j.running?"skip":"todo");
  const note=(k,s,st)=>{if(st==="skip")return tl("nothing to do");if(!s)return "";
    if(s.note&&s.note.new!=null)return s.note.new?tln(s.note.new,"{n} new match","{n} new matches"):tl("nothing new");
    if(s.n&&k==="page")return s.n>1?tln(s.n,"{n} profile","{n} profiles"):"";
    if(s.n)return st!=="done"?tl("{i} of {n}",{i:s.i||0,n:s.n}):["download","extract"].includes(k)?tln(s.n,"{n} demo","{n} demos"):tln(s.n,"{n} match","{n} matches");
    return ""};
  return {plan,by,cur,ci,state,note}}
function trackHtml(j){const S=jobSteps(j);if(!S)return "";const now=Date.now()/1000;
  return `<ol class="jtrack" aria-hidden="true">${S.plan.map((k,i)=>{const s=S.by[k],st=S.state(k,i),
    fr=st==="done"?1:st==="run"&&s&&s.n?Math.min(1,(s.i||0)/s.n):0,tip=[stepName(k),S.note(k,s,st),s?durTxt((s.t1||now)-s.t0):""].filter(Boolean).join(" · ");
    return `<li class="${st}${st==="run"&&!(s&&s.n)?" ind":""}" title="${esc(tip)}"><i style="width:${Math.round(fr*100)}%"></i></li>`}).join("")}</ol>`}
function curHtml(j){const S=jobSteps(j);if(!S||!S.cur)return "";const s=S.by[S.cur],nt=S.note(S.cur,s,S.state(S.cur,S.ci));
  return `<span class="jcur">${stepName(S.cur)}${nt?` <small>${nt}</small>`:""}</span><span class="sr-only">${tl("Step {i} of {n}: {name}",{i:S.ci+1,n:S.plan.length,name:stepName(S.cur)})}</span>`}
// the summary of a finished job: the new matches and the time it took
function doneHtml(j){const S=jobSteps(j),h=S&&S.by.history,n=h&&h.note?h.note.new:null;
  return `${n!=null?`<span class="jcur">${n?tln(n,"{n} new match","{n} new matches"):tl("nothing new")}</span>`:""}${j.t0&&j.t1?`<span class="jtime">${durTxt(j.t1-j.t0)}</span>`:""}`}
const moreBtn=logs=>logs?`<button type="button" class="jmore" aria-expanded="${jobLogOpen}">${tl("Details")}</button>`:"";
const logPre=(logs,open)=>logs?`<pre class="jlog"${open||jobLogOpen?"":" hidden"}>${logs}</pre>`:"";
function jobPanel(html,cls){const j=$("#job");j.hidden=false;const box=$(".in",j);box.className="in "+(cls||"");
  box.innerHTML=html+`<button type="button" class="jx" aria-label="${tl("Close")}" title="${tl("Close")}">×</button>`;$(".jx",box).onclick=()=>{j.hidden=true};
  const mb=$(".jmore",box),pr=$(".jlog",box);
  if(mb&&pr)mb.onclick=()=>{jobLogOpen=!jobLogOpen;pr.hidden=!jobLogOpen;mb.setAttribute("aria-expanded",String(jobLogOpen));if(jobLogOpen)pr.scrollTop=pr.scrollHeight};
  if(pr&&!pr.hidden)pr.scrollTop=pr.scrollHeight}
// demos given by hand (16/10: FACEIT's, while its download API waits for its approval): the account menu's Import, or
// files dropped anywhere on the page. Each one sent in turn (its progress), then one analysis of them all
const IMPORT_EXT=/\.(dem|zst|gz|bz2|xz|zip)$/i;
let importNote="";
function importDemos(list){
  const files=[...(list||[])].filter(f=>IMPORT_EXT.test(f.name));acctClose();
  if(!files.length){jobPanel(`<div class="jhead"><span class="jico bad" aria-hidden="true">!</span><b>${tl("No demo in these files (a .dem, or FACEIT's .dem.zst).")}</b></div>`,"err");return}
  const ok=[],bad=[];let i=0;
  const draw=(f,pct)=>jobPanel(`<div class="jhead"><span class="spin" aria-hidden="true"></span><b>${tl("Importing your demos…")}</b>`
    +`<span class="jcur">${esc(f.name)} <small>${tl("{i} of {n}",{i:i+1,n:files.length})}</small></span><span class="jtime" aria-hidden="true">${pct}%</span></div>`
    +`<ol class="jtrack" aria-hidden="true">${files.map((_,k)=>`<li class="${k<i?"done":k===i?"run":"todo"}"><i style="width:${k<i?100:k===i?pct:0}%"></i></li>`).join("")}</ol>`);
  const errs=()=>bad.length?`<ul class="jerr">${bad.map(b=>`<li><b>${esc(b.name)}</b> · ${esc(b.error)}</li>`).join("")}</ul>`:"";
  const finish=async()=>{
    if(!ok.some(d=>d.new)){jobPanel(`<div class="jhead"><span class="jico${bad.length?" bad":""}" aria-hidden="true">${bad.length?"!":"✓"}</span><b>${ok.length?tln(ok.length,"{n} demo already here: nothing new to analyze.","{n} demos already here: nothing new to analyze."):tl("No demo imported.")}</b></div>${errs()}`,bad.length?"err":"ok");return}
    try{const r=await fetch("/api/import/run",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
      if(!r.ok){const j=await r.json().catch(()=>({}));jobPanel(`<div class="jhead"><span class="jico bad" aria-hidden="true">!</span><b>${esc(j.error||tl("Error"))}</b></div>${errs()}`,"err");if(r.status===409)poll();return}
      importNote=errs();jobFrom=S.view;poll()}
    catch(e){jobPanel(`<div class="jhead"><span class="jico bad" aria-hidden="true">!</span><b>${tl("Wily's local server isn't responding.")}</b></div>`,"err")}};
  const next=()=>{if(i>=files.length)return finish();const f=files[i];draw(f,0);
    const x=new XMLHttpRequest();x.open("POST",`/api/import?name=${encodeURIComponent(f.name)}&mtime=${f.lastModified||0}`);
    x.upload.onprogress=e=>{if(e.lengthComputable)draw(f,Math.round(95*e.loaded/e.total))};
    x.onload=()=>{let r={};try{r=JSON.parse(x.responseText)}catch(e){}
      if(x.status===200)ok.push(r);else bad.push({name:f.name,error:r.error||x.statusText||String(x.status)});i++;next()};
    x.onerror=()=>{bad.push({name:f.name,error:tl("Wily's local server isn't responding.")});i++;next()};
    x.send(f)};
  next()}
{const ib=$("#impbtn"),fi=$("#impfile");if(ib&&fi){ib.onclick=()=>fi.click();fi.onchange=()=>{importDemos(fi.files);fi.value=""}}}
// a file dragged over the page: the drop zone shows (the app on this PC only: the files go to its server)
{let n=0;const has=e=>D.local&&[...((e.dataTransfer||{}).types||[])].includes("Files"),off=()=>{n=0;document.body.classList.remove("dropping")};
  document.addEventListener("dragenter",e=>{if(!has(e))return;n++;document.body.classList.add("dropping")});
  document.addEventListener("dragleave",()=>{if(n&&--n===0)off()});
  document.addEventListener("dragover",e=>{if(document.body.classList.contains("dropping"))e.preventDefault()});
  document.addEventListener("drop",e=>{if(!document.body.classList.contains("dropping"))return;e.preventDefault();off();importDemos(e.dataTransfer.files)})}
// the page only switches player or view for a job you started from here and while you stayed on that view:
// a background sync, or a job finishing while you read something else, never pulls you away
let polling=null,partialShown=null,jobFrom=null;
const mayGo=()=>jobFrom!==null&&S.view===jobFrom;
const openBtn=(sid,name,view)=>`<button type="button" class="jopen" data-open="${sid}" data-view="${view}">${name?tl("Open {name}",{name:esc(name)}):tl("Open the profile")}</button>`;
function bindOpen(){$$("[data-open]",$("#job")).forEach(b=>b.onclick=async()=>{delete D.players[b.dataset.open];await setPlayer(b.dataset.open,true);go(b.dataset.view)})}
async function startAnalysis(q,after){
  jobFrom=S.view;afterJob=after||null;   // after: what to open once done (the match of a /match/ address)
  $("#qbtn").disabled=true;
  try{const r=await fetch("/api/analyze?q="+encodeURIComponent(q));const j=await r.json();
    if(!r.ok){jobPanel(`<b>${esc(j.error||tl("Error"))}</b>${j.query?` (${esc(j.query)})`:""}`,"err");$("#qbtn").disabled=false;if(r.status===409)poll();return}
    poll()}catch(e){jobPanel(tl("<b>The local server doesn't answer.</b> Restart \"Wily.bat\" and I'll be back."),"err");$("#qbtn").disabled=false}}
function poll(){clearTimeout(polling);polling=setTimeout(async()=>{
  let j;try{j=await (await fetch("/api/job")).json()}catch(e){return poll()}
  const logs=(j.log||[]).slice(-60).map(esc).join("\n");
  if(j.running){
    if(j.partial&&partialShown!==j.partial&&mayGo()){partialShown=j.partial;try{D.index=await (await fetch(`index.json?t=${Date.now()}`)).json();playerOptions();delete D.players[j.partial];await setPlayer(j.partial,true);go(j.partial===D.own?"review":"analysis");jobFrom=S.view}catch(e){}}
    const steps=Array.isArray(j.steps);
    jobPanel(`<div class="jhead"><span class="spin" aria-hidden="true"></span><b>${partialShown?tl("First preview shown. Full demo analysis running…"):j.view==="matches"?tl("Analyzing the match again…"):/^Steam sync/.test(j.query||"")?tl("Updating your matches…"):/^Demo import/.test(j.query||"")?tl("Analyzing your imported demos…"):tl("Analyzing {what}…",{what:esc(j.query)})}</b>${curHtml(j)}<span class="jtime" aria-hidden="true">${j.t0?durTxt(Date.now()/1000-j.t0):""}</span>${steps?moreBtn(logs):""}</div>${trackHtml(j)}${logPre(logs||tl("Starting…"),!steps)}`);poll();return}
  $("#qbtn").disabled=false;const go_=mayGo(),aj=afterJob;jobFrom=null;afterJob=null;
  if(j.error){updFrom=null;const ub=$("#updbtn");if(ub)ub.disabled=false;jobPanel(`<div class="jhead"><span class="jico bad" aria-hidden="true">!</span><b>${esc(j.error)}</b>${moreBtn(logs)}</div>${trackHtml(j)}${logPre(logs)}`,"err");return}
  if(j.players&&j.players.length){D.index=await (await fetch(`index.json?t=${Date.now()}`)).json();playerOptions();
    const nm=((j.query||"").match(/CSGO(-[\w]{5}){5}/g)||[]).length,ps=[...j.players].sort((a,b)=>(b.steamid===D.own)-(a.steamid===D.own)),
      btn=p=>`<button type="button" data-mp="${p.steamid}">${esc(p.name)}</button>`;
    jobPanel(`<div class="jhead"><span class="jico" aria-hidden="true">✓</span><b>${nm>1?tl("{n} players analyzed in these {m} matches.",{n:j.players.length,m:nm}):tl("{n} players analyzed in this match.",{n:j.players.length})}</b>${doneHtml(j)}${moreBtn(logs)}</div><div class="btns">${ps.slice(0,10).map(btn).join("")}</div>
      ${ps.length>10?`<details><summary style="cursor:pointer" class="note">${tl("The other {n} players",{n:ps.length-10})}</summary><div class="btns">${ps.slice(10).map(btn).join("")}</div></details>`:""}${logPre(logs)}`,"ok");
    $$("[data-mp]",$("#job")).forEach(b=>b.onclick=()=>{delete D.players[b.dataset.mp];setPlayer(b.dataset.mp,true).then(()=>go("analysis"))});
    if(aj&&go_)aj();return}
  if(j.steamid&&j.view==="matches"){try{D.index=await (await fetch(`index.json?t=${Date.now()}`)).json();playerOptions();delete D.players[j.steamid];   // a re-analysis: back on that match
      if(go_){await setPlayer(j.steamid,true);const i=P().matches.findIndex(x=>x.id===j.match);S.match=i<0?0:i;S.mpin=i>=0;go("matches")}
      jobPanel(`<div class="jhead"><span class="jico" aria-hidden="true">✓</span><span>${tl("<b>The match is analyzed again.</b> Profile, plan and in-game sheet updated.")}</span>${doneHtml(j)}${go_?"":openBtn(j.steamid,null,"matches")}${moreBtn(logs)}</div>${logPre(logs)}`,"ok");bindOpen()}
    catch(e){jobPanel(`<div class="jhead"><span class="jico bad" aria-hidden="true">!</span><b>${tl("The match could not be shown.")}</b>${moreBtn(logs)}</div>${logPre(logs)}`,"err")}return}
  if(j.steamid){try{D.index=await (await fetch(`index.json?t=${Date.now()}`)).json();playerOptions();delete D.players[j.steamid];
      const upd=updFrom;updFrom=null;const ub=$("#updbtn");if(ub)ub.disabled=false;
      if(upd&&/(^|\D)0 new match/.test((j.log||[]).slice(-3).join(" "))&&!(j.log||[]).some(l=>/demo\(s\) from Valve|Analyzing/.test(l))){if(S.player===j.steamid)await setPlayer(j.steamid,true);go(upd);jobPanel(`<div class="jhead"><span class="jico" aria-hidden="true">✓</span><span>${tl("<b>Up to date</b>: no new match since the last analysis.")}</span>${doneHtml(j)}</div>`,"ok");return}
      const e=(D.index||[]).find(x=>x.steamid===j.steamid)||{},view=upd||(j.steamid===D.own?"review":"analysis");
      if(go_){await setPlayer(j.steamid,true);S.map=null}
      jobPanel(`<div class="jhead"><span class="jico" aria-hidden="true">✓</span><b>${tl("{name} is analyzed.",{name:esc(e.name||j.steamid)})}</b><span class="note">${e.light?tl("Light profile (Leetify stats, no demo available)."):e.n!=null?tln(e.n,"{n} demo analyzed.","{n} demos analyzed."):""}</span>${doneHtml(j)}${go_?"":openBtn(j.steamid,e.name,view)}${moreBtn(logs)}</div>${importNote}${logPre(logs)}`,"ok");importNote="";bindOpen();if(go_)go(view)}
    catch(e){jobPanel(`<div class="jhead"><span class="jico bad" aria-hidden="true">!</span><b>${tl("Nothing to show for this player.")}</b>${moreBtn(logs)}</div>${logPre(logs)}`,"err")}}},1000)}
$("#search").addEventListener("submit",async e=>{e.preventDefault();const q=$("#q").value.trim();if(!q)return;acctClose();
  const ps=await loadPros(),ql=q.toLowerCase(),idm=(q.match(/7656\d{13}/)||[])[0];
  const pro=ps.find(x=>x.handle.toLowerCase()===ql||x.steamid===idm);
  if(pro){$("#q").value="";$("#job").hidden=true;openPro(pro.steamid);return}
  const known=findKnown(q);
  if(known){const v0=S.view;await setPlayer(known);$("#job").hidden=true;$("#q").value="";
    go(known===D.own?"review":["profile","matches","maps","analysis","midround","progress","routine"].includes(v0)?v0:"profile");
    if(D.local){const e=IDX()[known]||{};   // one line, like the analyses' panel (16/10): who, how much, how recent, the update
      jobPanel(`<div class="jhead"><span class="jico" aria-hidden="true">✓</span><b>${tl("{name} is already analyzed.",{name:esc(P().name)})}</b>`
        +`<span class="note">${[e.n?tln(e.n,"{n} demo","{n} demos"):"",e.last?tl("last match {date}",{date:fmtDate(e.last)}):""].filter(Boolean).join(" · ")}</span>`
        +`<button type="button" class="jopen" id="refresh">${known===D.own?tl("↻ Update my matches"):tl("↻ Update their matches")}</button></div>`,"ok");$("#refresh").onclick=()=>startAnalysis(q)}
    return}
  if(D.local){partialShown=null;startAnalysis(q);return}
  const local=`http://127.0.0.1:8765/?q=${encodeURIComponent(q)}#ingame`;
  jobPanel(`<b>${tl("This player isn't in this page yet.")}</b><p>${tl("The analysis runs on your PC. Click below: the local app opens in a new tab and starts the analysis right away (a first preview in seconds, the full profile in a few minutes).")}</p>
    <p><a href="${esc(local)}" target="_blank" rel="noopener" style="display:inline-block;font:600 15px var(--f-body);padding:8px 14px;background:var(--ink);color:var(--bg);border-radius:3px;text-decoration:none">${tl("Analyze on my PC")}</a></p>
    <p class="note">${tl("I need to be running: double-click <code>Wily.bat</code> in my folder, or turn on its automatic start with <code>autostart.bat</code>.")}</p>`)});

// ---------- routing ----------
const RENDER={ingame:renderIngame,prepare:renderPrepare,review:renderReview,profile:renderProfile,analysis:renderAnalysis,routine:renderRoutine,midround:renderMidround,progress:renderProgress,team:renderTeam,matches:renderMatches,maps:renderMaps,players:renderPlayers,pros:renderPros,settings:renderSettings};
// The addresses (07/10, the user: "rends les URLs et la gestion de la navigation par URL plus UX"): the menus' own words,
// yours short, another player's the same under /player/<steamid>, and what you chose in them:
//   /review[?period=7d|week|month|30d|all] · /profile · /profile/reads · /profile/mid-round · /profile/maps/<map> ·
//   /profile/weapons · /profile/habits · /matches[/<share code>] · /prepare · /live · /settings
//   /player/<steamid>[/<the same>] (their Profile first)
// Older ones still open: /player/<steamid>/<view> (analysis, midround, progress, routine, ingame...), /match/<code>[?as=],
// /#review. The published page (one file) keeps #view.
// 07/10: Review first; Live opens itself when CS2 starts (serve.py) and from the bar
const GLOBAL=["team","players","pros","settings"],homeView=sid=>sid&&sid===D.own?"review":"profile";
const VSLUG={ingame:"live",prepare:"prepare",review:"review",profile:"profile",analysis:"profile/reads",midround:"profile/mid-round",
  maps:"profile/maps",progress:"profile/weapons",routine:"profile/habits",matches:"matches"};
const SLUGV=Object.fromEntries(Object.entries(VSLUG).map(([v,s])=>[s,v]));
const mapSlug=m=>String(m||"").replace(/^(de|cs|ar)_/,"");   // de_nuke -> nuke
const VTITLE={ingame:tl("Live"),prepare:tl("Prepare"),review:tl("Review"),profile:tl("Profile"),analysis:tl("Reads"),midround:tl("Mid-round"),maps:tl("Maps"),progress:tl("Weapons & buys"),
  routine:tl("Habits"),matches:tl("Matches"),settings:tl("Settings"),players:tl("Players"),pros:tl("Pros"),team:tl("Team")};
let navAt=0,navQuiet=0,afterJob=null,CODES={};   // CODES: match id -> share code
// a view's address for a player (you: no prefix)
function viewPath(v,sid){sid=sid===undefined?S.player:sid;if(GLOBAL.includes(v))return "/"+v;
  const mine=!sid||sid===D.own,base=mine?"":`/player/${sid}`;
  if(!mine&&v===homeView(sid))return base;
  return `${base}/${VSLUG[v]||v}`}
function pathNow(){const v=S.view;if(GLOBAL.includes(v))return "/"+v;if(!S.player)return "/";
  let u=viewPath(v);
  if(v==="maps"&&S.cmap)u+="/"+mapSlug(S.cmap);
  const m=v==="matches"&&S.mpin&&P()?P().matches[S.match]:null;
  if(m)u+="/"+(CODES[m.id]||m.id);
  if(v==="review"){const per=store("revper");if(per&&per!=="session")u+="?period="+per}
  return u}
function setTitle(){const v=S.view,p=S.player&&D.players[S.player],who=p&&S.player!==D.own?p.name+" · ":"";
  const mp=v==="maps"&&S.cmap?" · "+MAPN(S.cmap):"";document.title=`${who}${VTITLE[v]||"Wily"}${mp} · Wily`}
// the address of what is on screen: a new history entry for each move of yours (back works), the same entry for the
// steps of one move (a profile loading, then its view) and when the address itself led here
function syncUrl(){
  if(!D.local){if(location.hash.slice(1)!==S.view)history.replaceState(null,"",location.pathname+location.search+"#"+S.view);return}
  let u=pathNow();
  if(navQuiet){const k=[...new URLSearchParams(location.search)].filter(([n])=>n!=="as"&&n!=="q"&&n!=="period");if(k.length)u+=(u.includes("?")?"&":"?")+new URLSearchParams(k)}   // ?steam=… (back from Steam) stays for its page
  setTitle();
  if(location.pathname+location.search+location.hash===u)return;
  const now=Date.now();if(navQuiet||now-navAt<500)history.replaceState(null,"",u);else{history.pushState(null,"",u);navAt=now}}
function defPlayer(){const sp=store("player");return sp&&IDX()[sp]?sp:(D.own&&IDX()[D.own]?D.own:(D.local&&D.own?null:(D.default||(D.index[0]||{}).steamid||null)))}
// the address -> what to show
async function route(){
  const path=location.pathname.replace(/\/+$/,"")||"/",qs=new URLSearchParams(location.search),as=qs.get("as");
  const h=ALIAS[location.hash.slice(1)]||location.hash.slice(1),hv=RENDER[h]?h:null;   // an old link (/#review), or a #view link opened in a new tab
  let m,sid,rest=path;
  if((m=path.match(/^\/match\/([A-Za-z0-9-]+)$/)))return openMatch(m[1],as);   // the older match addresses
  if((m=path.match(/^\/player\/(\d{17})(\/.*)?$/))){sid=m[1];rest=m[2]||"";
    if(!IDX()[sid])return notYet(tl("This player (SteamID {id}) isn't analyzed yet.",{id:sid}),sid)}
  else sid=D.own&&IDX()[D.own]?D.own:defPlayer();   // an address without /player/<id> is yours, whoever you looked at last
  const seg=rest.split("/").filter(Boolean).map(x=>x.toLowerCase());
  if(seg[0]&&GLOBAL.includes(ALIAS[seg[0]]||seg[0])&&!m){S.view=ALIAS[seg[0]]||seg[0];return setPlayer(sid)}
  let v=null;
  if(seg[0]==="profile"){v=seg[1]?SLUGV["profile/"+seg[1]]||null:"profile";if(v==="maps"&&seg[2])S.cmapSlug=seg[2]}
  else if(seg[0]==="matches"){if(seg[1])return openMatch(seg[1],sid);v="matches"}
  else if(seg[0]){const o=ALIAS[seg[0]]||seg[0];v=SLUGV[o]||(RENDER[o]&&!GLOBAL.includes(o)?o:null)}   // review, prepare, live; analysis, midround, ingame…
  if(v==="review"||(!v&&!seg.length&&homeView(sid)==="review")){const per=qs.get("period");store("revper",["7d","week","month","30d","all"].includes(per)?per:"session")}   // the address says the period (back and forward too)
  if(seg.length&&!v&&!hv)return notYet(tl("Nothing at this address: {path}.",{path:esc(path)}));
  S.view=hv||v||homeView(sid);return setPlayer(sid)}
// /match/<id or share code>: that match, seen as the player of the address (?as=), else you, else an analyzed player in it
async function openMatch(code,as){
  let j=null;try{const r=await fetch("/api/match?code="+encodeURIComponent(code));if(r.ok)j=await r.json()}catch(e){}
  if(!j)return notYet(tl("No match at this address: a share code (CSGO-…) or a match id goes after /match/."));
  if(j.code)CODES[j.id]=j.code;
  for(const sid of [...new Set([as,D.own,...j.players])].filter(x=>x&&IDX()[x]&&(x===as||j.players.includes(x)))){
    S.view="matches";await setPlayer(sid);const i=((P()||{}).matches||[]).findIndex(x=>x.id===j.id);
    if(i>=0){S.match=i;S.mpin=true;show("matches");return}}
  const what=esc([j.map?MAPN(j.map):null,j.time?fmtDate(j.time):null].filter(Boolean).join(" · ")||tl("match {id}",{id:j.id}));
  if(j.code)return notYet(j.analyzed?tl("No analyzed profile shows this match yet ({what}).",{what}):tl("This match ({what}) isn't analyzed yet.",{what}),j.code,()=>openMatch(j.id,as));
  notYet(tl("This match ({what}) isn't analyzed: paste its share code (CSGO-…) in the search, or open /match/ with it.",{what}))}
// an address of a player or match the app doesn't show yet: said, and one click analyzes it
function notYet(msg,q,after){
  if(!S.player){const d=defPlayer();if(d){S.player=d;loadPlayer(d).catch(()=>{})}}   // the menus keep working
  if(!RENDER[S.view]||GLOBAL.includes(S.view))S.view=homeView(S.player);
  const v=$("#v-"+S.view);$$("main>.view").forEach(x=>x.hidden=x!==v);navUpdate(S.view);
  v.innerHTML=`<div class="empty">${msg}${q&&D.local?`<div class="btns" style="justify-content:center;margin-top:12px"><button type="button" id="nyet">${tl("Analyze it")}</button></div>`:""}</div>`;
  const b=$("#nyet",v);if(b)b.onclick=()=>{b.disabled=true;partialShown=null;startAnalysis(q,after)}}
function go(view){view=ALIAS[view]||view;if(!D.local&&location.hash!=="#"+view)history.replaceState(null,"",location.pathname+location.search+"#"+view);show(view)}
function show(view){view=ALIAS[view]||view;if(!RENDER[view])view="review";if(view!=="ingame")document.body.classList.remove("igfull");
  S.view=view;$$("main>.view").forEach(x=>x.hidden=x.id!=="v-"+view);setTitle();
  if(!D.local||GLOBAL.includes(view)||!S.player||D.players[S.player])syncUrl();   // a profile still loading: its address once it is in
  navUpdate(view);usageView(view);if(view!=="ingame")clearTimeout(gsiTimer);
  if(view==="players"){renderPlayers();return}
  if(view==="pros"){renderPros();window.scrollTo(0,0);return}
  if(view==="settings"){renderSettings();window.scrollTo(0,0);return}
  if(view==="team"){renderTeam();window.scrollTo(0,0);return}
  // no profile: the welcome (and on a new install, 05/10, everywhere until a first profile)
  if(!S.player){if(view==="ingame"||view==="review"||!Object.keys(IDX()).length)welcome($("#v-"+view));else $("#v-"+view).innerHTML=`<div class="empty">${tl("Show me a profile first: yours from the home page, or anyone from your menu (top right).")}</div>`;return}
  if(!D.players[S.player]){$("#v-"+view).innerHTML=`<div class="empty"><span class="spin" aria-hidden="true"></span>${tl("Loading the profile…")}</div>`;return}
  RENDER[view]();navUpdate(view);window.scrollTo(0,0);
  if(view==="maps"&&D.local){navQuiet++;try{syncUrl()}finally{navQuiet--}}   // the map is known once the page is drawn: /profile/maps/<map>
  if(view==="prepare"&&D.local)prepWatch();   // CS2 loads a map: Live takes over
  if(view==="ingame"&&D.local){if(!gsiStatus)fetch("/api/gsi/status").then(r=>r.json()).then(j=>{gsiStatus=j;if(S.view==="ingame"&&D.players[S.player])renderIngame()}).catch(()=>{});gsiPoll()}}
async function setPlayer(id,force){S.player=id;store("player",id);S.match=0;S.mpin=false;if(!id){show(S.view);return}
  if(!D.players[id]||force){show(S.view);try{await loadPlayer(id,force)}catch(e){$("#v-"+S.view).innerHTML=`<div class="empty">${tl("Couldn't load this profile ({why}).",{why:esc(e.message)})}</div>`;return}}
  show(S.view)}
S.map=HOST(store("map"))?null:store("map");S.side=store("side")||"T";
// a #view link: that view, at its address (the same history entry); back and forward: what their address says
window.addEventListener("hashchange",()=>{const h=location.hash.slice(1),v=ALIAS[h]||h;if(!D.local)return show(h);if(!RENDER[v])return;navQuiet++;try{show(v)}finally{navQuiet--}});
window.addEventListener("popstate",()=>{const h=location.hash.slice(1);if(!D.local||RENDER[ALIAS[h]||h])return;navQuiet++;route().finally(()=>navQuiet--)});
S.view=ALIAS[location.hash.slice(1)]||location.hash.slice(1)||"review";if(!RENDER[S.view])S.view="review";
{const f=store("focus");if(f||(f==null&&location.pathname.replace(/\/+$/,"")==="/live"))document.body.classList.add("focus")}   // /live: 2nd screen mode unless you left it
// Update: your new matches fetched and analyzed (the same as the automatic sync, now)
let updFrom=null;
{const ub=$("#updbtn");if(ub&&D.local&&D.own){ub.hidden=false;
  ub.onclick=async()=>{ub.disabled=true;acctClose();updFrom=S.view;jobFrom=S.view;
    try{await api("/api/steam/sync",{sid:D.own});poll()}
    catch(e){if(e.query!=null||/already running/i.test(e.message||""))poll();else{ub.disabled=false;updFrom=null;jobPanel(`<b>${esc(e.message||tl("Update impossible"))}</b>`,"err")}}}}}
if(D.local)fetch("/api/update").then(r=>r.json()).then(gearDot).catch(()=>{});   // a dot on the gear: an update is there
usageNotice();
{const at=$("#alphatag");if(at&&D.local&&D.role==="client"){at.hidden=false;at.onclick=()=>openReport("bug")}wireReport()}
if(D.local){wireFeedback();setTimeout(fbPoll,4000);liveDot()}   // how it went: after a warm-up, after a match (07/10, the closed alpha)   // the alpha: a report from any page
if(D.local){navQuiet++;route().finally(()=>navQuiet--);
  fetch("/api/codes").then(r=>r.json()).then(c=>{CODES={...c,...CODES};if(S.view==="matches"&&S.mpin){navQuiet++;try{syncUrl()}finally{navQuiet--}}}).catch(()=>{})}
else setPlayer(defPlayer());
if(D.local){
  const q0=new URLSearchParams(location.search).get("q");
  if(q0){history.replaceState(null,"",location.pathname+location.hash);$("#q").value=q0;$("#search").requestSubmit()}
  else fetch("/api/job").then(r=>r.json()).then(j=>{if(j.running)poll()}).catch(()=>{});
}

// a link of the app's (data-go: a view of the player on screen): followed in the page; a middle click or ctrl+click
// opens its real address in a new tab
document.addEventListener("click",e=>{const a=e.target.closest&&e.target.closest("a[data-go]");if(!a||e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||!D.local)return;
  e.preventDefault();const v=a.dataset.go;if(v==="matches"){S.mpin=false}go(v)});
// the app's language just changed (13/10): your analysis is written again in it in the background; said here, and the
// profile reloaded once it is done
{let rl=null;try{rl=sessionStorage.getItem("relang")}catch(e){}
  if((rl||D.relang)&&D.local){jobPanel(`<div class="row"><b><span class="spin" aria-hidden="true"></span>${tl("Your analysis is being written in the new language…")}</b><span class="note">${tl("A few minutes: the page updates by itself.")}</span></div>`);
    const tick=()=>fetch("/api/relang").then(r=>r.json()).then(async j=>{if(j.running)return setTimeout(tick,3000);
      try{sessionStorage.removeItem("relang")}catch(e){}$("#job").hidden=true;
      if(D.own&&D.players[D.own]){delete D.players[D.own];if(S.player===D.own)await setPlayer(D.own,true)}}).catch(()=>setTimeout(tick,5000));
    setTimeout(tick,2000)}}
