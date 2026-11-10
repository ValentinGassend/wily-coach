// ---------- view: prepare (05/10, reworked 06/10, redone 20/10): before you play, ONE warm-up on the training server
// (06/10, the user: "tout l'entraînement sur le même serveur comme avant, le bouton warmup pour tout lancer"; 07/10: "tu
// peux tout mettre sur la même page"). 20/10, the user: "refais complètement l'UX UI de /prepare": three steps on the
// left (how, which map, what), each one's choices right under it (a Stuff block's site takes, a Momentum block's jumps
// or ways: no time for those, "on n'est plus en fonction du temps"); on the right, kept in sight, what you will get,
// the one button, the session live once it runs, the bots' level. Your level at the top. When CS2 loads a map, Live
// takes over ----------
const PREP_LEN=[5,10,15,20,30,45];   // a full session's durations: its plan follows the one you pick, live (07/10)
// pend: a start or a stop on its way, note: its outcome for 30 s; both outlive the card's refreshes (08/10: the 4 s
// refresh wiped "Starting the server…", he clicked Stop, reloaded, clicked again)
const PREP={tick:null,watch:null,warm:null,sec:null,pend:null,note:null,base:null,cnt:null,ex:null,mo:null,gen:0};   // base: the maps the base covers (09/10); cnt: a focus block's drills per module; ex, mo: a map's site takes, its Momentum parts
// the focus block (13/10, the user: "pouvoir jouer intensivement certains blocs, 10 min de stuff only, 10 min de défense de
// bombsite only"): one module on one map, what each module is
const PREP_BLOCK=[10,15,20];
const FOCUS_DESC={crossfire:tl("real duels: hold an angle, peek, one spray for two"),defend:tl("hold a bombsite against the real hits, wave after wave"),
  push:tl("the push routes with their prefire angles"),nade:tl("site takes and defenses: each grenade, then all of them together"),wallbang:tl("the wallbangs and boosts that kill there"),
  situation:tl("your own rounds again, where they went wrong"),momentum:tl("the map's jumps worth knowing: the hard ones, the silent ones")};   // 14/10, rework section 9
const MOD_IC={aim:IC("crosshair"),crossfire:IC("crosshair"),defend:IC("shield"),push:IC("footprints"),nade:IC("cloud"),wallbang:IC("brick-wall"),situation:IC("repeat"),momentum:IC("fast-forward")};
const MOD_NAME={aim:tl("Aim"),crossfire:"Crossfire",defend:tl("Defense"),push:tl("Prefire"),nade:tl("Utility"),wallbang:tl("Wallbang"),situation:tl("Situations"),momentum:"Momentum"};
const WBLOCK=Object.fromEntries(Object.keys(MOD_NAME).map(k=>[k,`${MOD_IC[k]} ${MOD_NAME[k]}`]));
// the modules chosen by what's in them, not by a time (19/10 and 20/10): the choice's own list, from the app
const PICKS={nade:{key:"exec",api:"execs",list:"execs"},momentum:{key:"mpick",api:"momentum",list:"choices"}};
// your weapon (20/10, the user: "il faudrait pouvoir choisir son arme"): in the blocks fought with one (not Stuff, not your
// own rounds again, not a wallbang's gun); Auto: the ones you play in your matches
const PREP_GUNS=[["auto",tl("Auto")],["ak47","AK-47"],["m4a4","M4A4"],["m4a1s","M4A1-S"],["awp","AWP"],["deagle","Desert Eagle"],["usp","USP-S"],["glock","Glock-18"]];
const ARMED=["crossfire","defend","push","momentum"];
// what you chose today (your browser): the maps, the duration, the module and its choice
function prepState(){const day=new Date().toDateString();let st=store("prep");
  if(!st||st.day!==day)st={day,maps:[],min:20,done:{},cur:null,t0:null,mode:st&&st.mode,focus:st&&st.focus,bmin:st&&st.bmin,exec:st&&st.exec,mpick:st&&st.mpick,weapon:st&&st.weapon};   // the warm-up's type kept from day to day
  st.mode=st.mode==="block"?"block":"full";st.bmin=PREP_BLOCK.includes(st.bmin)?st.bmin:10;return st}
