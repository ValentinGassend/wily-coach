
// ---------- shared: sources, local API ----------
const srcLinks=(l,sm,lab)=>l&&l.length?`<div class="srcs${sm?" sm":""}"><span class="note">${lab||tl("Sources:")}</span>${l.map(x=>`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.label)}</a>`).join("")}</div>`:"";
async function api(path,body){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const j=await r.json().catch(()=>({}));if(!r.ok){const e=new Error(j.error||tl("Wily's local server returned an error"));e.status=r.status;e.query=j.query;throw e}return j}   // query: a job already running (its message is translated)
async function reloadPlayer(){const id=S.player;delete D.players[id];await loadPlayer(id,true);RENDER[S.view]()}
const lc=s=>s?s.charAt(0).toLowerCase()+s.slice(1):s;
const WNAME={awp:"AWP",scout:"Scout",rifle:tl("Rifles"),rifle_eco:"Galil / FAMAS",smg:tl("SMG"),shotgun:tl("Shotguns"),pistol:tl("Pistol"),heavy:tl("Machine gun"),auto:tl("Auto-sniper"),pro_awp:tl("Pro AWPers")};
// the player's experience (plan.level): a word the server sends in English, said in the page's language
const EXPN={veteran:tl("veteran player"),regular:tl("regular player"),improving:tl("improving player")};
// short (the Profile's line): the level and the hours; Premier, ranks, wins and the account's age are the Full analysis'
// public profile (07/10: said once)
function levelLine(L,short){if(!L)return "";const bits=[];
  if(L.rating&&!short)bits.push(tl("Premier {season}: {rating}",{season:esc(L.season||""),rating:L.rating.toLocaleString(LOC)}));
  if(L.comp&&!short)bits.push(tl("{rank} in Competitive",{rank:esc(L.comp)}));
  const xp=[L.hours!=null?(L.two_weeks_h!=null?tl("{h} h of CS2, {h2} h in the last 2 weeks",{h:L.hours.toLocaleString(LOC),h2:L.two_weeks_h.toLocaleString(LOC)}):tl("{h} h of CS2",{h:L.hours.toLocaleString(LOC)})):"",
    L.wins&&!short?tln(L.wins,"{n} Competitive win","{n} Competitive wins"):"",L.premier_wins&&!short?tl("{n} in Premier",{n:L.premier_wins}):"",L.since&&!short?tl("Steam account since {year}",{year:L.since}):""].filter(Boolean).join(", ");
  return `${L.name?tl("level {name}",{name:esc(L.name)}):tl("unknown level")}${bits.length?` · ${bits.join(" · ")}`:""} · ${EXPN[L.experience]||esc(L.experience)}${xp?` (${xp})`:""}`}

// ---------- view: routine ----------
let partySel=null,ckState={};
const LVL={"reliable":tl("reliable"),"trend":tl("trend"),"no clear gap":tl("no clear gap"),"not enough data":tl("too few games")};
const lvlCls=l=>l==="reliable"?"reliable":l==="trend"?"trend":"";
function contextBlock(C){
  const pf=v=>v==null?"—":v.toFixed(2),recs=C.recs||[];
  const src=Object.entries(C.sources_count||{}).map(([k,n])=>k==="demo"?tl("{n} with a demo",{n}):k==="steam"?tl("{n} from the Steam history",{n}):tl("{n} from Leetify",{n})).join(", ");
  return `<article class="card"><h3>${tl("Your playing habits")} ${itip(`${tln(C.n,"{n} dated match","{n} dated matches")} (${src}) · ${tln(C.sessions.n,"{n} session","{n} sessions")}, ${tl("{avg} games on average, {max} at most",{avg:C.sessions.avg_games,max:C.sessions.max_games})} · ${tln(C.sessions.games_after_2_losses,"{n} game started after 2 losses in a row","{n} games started after 2 losses in a row")} · ${tln(C.journal_n,"journal: {n} entry","journal: {n} entries")}. ${tl("\"Rating\": your match rating on the HLTV 2.0 model (1.00 = the lobby's average player). Your average: {r}.",{r:pf(C.overall.perf)})}`)}</h3>
   ${D.local&&!(C.sources_count||{}).steam?`<p class="note">${tl("To measure your habits over your whole history, not just your demos, connect your Steam history in {link}.",{link:`<a href="#settings" style="color:var(--ct)">${tl("Settings")}</a>`})}</p>`:""}
   ${recs.length?`<ul class="pl-list">${recs.map(r=>`<li class="coach">${esc(r.text)} <span class="lvl ${lvlCls(r.level)}">${esc(LVL[r.level]||r.level)}</span></li>`).join("")}</ul>`
     :`<p>${tl("No reliable personal rule yet: it takes more matches. Until then, follow the general rules below.")}</p>`}
   ${fold(tln(C.n,"Every situation: time of day, game of the session, after a loss, group, rest ({n} game)","Every situation: time of day, game of the session, after a loss, group, rest ({n} games)"),`<div class="tbl"><table><thead><tr><th>${tl("Situation")}</th><th class="n">${tl("Games")}</th><th class="n">${tl("W-L")}</th><th class="n">${tl("Wins")}</th><th class="n">${tl("Rating")}</th><th class="n">${tl("Rating gap")}</th><th>${tl("Reliability")}</th></tr></thead><tbody>
   ${C.factors.map(f=>`<tr><td class="grp" colspan="7">${esc(f.title)}</td></tr>`+f.rows.map(r=>`<tr><td>${esc(r.group)}</td><td class="n">${r.n}</td><td class="n">${r.w}-${r.l}</td>
     <td class="n">${r.winrate==null?"—":r.winrate+"%"}</td><td class="n">${pf(r.perf)}</td>
     <td class="n ${lvlCls(r.level)&&r.delta!=null?(r.delta>0?"good":"bad"):""}">${r.delta==null?"—":(r.delta>0?"+":"")+pf(r.delta)}</td>
     <td><span class="lvl ${lvlCls(r.level)}">${esc(LVL[r.level]||r.level)}</span></td></tr>`).join("")).join("")}
   </tbody></table></div>
   ${C.partners&&C.partners.length?`<p>${tl("<b>Regular teammates</b> (on your team in at least 2 matches):")} ${C.partners.map(x=>`${esc(x.name)} ${tl("{w}W-{l}L, rating {r} over {n} games",{w:x.w,l:x.l,r:pf(x.perf),n:x.n})}`).join(" · ")}</p>`:""}
   ${srcLinks([C.rating_source],true)}`,"rt-table")}</article>`}
function partyBlock(PL){const P_=PL.party;if(!P_)return "";const keys=["solo","duo","trio","quatuor","five"],cur=partySel||PL.party_mode||"solo",x=P_[cur];
  const how={solo:tl("You mostly play solo, judging by the teammates who keep showing up in your matches."),duo:tl("You mostly play as a duo, judging by the teammates who keep showing up in your matches."),
    trio:tl("You mostly play as a trio, judging by the teammates who keep showing up in your matches."),quatuor:tl("You mostly play as a 4-stack, judging by the teammates who keep showing up in your matches."),
    five:tl("You mostly play as a 5-stack, judging by the teammates who keep showing up in your matches.")};
  return `<article class="card"><h3>${tl("Depending on your group")}</h3>${PL.party_mode?`<p class="note">${how[PL.party_mode]||""}</p>`:""}
   <div class="btns" role="group" aria-label="${tl("Group size")}">${keys.map(k=>`<button type="button" data-party="${k}" aria-pressed="${k===cur}">${esc(P_[k].title)}</button>`).join("")}</div>
   <ul>${x.items.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>${srcLinks(x.src,true)}</article>`}
function noPlan(v){v.innerHTML=`<div class="empty">${tl("This player's plan isn't ready yet. Run their analysis again from the search bar.")}</div>`}
// ---------- the tabs' briefs (04/10) ----------
// mid-round: your weakest decisions against the base and the pros, your strengths, the fix or reflex to apply
function midBrief(PL){const M=PL.mid;if(!M)return "";const wk=M.weak.filter(w=>w.id!=="note"),pb=(PL.playbook||[]).find(x=>x.prio>0);
  const ln=w=>`<b>${esc(w.label[0].toUpperCase()+w.label.slice(1))}</b>: ${tl("you {v}",{v:fmtU(w.you,w.unit)})} <span class="note">· ${w.pro!=null?tl("base {b}, pros {p}",{b:fmtU(w.median,w.unit),p:fmtU(w.pro,w.unit)}):tl("base {b}",{b:fmtU(w.median,w.unit)})}</span>`;
  return tabBrief({id:"mr-brief",works:M.strong.slice(0,3).map(x=>esc(x.text)),fix:wk.slice(0,3).map(ln),
    next:wk[0]&&wk[0].fix?esc(wk[0].fix):pb?tl("If {if} → {then}",{if:esc(lc(pb.if)),then:esc(pb.then)}):null,nextLabel:tl("In your next match")})}
// progress: what improves and what slips over your last 3 matches, the test to run
function progBrief(PL){const K=PL.kpis||[],X=PL.experiments||{},act=(X.experiments||[]).filter(e=>e.status==="active"),L=PL.level;
  const d=k=>k.recent-k.before,better=k=>k.higher_better?d(k)>0:d(k)<0,moved=k=>k.recent!=null&&k.before!=null&&Math.abs(d(k))>1e-9;
  const kl=k=>`${esc(k.label)}: <b>${fmtU(k.recent,k.unit)}</b> <span class="note">· ${tl("before {v}",{v:fmtU(k.before,k.unit)})}</span>`;
  const nx=act[0]?tl("Keep testing: {test}",{test:esc(act[0].title)}):(X.suggested||[])[0]?tl("Start a test: {test}",{test:esc(X.suggested[0].title)}):L&&L.focus&&L.focus[0]?esc(L.focus[0]):null;
  return tabBrief({id:"pg-brief",works:K.filter(k=>moved(k)&&better(k)).map(kl),fix:K.filter(k=>moved(k)&&!better(k)).map(kl),next:nx,nextLabel:tl("This week"),
    worksNone:tl("No stat is improving over your last 3 matches yet."),fixNone:tl("No stat is slipping over your last 3 matches.")})}
// routine: the situations where you play clearly better or worse (time, session, group...), the first habit to keep
function routineBrief(PL){const C=PL.context,ph=(PL.phases||[])[0],first=ph&&ph.items&&ph.items[0];
  const rows=C?C.factors.flatMap(x=>x.rows.filter(r=>r.delta!=null&&(r.level==="reliable"||r.level==="trend")).map(r=>({...r,title:x.title}))):[];
  const rl=r=>`${esc(r.title)}: <b>${esc(r.group)}</b> <span class="note">· ${tl("rating {d} over {n} games",{d:(r.delta>0?"+":"")+r.delta.toFixed(2),n:r.n})}</span>`;
  return tabBrief({id:"rt-brief",works:rows.filter(r=>r.delta>0).sort((a,b)=>b.delta-a.delta).map(rl),fix:rows.filter(r=>r.delta<0).sort((a,b)=>a.delta-b.delta).map(rl),
    next:C&&C.recs&&C.recs[0]?esc(C.recs[0].text):first?`<b>${esc(first.title)}</b>: ${esc(first.text)}`:null,nextLabel:tl("Before your next session"),
    worksNone:tl("No situation where you clearly play better yet."),fixNone:tl("No situation where you clearly play worse yet.")})}
function renderRoutine(){
  const p=P(),v=$("#v-routine"),PL=p.advice.plan;if(!PL)return noPlan(v);
  v.innerHTML=`<div class="head"><div style="display:grid;gap:4px"><span class="eyebrow">${esc(p.name)}</span><h2>${tl("Your habits")}</h2></div></div>
   ${routineBrief(PL)}${anchor("rt-habits")}
   ${PL.context?contextBlock(PL.context):`<article class="card"><h3>${tl("Your playing habits")}</h3><p class="note">${tl("No dated match for this player: habits (times, sessions, group) need demos or a Leetify history.")}</p></article>`}
   ${fold(tl("Depending on your group"),partyBlock(PL),"rt-group")}`;
  $$("[data-party]",v).forEach(b=>b.onclick=()=>{partySel=b.dataset.party;renderRoutine()});
}
// ---------- view: mid-round ----------
let pbSide="me",midMap=null,wpSide=null;
const isBoth=x=>x.side==="both"||x.side==="tous";
function midMetricRows(B){const rows=Object.entries(B.metrics).filter(([k,m])=>m.you!=null).sort((a,b)=>(a[1].percentile??101)-(b[1].percentile??101));
  const col=q=>q<30?"var(--bad)":q<60?"var(--warn)":"var(--good)";
  return `<div class="card bench wide">${rows.map(([k,m])=>`<div class="row"><span class="lb">${esc(m.label[0].toUpperCase()+m.label.slice(1))}${m.higher_better==null?` <span class="note">${tl("(indicative)")}</span>`:""}</span>
    <div class="pbar" title="${m.percentile==null?tl("Neither good nor bad on its own"):tl("Better than {p}% of players",{p:m.percentile})}">${m.percentile==null?"":`<i style="width:${Math.max(2,m.percentile)}%;background:${col(m.percentile)}"></i>`}<b></b></div>
    <span class="v">${tl("you {v}",{v:fmtU(m.you,m.unit)})} · ${tl("median {v}",{v:fmtU(m.median,m.unit)})}${m.pro!=null?` · ${tl("pros {v}",{v:fmtU(m.pro,m.unit)})}`:""}</span></div>`).join("")}</div>`}
function rotCard(site,r){const s=x=>x==null?"—":x+" s",pc=x=>x==null?"—":x+"%";
  const my=r.n?Math.round(100*r.died_way/r.n):null,bd=r.base.died;
  return `<article class="card"><h3>${tl("Rotations to {site}",{site:esc(site)})}</h3>
   <div class="tbl"><table><thead><tr><th></th><th class="n">${tl("Leave after the hit")}</th><th class="n">${tl("Travel")}</th><th class="n">${tl("Deaths on the way")}</th><th class="n">${tl("Rotations")}</th></tr></thead><tbody>
    <tr><td>${tl("You")}</td><td class="n">${s(r.react)}</td><td class="n">${s(r.travel)}</td><td class="n ${my!=null&&bd!=null?(my>=bd+10?"bad":my<=bd-10?"good":""):""}">${pc(my)}</td><td class="n">${r.n}</td></tr>
    <tr><td>${tl("Base")}</td><td class="n">${s(r.base.react)}</td><td class="n">${s(r.base.travel)}</td><td class="n">${pc(bd)}</td><td class="n">${r.base.n??"—"}</td></tr>
    <tr><td>${tl("Pros")}</td><td class="n">${s(r.pro.react)}</td><td class="n">${s(r.pro.travel)}</td><td class="n">${pc(r.pro.died)}</td><td class="n">${r.pro.n??"—"}</td></tr></tbody></table></div>
   <ul>${r.mine.length?`<li>${tl("<b>Your routes:</b> {routes}",{routes:r.mine.map(x=>`${esc(x.route)}${x.n>1?` ×${x.n}`:""}`).join(" · ")})}</li>`:""}
    ${r.base.best?`<li>${tl("<b>Safest in the base:</b> {route} ({time}, {d}% deaths on the way, {n} rotations)",{route:esc(r.base.best.route),time:s(r.base.best.travel),d:r.base.best.died,n:r.base.best.n})}</li>`:""}
    ${r.pro.best?`<li>${tl("<b>Safest among pros:</b> {route} ({time}, {d}% deaths on the way, {n} rotations)",{route:esc(r.pro.best.route),time:s(r.pro.best.travel),d:r.pro.best.died,n:r.pro.best.n})}</li>`:""}</ul>
   ${Object.keys(r.base.by_weapon||{}).length?`<details><summary style="cursor:pointer" class="note">${tl("Routes by weapon (base)")}</summary><ul class="note">${Object.entries(r.base.by_weapon).map(([w,x])=>`<li><b>${esc(WNAME[w]||w)}</b>: ${x.routes.map(y=>esc(y.route)).join(` ${tl("or")} `)} · ${tl("{d}% deaths on the way over {n} rotations",{d:x.died,n:x.n})}</li>`).join("")}</ul></details>`:""}
  </article>`}
function wpBlock(W,side){const cl=W&&W[side];if(!cl)return `<p class="note">${tl("Not enough rounds on this map for this side.")}</p>`;
  const order=["awp","pro_awp","rifle","rifle_eco","smg","shotgun","scout"];
  return `<div class="insights wide">${order.filter(k=>cl[k]&&cl[k].zones.length).map(k=>{const x=cl[k],pro=k==="pro_awp";
    const lab=k==="rifle"?(side==="T"?tl("Rifles (AK-47, SG 553)"):tl("Rifles (M4, AUG)")):k==="rifle_eco"?(side==="T"?"Galil AR":"FAMAS"):(WNAME[k]||x.label);
    return `<article class="card"><h3>${esc(lab)}</h3><span class="note">${pro?tl("{n} rounds with an AWP kill",{n:x.rounds}):tl("{n} rounds",{n:x.rounds})}</span>
    <div class="tbl"><table><thead><tr><th>${tl("Zone")}</th><th class="n">${tl("Share")}</th>${pro?"":`<th class="n">${tl("Duels won")}</th><th class="n">${tl("Rounds won")}</th>`}</tr></thead><tbody>
    ${x.zones.map(z=>`<tr><td>${esc(z.name)}</td><td class="n">${z.share}%</td>${pro?"":`<td class="n ${z.duel_win!=null&&z.duel_win>=55?"good":z.duel_win!=null&&z.duel_win<=42?"bad":""}">${z.duel_win==null?"—":z.duel_win+"%"} <span class="note">(${z.duels})</span></td><td class="n">${z.round_win}%</td>`}</tr>`).join("")}
    </tbody></table></div></article>`}).join("")}</div>`}
