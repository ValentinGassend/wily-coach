// ---------- Wily, said out loud (06/10, the user: "que Wily fonctionne comme Jarvis... chaque information que je donne
// à Wily doit être prise en compte"): wily.py reads the order, gsi.wily keeps it on the round (g.wily) and the match's
// habits (g.wily_match). The page shows what Wily understood (a card; no voice since 20/10), what the order changes (the way,
// the tempo, your buy or theirs, what the panel and the map show), and asks in a few words when a piece is missing
// (numpad 1-2-3 or the word answers).
function wilyOf(g){const w=g&&g.wily;return w&&w.round===g.round?w:null}
// Wily's acknowledgement in a language: gsi.wily writes one per language of the app (acks, 13/10); an older state has
// the French one (ack) and the English one (ack_en)
function wilyAckIn(w,l){const A=w.acks||{};return A[l]||(l==="fr"?w.ack:l==="en"?w.ack_en:null)||null}
const ASK_Q=l=>({"From where?":tlv("From where?",l),"Which site?":tlv("Which site?",l)});
// what Wily understood, in the page's language
function wilyAck(w){return wilyAckIn(w,LANG)||wilyAckIn(w,"en")||w.ack||""}
// the card: the order understood (25 s), the question until it's answered
function vWily(g){const w=wilyOf(g);if(!w)return "";const age=Date.now()/1000-(w.t||0);if(age>25&&!w.ask)return "";
  return `<div class="vwily"><b>${IC("mic")} WILY</b><span>${esc(wilyAck(w))}</span>${w.ask?`<div class="vask"><em>${esc(ASK_Q(LANG)[w.ask.q]||w.ask.q)}</em>${w.ask.opts.map(o=>`<span class="vchip"><small>${{A:"1",MID:"2",B:"3"}[o]||""}</small> ${o==="MID"?tl("mid"):o}</span>`).join("")}</div>`:""}</div>`}
// your buy and theirs said to Wily ("Wily force-buy", "Wily anti-éco"): the odds of the round follow them
function wilyBuy(g){const w=wilyOf(g);return w&&w.buy?w.buy:null}
function enemyBuyW(p,g){const w=wilyOf(g);if(w&&w.their==="eco")return {eco:1,force:0,full:0};return enemyBuy(p,g)}
const WPN={m4a1_silencer:"M4A1-S",m4a1:"M4A4",ak47:"AK-47",awp:"AWP",deagle:"Deagle",mp9:"MP9",fiveseven:"Five-SeveN",usp_silencer:"USP-S",glock:"Glock",
  revolver:"R8",famas:"FAMAS",galilar:"Galil",aug:"AUG",sg556:"SG 553",ssg08:"Scout",mac10:"MAC-10",mp7:"MP7",ump45:"UMP-45",p90:"P90",mag7:"MAG-7",
  nova:"Nova",xm1014:"XM1014",hkp2000:"P2000",p250:"P250",tec9:"Tec-9",cz75a:"CZ75",bizon:"Bizon",mp5sd:"MP5-SD",negev:"Negev",m249:"M249",sawedoff:"Sawed-Off"};