function prepSave(st){store("prep",st)}
// your focus of the week: changed from Review or Profile (focus.py)
function wireFocus(v,p,rerender){const sel=$("[data-focus-pick]",v);if(!sel)return;
  sel.onchange=async()=>{const id=sel.value;if(!id)return;sel.disabled=true;
    try{const j=await api("/api/focus",{sid:p.steamid,id});const A=p.advice;A.plan=A.plan||{};A.plan.focus=j.focus;navUpdate(S.view);rerender()}
    catch(e){sel.disabled=false;sel.insertAdjacentHTML("afterend",` <span class="note">${esc(e.message)}</span>`)}}}
function renderPrepare(){
  const p=P(),v=$("#v-prepare"),PL=p.advice.plan;if(!PL)return noPlan(v);
  clearTimeout(PREP.warm);
  const st=prepState(),own=D.local&&p.steamid===D.own,maps=mapsOf(p);
  // 09/10, his warm-up: "trainer les maps sur lesquelles je n'ai pas de démo téléchargée, puisque j'ai le dataset des
  // matchs": the base's other bomb maps, trained on its own spots and lineups (no situations: they come from your demos)
  if(own&&PREP.base===null){PREP.base=[];fetch("/api/train/maps").then(r=>r.ok?r.json():null).then(j=>{PREP.base=(j&&j.maps)||[];if(S.view==="prepare"&&PREP.base.length)renderPrepare()}).catch(()=>{})}
  const extra=own?(PREP.base||[]).filter(m=>!maps.some(x=>x.map===m.map)):[];
  const okMap=m=>maps.some(x=>x.map===m)||extra.some(x=>x.map===m);
  const full=(st.maps||[]).filter(okMap).slice(0,3),block=own&&st.mode==="block";
  // a focus block: one map (its own pick, else the first of the session's)
  const sel=block?[okMap(st.bmap)?st.bmap:full[0]].filter(Boolean):full;
  // the bomb maps first (the modules are about their sites); the others (hostages, wingman: your situations only) folded
  const site=m=>/^de_/.test(m);
  const chip=(m,n)=>`<button type="button" class="pp-map" data-pmap="${esc(m)}" aria-pressed="${sel.includes(m)}"><b>${esc(MAPN(m))}</b><small>${n==null?tl("base"):tln(n,"{n} match","{n} matches")}</small><i class="pp-warn" data-pwarnm="${esc(m)}" hidden>${IC("triangle-alert")}</i></button>`;
  const A=[...maps.filter(m=>site(m.map)).map(m=>chip(m.map,m.n||0)),...extra.filter(m=>site(m.map)).map(m=>chip(m.map,null))];
  const O=[...maps.filter(m=>!site(m.map)).map(m=>chip(m.map,m.n||0)),...extra.filter(m=>!site(m.map)).map(m=>chip(m.map,null))];
  const step=(n,t,body,attr="")=>`<section class="pp-step"${attr}><h3><span class="pp-n">${n}</span>${t}</h3>${body}</section>`;
  v.innerHTML=`<div class="pp-head"><div><span class="eyebrow">${esc(p.name)} · ${tl("before you play")}</span><h2>${tl("Prepare")}</h2></div>${own?`<div class="pp-lvl" data-plvl></div>`:""}</div>
   <div class="pp${own?"":" pp-solo"}"><div class="pp-main">
    ${own?step(1,tl("How?"),`<div class="pp-seg" role="group" aria-label="${tl("Warm-up type")}">
      <button type="button" data-pmode="full" aria-pressed="${!block}"><b>${IC("puzzle")} ${tl("Full session")}</b><small>${tl("a bit of everything on one to three maps, the time shared out for you")}</small></button>
      <button type="button" data-pmode="block" aria-pressed="${block}"><b>${IC("crosshair")} ${tl("Focus block")}</b><small>${tl("one module on one map, its drills back to back")}</small></button></div>`):""}
    ${step(own?2:1,block?tl("Which map?"):tl("Which maps?"),`<div class="pp-maps" role="group" aria-label="${tl("Maps")}">${A.join("")}</div>
      ${O.length?`<details class="pp-more"${sel.some(m=>!site(m))?" open":""}><summary>${tl("Maps without bomb sites")} <small>(${O.length})</small></summary><div class="pp-maps">${O.join("")}</div></details>`:""}
      <p class="note">${block?tl("One map for the block."):tl("One to three: the warm-up follows them.")}${extra.length?" "+tl("“base”: no match of yours there, trained on the base's spots and lineups."):""}</p>
`)}
    ${own?`<section class="pp-step" data-pmain>${sel.length?`<p class="note"><span class="spin" aria-hidden="true"></span>${tl("Preparing your warm-up…")}</p>`:`<h3><span class="pp-n">3</span>${block?tl("What?"):tl("How long?")}</h3><p class="note">${tl("Pick a map: the warm-up builds itself here.")}</p>`}</section>`:""}
   </div>
   ${own?`<aside class="pp-side card" data-pwarm>${sel.length?`<p class="note"><span class="spin" aria-hidden="true"></span>${tl("Preparing your warm-up…")}</p>`:`<p class="note">${tl("Pick a map: the warm-up builds itself here.")}</p>`}</aside>`
     :`<aside class="pp-side card"><p class="note">${tl("The warm-up runs on the training server, from the local app (double-click <code>Wily.bat</code>).")}</p></aside>`}</div>`;   // no pre-session journal here either (07/10: "tu peux aussi enlever ça")
  $$("[data-pmap]",v).forEach(b=>b.onclick=()=>{const m=b.dataset.pmap;
    if(block){st.bmap=m;prepSave(st);renderPrepare();return}   // a focus block: that map
    const i=sel.indexOf(m);if(i>=0)sel.splice(i,1);else if(sel.length<3)sel.push(m);else return;
    st.maps=sel.slice();prepSave(st);renderPrepare()});   // another map: the warm-up redone under it
  $$("[data-pmode]",v).forEach(b=>b.onclick=()=>{st.mode=b.dataset.pmode;prepSave(st);renderPrepare()});
  if(own)prepStruggles(v,p,sel);   // the ⚠ on the maps
  if(sel.length&&own)prepWarm(v,p,sel,st)}