function renderMidround(){
  const p=P(),v=$("#v-midround"),PL=p.advice.plan;if(!PL)return noPlan(v);
  const M=PL.mid,all=PL.playbook||[],anyMe=all.some(x=>x.prio>0);if(pbSide==="me"&&!anyMe)pbSide="all";
  const pb=all.filter(x=>pbSide==="all"||(pbSide==="me"?x.prio>0:(x.side===pbSide||isBoth(x))));
  const maps=bombFirst([...new Set([...Object.keys(PL.routes||{}),...Object.keys(PL.weapon_positions||{})])]);
  if(!midMap||!maps.includes(midMap))midMap=maps.includes(S.map)&&!HOST(S.map)?S.map:maps[0];
  const R=(PL.routes||{})[midMap]||{},W=(PL.weapon_positions||{})[midMap],ws=W?Object.keys(W).sort():[];
  if(!wpSide||!ws.includes(wpSide))wpSide=ws.includes(S.side)?S.side:ws[0];
  const B=M&&M.bench,pbCard=x=>`<article class="pbc ${isBoth(x)?"":x.side}">${x.prio>0?`<span class="you">${tl("Priority for you")}</span>`:""}<span class="eyebrow">${isBoth(x)?tl("CT and T"):x.side}</span>
     <span class="if">${tl("If {if}",{if:esc(lc(x.if))})}</span><span>→ ${esc(x.then)}</span><span class="why">${esc(x.why)}</span>${srcLinks(x.src,true)}</article>`;
  v.innerHTML=`<div class="head"><div style="display:grid;gap:4px"><span class="eyebrow">${esc(p.name)}${B?` · ${tl("{m} matches · compared with {p} players of the base and {pro} pros",{m:B.matches,p:B.n_players,pro:B.n_pros})}`:""}</span><h2>${tl("Mid-round: movement and decisions")}</h2></div></div>
   ${midBrief(PL)}${anchor("mr-decisions")}
   ${M?`${M.weak.length?`<div class="insights">${M.weak.map(w=>`<article class="card"><h3>${w.id==="note"?tl("What pros do"):esc(w.label[0].toUpperCase()+w.label.slice(1))}</h3>
       <p>${w.id==="note"?esc(w.text):`<span class="num">${tl("you {v}",{v:fmtU(w.you,w.unit)})}</span> · ${tl("base median {v}",{v:fmtU(w.median,w.unit)})}${w.pro!=null?` · ${tl("pros {v}",{v:fmtU(w.pro,w.unit)})}`:""}`}</p>
       ${w.fix?`<div class="fix"><h4>${tl("What to do")}</h4><p>${esc(w.fix)}</p></div>`:""}${w.percentile!=null?`<span class="note">${tl("You do better than {p}% of the players in the base.",{p:w.percentile})}</span>`:""}</article>`).join("")}</div>`:""}
     ${M.strong.length?`<div class="strengths">${M.strong.map(s=>`<span>${esc(s.text)}</span>`).join("")}</div>`:""}
     ${B?fold(tl("All your mid-round stats"),`<p class="note">${tl("The bar is your percentile in the base: further right, you do better than most; the line marks the median. \"Indicative\": neither good nor bad on its own, read it with the rest.")}</p>${midMetricRows(B)}`,"mr-all"):""}`
     :`<div class="empty">${tl("Mid-round stats need this player's demos. The reflexes below apply to everyone.")}</div>`}
   ${anchor("mr-reflexes")}<h3>${tl("If… then…: mid-round reflexes")}</h3>
   <div class="btns" role="group" aria-label="${tl("Filter the reflexes")}">${[...(anyMe?[["me",tl("Priority for you")]]:[]),["all",tl("All")],["CT","CT"],["T","T"]].map(([k,t])=>`<button type="button" data-pb="${k}" aria-pressed="${pbSide===k}">${t}</button>`).join("")}</div>
   <div class="pb">${pb.slice(0,4).map(pbCard).join("")}</div>
   ${fold(tln(pb.length-4,"{n} more reflex","{n} more reflexes"),pb.length>4?`<div class="pb">${pb.slice(4).map(pbCard).join("")}</div>`:"","mr-reflexes")}
   ${maps.length?fold(tl("Per map: rotations, and where to play with your weapon"),`
   <div class="chips" role="group" aria-label="${tl("Map")}">${maps.map((m,i)=>`${chipSep(maps,i)}<button type="button" data-mm="${m}" aria-pressed="${m===midMap}">${MAPN(m)}</button>`).join("")}</div>
   ${Object.keys(R).length?`<div class="rot">${Object.entries(R).sort().map(([s,r])=>rotCard(s,r)).join("")}</div>
     <p class="note">${tl("\"Leave after the hit\": seconds between at least 2 Ts reaching the site and you leaving for it (negative: you had already left). \"Travel\": from leaving to arriving. Routes: the first 3 zones crossed.")}</p>`
     :`<p class="note">${tl("No rotation of yours found on {map}.",{map:MAPN(midMap)})}</p>`}
   ${W?`<h3>${tl("Where to play with your weapon on {map}",{map:MAPN(midMap)})}</h3><div class="btns side" role="group" aria-label="${tl("Side")}">${ws.map(s=>`<button type="button" data-wps="${s}" aria-pressed="${s===wpSide}">${s}</button>`).join("")}</div>${wpBlock(W,wpSide)}
     <p class="note">${tl("Where each player stands between {a} and {b} on the round clock, by their weapon that round (matchmaking base). \"Duels won\": their duels in that zone. Pro AWPers: players with an AWP kill in the round (HLTV demos).",{a:clock(15),b:clock(25)})}</p>`:""}
   ${(PL.videos||{})[midMap]?`${srcLinks(PL.videos[midMap],false,tl("Videos on {map}:",{map:MAPN(midMap)}))}`:""}`,"mr-maps"):""}`;
  $$("[data-pb]",v).forEach(b=>b.onclick=()=>{pbSide=b.dataset.pb;renderMidround()});
  $$("[data-mm]",v).forEach(b=>b.onclick=()=>{midMap=b.dataset.mm;renderMidround()});
  $$("[data-wps]",v).forEach(b=>b.onclick=()=>{wpSide=b.dataset.wps;renderMidround()});
}

// ---------- view: progress ----------
const WORKS=v=>v==="it works"||v==="ça marche",HURTS=v=>v==="it hurts"||v==="ça dégrade";
// an experiment's verdict (experiments.py sends it in English)
// experiments.py's categories and units (data, in English)
const XCAT={Weapon:tl("Weapon"),Position:tl("Position"),Habit:tl("Habit"),"Mi-round":tl("Mid-round"),Training:tl("Training"),Session:tl("Session")},
  XUNIT={duels:tl("duels"),rounds:tl("rounds"),games:tl("games"),sessions:tl("sessions")};
const VERDICT={"it works":tl("it works"),"it hurts":tl("it hurts"),"no clear effect":tl("no clear effect"),"not enough data to compare yet":tl("not enough data to compare yet"),"in progress":tl("in progress")};
function expValue(x,unit){if(!x||x.value==null)return "—";return x.kind==="prop"?`${x.value}% (${x.k}/${x.n})`:fmtU(x.value,unit)}
function expCard(e){const pr=e.progress||[0,1,""],pct=Math.min(100,Math.round(100*pr[0]/Math.max(pr[1],1)));
  const cls=WORKS(e.verdict)?"strong":HURTS(e.verdict)?"weak":"";
  return `<article class="card exp"><div class="top"><span class="tag">${esc(XCAT[e.category]||e.category)}</span><span class="pill ${cls}">${e.status==="active"?"":`${tl("finished")} · `}${VERDICT[e.verdict]||esc(e.verdict)}</span></div>
   <span class="ttl">${esc(e.title)}</span>
   <ul>${(e.how||[]).map(h=>`<li>${esc(h)}</li>`).join("")}</ul>
   <div class="prog" title="${pct}%"><i style="width:${pct}%"></i></div><span class="note">${pr[0]}/${pr[1]} ${esc(XUNIT[pr[2]]||pr[2])} · ${tl("started {date}",{date:fmtDate(e.started)})}${e.ended?` · ${tl("finished {date}",{date:fmtDate(e.ended)})}`:""}</span>
   <div class="standing"><span>${esc(e.metric)}</span><span>${tl("before: {a} · since: {b}",{a:expValue(e.before,e.unit),b:expValue(e.after,e.unit)})}</span></div>
   ${e.status==="active"&&D.local?`<div class="btns"><button type="button" data-xstop="${e.id}">${tl("End the experiment")}</button></div>`:""}</article>`}
function suggestCard(s,i){return `<article class="card exp"><div class="top"><span class="tag">${esc(XCAT[s.category]||s.category)}</span></div><span class="ttl">${esc(s.title)}</span><p>${esc(s.why)}</p><span class="note">${tl("Measured with: {metric}",{metric:esc(s.metric)})}</span>${D.local?`<div class="btns"><button type="button" class="primary" data-xstart="${i}">${tl("Start")}</button></div>`:""}</article>`}
function kpiCard(k){const vals=k.series.map(x=>x[1]),W=200,H=40,mn=Math.min(...vals),mx=Math.max(...vals),rg=(mx-mn)||1;
  const pts=vals.map((y,i)=>`${(i/Math.max(vals.length-1,1)*W).toFixed(1)},${(H-4-(y-mn)/rg*(H-8)).toFixed(1)}`).join(" ");
  const d=k.recent-k.before,better=k.higher_better?d>0:d<0;
  return `<div class="kpi"><span class="note">${esc(k.label)}</span><b class="${Math.abs(d)<1e-9?"":better?"good":"bad"}">${fmtU(k.recent,k.unit)}</b>
   <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${tl("Trend over {n} matches",{n:vals.length})}"><polyline points="${pts}" fill="none" stroke="var(--ct)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>
   <span class="note">${tl("last 3: {a} · before: {b} · {n} matches",{a:fmtU(k.recent,k.unit),b:fmtU(k.before,k.unit),n:vals.length})}</span></div>`}
function weaponsBlock(W){const RD=W.ref_duels||{};
  return `<h3>${tl("Your weapons")} ${itip(tl("Over {n} analyzed rounds. Duels: kills and deaths with the weapon in hand, compared with every player in the base.",{n:W.n_rounds}))}</h3>${W.suggestions.length?`<ul class="pl-list">${W.suggestions.map(s=>`<li class="${s.kind==="weapon_weak"?"avoid":/strong/.test(s.kind)?"exploit":"coach"}">${esc(s.text)}</li>`).join("")}</ul>`:""}
   ${fold(tl("Every weapon you played: kills, damage, survival and duels ({n})",{n:W.by_weapon.length}),`<div class="tbl"><table><thead><tr><th>${tl("Main weapon of the round")}</th><th class="n">${tl("Rounds")}</th><th class="n">${tl("Kills / round")}</th><th class="n">${tl("Damage / round")}</th><th class="n">${tl("Survival")}</th><th class="n">${tl("Rounds won")}</th><th class="n">${tl("Duels won: you · base")}</th></tr></thead><tbody>
   ${W.by_weapon.map(x=>{const d=W.duels[x.key],r=RD[x.key];return `<tr><td>${esc(x.key)}</td><td class="n">${x.rounds}</td><td class="n">${f1(x.kpr)}</td><td class="n">${x.adr}</td><td class="n">${x.survival}%</td><td class="n">${x.win}%</td>
     <td class="n ${d&&r!=null&&d.n>=10?(d.win>=r+8?"good":d.win<=r-8?"bad":""):""}">${d?`${d.win}% <span class="note">(${d.n})</span>`:"—"} · ${r!=null?r+"%":"—"}</td></tr>`}).join("")}
   </tbody></table></div>
   ${W.force&&W.force.length?`<p class="note">${tl("<b>On force buys:</b> {list}",{list:W.force.filter(x=>x.rounds>=2).map(x=>`${esc(x.key)} ${tl("{adr} damage/round ({n} rounds)",{adr:x.adr,n:x.rounds})}`).join(" · ")})}</p>`:""}`,"pg-wtable")}`}
function buysBlock(B){if(!B||!B.types)return "";const T=B.types,p=P(),sw=s=>KIT_L(typeof expSwapTxt==="function"?expSwapTxt(p,s):s);
  const cell=(s,r)=>{const b=s&&s.kits&&s.kits[0];return b?`<b>${esc(sw(b.key))}</b> ${itip(b.why.map(esc).join(" · "),r)}${s.kits.length>1?`<br><span class="note">${tl("or {list}",{list:s.kits.slice(1).map(y=>esc(sw(y.key))).join(", ")})}</span>`:""}`:`<span class="note">${tl("not enough rounds")}</span>`};
  return `<h3>${tl("Your buys by type of round")} ${itip(tl("Fitted to you: your rounds first, then players of your profile ({profile}), then the whole base, per side. All maps together; the per-map detail is in Live. Eco: the weapon only, the one that keeps your next full buy.",{profile:(B.profile||[]).map(esc).join(", ")})+((typeof expSwaps==="function"?expSwaps(p):[]).length?" "+tl("🧪 = the weapon of your running experiment."):""))}</h3>
   <div class="tbl"><table><thead><tr><th>${tl("Round")}</th><th class="n">${tl("Your rounds")}</th><th class="n">${tl("Won: you · your profile")}</th><th>${tl("As T")}</th><th>${tl("As CT")}</th></tr></thead><tbody>
   ${["pistol","eco","force","full","anti-eco"].filter(k=>T[k]).map(k=>{const x=T[k],S2=x.sides||{};return `<tr><td><b>${esc(x.label)}</b></td><td class="n">${x.rounds}</td><td class="n">${x.win??"—"}% · ${x.peer_win??"—"}%</td>
     <td class="wrap">${cell(S2.T||(S2.CT?null:x))}</td><td class="wrap">${cell(S2.CT,true)}</td></tr>`}).join("")}</tbody></table></div>`}
function renderProgress(){
  const p=P(),v=$("#v-progress"),PL=p.advice.plan;if(!PL)return noPlan(v);
  const L=PL.level,Wp=PL.weapons,K=PL.kpis||[];
  v.innerHTML=`<div class="head"><div style="display:grid;gap:4px"><span class="eyebrow">${esc(p.name)}</span><h2>${tl("Weapons and buys")}</h2></div></div>
   ${progBrief(PL)}
   ${Wp?anchor("pg-weapons")+weaponsBlock(Wp):""}
   ${PL.buys&&PL.buys.types?anchor("pg-buys"):""}${buysBlock(PL.buys)}
   ${fold(L&&L.name?tl("At your level ({level}), work on",{level:esc(L.name)}):tl("At your level, work on"),L&&L.focus.length?`<ol>${L.focus.map(f=>`<li>${esc(f)}</li>`).join("")}</ol>${srcLinks(L.src,true)}`:"","pg-level")}
   ${K.length?fold(tl("Your stats, match by match"),`<p class="note">${tl("In color: the trend of your last 3 matches against the ones before.")}</p><div class="kpis">${K.map(kpiCard).join("")}</div>`,"pg-kpis"):""}`;
}
// ---------- training: your situations played again on the local server (bots on the recorded paths) ----------
const TRAIN={map:null,timer:null};
const DIFF=[tl("Easy"),tl("Normal"),tl("Hard"),tl("Expert")];
function trainDiff(){try{return +(localStorage.getItem("coach_diff")??2)}catch(e){return 2}}
function tPref(k,d){try{return localStorage.getItem("coach_t"+k)??d}catch(e){return d}}
function tSet(k,v){try{localStorage.setItem("coach_t"+k,v)}catch(e){}}
const BLOCK={defend:IC("shield")+" "+tl("Defense"),push:IC("footprints")+" "+tl("Push"),aim:IC("crosshair")+" "+tl("Aim"),crossfire:IC("crosshair")+" Crossfire",nade:IC("cloud")+" "+tl("Utility"),wallbang:IC("brick-wall")+" "+tl("Wallbang"),situation:IC("repeat")+" "+tl("Situations"),momentum:IC("fast-forward")+" Momentum"};
// not on this PC yet (a player's copy of the app, 05/10): made from the app, CS2's files linked next to the game
// again: what to show once the install started (13/10: from Prepare, its warm-up card, not the older training panel)
function trainInstall(box,sid,st,again){const ins=st.install||{},next=again||(()=>trainLoad(box,sid));
  box.innerHTML=`<div class="tinstall"><p>${tl("<b>The training server isn't on this PC yet.</b> It's a separate copy of CS2 next to the game, where bots replay real situations from your matches. Its files are links to the game's, so it takes no extra space and the game itself is never touched. Metamod:Source, CounterStrikeSharp and Wily's plugin only go into that copy. It takes a few minutes.")}</p>
   ${ins.running?`<p class="note"><span class="spin" aria-hidden="true"></span>${esc(ins.log||tl("Installing…"))}</p>`:`${ins.error?`<p class="note">${tl("Failed: {error}",{error:esc(ins.error)})}</p>`:""}<div class="btns"><button type="button" class="primary" id="t-install">${tl("Install the training server")}</button></div>`}
   ${st.path?`<p class="note">${tl("Folder: {path}",{path:`<code>${esc(st.path)}</code>`})}</p>`:""}</div>`;
  const b=box.querySelector("#t-install");
  if(b)b.onclick=async()=>{b.disabled=true;try{await api("/api/train/install",{})}catch(e){b.disabled=false;b.insertAdjacentHTML("afterend",`<span class="note">${esc(e.message)}</span>`);return}next()};
  if(ins.running&&!again)TRAIN.timer=setTimeout(()=>{if(box.isConnected)trainLoad(box,sid)},2500)}
