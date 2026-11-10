
// ---------- navigation: three moments (05/10): Live during the match, Prepare before it, Review after it ----------
const GROUP={ingame:"ingame",prepare:"prepare",review:"review",profile:"review",matches:"review",maps:"review",midround:"review",progress:"review",analysis:"review",routine:"review",team:"review",players:"review",pros:"review",settings:"settings"};
// Review in three levels (05/10): the session, your profile, every match; the detailed pages open from the profile
const SUB={review:[["review",tl("Session")],["profile",tl("Profile")],["matches",tl("Matches")]]};   // 07/10: no Explore (the menu's favorites instead)
const PLAYER_VIEWS=["ingame","prepare","review","profile","matches","maps","midround","progress","analysis","routine"];
// old French addresses keep working, and the moments' names
const ALIAS={partie:"ingame",avant:"prepare",bilan:"review",matchs:"matches",cartes:"maps",mid:"midround",prog:"progress",synthese:"analysis",equipe:"team",joueurs:"players",steam:"settings",live:"ingame",prep:"prepare",warmup:"prepare"};
// your account on the right of the bar (05/10), its menu (07/10, the user: "juste un espace favoris quand je clique sur
// mon profil, avec les autres profils que j'ai mis en favoris, à la place d'une répétition des onglets de la nav; mets
// aussi les paramètres et le bouton update"): you and your favorite profiles, a player or a match to open, your
// update, the settings. Nothing the bar's three moments already give.
let ACCT=null;   // your Steam avatar when the profile has none (/api/account: the public profile, kept a day)
const avatarHtml=(av,nm,cls="av")=>av?`<img class="${cls}" src="${esc(av)}" alt="" width="22" height="22">`:`<span class="${cls} ini" aria-hidden="true">${esc(String(nm||"?").trim().charAt(0).toUpperCase())}</span>`;
function acctUpdate(){const ac=$("#acct"),ab=$("#acctbtn"),am=$("#acctmenu");if(!ac)return;
  ac.hidden=!D.local;if(ac.hidden)return;
  const mi=D.own&&IDX()[D.own],me=D.own&&D.players[D.own];
  const av=mi?((me&&((me.advice||{}).steam||{}).avatar)||mi.avatar||(ACCT&&ACCT.avatar)):null,nm=(me&&me.name)||(mi&&mi.name)||tl("Menu");
  if(mi&&!av&&ACCT===null){ACCT={};fetch("/api/account").then(r=>r.json()).then(j=>{ACCT=j||{};if(ACCT.avatar)acctUpdate()}).catch(()=>{})}
  ab.innerHTML=`${mi?avatarHtml(av,nm):`<span class="av ini" aria-hidden="true">${IC("menu")}</span>`}<span class="an">${esc(nm)}</span><span class="caret" aria-hidden="true">▾</span>`;
  ab.title=mi?tl("{name}: your favorites, open a player, update, settings",{name:nm}):tl("Menu");ab.setAttribute("aria-label",ab.title);
  const im=$("img.av",ab);if(im)im.onerror=()=>{const sp=document.createElement("span");sp.className="av ini";sp.setAttribute("aria-hidden","true");sp.textContent=String(nm).trim().charAt(0).toUpperCase();im.replaceWith(sp)};   // an avatar that doesn't load: your initial
  favRender();
  ab.onclick=e=>{e.stopPropagation();langClose();const open=am.hidden;am.hidden=!open;ab.setAttribute("aria-expanded",String(open));if(open){const f=$("a,input",am);if(f)f.focus()}};
  am.onclick=e=>e.stopPropagation()}
