
// ---------- view: review (after the session, or the next day) ----------
// its four numbers only when one of them exists (03/11, the interface's review: four "—" for a match not analyzed yet, its
// note above already saying so)
function callsBlock(PL){const C=PL.calls||[];if(!C.length)return D.local&&P()&&P().steamid===D.own?`<h3>${tl("Your calls")}</h3><p class="note">${tl("No recording yet: turn on \"Your calls\" in <a href=\"#settings\" style=\"color:var(--ct)\">Settings</a>, play, and I analyze your communication after the match.")}</p>`:"";
  const a=C[0],pct=(x,n)=>n?Math.round(100*x/n)+"%":"—";
  // each number once (07/10): its advice in its own tile, the other advice below
  // tip_k: each tip's English (the tips themselves may be translated, 13/10); an older analysis: the tips are English
  const TK=a.tip_k||a.tips||[],TIP_RX=[/deaths out of/,/say where AND how many/,/grenades called out of/,/teammate clutch/],tipFor=(rx,t)=>TK.some(x=>rx.test(x))?`<em class="gtip">${esc(t)}</em>`:"";
  const rest=(a.tips||[]).filter((x,i)=>{const k=TK[i]||x;return !TIP_RX.some(rx=>rx.test(k))&&!/^Your calls are clean/.test(k)});
  const sp=(a.speech_s||0)<60?`${Math.round(a.speech_s||0)} s`:tl("{n} min",{n:Math.round(a.speech_s/60)});
  return `<h3>${tl("Your calls")}</h3>
   <p class="note">${a.map?MAPN(a.map):tl("Match")} · ${fmtDate(a.start)} · ${tln(a.utterances,"{n} phrase, {t} of speech","{n} phrases, {t} of speech",{t:sp})}${a.match?"":" · "+tl("match not analyzed yet: update your profile")}${a.aligned?"":" · "+tl("without game detection, calls aren't lined up with rounds")}.</p>
   ${(a.deaths||a.info||a.throws||a.clutch_talk_rounds)?`<div class="gauge">
    <div><b>${a.deaths?pct(a.deaths-a.silent_deaths,a.deaths):"—"}</b><span>${tl("of your deaths preceded by a call (10 s before)")}${a.deaths?" · "+tl("{a} of {b} without",{a:a.silent_deaths,b:a.deaths}):""}</span>${tipFor(/deaths out of/,tl("Call what you see before taking the duel, not after."))}</div>
    <div><b>${a.info?a.complete_share+"%":"—"}</b><span>${tl("of your calls say where and how many")}</span>${tipFor(/say where AND how many/,tl("'Two B, one tagged for 80' rather than 'they're B'."))}</div>
    <div><b>${a.throws?pct(a.announced,a.throws):"—"}</b><span>${tl("of your grenades called")}${a.throws?" · "+tl("{a} of {b}",{a:a.announced,b:a.throws}):""}</span>${tipFor(/grenades called out of/,tl("Say 'flash' before throwing it: your teammates turn away."))}</div>
    <div><b>${a.clutch_talk_rounds}</b><span>${tln(a.clutch_talk_rounds,"teammate clutch where you talked","teammate clutches where you talked")}</span>${tipFor(/teammate clutch/,tl("One useful piece of info, then silence."))}</div></div>`:""}
   ${rest.length?`<ul class="pl-list">${rest.map(t=>`<li class="coach">${esc(t)}</li>`).join("")}</ul>`:""}
   ${a.examples.length?`<p class="note">${tl("Your best calls: {list}",{list:a.examples.map(x=>"“"+esc(x)+"”").join(" · ")})}</p>`:""}
   ${teamCallsBlock(C)}
   `}