// a short list of lineups: type, where to, from where, how (no images yet: the map shows where you stand)
const nadeLi=u=>`<span class="vnd"><i style="background:${NADE_C[u.type]||"#ccc"}">${NADE_L[u.type]||"?"}</i>${esc(vShort(u.to||"?"))}<small>${esc(vShort(u.from||""))}${HOW_S(u.how)?" · "+esc(HOW_S(u.how)):""}</small></span>`;
// CT, "Wily contre rush B 5 stack": how often a rush there is held, what kills it (the spots, the weapons of bought
// rounds), the grenades onto its ways in that hold it most (rounds held when thrown, vs the usual)
function vCounter(p,g,f){const TD=tdirsOf(g.map),D_=TD&&TD.defense&&TD.defense[f.site];if(!D_)return `<div class="vdir"><div class="vdir-h"><b>${tl("VS RUSH {site}",{site:esc(f.site||"")})}</b> · ${tl("no rush on that site in my base yet")}</div></div>`;
  const W=(D_.weapons||[]).slice(0,3).map(w=>`<span class="vtag">${esc(WPN[w.w]||w.w)} <small>${w.share}%</small></span>`).join("");
  const sp=(D_.spots||[]).slice(0,3).map(s=>`<span class="vchip">${IC("map-pin")} ${esc(vShort(s.zone||"?"))} <small>${tln(s.kills,"{n} kill","{n} kills")}</small></span>`).join("");
  const U=(D_.util||[]).filter(u=>u.edge>0).slice(0,3).map(u=>`<div class="vstack">${nadeLi(u)}<small class="edge">${tl("+{n} held",{n:u.edge})}</small></div>`).join("");
  return `<div class="vdir"><div class="vdir-h"><b>${tl("VS RUSH {site}",{site:esc(f.site)})}</b>${f.n?" · "+tl("{n} stack",{n:f.n}):""} · ${tl("held {p}%",{p:D_.ct_win})} <small>(${tln(D_.n,"{n} rush","{n} rushes")})</small></div>
    ${U?`<div class="vhead">${tl("UTILITY THAT HOLDS IT")}</div><div class="vstacks">${U}</div>`:""}${sp?`<div class="vhead">${tl("WHERE THE KILLS ARE")}</div><div class="vchips">${sp}</div>`:""}${W?`<div class="vhead">${tl("WITH")}</div><div class="vtags">${W}</div>`:""}</div>`}
// CT, "Wily B fake défense A": the grenades CTs throw onto A's ways in, from the ones closest to where you play
function fakeDefList(TD,f){const U=((TD&&TD.ct_util)||{})[f.site]||[];if(!U.length)return [];
  const G=(TD.gates||[]).filter(x=>f.frm==="MID"?x.mid:x.site===f.frm),c=G.length?[G.reduce((a,x)=>a+x.px[0],0)/G.length,G.reduce((a,x)=>a+x.px[1],0)/G.length]:null;
  return U.slice().sort((a,b)=>c?Math.hypot(a.from_px[0]-c[0],a.from_px[1]-c[1])-Math.hypot(b.from_px[0]-c[0],b.from_px[1]-c[1]):b.n-a.n).slice(0,3)}
function vFakeDef(p,g,f){const TD=tdirsOf(g.map),L=fakeDefList(TD,f);
  return `<div class="vdir"><div class="vdir-h"><b>${tl("FAKE {site}",{site:esc(f.site||"")})}</b>${f.frm?" · "+tl("from {where}",{where:f.frm==="MID"?tl("mid"):esc(f.frm)}):""}</div>
    ${L.length?`<div class="vstacks">${L.map(u=>`<div class="vstack">${nadeLi(u)}</div>`).join("")}</div><p class="mini">${tl("Show them {site}: utility onto its ways in, a sound, then back to {back}.",{site:esc(f.site),back:f.frm==="MID"?tl("mid"):f.frm?esc(f.frm):tl("your spot")})}</p>`:`<p class="mini">${tl("No CT grenade onto {site} in my base yet.",{site:esc(f.site||"")})}</p>`}</div>`}