async function trainLoad(box,sid){clearTimeout(TRAIN.timer);
  let d;try{d=await (await fetch("/api/train?sid="+sid)).json()}catch(e){box.innerHTML=`<span class="note">${tl("Wily's local server isn't responding.")}</span>`;return}
  if(!box.isConnected)return;
  const st=d.status||{},R=d.results||{},sc=d.scenarios||[],P=d.progress||{level:1,xp:0,from:0,to:300,due:{}},M=d.maps||{},ss=st.session;
  if(!st.installed){trainInstall(box,sid,st);return}
  // the bots' level and the warm-up preselected from your last sessions and matches, unless you chose them in the last
  // 12 hours (04/10: "the bots' level preselected from my level in training")
  const sg=P.suggest||null,chose=Date.now()-(+tPref("at","0"))<12*3600e3;
  let mins=+tPref("min","20"),df=trainDiff();if(sg&&!chose){df=sg.diff;if(sg.warmup)mins=5}
  const where=tPref("where","random"),due=P.due||{},nd=Object.values(due).reduce((a,b)=>a+b,0);
  const pct=Math.max(0,Math.min(100,100*(P.xp-P.from)/Math.max(1,P.to-P.from)));
  const mapsTop=Object.keys(M).slice(0,8);
  const chip=(k,v,lab,on)=>`<button type="button" data-t${k}="${v}" aria-pressed="${on}">${lab}</button>`;
  // the session running: what the server says (block, drill, points)
  const live=ss&&st.running?`<div class="tlive"><b>●</b><span>${BLOCK[ss.block]||tl("Session")} · ${esc(ss.drill||"…")}</span><span>${IC("star")} ${ss.points||0} · ${ss.ok||0}/${ss.done||0} ✔${ss.streak>=2?` · ${IC("flame")}${ss.streak}`:""}</span><span>${ss.left?`${Math.floor(ss.left/60)}:${String(ss.left%60).padStart(2,"0")}`:""}</span>${st.humans?"":`<span class="note">${tl("waiting for you on the server")}</span>`}</div>`:"";
  const maps=[...new Set(sc.map(s=>s.map))];if(TRAIN.map&&!maps.includes(TRAIN.map))TRAIN.map=null;
  const list=sc.filter(s=>!TRAIN.map||s.map===TRAIN.map).slice(0,12);
  const lab=s=>s.kind==="clutch"?tl("1v{n} clutch",{n:s.vs}):[tl("death"),s.opening?tl("opening"):"",s.traded?"":tl("no trade")].filter(Boolean).join(" · ");
  const res=s=>{const r=R[s.id];return r&&r.tries?`<span class="tres ${r.won+r.survived?"ok":""}">${r.tries}× · ${r.won+r.survived} ✓</span>`:r&&r.watched?`<span class="tres">${IC("eye")} ${r.watched}</span>`:`<span class="tres">${tl("new")}</span>`};
  box.innerHTML=`<div class="tplay">
     <div class="tlvl"><b>${tl("LVL {n}",{n:P.level})}</b><div class="tbar"><i style="width:${pct}%"></i></div><span>${P.xp} / ${P.to} XP</span>${nd?`<span class="tdue">${IC("repeat")} ${tl("{n} to redo",{n:nd})}</span>`:""}${P.mastered?`<span>⭐ ${tl("{n} mastered",{n:P.mastered})}</span>`:""}</div>
     ${live}
     <div class="trow"><span class="tk2">⏱</span>${[5,10,20,30,45].map(m=>chip("min",m,m===5?tl("5 min · warm-up"):tl("{n} min",{n:m}),m===mins)).join("")}</div>
     <div class="trow"><span class="tk2">${IC("map")}</span>${chip("where","random",IC("dices")+" "+tl("Random"),where==="random")}${chip("where","mix",IC("shuffle")+" "+tl("Mix"),where==="mix")}${mapsTop.map(m=>chip("where",m,MAPN(m),where===m)).join("")}</div>
     <div class="trow"><span class="tk2">${IC("bot")}</span>${DIFF.map((n,i)=>`<button type="button" data-tdiff="${i}" aria-pressed="${i===df}">${n}</button>`).join("")}${sg?`<span class="note">${tl("suggested: {level} · {why}",{level:DIFF[sg.diff],why:esc(sg.why)})}${sg.warmup?` · ${tl("warm-up: {why}",{why:esc(sg.warm_why)})}`:""}</span>`:""}</div>
     <div class="trow"><button type="button" class="tbig" data-tgo>${ss&&st.running?"↻ "+tl("NEW SESSION"):"▶ "+tl("PLAY")}</button>${ss&&st.running&&!st.humans?`<button type="button" data-tjoin>↪ ${tl("Rejoin the server")}</button>`:""}${st.running?`<button type="button" data-tstop>${tl("Stop the server")}</button>`:""}<span class="note" id="tmsg" role="status">${mins<=5?`${BLOCK.defend} → ${BLOCK.push}`:`${BLOCK.defend} → ${BLOCK.push} → ${BLOCK.nade} → ${BLOCK.situation}`}</span></div>
   </div>
   <details class="tcarte"><summary>${tl("Situations one by one ({n})",{n:sc.length})}</summary>
   ${maps.length>1?`<div class="btns" role="group" aria-label="${tl("Map")}"><button type="button" data-tmap="" aria-pressed="${!TRAIN.map}">${tl("All")}</button>${maps.map(m=>`<button type="button" data-tmap="${m}" aria-pressed="${TRAIN.map===m}">${MAPN(m)}</button>`).join("")}</div>`:""}
   <div class="tlist">${list.map((s,i)=>`<div class="tsit ${st.scenario===s.id?"cur":""}"><b>${MAPN(s.map)} R${s.round}</b>
     <span class="tk ${s.kind}">${lab(s)}</span><span class="tz">${esc(s.zone||"")}${s.mine?` · ${esc(s.mine)}`:""}${s.by?` <span class="note">${tl("vs {name} ({weapon})",{name:esc(s.by),weapon:esc(s.weapon||"")})}</span>`:""}</span>${res(s)}
     <button type="button" data-tplay="${i}" data-mode="actor">▶ ${tl("Play")}</button><button type="button" data-tplay="${i}" data-mode="spec">${IC("eye")} ${tl("Watch")}</button></div>`).join("")||`<span class="note">${tl("No situation yet: it needs the demos of your matches.")}</span>`}</div>
   <p class="note">${tl("In game: <b>!r</b> again · <b>!n</b> next · <b>!p</b> previous · <b>!spec</b> watch / play · <b>!stop</b>")}</p></details>`;
  if(TRAIN.open)$(".tcarte",box).open=true;
  $(".tcarte",box).ontoggle=e=>TRAIN.open=e.target.open;
  const msg=$("#tmsg",box);
  $$("[data-tmin]",box).forEach(b=>b.onclick=()=>{tSet("min",b.dataset.tmin);tSet("at",Date.now());trainLoad(box,sid)});
  $$("[data-twhere]",box).forEach(b=>b.onclick=()=>{tSet("where",b.dataset.twhere);trainLoad(box,sid)});
  $$("[data-tmap]",box).forEach(b=>b.onclick=()=>{TRAIN.map=b.dataset.tmap||null;trainLoad(box,sid)});
  $$("[data-tdiff]",box).forEach(b=>b.onclick=()=>{try{localStorage.setItem("coach_diff",b.dataset.tdiff)}catch(e){}tSet("at",Date.now());trainLoad(box,sid)});
  // the game crashed or was closed during a session: back on its server (04/10: "a rejoin button is missing")
  const jn=$("[data-tjoin]",box);if(jn)jn.onclick=async()=>{jn.disabled=true;msg.textContent=tl("CS2 is joining the server (it starts first if it's closed)…");
    try{await api("/api/train/join",{})}catch(e){msg.textContent=tl("Failed: {error}",{error:e.message});jn.disabled=false}};
  const sp=$("[data-tstop]",box);if(sp)sp.onclick=async()=>{sp.disabled=true;try{await api("/api/train/stop",{})}catch(e){msg.textContent=tl("Failed: {error}",{error:e.message})}trainLoad(box,sid)};
  const go=$("[data-tgo]",box);if(go)go.onclick=async()=>{go.disabled=true;msg.textContent=st.running?tl("Preparing the session…"):tl("Preparing the session and starting the server (about 15 s)…");
    try{const r=await api("/api/train/session",{sid,minutes:mins,where,diff:df});
      msg.innerHTML=`${r.blocks.map(b=>`${BLOCK[b.kind]} ${Math.round(b.seconds/60)}′`).join(" → ")} · ${r.session.maps.map(MAPN).join(", ")} — ${tl("CS2 is joining the server: follow the screen.")}`;
      setTimeout(()=>trainLoad(box,sid),4000)}
    catch(e){msg.textContent=tl("Failed: {error}",{error:e.message});go.disabled=false}};
  $$("[data-tplay]",box).forEach(b=>b.onclick=async()=>{const s=list[+b.dataset.tplay];$$("[data-tplay]",box).forEach(x=>x.disabled=true);
    msg.textContent=st.running?tl("Loading the situation…"):tl("Starting the training server (about 10 s)…");
    try{const r=await api("/api/train/play",{sid,mid:s.mid,round:s.round,kind:s.kind,mode:b.dataset.mode,diff:df});
      msg.innerHTML=r.humans?tl("{title}: starting on the server.",{title:esc(r.scenario.title)}):tl("Ready. In the CS2 console: <code>connect 127.0.0.1</code> (copied).");
      if(!r.humans)try{navigator.clipboard.writeText("connect 127.0.0.1")}catch(e){}
      setTimeout(()=>trainLoad(box,sid),2500)}
    catch(e){msg.textContent=tl("Failed: {error}",{error:e.message});$$("[data-tplay]",box).forEach(x=>x.disabled=false)}});
  if(st.running)TRAIN.timer=setTimeout(()=>{if(box.isConnected&&S.view==="prepare")trainLoad(box,sid)},4000)}
function wireExp(v,X,p){const msg=$("#xmsg",v);
  $$("[data-xstart]",v).forEach(b=>b.onclick=async()=>{const s=X.suggested[+b.dataset.xstart];b.disabled=true;
    try{await api("/api/experiment",{sid:p.steamid,action:"start",template:s.template,params:s.params});await reloadPlayer()}catch(e){if(msg)msg.textContent=tl("Failed: {error}",{error:e.message});b.disabled=false}});
  $$("[data-xstop]",v).forEach(b=>b.onclick=async()=>{b.disabled=true;
    try{await api("/api/experiment",{sid:p.steamid,action:"stop",id:b.dataset.xstop});await reloadPlayer()}catch(e){if(msg)msg.textContent=tl("Failed: {error}",{error:e.message});b.disabled=false}})}

// ---------- view: settings ----------
let steamForget=false;
// a player's copy (05/10): the coach's new versions of the app and of the base, signed by him, installed on a click
const fmtMB=b=>tl("{n} MB",{n:Math.max(1,Math.round((b||0)/1048576))}),UPW={code:tl("the app"),base:tl("the base"),runtime:tl("Python and its libraries")};
const when=x=>new Date(x*1000).toLocaleString(LOC,{dateStyle:"short",timeStyle:"short"});
function updateCard(u){
  if(!u||!u.enabled)return "";
  const c=u.current||{},av=u.available||[],pr=u.progress||{},busy=pr.busy||pr.restarting,pct=pr.total?Math.round(100*pr.done/pr.total):0;
  const list=av.map(a=>`<li>${UPW[a.part]||esc(a.part)} ${esc(a.version||"")}${a.matches?` · ${tl("{n} matches",{n:Number(a.matches).toLocaleString(LOC)})}`:""} · ${fmtMB(a.size)}</li>`).join("");
  return `<article class="card" id="up-card"><h3>${tl("App updates")} ${av.length?`<span class="pill strong">${tl("available")}</span>`:""}${itip(tl("Every update is signed by the developer and checked on your PC before it's installed. Your settings, matches, profile and recordings stay as they are."))}</h3>
   <p class="note">${tl("This version: {v}",{v:esc(c.app||"?")})}${c.build?` · ${tl("build {b}",{b:esc(c.build)})}`:""} · ${c.matches?tl("base {b} ({n} matches)",{b:esc(c.base||"?"),n:Number(c.matches).toLocaleString(LOC)}):tl("base {b}",{b:esc(c.base||"?")})}${u.checked?` · ${tl("checked {date}",{date:when(u.checked)})}`:""}</p>
   ${av.length?`<ul class="note">${list}</ul>${u.latest&&u.latest.notes?`<p>${esc(u.latest.notes)}</p>`:""}`:`<p class="note">${u.error?tl("Check failed: {error}",{error:esc(u.error)}):tl("Up to date.")}</p>`}
   ${busy?`<div class="sbar"><i style="width:${pct}%"></i></div><p class="note">${pr.restarting?tl("Restarting the app…"):pr.part==="installing"?tl("Installing…"):tl("Downloading {part}…",{part:UPW[pr.part]||""})}</p>`:""}
   ${pr.error?`<p class="note">${tl("Failed: {error}",{error:esc(pr.error)})}</p>`:""}
   ${setChk("up-auto",u.auto!==false,tl("Install updates automatically when you're not using the app (never while CS2 is open)"))}
   <div class="btns">${av.length&&!busy?`<button type="button" class="primary" id="up-go">${tl("Install the update")}</button>`:""}<button type="button" id="up-check"${busy?" disabled":""}>${tl("Check now")}</button></div></article>`}
function wireUpdate(v){
  const go=$("#up-go",v),ck=$("#up-check",v),au=$("#up-auto",v);
  if(au)au.onchange=async()=>{try{await api("/api/app/options",{auto_update:au.checked})}catch(e){}};
  if(ck)ck.onclick=async()=>{ck.disabled=true;try{await api("/api/update/check",{})}catch(e){}pollUpdate(v)};
  if(go)go.onclick=async()=>{go.disabled=true;try{await api("/api/update/apply",{})}catch(e){go.disabled=false;go.insertAdjacentHTML("afterend",`<span class="note">${esc(e.message)}</span>`);return}pollUpdate(v)}}
async function pollUpdate(v){clearTimeout(S.upTimer);
  let u=null;try{u=await (await fetch("/api/update")).json()}catch(e){S.upTimer=setTimeout(()=>pollUpdate(v),2000);return}   // restarting: back when it answers
  const pr=u.progress||{};
  if(S.upRestart&&!pr.restarting){location.reload();return}
  if(pr.restarting)S.upRestart=true;
  gearDot(u);const c=$("#up-card",v);if(!c||!c.isConnected)return;
  c.outerHTML=updateCard(u);wireUpdate(v);
  if(pr.busy||pr.restarting)S.upTimer=setTimeout(()=>{if(S.view==="settings")pollUpdate(v)},1500)}
// the coach's messages to the players' apps (14/10, tools/notices.py): signed, under the top bar, until closed or expired
function bcast(u){const box=$("#bcast");if(!box)return;const N=((u||{}).notices||[]);
  box.hidden=!N.length;box.innerHTML=N.map(n=>`<div class="bc ${n.level==="warn"?"warn":""}" data-bc="${esc(n.id)}"><span class="bc-k">${n.level==="warn"?IC("triangle-alert"):IC("megaphone")} ${tl("From Wily's author")}</span><span class="bc-t">${esc(n.text)}${n.link?` <a href="${esc(n.link)}" target="_blank" rel="noopener noreferrer">${tl("More")} ↗</a>`:""}</span><button type="button" class="bc-x" aria-label="${tl("Close")}" title="${tl("Close")}">✕</button></div>`).join("");
  $$(".bc-x",box).forEach(b=>b.onclick=async()=>{const el=b.closest("[data-bc]");el.remove();box.hidden=!box.children.length;
    try{await api("/api/update/dismiss",{id:el.dataset.bc})}catch(e){}})}
function gearDot(u){bcast(u);const g=$(".gear");if(!g)return;const n=((u||{}).available||[]).length;g.classList.toggle("has-update",!!n);
  const ab=$("#acctbtn");if(ab)ab.classList.toggle("has-update",!!n);
  g.title=n?tl("Settings: an app update is available"):tl("Settings: Steam, game detection, microphone")}
// the base grows with the players (05/10): a player's switch (off until they turn it on), or what the coach received
function shareCard(c){
  if(!c)return "";
  if(!c.client){const st=c.stats||{};
    return `<article class="card" id="ct-card"><h3>${tl("Matches shared by players")}${itip(tl("The base loop pulls them every hour while it runs; each match is checked again here (the app's own tables, no real SteamID, no name) and kept once."))}</h3>
     <p class="note">${c.token?`${tl("{a} joined the base · {b} already there · {c} refused",{a:st.joined||0,b:st.duplicates||0,c:st.refused||0})}${c.held?` · <b>${tl("{n} held",{n:c.held})}</b>${itip(tl("Sent by a build whose first-launch notice didn't mention the matches (10/10): kept out of the base. <code>python -m wily.sharing.contributions release</code> adds them, deleting <code>out/contrib_in/held</code> drops them."))}`:""}${c.waiting?` · ${tl("{n} waiting here",{n:c.waiting})}`:""}${c.last?` · ${tl("last pull {date}",{date:when(c.last)})}`:""}`:tl("Not set up yet: python -m wily.sharing.contributions init, then publish the site (website/deploy.py).")}</p>
     ${c.token?`<div class="btns"><button type="button" id="ct-pull"${c.pulling?" disabled":""}>${tl("Pull now")}</button>${c.held&&!c.pulling?`<button type="button" id="ct-release">${tl("Add the {n} held to the base",{n:c.held})}</button><button type="button" id="ct-drop">${tl("Delete the held")}</button>`:""}</div>`:""}
     <div id="pd-box"></div></article>`}
  return `<article class="card" id="ct-card"><h3>${tl("Share my matches with the base")} ${c.on?`<span class="pill strong">${tl("on")}</span>`:`<span class="pill">${tl("off")}</span>`}</h3>
   <p class="note">${c.on?`${tln(c.sent,"{n} match shared","{n} matches shared")}${c.waiting?` · ${tl("{n} waiting",{n:c.waiting})}`:""}${c.last?` · ${tl("last {date}",{date:when(c.last)})}`:""}`:tl("Off: nothing leaves this PC.")}${c.error?` · ${tl("last try failed: {error}",{error:esc(c.error)})}`:""}</p>
   ${setFold("set-share",tl("What is shared, and how to have it deleted"),`<p class="note">${tl("The base you're compared with grows with the players who use the app. When this is on, your new matches are sent anonymized: what the app extracted from each demo (positions, duels, grenades, buys, rounds), with every SteamID replaced by a random ID used for that match only, every name removed and a random match ID. Never your demos, your voice, your settings or your profile.")}</p>
   <p class="note">${tl("You can turn it off at any time. To have what this PC sent deleted before it joins the base, write to the developer with this installation's ID: {id}.",{id:`<code>${esc(c.install||"")}</code>`})} <a href="https://wily.valentingassend.com/${LANG==="fr"?"confidentialite":"privacy"}.html" target="_blank" rel="noopener" style="color:var(--ct)">${tl("Privacy policy")}</a></p>`)}
   <div class="btns"><button type="button"${c.on?"":` class="primary"`} id="ct-on" data-on="${c.on?0:1}">${c.on?tl("Stop sharing"):tl("Share my matches")}</button>${c.on&&c.waiting?`<button type="button" id="ct-send"${c.sending?" disabled":""}>${tl("Send now")}</button>`:""}</div></article>`}