// after your team's calls naming a place (your team's sound, recorded when every teammate agreed): where you went
function teamCallsBlock(C){const T=C.filter(a=>a.team_calls&&a.team_calls.calls);if(!T.length)return "";
  const S=k=>T.reduce((s,a)=>s+(a.team_calls[k]||0),0),n=S("calls"),pc=x=>n?Math.round(100*x/n)+"%":"—",t=T[0].team_calls;
  const W={toward:tl("went toward it"),away:tl("went the other way"),stayed:tl("stayed"),there:tl("already there"),died:tl("died")};
  return `<h3>${tl("After your team's calls")} ${itip(tln(T.length,"Your teammates' calls that name a place ({c}, in {n} match where they agreed to be recorded), and where you went in the next 8 seconds.","Your teammates' calls that name a place ({c}, in {n} matches where they agreed to be recorded), and where you went in the next 8 seconds.",{c:n}))}</h3>
   <div class="gauge"><div><b>${pc(S("toward"))}</b><span>${tl("you went toward the place called")}</span></div><div><b>${pc(S("stayed"))}</b><span>${tl("you stayed where you were")}</span></div>
    <div><b>${pc(S("away"))}</b><span>${tl("you went the other way")}</span></div><div><b>${t.react_s!=null?t.react_s+" s":"—"}</b><span>${tl("from their call to your move")}</span></div></div>
   <details><summary style="cursor:pointer">${tl("Call by call, {match}",{match:T[0].map?MAPN(T[0].map):tl("last match")})}</summary><div class="tbl" style="margin-top:8px"><table><thead><tr><th class="n">${tl("Round")}</th><th class="n">${tl("Time")}</th><th>${tl("Your team said")}</th><th>${tl("You")}</th></tr></thead><tbody>
     ${t.list.map(x=>`<tr><td class="n">${x.round}</td><td class="n">${Math.round(x.t)} s</td><td class="wrap">“${esc(x.text)}”</td><td>${W[x.went]||esc(x.went)}${x.react!=null?` <span class="note">${tl("after {n} s",{n:x.react})}</span>`:""}</td></tr>`).join("")}</tbody></table></div></details>`}
// what the demos say about the frustrations of the game: blocks both ways, how your flashes are played, team flashes,
// and the enemies whose kills look odd or who got banned (indicators, not proof)
function factsBlock(PL){const F=PL.facts;if(!F||!F.matches)return "";const fy=F.flashes.yours,pm=x=>(x/F.matches).toFixed(1),pc=(x,n)=>n?Math.round(100*x/n)+"%":"—";
  const bar=parts=>`<div class="fbar">${parts.filter(x=>x.v>0).map(x=>`<i style="flex:${x.v};background:${x.c}"><title>${esc(x.l)}: ${x.v}</title></i>`).join("")}</div>`;
  return `<h3>${tln(F.matches,"What the demos say · your last match","What the demos say · your last {n} matches")}</h3>
   <div class="gauge">
    <div><b>${pm(F.blocks.by_n)} <small>vs ${pm(F.blocks.on_n)}</small></b><span>${tl("blocks per match: a teammate blocks you vs you block a teammate")}${F.blocks.by.length?` (${tl("most: {names}",{names:F.blocks.by.slice(0,2).map(x=>esc(x.name)).join(", ")})})`:""}</span></div>
    <div><b>${pc(fy.mate_used,fy.n)}</b><span>${tl("of your flashes that blind ({n}): a teammate shoots behind within 2.5 s",{n:fy.n})}</span></div>
    <div><b>${pc(fy.mate_early,fy.n)}</b><span>${tl("a teammate peeked and got hit before your flash popped")}</span></div>
    <div><b>${pm(F.teamflash.by_n)} <small>vs ${pm(F.teamflash.on_n)}</small></b><span>${tl("team flashes per match: on you vs by you")}</span></div></div>
   ${fy.n?`${bar([{v:fy.mate_used,c:"var(--good)",l:tl("a teammate shot behind")},{v:fy.self_used,c:"var(--ct)",l:tl("only you shot")},{v:fy.unused,c:"var(--muted)",l:tl("nobody shot")}])}
   <div class="vleg"><span><i style="background:var(--good)"></i>${tl("a teammate shoots behind")}</span><span><i style="background:var(--ct)"></i>${tl("only you")}</span><span><i style="background:var(--muted)"></i>${tl("nobody: say \"flash\" before throwing")}</span></div>`:""}
   `}