// favorites: profiles kept at hand (this browser); the first time, your team's players
function favs(){const f=store("favs");return Array.isArray(f)?f:[]}
function favToggle(sid){const f=favs();store("favs",f.includes(sid)?f.filter(x=>x!==sid):[...f,sid]);favRender();navUpdate(S.view)}
function favSeed(){if(store("favs")!==null||!D.local||!D.own)return;store("favs",[]);
  fetch("teams/index.json").then(r=>r.ok?r.json():[]).then(T=>{const m=new Set();for(const t of T||[])if((t.members||[]).some(x=>String(x.steamid)===D.own))for(const x of t.members||[])if(String(x.steamid)!==D.own)m.add(String(x.steamid));
    if(m.size){store("favs",[...m]);favRender()}}).catch(()=>{})}
function favRender(){const box=$("#favlist");if(!box)return;favSeed();const I=IDX(),list=[...(D.own&&I[D.own]?[D.own]:[]),...favs().filter(s=>I[s]&&s!==D.own)];
  box.innerHTML=list.map(s=>{const e=I[s];return `<a href="#" data-fav="${s}" ${s===S.player?'aria-current="true"':""}>${avatarHtml(e.avatar,e.name)}<span>${esc(e.name)}${s===D.own?` <small>${tl("you")}</small>`:""}</span></a>`}).join("")
    +(list.length<2?`<span class="none">${tl("Open a player below, then click ☆ in the bar to keep them here.")}</span>`:"");
  $$("img.av",box).forEach(im=>im.onerror=()=>{const sp=document.createElement("span");sp.className="av ini";sp.setAttribute("aria-hidden","true");sp.textContent=(im.closest("a").textContent||"?").trim().charAt(0).toUpperCase();im.replaceWith(sp)});   // an avatar gone: the initial
  $$("[data-fav]",box).forEach(a=>a.onclick=e=>{e.preventDefault();acctClose();const s=a.dataset.fav;if(s===S.player)return;
    S.view=s===D.own?"review":(["profile","matches","maps","analysis","midround","progress","routine"].includes(S.view)?S.view:"profile");setPlayer(s)})}
function acctClose(){const am=$("#acctmenu"),ab=$("#acctbtn");if(am&&!am.hidden){am.hidden=true;if(ab)ab.setAttribute("aria-expanded","false")}}
// the app's language in the bar (20/10, the user: "passe le changement de langue dans la nav"): its code, a list of the
// languages in their own names, your browser's first; a choice saved for the whole app, the page then loaded again in it
const GLOBE=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z"/></svg>`;
function langUpdate(){const lw=$("#lang"),lb=$("#langbtn"),lm=$("#langmenu");if(!lw)return;
  lw.hidden=!D.local;if(lw.hidden)return;
  const LG=Object.entries(D.langs||{en:"English"}),cur=D.ui_lang||"auto",name=(D.langs||{})[LANG]||LANG;
  lb.innerHTML=`${GLOBE}<span class="lc">${esc(LANG.toUpperCase())}</span><span class="caret" aria-hidden="true">▾</span>`;
  lb.title=tl("Language: {name}",{name});lb.setAttribute("aria-label",lb.title);
  lm.innerHTML=`<span class="am-h">${tl("The app's language")}</span>`
    +[["auto",tl("Your browser's language")],...LG].map(([k,x])=>`<button type="button" data-lang="${k}" aria-pressed="${cur===k}" lang="${k==="auto"?LANG:k}"><span class="ck" aria-hidden="true">${cur===k?"✓":""}</span><span>${esc(x)}</span><span class="lc">${k==="auto"?"auto":esc(k.toUpperCase())}</span></button>`).join("")
    +`<p class="lm-note">${tl("Pages and analyses; yours written again in it in a few minutes.")}</p>`;
  lb.onclick=e=>{e.stopPropagation();acctClose();const open=lm.hidden;lm.hidden=!open;lb.setAttribute("aria-expanded",String(open));if(open){const f=$("[aria-pressed=\"true\"]",lm)||$("button",lm);if(f)f.focus()}};
  lm.onclick=e=>e.stopPropagation();
  $$("[data-lang]",lm).forEach(b=>b.onclick=async()=>{if(b.dataset.lang===cur){langClose();return}
    $$("[data-lang]",lm).forEach(x=>x.disabled=true);
    try{const j=await api("/api/app/options",{ui_lang:b.dataset.lang});if(j.relang)try{sessionStorage.setItem("relang","1")}catch(e){}}catch(e){}
    location.reload()})}