function wireShare(v){
  wirePro(v);
  const on=$("#ct-on",v),sd=$("#ct-send",v),pl=$("#ct-pull",v),rl=$("#ct-release",v),dr=$("#ct-drop",v);
  const redo=async()=>{let c=null;try{c=await (await fetch("/api/contrib")).json()}catch(e){return}const k=$("#ct-card",v);if(k&&k.isConnected){k.outerHTML=shareCard(c);wireShare(v)}};
  if(on)on.onclick=async()=>{on.disabled=true;try{await api("/api/contrib/set",{on:on.dataset.on==="1"})}catch(e){}redo()};
  if(sd)sd.onclick=async()=>{sd.disabled=true;try{await api("/api/contrib/send",{})}catch(e){}setTimeout(redo,3000)};
  // the held uploads (15/10): into the base (checked like any pull, in the background) or deleted, the coach's call
  if(rl)rl.onclick=async()=>{rl.disabled=true;if(dr)dr.disabled=true;rl.textContent=tl("Adding…");
    try{await api("/api/contrib/release",{})}catch(e){rl.insertAdjacentHTML("afterend",`<span class="note"> ${tl("failed: {error}",{error:esc(e.message)})}</span>`);return}
    for(let i=0;i<450;i++){await new Promise(r=>setTimeout(r,2000));if(!rl.isConnected)return;const c=await getC();if(c&&!c.pulling)break}
    redo()};
  if(dr)dr.onclick=async()=>{const n=dr.dataset.sure;if(!n){dr.dataset.sure="1";dr.textContent=tl("Delete them for good?");return}
    dr.disabled=true;if(rl)rl.disabled=true;try{await api("/api/contrib/drop",{})}catch(e){}redo()};
  // Pull now (12/10): the server pulls and checks in the background, often longer than a few seconds: the button
  // follows it to its end, then says what joined, that nothing was new, or why it failed
  const getC=async()=>{try{return await (await fetch("/api/contrib")).json()}catch(e){return null}};
  if(pl)pl.onclick=async()=>{pl.disabled=true;pl.textContent=tl("Pulling…");const b4=(await getC())||{},t0=Date.now();
    const done=(html)=>{const k=$("#ct-pull",v);if(k)k.insertAdjacentHTML("afterend",`<span class="note"> ${html}</span>`)};
    try{await api("/api/contrib/pull",{})}catch(e){pl.textContent=tl("Pull now");pl.disabled=false;done(tl("failed: {error}",{error:esc(e.message)}));return}
    let c=null;
    while(Date.now()-t0<15*60e3){await new Promise(r=>setTimeout(r,2000));if(!pl.isConnected)return;c=await getC();if(c&&!c.pulling)break;
      const k=$("#ct-pull",v);if(k)k.textContent=tl("Pulling… {n} s",{n:Math.round((Date.now()-t0)/1e3)})}
    await redo();
    if(!c||c.pulling){done(tl("still running: the result will show here when you open Settings again"));return}
    if(c.pull_error){done(tl("failed: {error}",{error:esc(c.pull_error)}));return}
    const a=(b4.stats||{}),z=(c.stats||{}),d=["joined","duplicates","refused"].map(x=>(z[x]||0)-(a[x]||0)),h=Math.max(0,(c.held||0)-(b4.held||0)),n=d[0]+d[1]+d[2]+h;
    done(n?(h?tl("pulled {n} match(es): {a} joined, {b} already there, {c} refused, {h} held",{n,a:d[0],b:d[1],c:d[2],h}):tl("pulled {n} match(es): {a} joined, {b} already there, {c} refused",{n,a:d[0],b:d[1],c:d[2]})):tl("checked just now: nothing new"))}}
// pro demos you downloaded yourself (22/10, the coach: "rajoute un bouton pour ajouter les démos ... à l'analyse pour
// s'en servir aussi pour trouver des stuffs"): each file sent whole, then the inbox analyzed into the pro base in the
// background; the box follows the run to its end and says what joined the pro base, or why not
function pdBox(p,up){
  const L=p.last||{},cur=p.running?L.file:null,run=new Set(p.running?L.files||[]:[]),here=new Set((p.waiting||[]).map(w=>w.name));
  const W=p.running&&!L.files?[]:(p.waiting||[]).filter(w=>!run.has(w.name));   // the run's own files (its list not written yet: all of them) not waiting
  const why={"a match is going on":tl("a match is going on"),"the app is analyzing":tl("the app is analyzing"),
    "a recording or a transcription":tl("a recording or a transcription"),"the app is updating its references":tl("the app is updating its references")};
  const now=up?tl("Sending {name}… {p}%",{name:esc(up.name),p:up.p})
    :!p.running?"":L.step==="wait"?tl("Waiting: {why}",{why:why[L.why]||esc(L.why||"")})
    :L.step==="refresh"?tl("The pros' references computed again…")
    :cur?tl("Analyzing {name}…",{name:esc(cur)})+(L.step==="map"&&L.n>1?` · ${tl("map {i}/{n}",{i:L.i,n:L.n})}`:""):tl("Analyzing…");
  const who=d=>esc((d.teams||[]).join(" vs ")||tl("teams not in the demo")),maps=d=>esc((d.maps||[]).map(m=>MAPN(m)).join(", "));
  const res=[...(L.done||[]).map(d=>d.already?tl("{file}: already in the pro base",{file:esc(d.file)}):`${who(d)} (${maps(d)})`),
    ...(L.failed||[]).filter(f=>here.has(f.file)).map(f=>tl("{file}: not added ({why})",{file:esc(f.file),why:f.why==="no demo"?tl("no demo inside, or 7-Zip could not open it"):esc(f.why||"")}))];
  return `<p class="note"><b>${tl("Pro demos")}</b>${itip(tl("Demos you downloaded yourself (a match's GOTV Demo on HLTV, a LAN's archive: .dem, .rar, .zip or .7z): each map is analyzed into the pro base with its teams, then used to find the stuffs (a pro's throw counts three times) and for the pros' references. The analysis waits while a match is going on; the copies sent here are deleted once analyzed, your own files stay where they are."))} · ${tln(p.maps||0,"{n} map in the pro base","{n} maps in the pro base")}${now?` · ${now}`:""}${W.length?` · ${tln(W.length,"{n} file waiting","{n} files waiting")}`:""}${L.step==="disk"&&!p.running?` · ${tl("Stopped: not enough room on the disk")}`:""}</p>
   ${!p.running&&!up&&L.ended&&res.length?`<p class="note">${tl("Last import: {list}",{list:res.join(" · ")})}</p>`:""}
   ${W.length&&!p.running&&!up?`<ul class="note">${W.map(w=>`<li>${esc(w.name)} · ${tl("{n} MB",{n:w.mb})} <button type="button" data-pd-drop="${esc(w.name)}">${tl("Delete")}</button></li>`).join("")}</ul>`:""}
   <div class="btns"><button type="button" id="pd-add"${up?" disabled":""}>${tl("Add demos")}</button>${W.length&&!p.running&&!up?`<button type="button" id="pd-run">${tl("Analyze them")}</button>`:""}<input type="file" id="pd-file" accept=".dem,.rar,.zip,.7z" multiple hidden></div>`}
async function wirePro(v){
  const get=async()=>{try{return await (await fetch("/api/prodemos")).json()}catch(e){return null}};
  let p=await get(),following=false;if(!p||p.maps===undefined)return;   // an app not restarted since: no box
  const show=(up,err)=>{const b=$("#pd-box",v);if(!b||!b.isConnected)return false;b.innerHTML=pdBox(p,up)+(err?`<p class="note">${err}</p>`:"");wire();return true};
  // the run to its end: what it is on, then what joined
  const follow=async()=>{if(following)return;following=true;
    while(true){await new Promise(r=>setTimeout(r,2000));const q=await get();if(!q)continue;p=q;if(!show()||!q.running)break}following=false};
  function wire(){
    const add=$("#pd-add",v),inp=$("#pd-file",v),run=$("#pd-run",v);
    if(add&&inp){add.onclick=()=>inp.click();inp.onchange=async()=>{const fs=[...inp.files];inp.value="";let err="";
      for(const f of fs){try{await pdSend(f,pc=>show({name:f.name,p:pc}))}catch(e){err+=` ${tl("failed: {error}",{error:esc(`${f.name}: ${e.message}`)})}`}}
      const q=await get();if(q)p=q;show(null,err.trim());if(p.running)follow()}}
    if(run)run.onclick=async()=>{run.disabled=true;try{p=await api("/api/prodemos/run",{})}catch(e){}show();if(p.running)follow()};
    $$("[data-pd-drop]",v).forEach(b=>b.onclick=async()=>{b.disabled=true;try{p=await api("/api/prodemos/drop",{name:b.dataset.pdDrop})}catch(e){}show()})}
  show();if(p.running)follow()}
// one file sent whole to the app (an archive of a whole match is up to 1.5 GB): its progress, then the app's answer
function pdSend(f,prog){return new Promise((ok,ko)=>{const x=new XMLHttpRequest();
  x.open("POST",`/api/prodemos/add?name=${encodeURIComponent(f.name)}&mtime=${f.lastModified||0}`);
  x.upload.onprogress=e=>{if(e.lengthComputable)prog(Math.round(100*e.loaded/e.total))};
  x.onload=()=>{let r={};try{r=JSON.parse(x.responseText||"{}")}catch(e){}x.status<300?ok(r):ko(new Error(r.error||x.statusText||String(x.status)))};
  x.onerror=()=>ko(new Error(tl("Wily's local server isn't responding.")));x.send(f)})}
// a bug report (05/10, the alpha): the player writes, sees what is sent, sends; kept and sent later when offline
function bugPage(){return `${S.view||"?"}${S.player&&S.player===D.own?" (own profile)":S.player?" (another profile)":""} ${location.pathname}${location.hash}`.slice(0,120)}
function openReport(kind){const d=$("#bugdlg");if(!d)return;$("#bug-msg").textContent="";$("#bug-send").disabled=false;
  $$("input[name=kind]",d).forEach(r=>r.checked=r.value===(kind||"bug"));$("#bug-pre").textContent="…";$("#bug-prev").open=false;
  if(typeof d.showModal==="function")d.showModal();else d.setAttribute("open","");$("#bug-text").focus()}
function wireReport(){const d=$("#bugdlg");if(!d||d.dataset.wired)return;d.dataset.wired="1";
  $("#bug-close").onclick=()=>d.close();
  $("#bug-prev").ontoggle=async()=>{if(!$("#bug-prev").open)return;$("#bug-pre").textContent=tl("Reading…");
    if(!$("#bug-diag").checked){$("#bug-pre").textContent=tl("No technical details: only what you wrote.");return}
    try{const r=await api("/api/report/preview",{page:bugPage(),errors:ERRS});$("#bug-pre").textContent=JSON.stringify(r,null,1)}catch(e){$("#bug-pre").textContent=e.message}};
  $("#bug-diag").onchange=()=>{if($("#bug-prev").open)$("#bug-prev").ontoggle()};
  $("#bug-send").onclick=async()=>{const t=$("#bug-text").value.trim(),m=$("#bug-msg");if(!t){m.textContent=tl("Describe what happened first.");$("#bug-text").focus();return}
    const b=$("#bug-send");b.disabled=true;m.textContent=tl("Sending…");
    try{const r=await api("/api/report/send",{text:t,expected:$("#bug-exp").value,email:$("#bug-email").value,include:$("#bug-diag").checked,
        page:bugPage(),errors:ERRS,kind:($("input[name=kind]:checked",d)||{}).value||"bug"});
      if(r.ok){m.textContent=tl("Sent, thank you (report {id}).",{id:r.id});$("#bug-text").value="";$("#bug-exp").value="";setTimeout(()=>d.close(),2500)}
      else{m.textContent=tl("Wily's website can't be reached right now: your report is saved on this PC and will be sent as soon as possible.");b.disabled=false}}
    catch(e){m.textContent=e.message;b.disabled=false}}}
function reportCard(){if(D.role!=="client")return "";
  return `<article class="card"><h3>${tl("Alpha")} <span class="pill">0.0.x</span></h3><p>${tl("Wily is in alpha and open to everyone for the first time, so things will break. Tell me what broke, or share an idea: the \"alpha · report\" tag at the top works from any page.")}</p>
   <div class="btns"><button type="button" class="primary" data-report="bug">${tl("Report a bug")}</button><button type="button" data-report="idea">${tl("Suggest an idea")}</button></div></article>`}