// the review as plan.py builds it; a plan written in the "pro review" format (quick_brief, map_briefs, deep_dive) keeps it
// whole under raw (04/10: a plan written by a server still running that format crashed this page)
const reviewOf=PL=>{const R=PL.review;return R&&!R.session&&R.raw&&R.raw.session?R.raw:R&&R.session?R:null};
// HLTV's rating colors: under 0.85, 0.85-0.95, 0.95-1.05, 1.05-1.20, over 1.20
const rtCls=r=>r==null?"":r>=1.2?"rt-elite":r>=1.05?"rt-good":r>=.95?"rt-avg":r>=.85?"rt-low":"rt-bad";
const rtBadge=r=>r==null?`<span class="note">—</span>`:`<span class="rt ${rtCls(r)}">${(+r).toFixed(2)}</span>`;
// the rating match by match: a dot per match (green won, red lost), the session's bright on a band, the line at 1.00.
// 13/10, the user: "get few data on dot hover (map, result, rating, adr)": over each dot a target bigger than the dot
// (hover, or focus: a tap on a phone, the keyboard) shows its match's map, date, result and score, rating and ADR; a
// click opens that match (on a touchscreen the first tap shows the card, the second opens it)
// a loss a ring, a win a dot (03/11, the interface's review: the result was told by its color alone)
function ratingSpark(T){if(!T||T.length<2)return "";const W=640,H=120,pad=12,rs=T.map(x=>x.rating),lo=Math.min(.4,...rs),hi=Math.max(1.8,...rs);
  const X=i=>pad+i*(W-2*pad)/(T.length-1),Y=r=>H-pad-(r-lo)/(hi-lo)*(H-2*pad),first=T.findIndex(x=>x.recent),bx=first>0?(X(first-1)+X(first))/2:pad;
  const RES={win:tl("Win"),loss:tl("Loss"),draw:tl("Draw")};
  const tip=x=>{const sc=x.score&&x.score.me!=null?` ${x.score.me}-${x.score.them}`:"";
    return `<b>${esc(MAPN(x.map))}</b> · ${esc(fmtDate(x.time))}<br><span class="res ${x.result}">${esc(RES[x.result]||x.result||"")}${sc}</span> · ${tl("Rating")} ${rtBadge(x.rating)}${x.adr!=null?` · ADR <b>${(+x.adr).toFixed(1)}</b>`:""}${x.id?`<br><span class="note">${tl("Open this match")} ↗</span>`:""}`};
  const lbl=x=>`${MAPN(x.map)}, ${fmtDate(x.time)}, ${RES[x.result]||x.result||""}${x.score&&x.score.me!=null?` ${x.score.me}-${x.score.them}`:""}, ${tl("Rating")} ${x.rating}${x.adr!=null?`, ADR ${(+x.adr).toFixed(1)}`:""}`;
  return `<div class="spark-w"><svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="${tl("Rating match by match")}">
   <rect x="${bx}" y="0" width="${W-bx}" height="${H}" rx="6" fill="var(--ct)" opacity=".08"/>
   <line x1="${pad}" x2="${W-pad}" y1="${Y(1)}" y2="${Y(1)}" stroke="var(--muted)" stroke-dasharray="4 4" opacity=".55"/>
   <text x="${pad}" y="${Y(1)-5}" class="vct">1.00</text>
   <polyline points="${T.map((x,i)=>`${X(i).toFixed(1)},${Y(x.rating).toFixed(1)}`).join(" ")}" fill="none" stroke="var(--ink)" stroke-opacity=".3" stroke-width="1.5"/>
   ${T.map((x,i)=>`<circle cx="${X(i).toFixed(1)}" cy="${Y(x.rating).toFixed(1)}" r="${x.recent?5:3.2}" fill="${x.result==="win"?"var(--good)":x.result==="loss"?"var(--panel)":"var(--muted)"}"${x.result==="loss"?` stroke="var(--bad)" stroke-width="2"`:""} opacity="${x.recent?1:.45}"/>`).join("")}</svg>
   ${T.map((x,i)=>{const px=X(i)/W,py=Y(x.rating)/H;
     return `<button type="button" class="sp-dot${px<.2?" l":px>.8?" r":""}${py<.45?" b":""}"${x.id?` data-dmid="${esc(x.id)}"`:""} style="left:${(px*100).toFixed(2)}%;top:${(py*100).toFixed(2)}%" aria-label="${esc(lbl(x))}"><span class="sp-tip" aria-hidden="true">${tip(x)}</span></button>`}).join("")}</div>`}