function langClose(){const lm=$("#langmenu"),lb=$("#langbtn");if(lm&&!lm.hidden){lm.hidden=true;if(lb)lb.setAttribute("aria-expanded","false")}}
function langOpen(){const lb=$("#langbtn");if(lb&&!$("#lang").hidden){window.scrollTo({top:0,behavior:"smooth"});lb.click()}}
document.addEventListener("click",e=>{if(!e.target.closest||!e.target.closest("#acct"))acctClose();if(!e.target.closest||!e.target.closest("#lang"))langClose()});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){const am=$("#acctmenu");if(am&&!am.hidden){acctClose();const ab=$("#acctbtn");if(ab)ab.focus()}
  const lm=$("#langmenu");if(lm&&!lm.hidden){langClose();const lb=$("#langbtn");if(lb)lb.focus()}}});
// the focus of the week (focus.py: the coach's first axis, kept 7 days); a profile built before it: the first axis
function focusOf(p){const A=p&&p.advice;if(!A)return null;const F=(A.plan||{}).focus;if(F&&F.short)return F;
  const r=(A.rules||[])[0];return r?{id:r.id,title:r.title,short:r.short||r.title,do:(r.do||[]).slice(0,2),drills:(r.drills||[]).slice(0,2),others:(A.rules||[]).slice(1,6).map(x=>({id:x.id,short:x.short||x.title}))}:null}
// your profile in tabs (07/10, the user: "plein de liens différents qui redirigent vers plein de choses"): one row, the
// same on each of its pages, instead of cards that each led somewhere else
const PTABS=[["profile",tl("Overview")],["maps",tl("Maps")],["analysis",tl("Reads")],["midround",tl("Mid-round")],["progress",tl("Weapons & buys")],["routine",tl("Habits")]];
// the Live button as a camera's REC (07/10, the user: "met le bouton live beaucoup plus visible et met le en rouge avec
// un point à côté quand il détecte une game live et qu'il est actif"): red with a blinking dot while Wily follows a match
// (CS2 sends its state, a map is loaded, not the training server), a plain pill otherwise. A peek at the game state every
// 4 s (15 s in a hidden tab) that doesn't count as an open Live page
const LIVEDOT={t:null,on:null};
const liveIs=g=>!!(g&&g.map&&!g.practice&&(g.age==null||g.age<30)&&g.map_phase&&g.map_phase!=="gameover");
function liveDot(){clearTimeout(LIVEDOT.t);if(!D.local)return;const next=()=>{LIVEDOT.t=setTimeout(liveDot,document.hidden?15000:4000)};
  fetch("/api/gsi/state?peek=1").then(r=>r.ok?r.json():null).then(g=>{const on=liveIs(g),a=$(".livebtn");
    if(a){if(on!==LIVEDOT.on){LIVEDOT.on=on;a.classList.toggle("rec",on);a.innerHTML=on?`<i class="recdot" aria-hidden="true"></i>${tl("LIVE")}`:tl("Live")}
      const where=[g.map?MAPN(g.map):"",g.round?tl("round {n}",{n:g.round}):""].filter(Boolean).join(" · ");
      a.title=on?(where?tl("Your match is live ({where}): open Live",{where}):tl("Your match is live: open Live")):tl("During your match, on a second screen")}
    next()}).catch(next)}