// the coach's PC: what players reported (16/10: their feedback apart, read and never "done"; a report sent again shown once)
const isFb=r=>r.kind==="feedback"||/^\[feedback/.test(r.text||""),FACES=[IC("angry"),IC("frown"),IC("meh"),IC("smile"),IC("laugh")];
function fbParse(r){const L=(r.text||"").split("\n"),h=/^\[feedback · (.*?) · (\d)\/5\]\s*(.*)$/.exec(L[0]||"")||[],tags=[],note=[];
  L.slice(1).forEach(x=>{const t=/^Tags: (.*)$/.exec(x);if(t)tags.push(...t[1].split(/,\s*/).filter(Boolean));else if(x.trim())note.push(x.trim())});
  return {r,warm:/warm-up|training/.test(`${h[1]||""} ${r.page||""}`),n:r.rating||+(h[2]||0),sum:h[3]||"",tags,note:note.join(" ")}}
function feedbackCard(rs){if(D.role==="client"||!Array.isArray(rs))return "";
  const fb=rs.filter(isFb).map(fbParse);if(!fb.length)return "";
  const rated=fb.filter(f=>f.n),avg=rated.length?rated.reduce((a,f)=>a+f.n,0)/rated.length:0,cnt=[1,2,3,4,5].map(n=>rated.filter(f=>f.n===n).length),mx=Math.max(1,...cnt),tags={};
  fb.forEach(f=>f.tags.forEach(t=>tags[t]=(tags[t]||0)+1));
  const one=f=>`<li><span class="fb-face" title="${f.n?f.n+"/5":""}">${f.n?FACES[f.n-1]:"·"}</span><div><b>${f.warm?tl("Warm-up"):tl("Match with Live")}</b> <span class="note">${esc(f.sum)} · ${when(f.r.at)}</span>
     ${f.tags.length?`<div class="fb-tags">${f.tags.map(t=>`<span class="pill">${esc(t)}</span>`).join("")}</div>`:""}${f.note?`<p>“${esc(f.note)}”</p>`:""}</div></li>`;
  return `<article class="card" id="fb-card"><h3>${tl("Players' feedback")} <span class="pill">${fb.length}</span>${itip(tl("Asked after a warm-up and after a match with Live: a face, a few tags, a few words. To read: nothing to mark."))}</h3>
   <div class="fb-sum"><b class="fb-avg">${avg?avg.toLocaleString(LOC,{maximumFractionDigits:1}):"—"}<small>/5</small></b>
    <div class="fb-dist">${cnt.map((c,i)=>`<span><i style="height:${Math.round(100*c/mx)}%"></i><em>${FACES[i]}</em><small>${c}</small></span>`).join("")}</div>
    ${Object.keys(tags).length?`<div class="fb-tags">${Object.entries(tags).sort((a,b)=>b[1]-a[1]).map(([t,n])=>`<span class="pill">${esc(t)} · ${n}</span>`).join("")}</div>`:""}</div>
   <ul class="fblist">${fb.slice(0,3).map(one).join("")}</ul>
   ${fb.length>3?setFold("set-fbmore",`${tl("Older")} <span class="note">${fb.length-3}</span>`,`<ul class="fblist">${fb.slice(3,40).map(one).join("")}</ul>`):""}</article>`}
function reportsCard(rs){if(D.role==="client"||!Array.isArray(rs))return "";
  const by={},grp=[];   // the newest of each text first; handled when all its copies are
  rs.filter(r=>!isFb(r)).forEach(r=>{const k=(r.text||"").trim();if(by[k]){by[k].ids.push(r.id);by[k].done=by[k].done&&r.done;return}grp.push(by[k]={...r,ids:[r.id]})});
  const open=grp.filter(g=>!g.done),shut=grp.filter(g=>g.done),one=r=>`<li class="rep${r.done?" done":""}"><div><b>${/^\[in-game !report/.test(r.text||"")?IC("gamepad-2")+" "+tl("In-game report"):r.kind==="idea"?IC("lightbulb")+" "+tl("Idea"):IC("bug")+" "+tl("Bug")}</b>${r.ids.length>1?` <span class="pill">${tln(r.ids.length,"sent {n} time","sent {n} times")}</span>`:""} · ${when(r.at)} · ${esc(r.app||"?")}${r.email?` · <a href="mailto:${esc(r.email)}">${esc(r.email)}</a>`:""}</div>
     <p>${esc(r.text||"")}</p>${r.expected?`<p class="note">${tl("Expected: {text}",{text:esc(r.expected)})}</p>`:""}<p class="note">${esc(r.page||"")}</p>
     <div class="btns">${r.has_diag?`<button type="button" data-rdiag="${esc(r.id)}">${tl("Technical details")}</button>`:""}<button type="button" data-rdone="${esc(r.ids.join(","))}" data-v="${r.done?0:1}">${r.done?tl("Reopen"):tl("Mark as handled")}</button></div><pre class="rdiag" hidden></pre></li>`;
  return `<article class="card wide" id="rp-card"><h3>${tl("Bug reports")} ${open.length?`<span class="pill weak">${tl("{n} open",{n:open.length})}</span>`:""}${itip(tl("Sent by players from their app (the \"alpha · report\" tag, !report on the training server), pulled every hour by the base loop while it runs."))}</h3>
   ${open.length?`<ul class="replist">${open.slice(0,30).map(one).join("")}</ul>`:`<p class="note">${grp.length?tl("Nothing open."):tl("None yet.")}</p>`}
   ${shut.length?setFold("set-rdone",`${tl("Handled")} <span class="note">${shut.length}</span>`,`<ul class="replist">${shut.slice(0,30).map(one).join("")}</ul>`):""}
   <div class="btns"><button type="button" id="rp-pull">${tl("Pull now")}</button></div></article>`}
function wireReports(v){
  $$("[data-report]",v).forEach(b=>b.onclick=()=>openReport(b.dataset.report));
  const redo=rs=>{[["#rp-card",reportsCard],["#fb-card",feedbackCard]].forEach(([id,f])=>{const k=$(id,v);if(k&&k.isConnected)k.outerHTML=f(rs)});wireReports(v)};
  const pl=$("#rp-pull",v);if(pl)pl.onclick=async()=>{pl.disabled=true;pl.textContent=tl("Pulling…");try{const r=await api("/api/reports/pull",{});redo(r);
      const k=$("#rp-pull",v);if(k)k.insertAdjacentHTML("afterend",`<span class="note"> ${tl("checked just now: {n} report(s) here",{n:(r||[]).length})}</span>`)}catch(e){pl.textContent=tl("Pull now");pl.disabled=false;pl.insertAdjacentHTML("afterend",`<span class="note"> ${tl("failed: {error}",{error:esc(e.message)})}</span>`)}};
  $$("[data-rdone]",v).forEach(b=>b.onclick=async()=>{b.disabled=true;let rs=null;
    try{for(const id of b.dataset.rdone.split(","))rs=await api("/api/reports/done",{id,done:b.dataset.v==="1"});redo(rs)}catch(e){b.disabled=false}});
  $$("[data-rdiag]",v).forEach(b=>b.onclick=async()=>{const pre=b.closest("li").querySelector(".rdiag");if(!pre.hidden){pre.hidden=true;return}
    try{const r=(await (await fetch("/api/reports?id="+encodeURIComponent(b.dataset.rdiag))).json()).find(x=>x.id===b.dataset.rdiag);pre.textContent=JSON.stringify(r&&r.diag,null,1);pre.hidden=false}catch(e){}})}
// anonymous usage statistics (05/10): a player's switch and today's counters; the coach's ranking of what players use
function usageCard(u){if(!u||!u.client)return "";
  const t=u.today||{},nv=Object.keys(t.views||{}).length,na=Object.values(t.actions||{}).reduce((a,b)=>a+b,0);
  return `<article class="card" id="us-card"><h3>${tl("Usage statistics")} ${u.on?`<span class="pill strong">${tl("on")}</span>`:`<span class="pill">${tl("off")}</span>`}${itip(tl("Anonymous counters, per day: the pages you open and for how long, the buttons you use, the errors on the page, whether Live runs during a match, the app's version and your screen size class. No ID, no SteamID, no name, nothing you type. A finished day is sent, added to that day's totals and thrown away."))}</h3>
   <p class="note">${u.on?tl("Today so far: {v} page(s), {a} click(s) counted · {d} day(s) sent",{v:nv,a:na,d:u.days_sent}):tl("Off: nothing is counted or sent.")}</p>
   ${u.on&&u.today?`<details><summary>${tl("Today's counters, exactly")}</summary><pre class="uspre">${esc(JSON.stringify(u.today,null,1))}</pre></details>`:""}
   <div class="btns"><button type="button" id="us-on" data-on="${u.on?0:1}">${u.on?tl("Turn it off"):tl("Turn it on")}</button></div></article>`}
const VLABEL={ingame:tl("Live"),prepare:tl("Prepare"),review:tl("Review"),profile:tl("Profile"),players:tl("Players"),pros:tl("Pros"),team:tl("Team"),settings:tl("Settings")};
function usageStatsCard(st){if(!st||D.role==="client")return "";
  const T=st.totals||{},pd=T.reports||0,mins=s=>(s/60).toFixed(1);
  if(!pd)return `<article class="card wide" id="ust-card"><h3>${tl("How players use the app")}</h3><p class="note">${tl("No usage statistics yet: they come from players' apps one day after use, once the player has seen the first-launch notice, and are pulled every hour by the base loop while it runs.")}</p><div class="btns"><button type="button" id="ust-pull">${tl("Pull now")}</button></div></article>`;
  const row=(c)=>`<tr>${c.map(x=>`<td>${x}</td>`).join("")}</tr>`;
  const views=(st.views||[]).map(v=>row([esc(VLABEL[v.view]||v.view),`${v.users} <span class="note">(${v.share}%)</span>`,v.visits,mins(v.seconds),v.minutes_per_user])).join("");
  const acts=(st.actions||[]).slice(0,25).map(a=>row([`<code>${esc(a.action)}</code>`,`${a.users} <span class="note">(${a.share}%)</span>`,a.count])).join("");
  const rare=(st.rare||[]).map(a=>`<code>${esc(a.action)}</code> ${a.users}`).join(" · ");
  const dict=o=>Object.entries(o||{}).sort((a,b)=>b[1]-a[1]).map(([k,n])=>`${esc(k)} ${n}`).join(" · ");
  return `<article class="card wide" id="ust-card"><h3>${tl("How players use the app")} <span class="pill">${tl("last {n} days",{n:st.days})}</span>${itip(tl("An element nobody clicked doesn't appear at all: compare with the page to find what nobody uses."))}</h3>
   <p class="note">${tl("{pd} player-day(s) over {d} day(s) · Live during a match: {lu} player-day(s), {lm} min · days with page errors: {er} ({e} errors) · versions: {v} · screens: {s}",{pd,d:T.days,lu:T.live_users,lm:mins(T.live_seconds),er:T.error_reports,e:T.errors,v:dict(T.apps),s:dict(T.screens)})}</p>
   <h4>${tl("Pages")}</h4><div class="oxs"><table class="ustab"><thead><tr><th>${tl("Page")}</th><th>${tl("Player-days")}</th><th>${tl("Visits")}</th><th>${tl("Minutes")}</th><th>${tl("Min / player-day")}</th></tr></thead><tbody>${views}</tbody></table></div>
   ${setFold("set-uacts",`${tl("Most used actions")} <span class="note">${(st.actions||[]).length}</span>`,`<div class="oxs"><table class="ustab"><thead><tr><th>${tl("Action (page:element)")}</th><th>${tl("Player-days")}</th><th>${tl("Clicks")}</th></tr></thead><tbody>${acts}</tbody></table></div>`)}
   ${rare?setFold("set-urare",tl("Rarely used"),`<p class="note">${rare}</p>`):""}
   <div class="btns"><button type="button" id="ust-pull">${tl("Pull now")}</button></div></article>`}
function wireUsage(v){
  const on=$("#us-on",v);if(on)on.onclick=async()=>{on.disabled=true;try{const r=await api("/api/usage/set",{on:on.dataset.on==="1",noticed:true});D.usage={on:r.on,noticed:true};const k=$("#us-card",v);if(k){k.outerHTML=usageCard(r);wireUsage(v)}}catch(e){on.disabled=false}};
  const pl=$("#ust-pull",v);if(pl)pl.onclick=async()=>{pl.disabled=true;try{const r=await api("/api/usage/pull",{days:30});const k=$("#ust-card",v);if(k){k.outerHTML=usageStatsCard(r);wireUsage(v);
      const b=$("#ust-pull",v);if(b)b.insertAdjacentHTML("afterend",`<span class="note"> ${tl("checked just now: {n} report(s) over {d} day(s)",{n:((r||{}).totals||{}).reports||0,d:((r||{}).totals||{}).days||0})}</span>`)}}catch(e){pl.disabled=false;pl.insertAdjacentHTML("afterend",`<span class="note">${esc(e.message)}</span>`)}}}
// ---------- Settings (12/10, reworked: 87 min spent there over 3 player-days, the setup lost among long cards). The
// setup guide's steps first, one line each once done and open while something is left; then Live (what you tune
// before a match), the app, what leaves the PC, the base. Explanations in the "i", the rarely needed in folds, two
// cards a row. Every control keeps its id: the usage statistics count the clicks by it.
const SET_OPEN={};   // a step open or closed as the player left it, across the re-renders that follow each click
document.addEventListener("toggle",e=>{const d=e.target;if(d&&d.dataset&&d.dataset.sstep)SET_OPEN[d.dataset.sstep]=d.open},true);
// a step: st "ok" (done, closed), "todo" (open), "opt" (optional and off, closed); state: one short line, never repeated
// in the step's body
function setStep(id,n,st,title,state,body){const open=id in SET_OPEN?SET_OPEN[id]:st==="todo";
  return `<details class="card sstep ${st}" id="${id}" data-sstep="${id}"${open?" open":""}><summary><b class="sstep-n" aria-hidden="true">${st==="ok"?"✓":n}</b><span class="sstep-h"><span class="sstep-t">${title}</span><span class="sstep-s">${state}</span></span></summary><div class="sstep-b">${body}</div></details>`}
const setChk=(id,on,label,tip)=>`<div class="srow chkrow"><label class="chk"><input type="checkbox" id="${id}"${on?" checked":""}> ${label}</label>${tip?itip(tip):""}</div>`;
const setFold=(id,title,html)=>`<details class="set-more" data-fold="${id}"${FOLD_OPEN.has(id)?" open":""}><summary>${title}</summary>${html}</details>`;
// a microphone that hears nothing (16/10): nothing at all is a mute, Windows or another app; almost nothing, another microphone
const micWhy=p=>p?tl("Almost nothing: not the microphone you speak into, or its volume is very low (Windows: Settings › Sound › Input)."):tl("Nothing at all usually means the microphone is muted (its button: a red light on many USB microphones), Windows blocks it (Settings › Privacy › Microphone), or another app holds it alone.");
function micLevel(v,r){const b=$("#v-lvl",v),t=$("#v-verdict",v);if(!b||!t)return;const p=Math.max(0,r.peak||0);
  b.style.width=(p>0?Math.max(4,Math.min(100,Math.round((20*Math.log10(p)+50)*2))):0)+"%";b.className=p<0.01?"lo":"";   // -50 dBFS: empty, 0 dBFS: full
  if(r.recording){t.className="note";t.textContent=`${r.device||""} · ${tl("level now")}`;return}
  t.className=p<0.01?"bad":"good";t.textContent=`${r.device||""}: ${p>=0.01?tl("it hears you."):p?tl("almost silent."):tl("no sound at all.")}${p<0.01?" "+micWhy(p):""}`}
const INPUT_S="font:14px var(--f-mono);background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:3px;padding:5px 8px";
async function renderSettings(){
  const v=$("#v-settings");
  const head=`<div class="head"><div style="display:grid;gap:4px"><span class="eyebrow">${tl("Your demos, profile and codes stay on this PC")}</span><h2>${tl("Settings")}</h2></div>${D.local?`<button type="button" id="sg-open">${tl("Setup guide")}</button>`:""}</div>`;
  if(!D.local){v.innerHTML=head+`<div class="empty">${tl("Settings live in the desktop app: double-click <code>Wily.bat</code>, then open Settings.")}</div>`;return}
  v.innerHTML=head+`<div class="empty"><span class="spin" aria-hidden="true"></span>${tl("Reading your Steam connection…")}</div>`;
  let st;try{st=await (await fetch("/api/steam/status"+(D.own?`?sid=${D.own}`:""))).json()}catch(e){v.innerHTML=head+`<div class="empty">${tl("Wily isn't responding: restart Wily.bat and it will be back.")}</div>`;return}
  let gs=null;try{gs=await (await fetch("/api/gsi/status")).json()}catch(e){}
  let vs=null;try{vs=await (await fetch("/api/voice/status")).json()}catch(e){}
  let cc=null;try{cc=await (await fetch("/api/coach/status")).json()}catch(e){}
  let up=null;try{up=await (await fetch("/api/update")).json()}catch(e){}
  let ct=null;try{ct=await (await fetch("/api/contrib")).json()}catch(e){}
  let rs=null;if(D.role!=="client"){try{rs=await (await fetch("/api/reports")).json()}catch(e){}}
  let us=null;try{us=await (await fetch(D.role==="client"?"/api/usage":"/api/usage/stats?days=30")).json()}catch(e){}
  const flag=new URLSearchParams(location.search).get("steam"),L=st.links||{},client=D.role==="client";
  // 1. your Steam account: signed in through Steam's page, or the account open in Steam on this PC (as the guide)
  const pc=st.pc_account||{},s1=!!(st.login||D.own),who=st.login?(st.login.name||st.login.steamid):(pc.steamid&&pc.steamid===String(D.own)?pc.name:D.own);
  const step1=setStep("set-steam",1,s1?"ok":"todo",tl("Your Steam account"),s1?esc(who||""):tl("sign in with Steam"),
    `${st.login?`<p class="note">${tl("SteamID {id} · signed in through Steam on {date} · your default profile in the app",{id:`<span class="num">${esc(st.login.steamid)}</span>`,date:fmtDate(st.login.time)})}</p>`
      :s1?`<p class="note">${tl("The account signed in to Steam on this PC: {id}. To use another one, sign in on Steam's website.",{id:`<span class="num">${esc(String(D.own))}</span>`})}</p>`
      :`<p>${tl("Open Steam and sign in to your account, then reload this page. Or sign in on Steam's website: it confirms your account to Wily, which never sees your password.")}</p>`}
     ${st.login&&pc.steamid&&pc.steamid!==st.login.steamid?`<p class="note">${tl("Signed in to Steam on this PC: {name}",{name:`${esc(pc.name||"")} <span class="num">${esc(pc.steamid)}</span>`})}</p>`:""}
     <div class="srow"><a class="lbtn${s1?"":" primary"}" href="/api/steam/login">${st.login?tl("Sign in with Steam again"):tl("Sign in with Steam")}</a><span class="btns"><button type="button" id="st-forget">${steamForget?tl("Confirm: remove the sign-in and the codes"):tl("Disconnect everything")}</button></span><span class="note" id="sf-msg" role="status"></span></div>`);
  // 2. connect CS2: game detection, and the launch option that writes the console (numpad keys) and loads the keys
  const c2a=!!(gs&&gs.installed),c2b=!!(cc&&(cc.console||cc.bound)),s2=c2a&&c2b;
  const step2=setStep("set-cs2",2,s2?"ok":"todo",tl("Connect CS2"),
    s2?(gs.receiving?tl("CS2 is sending its data"):tl("ready: CS2 sends its data once started")):[c2a?"":tl("game detection off"),c2b?"":tl("launch option missing")].filter(Boolean).join(" · "),
    `<div class="srow">${sgTick(c2a)}<b>${tl("Game detection")}</b>${itip(tl("Valve's Game State Integration, the official feature HUDs and RGB keyboards use: CS2 sends Wily the map, your side, the round, the score, your money and your grenades, so Live follows your match on its own. During a match CS2 only sends your own info, never the enemies'.")+(gs&&gs.path?`<br><br>${tl("File: {path}",{path:`<code>${esc(gs.path)}</code>`})}`:""))}
       ${c2a?`<span class="btns"><button type="button" id="gsi-off">${tl("Turn detection off")}</button></span>`:gs&&gs.cfg_dir?`<span class="btns"><button type="button" class="primary" id="gsi-on">${tl("Turn detection on")}</button></span>`:`<span class="note">${tl("CS2 folder not found on this PC.")}</span>`}</div>
     <div class="srow">${sgTick(c2b)}<b>${tl("Launch option")}</b>${itip(tl("It makes CS2 write its console log (Live's numpad keys go through it) and loads Wily's key binds. Checked once CS2 has started with it."))}<span class="note">${tl("Steam › right-click <b>Counter-Strike 2</b> › <b>Properties</b> › <b>Launch options</b>:")}</span></div>
     <div class="sg-copy"><code>${SG_LAUNCH}</code><span class="btns"><button type="button" id="st-cp">${tl("Copy")}</button></span></div>
     ${cc&&cc.bound&&!cc.tempo_bound?`<p>${tl("Numpad 4-5-6 are new: run <code>exec wily_bind</code> once more in CS2's console (your numpad 5 ran <code>bot_crouch 1</code>: it now sets a slow tempo).")}</p>`:""}
     ${cc&&cc.bound&&cc.tempo_bound&&!cc.rt_bound?`<p>${tl("F5 is new: it throws your last grenade again in the training server's sandbox. Run <code>exec wily_bind</code> once more in CS2's console.")}</p>`:""}
     ${setChk("o-cs2",!gs||gs.open_on_cs2!==false,tl("Open Live when CS2 starts (if no Wily page is open yet)"),tl("Nothing can write in CS2's lobby chat, so Wily opens itself instead: the page first, then CS2's window comes back on top. Wily must be running: it starts with Windows if a shortcut to it is in your Startup folder (Win+R, shell:startup)."))}
     <span class="note" id="gsi-msg" role="status"></span>`);
  // 3. your matches: the history code
  const s3=!!st.has_auth;
  const step3=setStep("set-hist",3,s3?"ok":"todo",tl("Your matches"),
    s3?`${tln(st.known_matches,"{n} match known","{n} matches known")} · ${tl("last sync {date}",{date:st.last_sync?fmtDate(st.last_sync):tl("never")})}${st.pending?` · ${tl("{n} pending (Steam open, CS2 closed)",{n:st.pending})}`:""}`:tl("add your history code"),
    `<p>${s3?tl("Your history code is saved: I find each new match on my own."):tl("Valve only gives your <b>last 8 matches</b> and deletes demos after about <b>a month</b>. With your history code, I find <b>every new match</b>, analyze the demos still available and keep the date, score, kills and teammates of the others.")}${itip(tl("<b>What it unlocks</b><br>No lost match: each one is found, analyzed while its demo exists and counted in your habits afterwards.<br>Habits over your whole history: the hours when you play best, games per session, loss streaks.<br>Your group: your Steam friends on your team are recognized, even after a single match together.<br>Your experience: your playtime sets the priorities in Weapons & buys.<br><br>Your codes stay in <code>out/settings.json</code> on this PC. They go to Steam's official API; without a key of your own, through Wily's website, which passes the request to Steam and stores nothing."))}</p>
     <div class="srow"><span class="f">${tl("History code")}</span><input id="st-auth" type="password" autocomplete="off" spellcheck="false" aria-label="${tl("Authentication code")}" placeholder="${s3?tl("saved · paste a new one"):"XXXX-XXXXX-XXXX"}" style="width:240px;${INPUT_S}">
       <input id="st-known" type="text" autocomplete="off" spellcheck="false" aria-label="${tl("Code of your last match")}" placeholder="${tl("Code of your last match CSGO-… (optional)")}" style="flex:1;min-width:240px;${INPUT_S}"></div>
     <p class="note">${tl("On {link} (signed in to your account): \"Create authentication code\". The same page shows the code of your last match; if you leave it empty, I find it from your last 8 matches (Steam open, CS2 closed).",{link:`<a href="${esc(L.auth)}" target="_blank" rel="noopener" style="color:var(--ct)">${tl("Steam's CS2 help page")}</a>`})}</p>
     ${setFold("set-key",`${tl("Your own Steam API key")} <span class="note">${st.has_key?tl("saved"):tl("optional")}</span>`,`<div class="srow"><input id="st-key" type="password" autocomplete="off" spellcheck="false" aria-label="${tl("Steam API key")}" placeholder="${st.has_key?tl("saved · paste a new key to replace it"):tl("32 characters")}" style="flex:1;min-width:220px;${INPUT_S}"></div>
       <p class="note">${tl("Without one, Wily's website asks Steam for you. To use your own, create it on {link} (signed in to your Steam account). Domain name: write <code>localhost</code>.",{link:`<a href="${esc(L.key)}" target="_blank" rel="noopener" style="color:var(--ct)">steamcommunity.com/dev/apikey</a>`})}</p>`)}
     <div class="srow"><span class="btns"><button type="button" class="primary" id="st-save">${tl("Save and check")}</button><button type="button" class="primary" id="st-sync" ${s3?"":"disabled"}>${tl("Sync now")}</button></span><span class="note" id="st-msg" role="status"></span></div>
     ${s3?setChk("st-auto",st.auto_sync,tl("Sync automatically when the app starts, then every 30 minutes"),tl("Off: \"Update my matches\" in your menu (top right) does it when you want.")+(st.friends!=null?" "+tln(st.friends,"{n} Steam friend known (used to detect your group).","{n} Steam friends known (used to detect your group)."):"")):""}`);
  // 4. your calls: optional ("opt" while off), "to do" when it records and its last recording heard nothing (16/10: 10 of
  // 14 recordings at exactly 0 under a step marked done); the microphone tested here, its level shown
  const va=!!(vs&&vs.available),auto=!!(va&&vs.settings&&vs.settings.auto),rec=va?vs.recordings||[]:[];
  const last=rec.filter(r=>(r.duration||0)>=60).slice(0,5),mute=last.filter(r=>r.silent),deaf=auto&&!!last[0]&&last[0].silent;
  const lh=va&&(vs.live||{}).last&&vs.live.last.text?`<br><br>${tl("Last heard: \"{text}\"",{text:esc(vs.live.last.text)})}${vs.live.last.parsed?` → ${esc([vs.live.last.parsed.rush?"rush":"",vs.live.last.parsed.n||"",vs.live.last.parsed.site||"",vs.live.last.parsed.zone||"",vs.live.last.parsed.bomb?tl("bomb"):""].filter(Boolean).join(" · "))}`:` ${tl("(not a call)")}`}.`:"";
  const step4=setStep("set-mic",4,deaf?"todo":auto?"ok":"opt",tl("Your calls (microphone)"),
    va&&vs.recording?`<b class="bad">● ${tl("Recording")}</b>${vs.current&&vs.current.map?` · ${MAPN(vs.current.map)}`:""}`:!va?tl("unavailable on this PC"):deaf?tl("your last recording heard nothing: test the microphone"):auto?tl("records your matches · {device}",{device:esc(vs.device||tl("Windows default microphone"))}):tl("off · optional"),
    `<p>${tl("Your calls, transcribed on this PC and lined up with the rounds: the Review then shows the info you gave before dying, \"where + how many\", the grenades you called, talking during a teammate's clutch, frustration.")}${itip(tl("Only your voice: with a headset, your teammates' voices don't reach your microphone. Nothing leaves the PC (folder <code>out/voice</code>, not versioned)."))}</p>
     <p class="note">${tl("<b>Only record other people with their consent</b>: recording someone's words without it is illegal in France (article 226-1 of the Code pénal) and in many other countries.")}</p>
     ${va?`${setChk("v-auto",vs.settings.auto,tl("Record automatically during my matches (with game detection)"))}
      ${setChk("v-live",(vs.live||{}).on!==false,tl("Live calls: my short calls (\"3 B\", \"rush A\", \"bomb B\", \"one Banana\") count like a tap on the T read"),tl("Short calls only (sentences are ignored), transcribed on this PC by a small model at low priority on the processor: the graphics card stays free for the game. About 2 to 3 s after you speak.")+lh)}
      <div class="micbox"><div class="srow"><span class="f">${tl("Microphone")}</span><select id="v-dev" style="font:14px var(--f-body);background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:3px;padding:5px 8px;max-width:360px"><option value="">${tl("Windows default microphone")}</option></select>${vs.recording?"":`<span class="btns"><button type="button" id="v-test">${tl("Test the microphone")}</button></span>`}</div>
       <div class="vmeter-row"><div class="vmeter" aria-hidden="true"><i id="v-lvl"></i></div><span class="note" id="v-verdict" role="status">${vs.recording?tl("Recording: the bar is what it hears now."):tl("Press the button and speak for 3 seconds: nothing is recorded.")}</span></div>
       ${mute.length?`<p class="${deaf?"bad":"note"}">${tl("{n} of your last {m} recordings heard nothing.",{n:mute.length,m:last.length})} ${micWhy(mute[0].peak||0)}</p>`:""}</div>
      ${vs.recording?`<div class="srow"><b class="bad">● ${tl("Recording")}</b><span class="note">${tl("since {date}",{date:fmtDate(vs.current.start_iso)})}</span><span class="btns"><button type="button" id="v-stop">${tl("Stop")}</button></span></div>`:""}
      ${vs.transcribing?`<p class="note"><span class="spin" aria-hidden="true"></span>${tl("Transcribing ({what}): it runs at low priority and pauses when a match starts.",{what:esc(vs.transcribing)})}</p>`:""}
      ${rec.length?setFold("set-recs",`${tl("Recordings")} <span class="note">${rec.length}</span>`,`<div class="tbl"><table><thead><tr><th>${tl("Date")}</th><th>${tl("Map")}</th><th class="n">${tl("Length")}</th><th class="n">${tl("Rounds found")}</th><th>${tl("Transcription")}</th><th></th></tr></thead><tbody>
        ${rec.map(r=>`<tr><td>${fmtDate(r.start)}</td><td>${r.map?MAPN(r.map):"—"}${r.practice?` <span class="pill">${tl("practice")}</span>`:""}${r.team?` <span class="pill" title="${esc(r.team)}">${tl("+ team sound")}</span>`:""}</td><td class="n">${r.duration?tl("{n} min",{n:Math.round(r.duration/60)}):tl("in progress")}</td><td class="n">${r.rounds_marked||"—"}</td>
          <td>${r.silent?`<span class="bad" title="${esc(micWhy(r.peak||0))}">${r.peak?tl("almost silent"):tl("no sound at all")}</span>`:r.transcribed?tl("done"):r.duration?`<button type="button" data-vtr="${r.id}">${tl("Transcribe")}</button>`:"—"}</td><td><button type="button" data-vdel="${r.id}">${tl("Delete")}</button></td></tr>`).join("")}</tbody></table></div>`)
       :`<p class="note">${tl("No recording yet.")}</p>`}`
     :`<p class="note">${vs&&vs.error?tl("Microphone unavailable on this PC ({error}).",{error:esc(vs.error)}):tl("Microphone unavailable on this PC.")}</p>`}<span class="note" id="v-msg" role="status"></span>`);
  // Live: the numpad keys (the coach's voice gone, 20/10: "enlève le TTS sur le module live")
  // the numpad as it is under the hand (16/10): each key where it sits, colored by what it does, the unused ones dimmed
  const NP=[["Num"],["/"],["*"],["−",tl("clear them"),"x"],["7",tl("A site"),"s"],["8"],["9",tl("B site"),"s"],["+",0,0,"tall"],
    ["4",tl("rush"),"t"],["5",tl("slow"),"t"],["6",tl("map control"),"t"],["1","A","d"],["2",tl("mid"),"d"],["3","B","d"],["⏎",0,0,"tall"],["0",0,0,"wide"],["."]];
  const keysCard=`<article class="card" id="set-keys"><h3>${tl("Numpad keys")}${itip(tl("On T, a key types what you pressed in the team chat: your direction and your tempo (\"A\", \"Rush B\", \"Map control, then mid\"; on A and B with CS2's own \"Go A\" / \"Go B\" from the chat wheel, the order bots follow). It tells Wily too: Live then shows the way in that wins most, its odds this round, when to be on the site and its utility, with a ping on the map. On CT, the keys only tell Wily: 1-2-3 where you play, 4-5-6 what the Ts do.<br><br>Live must be open during the match (it writes the lines). A key's file only contains its line and the chat wheel's order, never another command."))}</h3>
    <div class="np-wrap"><div class="numpad">${NP.map(([k,l,g,sz])=>`<span class="np np-${g||"off"}${sz?" "+sz:""}"><kbd>${k}</kbd>${l?`<small>${l}</small>`:""}</span>`).join("")}</div>
     <ul class="np-leg"><li><i class="np-d"></i><span><b>1 · 2 · 3</b> ${tl("where you go (T) or where you play (CT)")}</span></li>
      <li><i class="np-t"></i><span><b>4 · 5 · 6</b> ${tl("your tempo (T) or what the Ts do (CT)")}</span></li>
      <li><i class="np-s"></i><span><b>7 · 9</b> ${tl("on CT, the site you play; once the bomb is down, the site it was planted on")}</span></li></ul></div></article>`;
  const th0=store("theme")||"dark",lgName=(D.langs||{})[LANG]||LANG;
  const swRow=(id,on,title,words)=>`<label class="sw-row"><input type="checkbox" role="switch" id="${id}"${on?" checked":""}><span class="sw" aria-hidden="true"></span><span class="sw-t"><b>${title}</b><small>${words}</small></span></label>`;
  const prefCard=`<article class="card pref"><h3>${tl("Display")}</h3>
    <div class="pref-sec"><span class="pref-h">${tl("Theme")}</span>
     <div class="th-tiles" role="group" aria-label="${tl("Theme")}">${[["dark",tl("Dark")],["light",tl("Light")],["system",tl("Your system's")]].map(([k,l])=>`<button type="button" class="th-tile" data-theme-set="${k}" aria-pressed="${th0===k}"><span class="th-prev th-${k}" aria-hidden="true"><i></i><b></b><b></b><em></em></span><span class="th-l">${l}</span></button>`).join("")}</div>
     <p class="note">${tl("In this browser; \"Your system's\" follows Windows.")}</p></div>
    ${swRow("o-fb",!gs||gs.feedback_prompts!==false,tl("Ask me how it went"),tl("After a warm-up and after a match: a face, a few tags, a few words if you want. Sent only when you press Send."))}
    ${gs&&gs.linux?swRow("o-lxt",gs.linux_training,tl("Training server on Linux (experimental)"),tl("Its first runs on Linux: if it fails, send a report with the \"alpha · report\" tag, its log goes with it.")):""}
    ${D.local?`<div class="pref-lang"><span class="pref-h">${tl("Language")}</span><b lang="${LANG}">${esc(lgName)}</b><span class="btns"><button type="button" id="o-lang-open">${GLOBE}${tl("Change it in the bar")}</button></span></div>`:""}</article>`;
  const left=[s1,s2,s3].filter(x=>!x).length+(deaf?1:0),outT=client?tl("What leaves this PC"):tl("The base and the players' apps");
  v.innerHTML=head+`
  ${flag==="ok"?`<div class="jobpanel" style="padding:0"><div class="in ok">${tl("Steam confirmed the sign-in.")}</div></div>`:flag==="refused"||flag==="refus"?`<div class="jobpanel" style="padding:0"><div class="in err">${tl("Steam didn't confirm the sign-in. Try again.")}</div></div>`:""}
  ${secNav([["set-s-setup",tl("Setup")],["set-s-live",tl("Live")],["set-s-app",tl("This app")],["set-s-out",outT]])}
  <section class="set-sec" id="set-s-setup"><h3 class="set-h">${tl("Setup")} ${left?`<span class="pill weak">${tln(left,"{n} step left","{n} steps left")}</span>`:`<span class="pill strong">${tl("all set")}</span>`}${itip(tl("The setup guide's steps: a step closes once it's done; open it to change something."))}</h3><div class="ssteps">${step1}${step2}${step3}${step4}</div></section>
  <section class="set-sec" id="set-s-live"><h3 class="set-h">${tl("Live")}</h3><div class="set-grid">${keysCard}</div></section>
  <section class="set-sec" id="set-s-app"><h3 class="set-h">${tl("This app")}</h3><div class="set-grid">${prefCard}${updateCard(up)}${reportCard()}</div></section>
  <section class="set-sec" id="set-s-out"><h3 class="set-h">${outT}</h3><div class="set-grid">${client?shareCard(ct)+usageCard(us):shareCard(ct)+feedbackCard(rs)+reportsCard(rs)+usageStatsCard(us)}</div></section>`;
  const sgo=$("#sg-open",v);if(sgo)sgo.onclick=()=>setupGuide(v,false);   // the three steps of the first launch, again
  const msg=$("#st-msg",v),gmsg=$("#gsi-msg",v),sid=st.steamid;
  const vmsg=$("#v-msg",v),vcall=async(path,body)=>{try{await api(path,Object.assign({sid},body||{}));renderSettings()}catch(e){if(vmsg)vmsg.textContent=e.message}};
  const va_=$("#v-auto",v);if(va_)va_.onchange=()=>vcall("/api/voice/settings",{auto:va_.checked});
  const vl=$("#v-live",v);if(vl)vl.onchange=()=>vcall("/api/voice/settings",{live:vl.checked});
  const vd=$("#v-dev",v);if(vd){fetch("/api/voice/devices").then(r=>r.json()).then(list=>{if(!Array.isArray(list))return;const cur=(vs.settings||{}).device||"",ch=list.findIndex(d=>d.chosen);
    vd.innerHTML=`<option value="">${vs.cs2_device?tl("The same as CS2 ({name})",{name:esc(vs.cs2_device)}):tl("Windows default microphone")}</option>`+list.map((d,i)=>`<option value="${esc(d.name)}" ${i===ch?"selected":""}>${esc(d.name)}${d.cs2?` ${tl("(used by CS2)")}`:d.default?` ${tl("(Windows default)")}`:""}</option>`).join("")
      +(cur&&ch<0?`<option value="${esc(cur)}" selected>${esc(cur)} ${tl("(not found on this PC)")}</option>`:"")}).catch(()=>{});
    vd.onchange=()=>vcall("/api/voice/settings",{device:vd.value||null})}
  const vst=$("#v-stop",v);if(vst)vst.onclick=()=>vcall("/api/voice/stop");
  const vt=$("#v-test",v);if(vt)vt.onclick=async()=>{vt.disabled=true;let k=3;const say=()=>{vt.textContent=tl("Speak now… {n}",{n:k})};say();const iv=setInterval(()=>{k=Math.max(1,k-1);say()},1000);
    try{micLevel(v,await api("/api/voice/test",{}))}catch(e){const t=$("#v-verdict",v);if(t){t.className="bad";t.textContent=e.message}}
    clearInterval(iv);vt.disabled=false;vt.textContent=tl("Test again")};
  const tok=S.micTok=(S.micTok||0)+1;
  if(va&&vs.recording){const tick=async()=>{if(S.micTok!==tok||S.view!=="settings"||!$("#v-lvl",v))return;try{micLevel(v,await api("/api/voice/test",{}))}catch(e){}setTimeout(tick,1000)};tick()}
  $$("[data-vtr]",v).forEach(b=>b.onclick=()=>{b.disabled=true;vcall("/api/voice/transcribe",{id:b.dataset.vtr})});
  $$("[data-vdel]",v).forEach(b=>b.onclick=()=>{if(b.dataset.ok!=="1"){b.dataset.ok="1";b.textContent=tl("Confirm");return}vcall("/api/voice/delete",{id:b.dataset.vdel})});
  const gon=$("#gsi-on",v),goff=$("#gsi-off",v);
  if(gon)gon.onclick=async()=>{gon.disabled=true;try{gsiStatus=await api("/api/gsi/install",{});renderSettings()}catch(e){gmsg.textContent=e.message;gon.disabled=false}};
  if(goff)goff.onclick=async()=>{goff.disabled=true;try{gsiStatus=await api("/api/gsi/uninstall",{});renderSettings()}catch(e){gmsg.textContent=e.message;goff.disabled=false}};
  const cp=$("#st-cp",v);if(cp)cp.onclick=async()=>{try{await navigator.clipboard.writeText(SG_LAUNCH);cp.textContent=tl("Copied ✓")}catch(e){gmsg.textContent=tl("Select the text and copy it (Ctrl+C).")}};
  const olo=$("#o-lang-open",v);if(olo)olo.onclick=e=>{e.stopPropagation();langOpen()};   // the bar's own list (20/10)
  $("#st-save",v).onclick=async()=>{const b=$("#st-save",v);b.disabled=true;msg.textContent=tl("Checking with Steam…");
    try{const j=await api("/api/steam/credentials",{sid,api_key:$("#st-key",v).value.trim(),auth_code:$("#st-auth",v).value.trim(),known_code:$("#st-known",v).value.trim()});
      msg.textContent=j.saved.length?tl("Saved: {what}.",{what:j.saved.map(x=>({"API key":tl("the API key"),"history code":tl("the history code")})[x]||x).join(", ")}):tl("Nothing new to save.");setTimeout(renderSettings,900)}
    catch(e){msg.textContent=e.message;b.disabled=false}};
  $("#st-sync",v).onclick=async()=>{msg.textContent="";try{await api("/api/steam/sync",{sid});poll()}catch(e){msg.textContent=e.message}};
  const au=$("#st-auto",v);if(au)au.onchange=async()=>{try{await api("/api/steam/options",{sid,auto_sync:au.checked})}catch(e){msg.textContent=e.message}};
  const oc=$("#o-cs2",v);if(oc)oc.onchange=async()=>{try{await api("/api/app/options",{open_on_cs2:oc.checked})}catch(e){}};
  const lxt=$("#o-lxt",v);if(lxt)lxt.onchange=async()=>{try{await api("/api/app/options",{linux_training:lxt.checked});D.linux_training=lxt.checked;if(gsiStatus)gsiStatus.linux_training=lxt.checked}catch(e){}};
  const ofb=$("#o-fb",v);if(ofb)ofb.onchange=async()=>{try{await api("/api/app/options",{feedback_prompts:ofb.checked})}catch(e){}};
  $$("[data-theme-set]",v).forEach(b=>b.onclick=()=>{store("theme",b.dataset.themeSet);applyTheme(b.dataset.themeSet);$$("[data-theme-set]",v).forEach(x=>x.setAttribute("aria-pressed",x===b))});
  wireUpdate(v);wireShare(v);wireReports(v);wireUsage(v);  $("#st-forget",v).onclick=async()=>{if(!steamForget){steamForget=true;renderSettings();return}steamForget=false;
    try{await api("/api/steam/forget",{sid});renderSettings()}catch(e){const m=$("#sf-msg",v);if(m)m.textContent=e.message}};
}

// ---------- view: team ----------
const TCOL=["#e8d44d","#4cb87a","#e0663a","#5b9be0","#c77dff"];
let teamSel=null,teamId=null,teamPlan=null,teamIdx=null,teamSug=null,teamQ="",teamMap=null,teamSide="CT",teamLevel=null,teamExec=null;
async function loadTeamIdx(force){if(teamIdx&&!force)return teamIdx;try{const r=await fetch("teams/index.json"+(force?`?t=${Date.now()}`:""));teamIdx=r.ok?await r.json():[]}catch(e){teamIdx=[]}return teamIdx}
async function loadTeam(id){const r=await fetch(`teams/${id}.json?t=${Date.now()}`);if(!r.ok)throw new Error("plan not found");teamPlan=await r.json();teamId=id;
  await Promise.all(Object.keys(teamPlan.plans||{}).map(loadRadar));return teamPlan}
function teamRadarDraw(box,map,level,items){const svg=$("svg",box),g=$("g",box);
  $("image",box).setAttribute("href",D.radars[`${map}:${level}`]||"");svg.setAttribute("viewBox",(D.viewboxes[map]||[0,0,1024,1024]).join(" "));g.replaceChildren();
  const defs=el("defs",{},g),mk=el("marker",{id:"tarrow",viewBox:"0 0 10 10",refX:"7",refY:"5",markerWidth:"5",markerHeight:"5",orient:"auto-start-reverse"},defs);
  el("path",{d:"M0,0 L10,5 L0,10 z",style:"fill:#ff5a4e"},mk);
  const on=it=>it.px&&(!it.level||!level||it.level===level);
  // T lanes: a red arrow toward the site, as thick as the lane is used, with its share of the rounds
  items.filter(it=>it.kind==="lane"&&on(it)&&it.to).forEach(it=>{
    const [x1,y1]=it.px,[x2,y2]=it.to,dx=x2-x1,dy=y2-y1,L=Math.hypot(dx,dy)||1,k=Math.max(0,(L-40)/L);
    tip(el("line",{x1,y1,x2:x1+dx*k,y2:y1+dy*k,"marker-end":"url(#tarrow)",style:`stroke:#ff5a4e;stroke-opacity:.75;stroke-width:${it.w||4};stroke-linecap:round;${it.dash?"stroke-dasharray:10 8":""}`},g),it.title||"");
    if(it.label)el("text",{x:x1,y:y1-10,"text-anchor":"middle",class:"zlabel",style:"fill:#ffb3ad"},g).textContent=it.label});
  items.filter(it=>it.kind==="site"&&on(it)).forEach(it=>{
    el("circle",{cx:it.px[0],cy:it.px[1],r:30,style:"fill:none;stroke:#fff;stroke-opacity:.5;stroke-width:2;stroke-dasharray:4 4"},g);
    el("text",{x:it.px[0],y:it.px[1]+46,"text-anchor":"middle",class:"zlabel"},g).textContent=it.label});
  // grenades: dotted arc from the thrower's spot to where it lands, letter on the landing
  items.filter(it=>it.kind==="nade"&&it.to&&on(it)).forEach(it=>{
    const [x1,y1]=it.px,[x2,y2]=it.to,mx=(x1+x2)/2-(y2-y1)*.15,my=(y1+y2)/2+(x2-x1)*.15;
    el("path",{d:`M${x1},${y1} Q${mx},${my} ${x2},${y2}`,style:`fill:none;stroke:${it.color};stroke-width:2;stroke-dasharray:3 4;opacity:.85`},g);
    tip(el("rect",{x:x2-9,y:y2-9,width:18,height:18,rx:4,style:`fill:${{smoke:"#9aa5b1",flash:"#f2e14c",molotov:"#ff8a3d",he:"#7bd88f"}[it.type]||"#ccc"};stroke:#111;stroke-width:1.5`},g),it.title||"");
    el("text",{x:x2,y:y2+4,"text-anchor":"middle",style:"font:700 11px var(--f-mono);fill:#111"},g).textContent=it.short||""});
  // positions: a disc in the player's color (grey with a number for an extra player), a ring when it is the player's own spot
  items.filter(it=>it.kind==="dot"&&on(it)).forEach(it=>{
    if(it.ring)el("circle",{cx:it.px[0],cy:it.px[1],r:18,style:`fill:none;stroke:${it.color};stroke-width:2.5`},g);
    tip(el("circle",{cx:it.px[0],cy:it.px[1],r:12,style:`fill:${it.color};stroke:#111;stroke-width:2`},g),it.title||"");
    if(it.n)el("text",{x:it.px[0],y:it.px[1]+4,"text-anchor":"middle",style:"font:700 12px var(--f-mono);fill:#111"},g).textContent=it.n;
    el("text",{x:it.px[0],y:it.px[1]-19,"text-anchor":"middle",class:"zlabel"},g).textContent=it.label})}
function teamBuilder(){
  const I=IDX(),own=D.own&&I[D.own]?D.own:S.player;
  if(!teamSel)teamSel=own?[own]:[];
  const chips=teamSel.map((id,i)=>`<button type="button" data-rm="${id}" ${i===0?"disabled":""} aria-label="${tl("Remove {name}",{name:esc((I[id]||{}).name||id)})}"><b style="color:${TCOL[i]}">●</b> ${esc((I[id]||{}).name||id)}${i===0?" "+tl("(you)"):" ✕"}</button>`).join("");
  const q=teamQ.toLowerCase(),res=q?D.index.filter(e=>!teamSel.includes(e.steamid)&&!e.minimal&&(e.name.toLowerCase().includes(q)||e.steamid.includes(q))).slice(0,8):[];
  const sug=(teamSug||[]).filter(s=>!teamSel.includes(s.steamid));
  return `<article class="card"><h3>${tl("Build the team")}</h3>
   <p class="note">${tl("You and 1 to 4 teammates already analyzed. To add someone new: paste their Steam link in the search bar at the top, then come back here.")}</p>
   <div class="btns" role="group" aria-label="${tl("Members")}">${chips}</div>
   ${sug.length?`<span class="lbl4" style="color:var(--muted)">${tl("Your frequent teammates")}</span><div class="btns">${sug.map(s=>`<button type="button" data-add="${s.steamid}" ${s.analyzed&&teamSel.length<5?"":"disabled"} title="${s.analyzed?"":tl("Not analyzed yet")}">${esc(s.name)} <span class="note">${tln(s.together,"{n} match together","{n} matches together")}</span></button>`).join("")}</div>`:""}
   <div class="btns" style="align-items:center"><input id="tq" type="search" value="${esc(teamQ)}" placeholder="${tl("Find an analyzed player (name, SteamID)")}" aria-label="${tl("Find a player")}" style="font:14px var(--f-body);background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:3px;padding:6px 10px;min-width:260px"></div>
   ${res.length?`<div class="btns">${res.map(e=>`<button type="button" data-add="${e.steamid}" ${teamSel.length<5?"":"disabled"}>${esc(e.name)}${e.archetype?` <span class="note">${esc(e.archetype)}</span>`:""}</button>`).join("")}</div>`:""}
   <div class="row" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">${D.local?`<button type="button" class="primary" id="tbuild" ${teamSel.length>=2?"":"disabled"}>${tl("Create the team plan")}</button>`:`<span class="note">${tl("Team plans are created in the local app.")}</span>`}<span class="note" id="tmsg" role="status"></span></div>
   ${(teamIdx||[]).length?`<span class="lbl4" style="color:var(--muted)">${tl("Saved plans")}</span><div class="btns">${teamIdx.map(t=>`<button type="button" data-team="${t.id}" aria-pressed="${t.id===teamId}">${t.members.map(m=>esc(m.name)).join(" · ")}</button>`).join("")}</div>`:""}</article>`}
function renderTeam(){
  const v=$("#v-team");
  v.innerHTML=`<div class="head"><div style="display:grid;gap:4px"><span class="eyebrow">${tl("Cross-data of every member, the base and pros")}</span><h2>${tl("Team")}</h2></div></div>${teamBuilder()}<div id="tplan"></div>`;
  const tq=$("#tq",v);tq.oninput=()=>{teamQ=tq.value.trim();const pos=tq.selectionStart;renderTeam();const n=$("#tq");n.focus();n.setSelectionRange(pos,pos)};
  $$("[data-add]",v).forEach(b=>b.onclick=()=>{if(teamSel.length<5&&!teamSel.includes(b.dataset.add))teamSel.push(b.dataset.add);teamQ="";renderTeam()});
  $$("[data-rm]",v).forEach(b=>b.onclick=()=>{teamSel=teamSel.filter(x=>x!==b.dataset.rm);renderTeam()});
  $$("[data-team]",v).forEach(b=>b.onclick=async()=>{try{await loadTeam(b.dataset.team);teamSel=teamPlan.members.map(m=>m.steamid);teamMap=null;renderTeam()}catch(e){$("#tmsg",v).textContent=e.message}});
  const tb=$("#tbuild",v);if(tb)tb.onclick=async()=>{tb.disabled=true;$("#tmsg",v).textContent=tl("Crossing the data…");
    try{const j=await api("/api/team",{sid:teamSel[0],ids:teamSel});await loadTeamIdx(true);await loadTeam(j.id);teamMap=null;renderTeam()}catch(e){$("#tmsg",v).textContent=e.message;tb.disabled=false}};
  if(!teamSug&&D.local&&teamSel[0]){fetch(`/api/team/suggest?sid=${teamSel[0]}`).then(r=>r.json()).then(j=>{teamSug=j;if(S.view==="team")renderTeam()}).catch(()=>{teamSug=[]})}
  if(!teamIdx){loadTeamIdx().then(()=>{if(S.view==="team"&&teamIdx.length)renderTeam()})}
  if(teamPlan)teamPlanView($("#tplan",v));
}
function teamPlanView(host){
  const T=teamPlan,col=Object.fromEntries(T.members.map((m,i)=>[m.steamid,TCOL[i]])),nm=Object.fromEntries(T.members.map(m=>[m.steamid,m.name]));
  const maps=Object.keys(T.plans||{});if(!teamMap||!maps.includes(teamMap))teamMap=maps[0];
  const P=T.plans[teamMap];
  const ind=Object.fromEntries((T.individual||[]).map(x=>[x.steamid,x]));
  const igl=T.igl[0],GREY="#8a96a3",pc=v=>v==null?"—":v+"%",rec=r=>r&&r.n?`${r.won}/${r.n}`:"—";
  const nExtra=5-T.size;
  host.innerHTML=`
  <div class="head" style="border-bottom-width:1px"><div style="display:grid;gap:4px"><span class="eyebrow">${tl("Plan created {date} · {n} players",{date:fmtDate(T.created),n:T.size})}${nExtra?" + "+tln(nExtra,"{n} extra player","{n} extra players"):""}</span>
    <h2>${T.members.map((m,i)=>`<span style="color:${TCOL[i]}">${esc(m.name)}</span>`).join(" · ")}</h2></div></div>
  <div class="tbl"><table><thead><tr><th>${tl("Player")}</th><th>${tl("Profile")}</th><th>${tl("T role")}</th><th>${tl("CT positions")}</th><th>${tl("Individual work")}</th></tr></thead><tbody>
   ${T.members.map((m,i)=>{const x=ind[m.steamid]||{};return `<tr><td><b style="color:${TCOL[i]}">●</b> ${esc(m.name)}${igl&&igl.steamid===m.steamid?` <span class="probadge">${tl("suggested IGL")}</span>`:""}</td>
     <td>${esc(m.archetype||"—")}${m.light?` <span class="note">${tl("(limited data)")}</span>`:""}</td><td><b>${esc(m.t_role_name||"—")}</b></td>
     <td class="wrap">${esc(x.ct_role||"—")}</td><td class="wrap">${(x.priorities||[]).slice(0,2).map(esc).join(" · ")}</td></tr>`}).join("")}
   ${nExtra?`<tr><td><b style="color:${GREY}">●</b> ${tln(nExtra,"Extra player ({n})","Extra players ({n})")}</td><td class="note">${tl("random teammates")}</td><td><b>${T.missing_roles.map(esc).join(", ")}</b></td><td class="wrap note">${tl("the grey positions on each map")}</td><td class="note">${tl("Tell them their spot in the lobby.")}</td></tr>`:""}</tbody></table></div>
  <div class="insights">
   <article class="card"><h3>${tl("Who calls?")}</h3><p>${tl("Suggestion: <b>{name}</b>",{name:esc(igl.name)})}${igl.why.length?` (${igl.why.map(esc).join(", ")})`:""}.</p>
     <p class="note">${tl("Ranking: {list}. Measured on converting advantages, isolated deaths, trades, profile and experience. It's your call: the IGL mostly needs to talk clearly and stay calm.",{list:T.igl.map(x=>`${esc(x.name)} ${x.score}`).join(" · ")})}</p></article>
   <article class="card"><h3>${tl("Your maps")}</h3><p>${tl("Pick in Premier:")} <b>${T.picks.length?T.picks.map(MAPN).join(", "):tl("no pool map with data yet")}</b>${T.to_work.length?" · "+tl("to work on: {maps}",{maps:T.to_work.map(MAPN).join(", ")}):""}.</p>
     <div class="tbl"><table><thead><tr><th>${tl("Map")}</th><th class="n">${tl("Rounds won")}</th><th class="n">${tl("Rounds")}</th>${T.members.map((m,i)=>`<th class="n" style="color:${TCOL[i]}">${esc(m.name.slice(0,10))}</th>`).join("")}</tr></thead><tbody>
      ${T.maps.filter(r=>r.members_with_data&&!/^cs_/.test(r.map)).slice(0,8).map(r=>`<tr><td>${MAPN(r.map)}${r.premier?' <span class="pill">Premier</span>':""}</td><td class="n">${pc(r.round_win)}</td><td class="n">${r.rounds}</td>
        ${r.per_member.map(x=>`<td class="n">${x.win==null?"—":`${x.win}% <span class="note">(${x.rounds})</span>`}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
     <p class="note">${tl("Rounds won by each member on the map (their demos, number of rounds in brackets). Bomb maps only. Since September 22, 2026, each team picks its maps and one of the four is drawn at random.")}</p></article>
  </div>
  ${maps.length?`<h3>${tl("Game plan per map")}</h3>
  <div class="chips" role="group" aria-label="${tl("Map")}">${maps.map(m=>`<button type="button" data-tmap="${m}" aria-pressed="${m===teamMap}">${MAPN(m)}</button>`).join("")}</div>
  <div class="btns side big" role="group" aria-label="${tl("Side")}"><button type="button" data-tside="CT" aria-pressed="${teamSide==="CT"}">CT · ${tl("setup")}</button><button type="button" data-tside="T" aria-pressed="${teamSide==="T"}">T · ${tl("plays")}</button></div>
  <div class="stage">${radarShell((P.levels||[]).length>1?`<div class="btns" role="group" aria-label="${tl("Level")}">${P.levels.map(l=>`<button type="button" data-tlevel="${l.key}" aria-pressed="${l.key===(teamLevel||P.levels[0].key)}">${esc(l.name)}</button>`).join("")}</div>`:"")}
   <div style="display:grid;gap:14px;min-width:0" id="tside"></div></div>
  <div id="tplays"></div>
  <div class="insights" id="tcalls"></div>`:`<div class="empty">${tl("No map in common with detailed data: play a few matches together, then create the plan again.")}</div>`}
  <h3>${tl("Economy and weapons")}</h3>
  <div class="insights"><article class="card"><ul>${T.economy.rules.map(r=>`<li>${esc(r)}</li>`).join("")}</ul>
    <p>${T.economy.awp?tl("AWP: <b>{name}</b>.",{name:esc(T.economy.awp)}):tl("No dedicated AWPer: the AWP is only bought when the team is rich.")} ${T.economy.pistol_openers.length?tln(T.economy.pistol_openers.length,"Pistol rounds: {names} takes the opening duels.","Pistol rounds: {names} take the opening duels.",{names:T.economy.pistol_openers.map(esc).join(", ")}):""}</p>${srcLinks(T.economy.src,true)}</article>
   <article class="card"><h3>${tl("Everyone's force-buy")}</h3><ul>${T.economy.members.map(x=>`<li><b>${esc(x.name)}</b>: ${x.force?`${esc(KIT_L(x.force))}: ${x.force_win!=null?tl("{p}% of {n} force-buy rounds won",{p:x.force_win,n:x.force_n})+", ":""}${tl("{n} damage per round",{n:x.force_adr})}`:tl("not enough force-buy rounds yet (8 needed)")}</li>`).join("")}</ul>
    <p class="note">${tl("Cheap weapons only (SMGs, shotguns, pistols, Galil, FAMAS): an AWP or a full rifle isn't a force-buy.")}</p></article></div>
  ${T.synergy.length?`<h3>${tl("You together")}</h3><div class="tbl"><table><thead><tr><th>${tl("Duo")}</th><th class="n">${tl("Matches together")}</th><th class="n">${tl("Rounds won")}</th><th>${tl("Trades (one avenges the other within 5 s)")}</th></tr></thead><tbody>
   ${T.synergy.map(s=>`<tr><td>${esc(s.name_a)} + ${esc(s.name_b)}</td><td class="n">${s.matches}</td><td class="n">${pc(s.round_win)}</td><td>${tl("{a} avenges {b} {n}×",{a:esc(s.name_a),b:esc(s.name_b),n:s.trades_ab})} · ${tl("{a} avenges {b} {n}×",{a:esc(s.name_b),b:esc(s.name_a),n:s.trades_ba})}</td></tr>`).join("")}</tbody></table></div>`:""}
  ${T.matches.length?`<p class="note">${tln(T.n_matches||T.matches.length,"{n} match with at least 2 members on the same team.","{n} matches with at least 2 members on the same team.")} ${tl("Latest: {list}.",{list:T.matches.slice(0,6).map(x=>`${MAPN(x.map||"?")} ${x.score?`${x.score.me}-${x.score.them}`:""}`).join(" · ")})}</p>`:""}
  ${T.collective.length?`<h3>${tl("Team goals")}</h3><div class="insights">${T.collective.map(c=>`<article class="card"><h3>${esc(c.title)}</h3><p>${esc(c.do)}</p>
    <p class="note">${tl("Team average percentile: {p}",{p:c.avg_percentile})} (${c.members.map(x=>`${esc(x.name)} ${x.percentile}`).join(" · ")}).</p></article>`).join("")}</div>`:""}
  <h3>${tl("Individual work for the team")}</h3>
  <div class="insights">${(T.individual||[]).map(x=>{const i=T.members.findIndex(m=>m.steamid===x.steamid),m=T.members[i];return `<article class="card"><h3 style="color:${TCOL[i]}">${esc(x.name)} · ${esc(x.t_role||"")}</h3>
    <p class="note">${esc(m.t_do||"")}</p><ol>${(x.priorities||[]).map(p=>`<li>${esc(p)}</li>`).join("")}</ol>${x.drill?`<p class="note">${tl("Warm-up: {drill}",{drill:esc(x.drill)})}</p>`:""}</article>`}).join("")}</div>
  ${T.party&&T.party[T.party_key]?`<h3>${esc(T.party[T.party_key].title)}</h3><article class="card"><ul>${T.party[T.party_key].items.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>${srcLinks(T.party[T.party_key].src,true)}</article>`:""}
  ${D.local?`<div class="btns"><button type="button" id="tdel">${tl("Delete this plan")}</button></div>`:""}`;
  $$("[data-tmap]",host).forEach(b=>b.onclick=()=>{teamMap=b.dataset.tmap;teamLevel=null;teamExec=null;teamPlanView(host)});
  $$("[data-tside]",host).forEach(b=>b.onclick=()=>{teamSide=b.dataset.tside;teamLevel=null;teamPlanView(host)});
  $$("[data-tlevel]",host).forEach(b=>b.onclick=()=>{teamLevel=b.dataset.tlevel;teamPlanView(host)});
  const del=$("#tdel",host);if(del)del.onclick=async()=>{if(del.dataset.ok!=="1"){del.dataset.ok="1";del.textContent=tl("Confirm deletion");return}
    try{await api("/api/team/delete",{sid:T.owner,id:T.id});teamPlan=null;teamId=null;await loadTeamIdx(true);renderTeam()}catch(e){}};
  if(!P)return;
  const TH=P.threats,s=x=>x==null?"—":x+" s",sites=P.site_px||{};
  const plays=P.t_plays||[];if(!teamExec||!plays.some(p=>p.key===teamExec))teamExec=plays[0]?plays[0].key:null;
  const PL=plays.find(p=>p.key===teamExec);
  const who=(sid,x)=>sid?col[sid]:GREY,dotN=x=>x.extra?(typeof x.extra==="number"?x.extra:""):"";
  const siteItems=L=>sites[L]?[{kind:"site",px:sites[L],level:TH&&TH.geo_sites&&TH.geo_sites[L]?TH.geo_sites[L].level:null,
    label:TH?`${L} · ${tl("{p}% of attacks",{p:TH.sites[L].odds})}${TH.sites[L].rush?" · "+tl("rush {p}%",{p:TH.sites[L].rush}):""}`:L}]:[];
  let items=[];
  if(teamSide==="CT"){
    if(TH)["A","B"].forEach(L=>{items.push(...siteItems(L));TH.sites[L].lanes.forEach(ln=>items.push({kind:"lane",px:ln.px,to:sites[L],level:ln.level,w:2+ln.odds/5,label:`${ln.name.split(" / ")[0]} ${ln.odds}%`,
      title:`${ln.name} → ${L}: ${tl("used in {p}% of the attacks",{p:ln.odds})}${ln.rush?", "+tl("{p}% of them rushes",{p:ln.rush}):""}`}))});
    P.ct.forEach(sl=>{items.push({kind:"dot",px:sl.px,level:sl.level,color:who(sl.member),n:sl.member?"":sl.extra,ring:sl.yours,label:sl.member?nm[sl.member]:tl("Extra {n}",{n:sl.extra}),title:`${sl.label} · ${sl.zone}`});
      (sl.nades||[]).filter(n=>n.from_px&&n.to_px).slice(0,sl.member?3:1).forEach(n=>items.push({kind:"nade",type:n.type,px:n.from_px,to:n.to_px,level:n.level,color:who(sl.member),short:{smoke:"S",flash:"F",molotov:"M",he:"H"}[n.type],title:`${TYPE[n.type]} ${n.from} → ${n.to}`}))});
  }else if(PL){
    items.push(...siteItems(PL.site));
    PL.lanes.forEach((ln,i)=>items.push({kind:"lane",px:ln.px,to:PL.site_px,level:ln.level,w:i?5:8,label:ln.name}));
    const at={};PL.roles.forEach(r=>{if(!r.lane||!r.lane.px)return;const k=r.lane.px.join(),j=at[k]=(at[k]||0)+1;
      if(r.lane.lurk)items.push({kind:"lane",px:r.lane.px,to:sites[PL.site==="A"?"B":"A"],level:r.lane.level,w:3,dash:true,label:tl("lurk")});
      items.push({kind:"dot",px:[r.lane.px[0]+((j-1)%3-1)*26,r.lane.px[1]+28+Math.floor((j-1)/3)*26],level:r.lane.level,color:who(r.member),n:r.extra?r.name.replace(/\D/g,""):"",label:r.extra?"":r.name,title:`${r.name}: ${r.role_name}`})});
    PL.nades.filter(n=>n.from_px&&n.to_px).forEach(n=>items.push({kind:"nade",type:n.type,px:n.from_px,to:n.to_px,level:n.level,color:who(n.member),short:{smoke:"S",flash:"F",molotov:"M",he:"H"}[n.type],title:`${TYPE[n.type]} ${n.from} → ${n.to}: ${n.name}`}));
  }
  const cnt={};items.filter(x=>x.kind==="dot"||x.kind==="nade").map(x=>x.level).filter(Boolean).forEach(l=>cnt[l]=(cnt[l]||0)+1);
  const busiest=Object.keys(cnt).sort((a,b)=>cnt[b]-cnt[a])[0];
  const level=teamLevel||busiest||(P.levels&&P.levels[0]?P.levels[0].key:null);
  $$("[data-tlevel]",host).forEach(b=>{b.setAttribute("aria-pressed",b.dataset.tlevel===level);if(cnt[b.dataset.tlevel])b.textContent=`${b.textContent.replace(/ \(\d+\)$/,"")} (${cnt[b.dataset.tlevel]})`});
  const box=$(".radar-box",host),side=$("#tside",host);
  teamRadarDraw(box,teamMap,level,items);
  const nadeLi=n=>`<li><b>${TYPE[n.type]}</b> ${esc(n.from)} → ${esc(nTo(n,teamMap))}${n.role?` <span class="pill">${{anti_rush:tl("anti-rush"),block:tl("blocks the lane"),flash:tl("flash"),damage:tl("damage")}[n.role]||esc(n.role)}</span>`:""}${n.timer?` <span class="note">${tl("around {t}",{t:esc(n.timer)})}</span>`:""}${n.yours?` <span class="pill strong">${tl("yours")}</span>`:""}${n.setpos?` <span class="cmd"><code hidden>${esc(n.setpos)}</code><button type="button" title="${esc(n.setpos)}">${tl("Copy setpos")}</button></span>`:""}</li>`;
  if(teamSide==="CT"){
    $(".caption",box).innerHTML=`<span>${tl("Red arrows: where the Ts of the base attack from (share of the attacks). Discs: the setup, a ring when it's the player's own strong spot; grey numbers are extra players. Squares: their grenades.")}</span>`;
    const heavy=P.heavy_site,two=P.ct.filter(sl=>sl.site===heavy).length;
    side.innerHTML=`${TH?`<div class="tread">${tl("<b>Where the Ts attack</b> ({n} rounds of the base):",{n:TH.rounds})} ${["A","B"].map(L=>`<b>${L}</b> ${TH.sites[L].odds}%${TH.sites[L].rush?` (${tl("rush {p}%",{p:TH.sites[L].rush})})`:""}`).join(" · ")}.
       ${two>=2?tl("{n} players on {site}, the most attacked site.",{n:two,site:heavy}):""}</div>`:""}
      <ul class="pl-list">${P.ct.map(sl=>`<li style="border-left-color:${who(sl.member)}"><b>${esc(sl.label)} · ${esc(sl.zone)}</b>: ${sl.member?`<b>${esc(sl.name)}</b>`:`<b>${tl("extra player {n}",{n:sl.extra})}</b>`}${sl.why&&sl.why.length?` (${sl.why.map(esc).join(", ")})`:""}.
       ${sl.lane?`<br>${tl("Faces <b>{lane}</b>: {p}% of the attacks",{lane:esc(sl.lane.name),p:sl.lane.odds})}${sl.lane.rush?", "+tl("{p}% of them rushes",{p:sl.lane.rush}):""}.`:""}
       ${sl.nades&&sl.nades.length?`<ul class="nlist">${sl.nades.slice(0,sl.member?3:2).map(nadeLi).join("")}</ul>`:""}
       <span class="note">${esc(sl.do)}${sl.base?" "+tl("Base CTs on this spot: {rec} in duels.",{rec:esc(sl.base)}):""}${sl.base_zone?" "+tl("(The base plays {zone} instead.)",{zone:esc(sl.base_zone)}):""}${sl.t_med?" "+tl("First duel around {t}.",{t:clock(sl.t_med)}):""}</span></li>`).join("")}</ul>
      ${P.rotations.length?`<span class="lbl4" style="color:var(--muted)">${tl("Rotations once the bomb is down on the other site")}</span><ul>${P.rotations.map(r=>`<li>${tl("<b>{name}</b> to {site}: {route}",{name:esc(r.name),site:r.to,route:esc(r.route)})} (${s(r.travel)}, ${tl("{p}% die on the way",{p:r.died})}, ${r.who==="pro"?tl("{n} pro rotations",{n:r.n}):tl("{n} base rotations",{n:r.n})})</li>`).join("")}</ul>`:""}`;
  }else{
    $(".caption",box).innerHTML=`<span>${PL?`${esc(PL.label)}: ${tl("thick arrow = main lane, thin = second lane, dashed = the lurker's. Squares: the grenades (S smoke, F flash, M molotov).")}`:tl("No play with enough rounds in the base on this map.")}</span>`;
    side.innerHTML=PL?`<div class="btns" role="group" aria-label="${tl("Play")}">${plays.map(p=>`<button type="button" data-texec="${p.key}" aria-pressed="${p.key===teamExec}">${esc(p.label)}</button>`).join("")}</div>
      <div class="tread">${tl("In the base: <b>{p}%</b> of rounds won by the Ts over {n} rounds",{p:PL.t_win,n:PL.n})}${TH.t_avg!=null?" "+tl("(map average {p}%)",{p:TH.t_avg}):""}${PL.hit_t!=null?", "+tl("site taken around {t}",{t:clock(PL.hit_t)}):""}. ${PL.team_t&&PL.team_t.n?tln(PL.team_t.n,"You ran it {n} time together: {w} won.","You ran it {n} times together: {w} won.",{w:PL.team_t.won}):tl("You haven't run it together yet.")}</div>
      <ul class="pl-list">${PL.roles.map(r=>`<li style="border-left-color:${who(r.member)}"><b>${esc(r.name)} · ${esc(r.role_name)}</b>${r.lane?` · ${esc(r.lane.name)}`:""}<br><span class="note">${esc(r.do)}</span></li>`).join("")}</ul>
      ${PL.nades.length?`<span class="lbl4" style="color:var(--muted)">${tl("Utility")}</span><div class="lineups">${PL.nades.map(it=>`<article class="lu" data-type="${it.type}" style="cursor:default"><div class="top"><span class="ty">${TYPE[it.type]} · ${esc(it.name)}</span><span class="pill ${it.known?"strong":""}">${it.known?tl("already thrown"):tl("to learn")}</span></div>
        <div class="route">${esc(it.from)} → ${esc(nTo(it,teamMap))}${it.lane?` <span class="note">(${esc(it.lane)})</span>`:""}</div><div class="meta">${esc(HOWL(it.how||""))}${it.t!=null?" · "+tl("around {t}",{t:clock(it.t)}):""} · ${tl("{n} throws in the base",{n:it.uses})}</div>
        ${it.setpos?`<div class="cmd"><code>${esc(it.setpos)}</code><button type="button">${tl("Copy")}</button></div>`:""}</article>`).join("")}</div>`:`<p class="note">${tl("Not enough grenades observed toward this site in the base.")}</p>`}`
      :`<p class="note">${tl("Not enough rounds of the base on this map to suggest plays.")}</p>`;
    $$("[data-texec]",side).forEach(b=>b.onclick=()=>{teamExec=b.dataset.texec;teamLevel=null;teamPlanView(host)});
  }
  copyBtn(side);
  // every play of the base, with the team's own rounds on both sides
  $("#tplays",host).innerHTML=TH&&TH.plays.length?`<h3>${tl("Plays of the base on {map}, and how you did",{map:MAPN(teamMap)})}</h3><div class="tbl"><table><thead><tr><th>${tl("Play")}</th><th class="n">${tl("Rounds of the base")}</th><th class="n">${tl("T win")}</th><th class="n">${tl("Site taken")}</th><th class="n">${tl("You as T (won)")}</th><th class="n">${tl("You as CT, against it (won)")}</th></tr></thead><tbody>
    ${TH.plays.map(p=>`<tr><td>${esc(p.label)}</td><td class="n">${p.odds}% <span class="note">(${p.n})</span></td><td class="n">${p.t_win}%</td><td class="n">${s(p.hit_t)}</td><td class="n">${rec(p.team_t)}</td><td class="n">${rec(p.team_ct)}</td></tr>`).join("")}</tbody></table></div>
    <p class="note">${tl("Plays learned from the paths of the Ts (lanes: the ways in each site). \"You\" counts the rounds where at least two of you were in the same team.")}</p>`:"";
  const V=P.vocab||[];
  $("#tcalls",host).innerHTML=`<article class="card"><h3>${tl("Shared vocabulary")}</h3><p class="note">${tl("The callouts used on FACEIT and by pros, grouped by area.")}</p>
    ${V.map(g=>`<p><b>${esc(g.title)}</b>: ${g.zones.map(esc).join(", ")}</p>`).join("")}</article>
   <article class="card"><h3>${tl("Everyone's calls")}</h3><ul>
    <li>${tl("<b>Entry, anchor</b>: \"how many, where, which grenades\": \"3 B, flash, molotov on box\".")}</li>
    <li>${tl("<b>Lurker</b>: the rotations heard: \"one CT through connector, B is light\".")}</li>
    <li>${tl("<b>AWPer</b>: \"pick mid\" or \"AWP repositioned\", never the same angle twice.")}</li>
    <li>${tl("<b>IGL</b>: the plan during buy time, the adjustment at 1:00, the call to save.")}</li>
    <li>${tl("<b>Dead</b>: one useful piece of info, then silence.")}</li></ul></article>
   <article class="card"><h3>${tl("Triggers as {side}",{side:teamSide})}</h3><ul>${(T.playbook||[]).filter(x=>x.side===teamSide||isBoth(x)).slice(0,5).map(x=>`<li><b>${tl("If {what}",{what:esc(lc(x.if))})}</b> → ${esc(x.then)}</li>`).join("")}</ul>${P.videos&&P.videos.length?`<p class="note"></p>${srcLinks(P.videos,true,tl("Videos on {map}:",{map:MAPN(teamMap)}))}`:""}</article>`;
}