// 1 · the session (07/10, the user: "évite les répétitions d'informations, de data, regroupe si plusieurs data parlent
// de la même chose"): each change and each analyst read once, in what works or what slips, its evidence folded under
// it (the reasons, the rounds, the base and the pros); the focus once; no "what changed" or "analyst reads" again below
function reviewBrief(R,f){const T=R.trend||[],rec=T.filter(x=>x.recent),bef=T.filter(x=>!x.recent),avg=a=>a.length?a.reduce((s,x)=>s+x.rating,0)/a.length:null;
  const ra=avg(rec),rb=avg(bef),M=R.maps||[],ng=M.reduce((s,m)=>s+m.games,0),adr=ng?M.reduce((s,m)=>s+m.adr*m.games,0)/ng:null,PI=(R.pro||{}).items||[];
  const RM=readsOf().meta||{},rdT=i=>i.title||(i.id==="spot"?tl("Deaths at {place} ({map})",{place:i.place,map:MAPN(i.map)}):(RM[i.id]||{}).title||i.id);
  const chg=c=>{const clear=c.level==="clear"||c.level==="net";
    return `<details class="bitem"><summary>${esc(c.label)}: ${f(c.before,c.unit)} → <b class="${c.better?"good":"bad"}">${f(c.after,c.unit)}</b> <span class="lvl ${clear?"clear":"trend"}">${clear?tl("clear gap"):tl("trend")}</span></summary>
     <p class="note">${c.better?tl("Improving over {period} against the {n} matches before.",{period:esc(R.label),n:c.n_before}):tl("Slipping over {period} against the {n} matches before.",{period:esc(R.label),n:c.n_before})}</p>
     ${(c.why||[]).length?`<p class="mini">${tl("Possible reasons, to check over the next matches:")}</p><ul class="why">${c.why.map(w=>`<li>${esc(w)}</li>`).join("")}</ul>`
       :`<p class="note">${c.better?tl("No single cause in your data: keep doing what you did in these games."):tl("No obvious explanation in your data: keep an eye on it.")}</p>`}</details>`};
  const rd=i=>`<details class="bitem"><summary>${esc(rdT(i))} <span class="note">${i.pct!=null?`<b>${i.pct}%</b> · `:""}${tl("{a} of {b}",{a:i.value,b:i.of})}</span></summary>
     ${i.ref!==undefined||i.id==="spot"?readCard(i,RM,P().advice.bench):`<p>${esc(i.detail||"")}</p>`}</details>`;
  const works=[...R.changes.filter(c=>c.better).map(chg),...PI.filter(i=>i.severity==="positive").map(rd)];
  const watch=[...R.changes.filter(c=>!c.better).map(chg),...PI.filter(i=>i.severity!=="positive").map(rd)];
  const n=(R.pro||{}).matches;
  const how=`${n?tln(n,"An item opens its evidence: the reasons, the rounds (one opens it in the 2D replay), you against the base and the pros ({n} demo read).","An item opens its evidence: the reasons, the rounds (one opens it in the 2D replay), you against the base and the pros ({n} demos read)."):""}${R.stable.length?`<br><strong>${tl("Stable:")}</strong> ${R.stable.map(esc).join(" · ")}.`:""}`;
  const games=tln(R.session.games,"{n} game","{n} games");
  return `<section class="tier" id="tier1"><div class="tier-h"><b>1</b><h3>${esc(PER_NAME[R.period]||tl("The session"))}</h3><span class="note">${bef.length?tl("{games}, against your {n} matches before",{games,n:bef.length}):games}</span>${itip(how)}</div>
   <div class="brief">
    <div class="tiles">
     <div class="tile"><span class="eyebrow">${tl("Record")}</span><b class="num big">${R.session.wins}-${R.session.losses}</b><span class="note">${games}</span></div>
     <div class="tile"><span class="eyebrow">${tl("Rating")}</span><b class="big">${rtBadge(ra)}</b><span class="note">${rb!=null&&ra!=null?`<span class="${ra>=rb?"good":"bad"}">${ra>=rb?"+":"−"}${Math.abs(ra-rb).toFixed(2)}</span> ${tl("vs {r} before",{r:rb.toFixed(2)})}`:""}</span></div>
     <div class="tile"><span class="eyebrow">ADR</span><b class="num big">${adr==null?"—":adr.toFixed(1)}</b><span class="note">${tl("damage per round")}</span></div>
     <div class="tile"><span class="eyebrow">${tl("Maps")}</span><b class="num big">${M.length}</b><span class="note">${M.map(m=>esc(MAPN(m.map))).join(" · ")}</span></div>
    </div>
    <div class="spark-box">${itip(R.period&&R.period!=="session"?tl("Your rating match by match: this period on the band, the {n} matches before dimmed. Green won, red lost.",{n:bef.length}):tl("Your rating match by match: this session on the band, the {n} matches before dimmed. Green won, red lost.",{n:bef.length}),true)}${ratingSpark(T)}</div>
   </div>
   <div class="brief3 brief2">
    <article class="card b-good"><span class="eyebrow">${tl("What works")}</span>${works.length?`<div class="blist">${works.join("")}</div>`:`<p class="note">${tl("Nothing stands out above your usual level.")}</p>`}</article>
    <article class="card b-bad"><span class="eyebrow">${tl("Watch out")}</span>${watch.length?`<div class="blist">${watch.join("")}</div>`:`<p class="note">${tl("Nothing slips: your numbers hold.")}</p>`}</article>
   </div>
</section>`}
// 2 · map by map: each map of the session, with its matches (one opens it)
// the maps' order (07/10, the user: "order by rating et mets des paramètres de sorting"): rating first; the active key
// clicked again turns the order over
const MSORT=[["rating",tl("Rating"),m=>m.rating??-1],["games",tl("Games"),m=>m.games||0],["win",tl("Win %"),m=>(m.wins+m.losses)?m.wins/(m.wins+m.losses):-1],["adr","ADR",m=>m.adr??-1]];
function reviewMaps(R){if(!(R.maps||[]).length)return "";const ms=R.session.matches||[];
  const so=store("mapsort")||{k:"rating",up:false},S_=MSORT.find(x=>x[0]===so.k)||MSORT[0],M=[...R.maps].sort((a,b)=>(so.up?1:-1)*(S_[2](a)-S_[2](b)));
  const sortBtns=`<div class="btns msort" role="group" aria-label="${tl("Sort the maps")}"><span class="note">${tl("Sort")}</span>${MSORT.map(([k,t])=>`<button type="button" data-msort="${k}" aria-pressed="${k===S_[0]}" title="${k===S_[0]?tl("Click again to reverse"):tl("Sort by {what}",{what:t.toLowerCase()})}">${t}${k===S_[0]?(so.up?" ↑":" ↓"):""}</button>`).join("")}</div>`;
  const side=(m,s)=>{const x=m.sides[s],pc=x.of?Math.round(100*x.won/x.of):null;
    return `<div class="mc-side"><span class="side-tag ${s}">${s}</span><div class="mc-bar"><i style="width:${pc||0}%;background:var(--${s==="T"?"t":"ct"})"></i></div><b class="num">${pc==null?"—":pc+"%"}</b><span class="note">${tl("{a}/{b} rounds",{a:x.won,b:x.of})}</span></div>`};   // 07/10: the zones to play or avoid are all-time (Profile, Maps): not repeated here
  return `<section class="tier" id="tier2"><div class="tier-h"><b>2</b><h3>${tl("Map by map")}</h3>${itip(tl("Each map of the period: its record, rating and damage, the rounds won per side, its matches (one opens it). The zones to play or avoid there are in your Profile's map cards."))}${sortBtns}</div>
   <div class="mapcards">${M.map(m=>`<article class="mapcard"><div class="mc-h"><b>${esc(MAPN(m.map))}</b><span class="res ${m.wins>m.losses?"win":m.wins<m.losses?"loss":"draw"}">${m.wins}-${m.losses}</span>
     ${rtBadge(m.rating)}<span class="note num">ADR ${m.adr}</span></div>${side(m,"T")}${side(m,"CT")}
     <div class="mc-matches">${(xs=>xs.slice(-6).reverse().map(x=>`<button type="button" class="mc-m" data-mid="${x.id}" title="${tl("Open this match")}"><span>${esc(fmtDate(x.time))}</span><span class="res ${x.result}">${x.score.me}-${x.score.them}</span>${rtBadge(x.rating)}</button>`).join("")+(xs.length>6?`<span class="note">${tl("+{n} earlier",{n:xs.length-6})}</span>`:""))(ms.filter(x=>x.map===m.map))}</div></article>`).join("")}</div></section>`}