document.addEventListener("visibilitychange",()=>{if(!document.hidden&&D.local)liveDot()});
function navUpdate(view){const g=GROUP[view]||view;
  $$("nav a, .gear, .livebtn").forEach(a=>{if(a.dataset.view===g)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");
    if(D.local&&typeof viewPath==="function"){a.setAttribute("href",viewPath(a.dataset.view));a.dataset.go=a.dataset.view}});   // real addresses (07/10)
  const sn=$("#subnav"),items=SUB[g],inProf=PTABS.some(([k])=>k===view);sn.hidden=!items;
  const hr=k=>D.local&&typeof viewPath==="function"?`href="${viewPath(k)}" data-go="${k}"`:`href="#${k}"`;
  if(items)sn.innerHTML=`<div class="sn-row">${items.map(([k,t])=>`<a ${hr(k)} ${k===view||(k==="profile"&&inProf)?'aria-current="page"':""}>${t}</a>`).join("")}</div>`
    +(inProf?`<div class="sn-row sn-2" aria-label="${tl("Your profile")}">${PTABS.map(([k,t])=>`<a ${hr(k)} ${k===view?'aria-current="page"':""}>${t}</a>`).join("")}</div>`:"");
  // another profile on screen: said by the views, with the way back to yours (yours: the account on the right says it)
  const w=$("#whochip"),p=S.player&&D.players[S.player],other=!!(p&&D.own&&S.player!==D.own);
  const fav=other&&D.local&&favs().includes(S.player);
  w.innerHTML=p&&PLAYER_VIEWS.includes(view)&&(other||!D.local||!D.own)?`${(other?tl("Viewing: {name}",{name:`<b>${esc(p.name)}</b>`}):tl("Profile: {name}",{name:`<b>${esc(p.name)}</b>`}))}${other&&D.local?` <button type="button" id="favme" class="fav" aria-pressed="${fav}" title="${fav?tl("In your favorites: click to remove"):tl("Add to your favorites (your menu, top right)")}">${fav?"★":"☆"}</button>`:""}${other&&IDX()[D.own]?` <button type="button" id="backme" title="${tl("Back to my profile")}">${tl("back to mine")}</button>`:""}`:"";
  const bm=$("#backme");if(bm)bm.onclick=()=>{S.view="review";setPlayer(D.own)};
  const fm=$("#favme");if(fm)fm.onclick=()=>favToggle(S.player);
  acctUpdate();langUpdate();
  document.body.classList.toggle("ingame",view==="ingame")}