// step 3 and the side card: the modules (a focus block) or the duration and its plan (a full session), what you will
// get, the button, the session live, the bots' level, your last warm-up
async function prepWarm(v,p,sel,st){const box=$("[data-pwarm]",v),main=$("[data-pmain]",v);if(!box||!main||!D.local)return;clearTimeout(PREP.warm);const gen=++PREP.gen;   // only the last call draws: an older one's answer coming after it drew the module chosen before (17/10: Stuff picked, a Momentum session started)
  const get=u=>fetch(u).then(r=>r.ok?r.json():null).catch(()=>null),where=sel.join(",");
  const block=st.mode==="block",mins=block?st.bmin:st.min,focus=block?(FOCUS_DESC[st.focus]?st.focus:"crossfire"):null;
  const [d,pv]=await Promise.all([get("/api/train?sid="+p.steamid),get(`/api/train/preview?sid=${p.steamid}&minutes=${mins}&where=${encodeURIComponent(where)}${focus?`&focus=${focus}`:""}`)]);
  if(gen!==PREP.gen||!box.isConnected||S.view!=="prepare")return;
  if(!d){box.innerHTML=`<p class="note">${tl("The local server doesn't answer.")}</p>`;main.innerHTML="";return}
  const T=d.status||{},Pg=d.progress||{level:1,xp:0,from:0,to:300},ss=T.session,Mo=(pv&&pv.modules)||[];
  if(focus&&Mo.length&&!Mo.some(m=>m.kind===focus&&m.ok)){const f=Mo.find(m=>m.ok);if(f){st.focus=f.kind;prepSave(st);return prepWarm(v,p,sel,st)}}   // nothing of it on that map: the first module that has
  if(!T.installed){main.innerHTML="";trainInstall(box,p.steamid,T,()=>prepWarm(v,p,sel,st));if((T.install||{}).running)PREP.warm=setTimeout(()=>prepWarm(v,p,sel,st),2500);return}
  // your level, at the top
  const lv=$("[data-plvl]",v),pct=Math.max(0,Math.min(100,100*(Pg.xp-Pg.from)/Math.max(1,Pg.to-Pg.from)));
  if(lv)lv.innerHTML=`<b>${tl("LVL {n}",{n:Pg.level})}</b><div class="tbar"><i style="width:${pct}%"></i></div><small>${tl("{a} / {b} XP to LVL {n}",{a:Math.max(0,Pg.xp-Pg.from).toLocaleString(LOC),b:Math.max(1,Pg.to-Pg.from).toLocaleString(LOC),n:Pg.level+1})}</small>`;
  // the aim first, on the game's aim map (06/10), then your maps
  const B=(pv&&pv.blocks)||[],byMap=[...new Set([...B.filter(x=>!sel.includes(x.map)).map(x=>x.map),...sel])].map(mp=>({mp,b:B.filter(x=>x.map===mp)})).filter(x=>x.b.length);
  const sug=Pg.suggest||null,chose=Date.now()-(+tPref("at","0"))<12*3600e3,df=sug&&!chose?sug.diff:trainDiff();
  const running=ss&&T.running,pend=PREP.pend,wait=!!(pend||T.busy);   // T.busy: a start the server side runs (a reload meanwhile)
  const say=pend?`${pend.text} (${Math.round((Date.now()-pend.t0)/1e3)} s)`:T.busy?tl("{what} is starting on the training server…",{what:T.busy.charAt(0).toUpperCase()+T.busy.slice(1)})
    :PREP.note&&Date.now()-PREP.note.t<30e3?PREP.note.text:T.dead?tl("The training server stopped answering: ▶ WARM-UP starts it again."):"";
  const pk=block&&PICKS[focus];   // a module chosen by what's in it: its choices, no time
  // step 3: a focus block's modules, the one picked's choices right under it; a full session's duration and plan
  const tiles=`<div class="pp-mods" role="group" aria-label="${tl("Module")}">${[...Mo.filter(m=>m.ok),...Mo.filter(m=>!m.ok)].map(m=>`<button type="button" class="pp-mod" data-pfocus="${m.kind}" aria-pressed="${m.kind===focus}"${m.ok?"":" disabled"}><span class="pp-ic" aria-hidden="true">${MOD_IC[m.kind]||"•"}</span><b>${esc(MOD_NAME[m.kind]||m.kind)}</b><small data-pfn="${m.kind}"></small><span class="pp-desc">${esc(m.ok?(m.note||FOCUS_DESC[m.kind]||""):(m.why||""))}</span></button>`).join("")}</div>`;
  const lens=`<div class="pp-seg sm pwlen" role="group" aria-label="${tl("Duration")}">${(block?PREP_BLOCK:PREP_LEN).map(n=>`<button type="button" data-pwlen="${n}" aria-pressed="${mins===n}"><b>${tl("{n} min",{n})}</b></button>`).join("")}</div>`;
  const plan=`<ol class="pwarm-plan">${byMap.map(({mp,b})=>`${byMap.length>1?`<li class="pwmap">${esc(MAPN(mp))}</li>`:""}${b.map(x=>`<li class="k-${x.kind}"><b>${WBLOCK[x.kind]||x.kind}</b><span>${Math.max(1,Math.round(x.seconds/60))}′</span></li>`).join("")}`).join("")}</ol>`;
  main.innerHTML=block?`<h3><span class="pp-n">3</span>${tl("What?")}</h3>${tiles}
      <div class="pp-opt"><h4>${MOD_IC[focus]||""} ${esc(MOD_NAME[focus]||focus)} · ${pk?(focus==="nade"?tl("which take or defense?"):tl("which part?")):tl("how long?")}</h4>
      ${pk?`<div class="pp-choices" data-pchoice><p class="note"><span class="spin" aria-hidden="true"></span>${focus==="nade"?tl("Finding the site takes on this map…"):tl("Finding the map's jumps and ways…")}</p></div>`:lens}
      ${!B.length?`<p class="note">${tl("nothing of this module on this map yet")}</p>`:""}</div>`
    :`<h3><span class="pp-n">3</span>${tl("How long?")}</h3>${lens}<p class="note">${tl("The time shared out for you, in this order:")}</p>${plan}`;
  // the side card: what you will get, the button, the session live, the bots' level, your last warm-up, the game's words
  const L=Pg.last,when=L&&L.t?new Date(L.t*1e3).toLocaleString(LOC,{weekday:"short",day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}):"";
  const recap=!running&&L&&L.n?`<details class="plast"><summary><b>${tl("Last warm-up")}</b> · ${esc(when)} · ${L.ok}/${L.n} ✔${L.points?` · ${IC("star")} ${L.points}`:""}</summary>
    <p class="note">${L.focus?`${WBLOCK[L.focus]||esc(L.focus)} ${L.minutes}′`:tl("{n} min",{n:L.minutes})} · ${esc((L.maps||[]).map(MAPN).join(", "))}${L.again?` · ${IC("repeat")} ${tln(L.again,"{n} comes back next time","{n} come back next time")}`:""}</p>
    <ul class="plast-l">${L.drills.map(x=>`<li class="${x.ok?"ok":"ko"}"><b>${x.ok?"✔":"✘"} ${esc(x.title)}</b>${x.detail?` <span class="note">${esc(x.detail)}</span>`:""}</li>`).join("")}</ul>
    ${L.again?`<p class="note">${tl("The missed ones come first next time you train these maps.")}</p>`:""}</details>`:"";
  const live=running?`<div class="tlive pp-live"><b>${ss.paused?"⏸":"●"}</b><span>${ss.paused?tl("PAUSED")+" · ":""}${WBLOCK[ss.block]||BLOCK[ss.block]||tl("Session")} · ${esc(ss.drill||"…")}</span><span>${IC("star")} ${ss.points||0} · ${ss.ok||0}/${ss.done||0} ✔${ss.streak>=2?` · ${IC("flame")}${ss.streak}`:""}</span><span>${ss.left?`${Math.floor(ss.left/60)}:${String(ss.left%60).padStart(2,"0")}`:""}</span>${T.humans?"":T.join&&/refused|failed/.test(T.join.state)?`<span class="note" style="color:var(--bad,#f87171)">${esc(T.join.why||tl("CS2 did not get in"))}</span>`:`<span class="note">${tl("waiting for you on the server")}</span>`}</div>`:"";
  const lxOff=D.local&&D.linux&&!D.linux_training;   // Linux: the training server is experimental, off until turned on here or in Settings
  const what=block?`${MOD_IC[focus]||""} ${esc(MOD_NAME[focus]||focus)}`:B.map(x=>MOD_IC[x.kind]||"").join(" ");
  const armed=!block||ARMED.includes(focus),gun=PREP_GUNS.some(g=>g[0]===st.weapon)?st.weapon:"auto",gunName=k=>(PREP_GUNS.find(g=>g[0]===k)||PREP_GUNS[0])[1];
  box.innerHTML=`<div class="pp-sum"><span class="eyebrow">${block?tl("Focus block"):tl("Full session")} · ${tl("on the training server")}</span>
      <b class="pp-sum-map">${esc(sel.map(MAPN).join(" · "))}</b>
      <span class="pp-sum-what">${what}${block?` · <span data-psum>${pk?"…":tl("{n} min",{n:mins})}</span>`:` · ${tl("{n} min",{n:mins})}`}${armed&&gun!=="auto"?` · <span data-psgun>${IC("target")} ${esc(gunName(gun))}</span>`:`<span data-psgun></span>`}</span></div>
    ${live}
    ${lxOff?`<div class="note" style="border:1px solid var(--line);border-radius:6px;padding:10px 12px;display:grid;gap:8px"><span>${tl("<b>Linux: the training server is experimental.</b> Its first runs on Linux: if it fails, the <b>alpha · report</b> tag sends its log to the developer.")}</span><div class="btns"><button type="button" class="primary" data-lxt>${tl("Turn on the training server")}</button></div></div>`:""}
    <button type="button" class="tbig pp-go" data-pwgo${wait?" disabled":""}>${running?"↻ "+tl("NEW WARM-UP"):"▶ "+tl("WARM-UP")}</button>
    ${D.local&&D.recette?`<button type="button" class="pp-go" data-pwrec${wait?" disabled":""} title="Tous les exercices ratés aux derniers tests, chacun une fois">${IC("flask-conical")} RECETTE</button>`:""}
    ${T.running?`<div class="pp-acts">${running&&!T.humans&&!wait?`<button type="button" data-pwjoin>↪ ${tl("Rejoin the server")}</button>`:""}${running&&T.humans?`<button type="button" data-pwpause${wait?" disabled":""}>${ss.paused?"▶ "+tl("Resume"):"⏸ "+tl("Pause")}</button>`:""}<button type="button" data-pwstop${wait?" disabled":""}>${tl("Stop")}</button></div>`:""}
    <p class="note pp-msg" role="status" data-pwmsg>${esc(say)}</p>
    ${armed?`<div class="pp-bots"><span>${IC("target")} ${tl("Your weapon")}</span><div class="pp-seg sm" role="group" aria-label="${tl("Your weapon")}">${PREP_GUNS.map(([k,n])=>`<button type="button" data-pwgun="${k}" aria-pressed="${gun===k}"><b>${esc(n)}</b></button>`).join("")}</div><small class="note">${tl("Auto: the ones you play in your matches. A rifle or the AWP replaces your main weapon (pistol rounds stay pistols); a pistol: that one alone.")}</small></div>`:""}
    <div class="pp-bots"><span>${IC("bot")} ${tl("Bots' level")}</span><div class="pp-seg sm" role="group" aria-label="${tl("Bots' level")}">${DIFF.map((n,i)=>`<button type="button" data-pwdiff="${i}" aria-pressed="${i===df}"><b>${n}</b></button>`).join("")}</div>${sug?`<small class="note">${tl("suggested: {level}",{level:DIFF[sug.diff]})} · ${esc(sug.why)}</small>`:""}</div>
    ${recap}
    <details class="pp-help"><summary>${tl("In game")}</summary><p class="note">${tl("One button: the server starts, the session is built on your maps, CS2 joins it (started first if it is closed). In game: <b>!n</b> skips a drill, <b>!r</b> again, <b>!pause</b> / <b>!resume</b>, <b>!stop</b> ends, <b>!report</b> followed by a few words tells the developer what's wrong.")}</p></details>`;
  const msg=$("[data-pwmsg]",box);
  $$("[data-pwlen]",main).forEach(b=>b.onclick=()=>{if(block)st.bmin=+b.dataset.pwlen;else st.min=+b.dataset.pwlen;prepSave(st);   // another duration: the parts redone at once
    $$("[data-pwlen]",main).forEach(x=>x.setAttribute("aria-pressed",String(x===b)));
    const pl=$(".pwarm-plan",main);if(pl)pl.style.opacity=".45";prepWarm(v,p,sel,st)});
  $$("[data-pwgun]",box).forEach(b=>b.onclick=()=>{st.weapon=b.dataset.pwgun;prepSave(st);   // your weapon: kept, no new plan needed
    $$("[data-pwgun]",box).forEach(x=>x.setAttribute("aria-pressed",String(x===b)));const sg=$("[data-psgun]",box);if(sg)sg.innerHTML=st.weapon!=="auto"?` · ${IC("target")} ${esc(gunName(st.weapon))}`:""});
  $$("[data-pwdiff]",box).forEach(b=>b.onclick=()=>{try{localStorage.setItem("coach_diff",b.dataset.pwdiff)}catch(e){}tSet("at",Date.now());prepWarm(v,p,sel,st)});   // your pick wins for 12 h
  // a start or a stop: shown, with its seconds, until it answers (a refresh meanwhile keeps it)
  const run=async(text,path,body,done)=>{PREP.pend={t0:Date.now(),text};PREP.note=null;
    $$("[data-pwgo],[data-pwstop],[data-pwjoin],[data-pwpause]",box).forEach(x=>x.disabled=true);msg.textContent=text;prepWarm(v,p,sel,st);   // at once: the card's own fetches take a second or two
    try{const r=await api(path,body);PREP.note=done?{t:Date.now(),text:done(r)}:null}catch(e){PREP.note={t:Date.now(),text:tl("Failed: {why}",{why:e.message})}}
    PREP.pend=null;if(S.view==="prepare")prepWarm(v,p,sel,st)};
  const lxt=$("[data-lxt]",box);if(lxt)lxt.onclick=async()=>{lxt.disabled=true;try{await api("/api/app/options",{linux_training:true});D.linux_training=true;prepWarm(v,p,sel,st)}catch(e){lxt.disabled=false;lxt.insertAdjacentHTML("afterend",`<span class="note"> ${esc(e.message)}</span>`)}};
  const old=focus&&pv&&!pv.modules;   // an app started before the focus blocks (13/10): it would start a full session
  if(lxOff||(block&&!B.length)||old){const g0=$("[data-pwgo]",box);if(g0)g0.disabled=true}
  if(old&&!pend)msg.textContent=tl("Restart Wily to use focus blocks.");
  $$("[data-pfocus]",main).forEach(b=>b.onclick=()=>{st.focus=b.dataset.pfocus;prepSave(st);   // another module: its plan at once
    $$("[data-pfocus]",main).forEach(x=>x.setAttribute("aria-pressed",String(x===b)));const o=$(".pp-opt",main);if(o)o.style.opacity=".45";prepWarm(v,p,sel,st)});
  // a module's choices: a Stuff block's takes (T) and defenses (CT), a Momentum block's jumps or ways; what's in the one picked
  if(pk){const mp=sel[0],sum=$("[data-psum]",box),cache=focus==="nade"?"ex":"mo",fillC=X=>{const el=$("[data-pchoice]",main);if(!el||gen!==PREP.gen)return;
      if(!X.length){el.innerHTML=`<p class="note">${focus==="nade"?tl("no site take found on this map yet"):tl("nothing of this module on this map yet")}</p>`;const g0=$("[data-pwgo]",box);if(g0)g0.disabled=true;if(sum)sum.textContent="—";return}
      if(!X.some(x=>x.key===st[pk.key])){st[pk.key]=X[0].key;prepSave(st)}
      const x0=X.find(x=>x.key===st[pk.key]),btn=x=>`<button type="button" ${focus==="nade"?"data-pwex":"data-pwmo"}="${esc(x.key)}" aria-pressed="${x.key===st[pk.key]}"><b>${esc(x.label)}</b>${focus==="nade"||x.mine?`<small>${focus==="nade"?tln(x.n,"{n} grenade","{n} grenades"):""}${x.mine?(focus==="nade"?" · ":"")+tl("yours"):""}</small>`:""}</button>`;
      const groups=focus==="nade"?[["T",tl("Site takes (T)")],["CT",tl("Site defenses (CT)")]].map(([sd,t])=>[t,X.filter(x=>x.side===sd)]).filter(g=>g[1].length):[["",X]];
      el.innerHTML=groups.map(([t,xs])=>`<div class="pp-cgroup">${t?`<span class="eyebrow">${t}</span>`:""}<div class="pp-seg" role="group" aria-label="${esc(t||tl("Module"))}">${xs.map(btn).join("")}</div></div>`).join("")
        +(x0&&x0.items.length?`<div class="pp-items">${x0.title?`<b>${esc(x0.title)}</b>`:""}<ol>${x0.items.map(i=>`<li>${esc(i)}</li>`).join("")}</ol></div>`:"")
        +`<p class="note">${focus!=="nade"?tl("Each drill once, in that order: no time to fill, the block ends with the last one.")
          :x0&&x0.key==="CT:rush"?tl("Each one on its own, timed on a real rush through its place.")
          :x0&&x0.side==="CT"?tl("Each grenade on its own first, then all of them, each on its spot before the Ts are on the site; then you hold the site against a real take.")
          :tl("Each grenade on its own first, then all of them up on the site at the same moment; then you go in as its entry.")}</p>`;   // 21/10: a defense's rule is not a take's
      if(sum&&x0)sum.textContent=focus==="nade"?`${x0.label} · ${tln(x0.n,"{n} grenade","{n} grenades")}`:x0.label;
      $$("[data-pwex],[data-pwmo]",el).forEach(b=>b.onclick=()=>{st[pk.key]=b.dataset.pwex||b.dataset.pwmo;prepSave(st);fillC(X)})};
    if(PREP[cache]&&PREP[cache].map===mp&&Date.now()-PREP[cache].at<6e5)fillC(PREP[cache].list);
    else get(`/api/train/${pk.api}?sid=${p.steamid}&map=${encodeURIComponent(mp)}`).then(j=>{if(!j)return;PREP[cache]={map:mp,at:Date.now(),list:j[pk.list]||[]};if(sel[0]===mp)fillC(PREP[cache].list)})}
  // each module's drills on that map, counted after the card (a map's first count takes a few seconds)
  if(block){const mp=sel[0],fill=c=>{if(!main.isConnected)return;let gone=false;
      // no count shown (20/10, the user: "le nombre d'exercices, on s'en fout"): only a module with nothing here says so
      $$("[data-pfn]",main).forEach(el=>{const k=el.dataset.pfn,n=c.counts[k],bt=el.closest("button");el.textContent="";if(n==null||bt.disabled)return;
        if(!n&&k!=="crossfire"){el.textContent=tl("none on this map yet");bt.disabled=true;if(k===focus)gone=true}});
      if(gone){const f=$$("[data-pfocus]",main).find(x=>!x.disabled);if(f){st.focus=f.dataset.pfocus;prepSave(st);prepWarm(v,p,sel,st)}}};
    if(PREP.cnt&&PREP.cnt.map===mp&&Date.now()-PREP.cnt.at<6e5)fill(PREP.cnt);
    else get(`/api/train/modules?sid=${p.steamid}&map=${encodeURIComponent(mp)}`).then(c=>{if(!c)return;PREP.cnt={...c,at:Date.now()};if(sel[0]===mp)fill(PREP.cnt)})}
  const goB=$("[data-pwgo]",box);if(goB)goB.onclick=()=>run(T.running?tl("Preparing the session (30 s, a few minutes the first time) · CS2 starts meanwhile…"):tl("Starting the server and preparing the session (30 s, a few minutes the first time) · CS2 starts meanwhile…"),
    "/api/train/session",(()=>{const f=st.mode==="block"?(FOCUS_DESC[st.focus]?st.focus:"crossfire"):null,m=st.mode==="block"?st.bmin:st.min,c=f&&PICKS[f]?st[PICKS[f].key]:null;   // the module, its choice and the time chosen when clicked
      const g=(!f||ARMED.includes(f))&&st.weapon&&st.weapon!=="auto"?{weapon:st.weapon}:{};   // your weapon, where you fight with one
      return f?{sid:p.steamid,minutes:m,where,diff:df,focus:f,...(c?{exec:c}:{}),...g}:{sid:p.steamid,minutes:m,where,diff:df,...g}})(),
    r=>`${r.blocks.map(b=>`${WBLOCK[b.kind]||b.kind} ${Math.max(1,Math.round(b.seconds/60))}′`).join(" → ")} — ${tl("CS2 joins the server. If Steam opens its \"game info\" window instead, click \"Join game\".")}`);
  // 29/10: his recette (his "recette" setting only): every drill the latest tests failed, map by map, each once
  const rc=$("[data-pwrec]",box);if(rc)rc.onclick=()=>run("Préparation de la recette (les exercices ratés aux derniers tests)…","/api/train/recette",{sid:p.steamid,diff:df},
    r=>`${r.blocks.map(b=>`${MAPN(b.map)} ${WBLOCK[b.kind]||b.kind} ${b.n}`).join(" → ")} — ${tl("CS2 joins the server. If Steam opens its \"game info\" window instead, click \"Join game\".")}`);
  const jn=$("[data-pwjoin]",box);if(jn)jn.onclick=async()=>{jn.disabled=true;PREP.note={t:Date.now(),text:tl("CS2 joins the server (started first if it is closed)…")};msg.textContent=PREP.note.text;
    try{await api("/api/train/join",{})}catch(e){PREP.note={t:Date.now(),text:tl("Failed: {why}",{why:e.message})};msg.textContent=PREP.note.text;jn.disabled=false}};
  const sp=$("[data-pwstop]",box);if(sp)sp.onclick=()=>run(tl("Stopping the training server…"),"/api/train/stop",{});
  const pz=$("[data-pwpause]",box);if(pz)pz.onclick=()=>run(ss.paused?tl("Going on…"):tl("Pausing (the block's clock waits)…"),ss.paused?"/api/train/resume":"/api/train/pause",{});   // 09/10: "la mettre en pause, et la reprendre"
  clearInterval(PREP.sec);if(pend)PREP.sec=setInterval(()=>{if(!PREP.pend||!box.isConnected){clearInterval(PREP.sec);return}   // its seconds, each second
    msg.textContent=`${PREP.pend.text} (${Math.round((Date.now()-PREP.pend.t0)/1e3)} s)`},1000);
  if(T.running||wait)PREP.warm=setTimeout(()=>{if(box.isConnected&&S.view==="prepare")prepWarm(v,p,sel,st)},4000)}