// the window of the Review (07/10, the user: "la dernière session exactement comme tu fais, mais un bouton pour changer
// en last 7 days, this week, this month"): the last session first, the others computed with the plan (review_periods)
const PER=[["session",tl("Last session")],["7d",tl("Last 7 days")],["week",tl("This week")],["month",tl("This month")],["30d",tl("Last 30 days")],["all",tl("All")]],
  PER_NAME={session:tl("The session"),"7d":tl("The last 7 days"),week:tl("This week"),month:tl("This month"),"30d":tl("The last 30 days"),all:tl("All your matches")};
function renderReview(){const p=P(),v=$("#v-review"),PL=p.advice.plan||{},RP=PL.review_periods||{};
  let per=store("revper")||"session";if(per!=="session"&&!RP[per])per="session";
  const R=per==="session"?reviewOf(PL):RP[per];
  const pick=Object.keys(RP).length?`<div class="btns per-pick" role="group" aria-label="${tl("Period")}">${PER.map(([k,t])=>{const ok=k==="session"?!!reviewOf(PL):!!RP[k];
    return `<button type="button" data-per="${k}" aria-pressed="${k===per}" ${ok?"":`disabled title="${tl("Fewer than 2 analyzed matches in it")}"`}>${t}</button>`}).join("")}</div>`:"";
  const head=`<div class="head"><div style="display:grid;gap:4px"><span class="eyebrow">${esc(p.name)}${R?" · "+(R.n_before?tl("{period}, compared with your previous {n} matches",{period:esc(R.label),n:R.n_before}):esc(R.label)):""}</span><h2>${tl("Review")}</h2></div>${pick}</div>`;
  if(!R){v.innerHTML=head+`<div class="empty">${tl("The review compares your latest matches with the previous ones: it takes at least 3 matches analyzed with their demo.")}${p.light?" "+tl("This profile has no demo yet."):""}</div>`;return}
  const f=(x,u)=>fmtU(x,u);
  const comms=callsBlock(PL),facts=factsBlock(PL);   // 07/10: no suspects table, no live check (the user: "enlève ça")
  v.innerHTML=head+`
   ${reviewBrief(R,f)}
   ${reviewMaps(R)}
   ${comms?`<section class="tier" id="tier3"><div class="tier-h"><b>3</b><h3>${tl("Your comms")}</h3>${itip(tl("Your calls, from your microphone's recordings, lined up with the rounds."))}</div>${comms}</section>`:""}
   ${facts?`<section class="tier" id="tier4"><div class="tier-h"><b>${comms?4:3}</b><h3>${tl("Teamplay")}</h3>${itip(tl("Blocks, flashes and team flashes, from the demos of your last matches."))}</div>${facts}</section>`:""}
`;
  $$("[data-per]",v).forEach(b=>b.onclick=()=>{store("revper",b.dataset.per);renderReview();syncUrl()});   // ?period= in the address
  $$("[data-msort]",v).forEach(b=>b.onclick=()=>{const k=b.dataset.msort,o=store("mapsort")||{k:"rating",up:false};store("mapsort",{k,up:o.k===k?!o.up:false});
    const y=$("#tier2",v)?$("#tier2",v).getBoundingClientRect().top:null;renderReview();const t2=$("#tier2",v);if(t2&&y!=null)window.scrollBy(0,t2.getBoundingClientRect().top-y)});   // stays where you are
  wireFocus(v,p,renderReview);
  $$("[data-mid]",v).forEach(r=>{r.onclick=()=>{const i=p.matches.findIndex(x=>x.id===r.dataset.mid);S.match=i<0?0:i;S.mpin=i>=0;go("matches")}});
  // the rating chart's dots (13/10, the user: "au click sur le dot ça doit ouvrir la map du match"): a mouse click or
  // Enter opens the match; a touch shows its card first (the first tap), then opens it (the second)
  $$(".sp-dot[data-dmid]",v).forEach(d=>{d.onpointerdown=e=>{d._touch=e.pointerType==="touch";d._shown=document.activeElement===d};
    d.onclick=()=>{if(d._touch&&!d._shown){d.focus();return}const i=p.matches.findIndex(x=>x.id===d.dataset.dmid);if(i<0)return;S.match=i;S.mpin=true;go("matches")}});
}