// ---------- the setup guide (08/10, the user: "une façon beaucoup plus simple d'installer l'app"): a player's first
// launch in three steps instead of Settings to explore: the Steam account of this PC, CS2 connected (game detection and
// one launch option to paste, which also loads the numpad keys), the match history code (no Steam key to create:
// Wily's site asks Steam), then the first analysis. Reopened from Settings ----------
const SG={t:null},SG_LAUNCH="-condebug +exec wily_bind";
const sgTick=b=>`<i class="sg-tick${b?" on":""}" aria-hidden="true">${b?"✓":""}</i>`;
async function setupGuide(v,first){clearTimeout(SG.t);if(!D.local)return;
  const get=u=>fetch(u).then(r=>r.ok?r.json():null).catch(()=>null);
  const [st,gs,cc]=await Promise.all([get("/api/steam/status"+(D.own?`?sid=${D.own}`:"")),get("/api/gsi/status"),get("/api/coach/status")]);
  if(!v.isConnected)return;
  const pc=(st&&st.pc_account)||{},who=D.own?(pc.steamid===String(D.own)?pc.name:(st&&st.name)):null;
  const s1=!!D.own,s2a=!!(gs&&gs.installed),s2b=!!(cc&&(cc.console||cc.bound)),s3=!!(st&&st.has_auth),L=(st&&st.links)||{};
  v.innerHTML=`<div class="sg"><div class="sg-h"><h2>${first?tl("Welcome! Three steps and you're ready"):tl("Setup guide")}</h2><p class="note">${tl("About two minutes. Your demos, profile and codes stay on this PC.")}</p></div>
   <article class="card sg-step${s1?" done":""}"><b class="sg-n">1</b><div><h3>${tl("Your Steam account")} ${sgTick(s1)}</h3>
     ${s1?`<p>${tl("{who}: the account signed in to Steam on this PC.",{who:`${who?`<b>${esc(who)}</b> · `:""}<span class="num note">${esc(String(D.own))}</span>`})}</p>`
       :`<p>${tl("Open Steam and sign in to your account, then reload this page. Or {link}.",{link:`<a href="/api/steam/login" style="color:var(--ct)">${tl("sign in on Steam's website")}</a>`})}</p>`}</div></article>
   <article class="card sg-step${s2a&&s2b?" done":""}" data-sg2><b class="sg-n">2</b><div><h3>${tl("Connect CS2")} <span data-sg2t>${sgTick(s2a&&s2b)}</span></h3>
     <p><span data-sg2a>${sgTick(s2a)}</span> ${tl("Game detection: CS2 sends Wily the map, the round, your money and your grenades (Valve's official feature, the one HUDs use).")} ${s2a?"":`<button type="button" class="primary" id="sg-gsi">${tl("Connect")}</button>`}</p>
     <p><span data-sg2b>${sgTick(s2b)}</span> ${tl("Paste this once in Steam: right-click <b>Counter-Strike 2</b> › <b>Properties</b> › <b>Launch options</b>:")}</p>
     <div class="sg-copy"><code>${SG_LAUNCH}</code><button type="button" id="sg-cp">${tl("Copy")}</button></div>
     <p class="note" data-sg2n>${s2b?tl("CS2 has started with it: Live's numpad keys work."):tl("It makes CS2 write its console log (Live's numpad keys go through it) and loads Wily's key binds. Checked once CS2 has started with it.")}</p></div></article>
   <article class="card sg-step${s3?" done":""}"><b class="sg-n">3</b><div><h3>${tl("Your matches")} ${sgTick(s3)}</h3>
     ${s3?`<p>${tl("History code saved: I'll find each new match on my own.")}</p>`
       :`<p>${tl("On {link} (signed in to your account), click <b>Create authentication code</b> and paste it here. The same page shows the code of your last match.",{link:`<a href="${esc(L.auth||"https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid=730&issueid=128")}" target="_blank" rel="noopener" style="color:var(--ct)">${tl("Steam's CS2 help page")}</a>`})}</p>
       <div class="row"><input id="sg-auth" type="text" autocomplete="off" spellcheck="false" placeholder="XXXX-XXXXX-XXXX" aria-label="${tl("Authentication code")}" style="width:200px;font:14px var(--f-mono)">
         <input id="sg-known" type="text" autocomplete="off" spellcheck="false" placeholder="${tl("Code of your last match CSGO-… (optional)")}" aria-label="${tl("Code of your last match")}" style="flex:1;min-width:240px;font:14px var(--f-mono)"></div>
       <p class="note">${tl("No Steam API key needed: Wily's website asks Steam for you and stores nothing.")}</p>`}</div></article>
   <div class="btns"><button type="button" class="primary" id="sg-go" ${s1?"":"disabled"}>${s3||!first?tl("Analyze my matches"):tl("Save and analyze my matches")}</button>
     <button type="button" id="sg-later">${first?tl("Later"):tl("Close")}</button><span class="note" id="sg-msg" role="status"></span></div>
   <p class="note">${tl("The first analysis needs Steam open and CS2 closed. It takes a few minutes, then your profile appears here.")}</p></div>`;
  const msg=$("#sg-msg",v);
  const g1=$("#sg-gsi",v);if(g1)g1.onclick=async()=>{g1.disabled=true;try{await api("/api/gsi/install",{});setupGuide(v,first)}catch(e){msg.textContent=e.message;g1.disabled=false}};
  $("#sg-cp",v).onclick=async()=>{try{await navigator.clipboard.writeText(SG_LAUNCH);$("#sg-cp",v).textContent=tl("Copied ✓")}catch(e){msg.textContent=tl("Select the text and copy it (Ctrl+C).")}};
  const done=async()=>{try{await api("/api/app/options",{setup_done:true})}catch(e){}D.setup=true};
  $("#sg-later",v).onclick=async()=>{clearTimeout(SG.t);await done();if(first)welcome(v);else renderSettings()};
  $("#sg-go",v).onclick=async()=>{const b=$("#sg-go",v),au=$("#sg-auth",v),kn=$("#sg-known",v);b.disabled=true;
    if(au&&au.value.trim()){msg.textContent=tl("Checking with Steam…");
      try{await api("/api/steam/credentials",{sid:String(D.own),auth_code:au.value.trim(),known_code:kn?kn.value.trim():""})}
      catch(e){msg.textContent=e.message;b.disabled=false;return}}
    clearTimeout(SG.t);await done();partialShown=null;startAnalysis(D.own)};
  if(!(s2a&&s2b))sgPoll(v)}