// CS2 loads a map (not the training server): Live takes over
function prepWatch(){clearTimeout(PREP.watch);if(S.view!=="prepare"||!D.local)return;
  fetch("/api/gsi/state").then(r=>r.json()).then(g=>{if(S.view!=="prepare")return;
    if(g&&g.map&&!g.practice&&(g.age==null||g.age<30)&&g.map_phase&&g.map_phase!=="gameover"){if(D.own&&S.player!==D.own){S.view="ingame";setPlayer(D.own)}else go("ingame");return}
    PREP.watch=setTimeout(prepWatch,3000)}).catch(()=>{PREP.watch=setTimeout(prepWatch,6000)})}

// where you lose rounds lately (06/10: "la game d'Overpass où on s'est pris des execs B en CT: priorise-les en
// entraînement"): the training puts their maps, the defense of those sites and those rounds first; a ⚠ on those maps
// (20/10, the user: "tu peux enlever ça de l'interface": their list under the maps gone)
async function prepStruggles(v,p){if(!D.local)return;let r;
  try{const x=await fetch("/api/train/struggles?sid="+encodeURIComponent(p.steamid));if(!x.ok)return;r=await x.json()}catch(e){return}
  new Set((r.struggles||[]).map(x=>x.map)).forEach(m=>{const w=$(`[data-pwarnm="${CSS.escape(m)}"]`,v);if(w){w.hidden=false;w.title=tl("where you lose rounds lately")}})}