// T, "Wily fake A go B": the stuff that shows A (the usual way onto A's grenades), and what the fake does in the base
function vFakeT(p,g,f){const TD=tdirsOf(g.map),M=(((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{},F=(M.fakes||{})[f.then||""];
  const way=TD&&TD.dirs.filter(d=>d.site===f.site&&!d.split&&d.n>=25).sort((a,b)=>b.n-a.n)[0],U=way?(way.util||[]).filter(u=>u.type!=="he").slice(0,3):[];
  return `<div class="vdir"><div class="vdir-h"><b>${tl("FAKE {site}",{site:esc(f.site)})}</b>${f.then?` → ${esc(f.then)}`:""}${F&&F.n>=20?" · "+tl("won {p}%",{p:F.won})+` <small>(${tl("straight {site}: {p}%",{site:f.then,p:F.won_direct})})</small>`:""}</div>
    ${U.length?`<div class="vhead">${tl("SHOW {site}",{site:esc(f.site)})} · ${esc(DL(way.label))}</div><div class="vstacks">${U.map(u=>`<div class="vstack">${nadeLi(u)}</div>`).join("")}</div>`:""}
    ${F&&F.t_hit?`<p class="mini">${tl("Then on {site} around {t}: the CTs who rotated are still on the way.",{site:esc(f.then),t:clock(F.t_hit)})}</p>`:""}</div>`}
// T, "Wily cover mid": the CTs' rotations through that place when your team hits elsewhere (their time on the way)
function vCover(p,g,f){const M=(((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{},R=M.rotations||{},rx=f.where==="MID"?/mid|connector|window|short/i:new RegExp(String(f.where).replace(/[^a-z ]/gi,""),"i");
  const L=[];Object.entries(R).forEach(([site,by])=>Object.entries(by||{}).forEach(([from,e])=>((e||{}).routes||[]).forEach(rt=>{if((rt.route||[]).some(z=>rx.test(z)))L.push({site,from,rt})})));
  L.sort((a,b)=>(b.rt.n||0)-(a.rt.n||0));
  return `<div class="vdir"><div class="vdir-h"><b>${tl("COVER {where}",{where:f.where==="MID"?tl("MID"):esc(f.where)})}</b></div>${L.length?L.slice(0,3).map(x=>`<div class="vstack"><span class="from">${esc(vShort(x.from))} → ${esc(x.site)}</span><span class="vnd">${esc(x.rt.route.map(vShort).join(" › "))}<small>${x.rt.travel!=null?Math.round(x.rt.travel)+" s":""}${x.rt.died!=null?" · "+tl("{p}% die",{p:x.rt.died}):""}</small></span></div>`).join(""):`<p class="mini">${tl("The CTs rarely rotate through there in my base.")}</p>`}<p class="mini">${tl("Hold it while your team hits: the rotating CTs come through here.")}</p></div>`}
// what the order puts in the focus slot (the round's main card); null: the usual one
function vWilyFocus(p,g){const w=wilyOf(g),f=w&&w.focus;if(!f)return null;const ct=g.side==="CT";
  if(f.k==="counter"&&ct&&f.site)return vCounter(p,g,f);
  if(f.k==="fakedef"&&ct&&f.site)return vFakeDef(p,g,f);
  if(f.k==="retake"&&ct&&f.site)return `<div class="vdir-h"><b>${tl("RETAKE {site}",{site:esc(f.site)})}</b>${f.via?" · "+tl("via {way}",{way:esc(vShort(f.via))}):""}</div>`+(vRetake(p,g,f.site)||"");
  if(f.k==="post"&&f.site)return ct?vRetake(p,g,f.site):vPostPlant(p,g,f.site);
  if(f.k==="fake"&&!ct&&f.site)return vFakeT(p,g,f)+(vDir(p,g)||"");
  if(f.k==="cover"&&!ct)return vCover(p,g,f);
  if(f.k==="stuff"&&!ct)return vDir(p,g,{stuff:4});
  return null}
// the map for the order: the counter's kill spots and grenades, the fake defense's grenades
function wilyRadar(p,g,level,Lnades,Ltop,legend){const w=wilyOf(g),f=w&&w.focus;if(!f)return;const TD=tdirsOf(g.map);if(!TD)return;
  const arcs=L=>L.forEach(u=>{if(!u.from_px||!u.to_px||(u.level&&level&&u.level!==level))return;nadeArc(Lnades,u.from_px[0],u.from_px[1],u.to_px[0],u.to_px[1],u.type);nadeIcon(Ltop,u.type,u.to_px[0],u.to_px[1],`${NSHORT[u.type]||u.type} ${u.from} → ${u.to}`)});
  if(f.k==="counter"&&g.side==="CT"){const D_=(TD.defense||{})[f.site];if(!D_)return;arcs((D_.util||[]).filter(u=>u.edge>0).slice(0,3));
    (D_.spots||[]).slice(0,3).forEach(s=>{if(s.level&&level&&s.level!==level)return;mkMark(Ltop,{px:s.px},true)});legend.push(`<span>${SW.star}${tl("where the CTs kill the rushes on {site}; the arcs: their grenades that hold it",{site:esc(f.site)})}</span>`)}
  if(f.k==="fakedef"&&g.side==="CT"){arcs(fakeDefList(TD,f));legend.push(`<span>${tl("grenades onto {site}'s ways in, from the closest to where you play",{site:esc(f.site)})}</span>`)}}