// step 2 ticks itself once CS2 started with the option (the typed codes of step 3 stay: only step 2 is touched)
function sgPoll(v){SG.t=setTimeout(async()=>{const box=$("[data-sg2]",v);if(!box||!v.isConnected)return;
  const [gs,cc]=await Promise.all([fetch("/api/gsi/status").then(r=>r.json()).catch(()=>null),fetch("/api/coach/status").then(r=>r.json()).catch(()=>null)]);
  const a=!!(gs&&gs.installed),b=!!(cc&&(cc.console||cc.bound));
  $("[data-sg2a]",box).innerHTML=sgTick(a);$("[data-sg2b]",box).innerHTML=sgTick(b);$("[data-sg2t]",box).innerHTML=sgTick(a&&b);box.classList.toggle("done",a&&b);
  if(b)$("[data-sg2n]",box).textContent=tl("CS2 has started with it: Live's numpad keys work.");
  if(!(a&&b))sgPoll(v)},5000)}
function welcome(v){const own=D.own,sn=$("#subnav");if(sn)sn.hidden=true;   // no profile yet: no profile tabs either
  if(D.local&&!D.setup)return setupGuide(v,true);
  v.innerHTML=`<div class="welcome"><h2>${tl("Hi, I'm Wily")}</h2>
   <p class="lede">${tl("I watch your CS2 matches and show you what wins rounds. I'm there at three moments:")}</p>
   <ul style="font-size:15px"><li>${tl("<b>Live</b>: a page for your second screen that follows your match: what to buy, where the Ts are likely to go, your paths, your rotations.")}</li>
     <li>${tl("<b>Prepare</b>: before you play, a timed warm-up built on your weak spots.")}</li>
     <li>${tl("<b>Review</b>: after your session or the next day: what changed and why, your focus for the week, what to try next.")}</li></ul>
   ${D.local&&own?`<p><button type="button" class="primary" id="w-own">${tl("Analyze this PC's Steam account")}</button></p>`:""}
   <form class="search" id="w-form" autocomplete="off"><input id="w-q" type="search" placeholder="${tl("Your Steam profile link or SteamID64")}" aria-label="${tl("Your Steam profile link")}"><button type="submit">${tl("Analyze")}</button></form>
   <p class="note">${D.local?tl("Everything runs on your PC. Keep Steam open and CS2 closed so I can fetch your latest matches: a first look in seconds, your full profile in a few minutes."):tl("I run in the desktop app: double-click Wily.bat.")}</p></div>`;
  const wo=$("#w-own",v);if(wo)wo.onclick=()=>{partialShown=null;startAnalysis(own)};
  $("#w-form",v).onsubmit=e=>{e.preventDefault();const q=$("#w-q",v).value.trim();if(!q)return;$("#q").value=q;$("#search").requestSubmit()}}

// the bar's height for what sticks under it (a profile page has a second row)
try{new ResizeObserver(()=>{const b=$(".bar");if(b)document.documentElement.style.setProperty("--bar-h",b.offsetHeight+"px")}).observe($(".bar"))}catch(e){}
