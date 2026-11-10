
// ---------- full-screen side panel: visual only (a glance between two duels), filtered by side and by moment ----------
const vTone=v=>v==null?"":v>=60?"good":v>=45?"warn":"bad";
const vShort=s=>esc(String(s||"").split(" / ")[0].replace(/^Bombsite /,"").replace(/ Site$/,""));
const vLetter={smoke:"S",flash:"F",molotov:"M",he:"H"};
const NSHORT={smoke:tl("smoke"),flash:tl("flash"),molotov:tl("molly"),he:tl("HE")};   // a grenade's short name, in a line
// the grenades you hold, each with the throw that fits this moment (same choice as the text panel), or none
function vNadePicks(p,g){const N=(p.advice.plan||{}).nades,E=N&&((N.maps||{})[g.map]||{})[g.side];if(!E)return [];
  const w=g.bomb==="planted"?"post":g.elapsed==null?null:g.elapsed<20?"debut":g.elapsed<40?"prise":g.elapsed<70?"action":"fin",el=g.elapsed;
  const MS=g.side==="CT"?mySite(g):null,GS=((((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{}).geo,MSg=MS&&GS&&GS.sites?GS.sites[MS]:null;
  const atMine=x=>MSg&&x.to_px&&Math.hypot(x.to_px[0]-MSg.px[0],x.to_px[1]-MSg.px[1])<300&&(!x.land_level||!MSg.level||x.land_level===MSg.level);
  // a path pressed (T) or the site you play (CT): every lineup of the base for it, not only your usual zones'
  const src=t=>{const P=(E.pool||[]).filter(x=>x.type===t);if(focusN(g)&&P.length)return P;if(MSg&&P.length){const m=P.filter(atMine);if(m.length)return m}return E.types[t].picks||[]};
  const all=t=>[...src(t),...(E.types[t].post||[])].filter((x,i,a)=>a.indexOf(x)===i);
  // what a throw brings: rounds won when it's thrown vs the map's average (shrunk on few throws), else its own score
  const eff=x=>x.win!=null&&x.base_win!=null?((x.win*(x.n||0)+x.base_win*10)/((x.n||0)+10)-x.base_win)/100:(x.score||0)/4;
  // T side: the throws that serve your way (path 1 of the radar) come first, the ones landing on the other site last
  const W=g.side===attackSide(g.map)?(isHostage(g.map)?hostageRank(p,g):typeof winsRank==="function"?winsRank(p,g):null):null;
  const RF=W&&(W.rows.find(x=>x.rank===focusN(g))||W.rows[0]),R1=RF&&RF.route,pts=R1?R1.pts:null;   // the path you pressed, else path 1
  const GEO=((((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{}).geo,end=pts?pts[pts.length-1]:null;
  // the level counts (Nuke: A is right above B): a throw is near a point only on the same level, when both are known
  const lvOK=(a,b)=>!a||!b||a===b,sk=RF?(RF.k.match(/[AB]$/)||RF.k.match(/^[AB]/)||[])[0]:null;
  const S1g=R1&&GEO&&GEO.sites&&sk?GEO.sites[sk]:null,S1=S1g?S1g.px:null;   // the site of that path
  const othG=GEO&&GEO.sites&&sk?GEO.sites[sk==="A"?"B":"A"]:null,oth=othG?othG.px:null;
  const near=(a,d,lv)=>a&&pts&&pts.some(q=>Math.hypot(q[0]-a[0],q[1]-a[1])<d&&lvOK(lv,q[2]));
  const way=x=>{if(!pts||!x.to_px)return null;const lv=x.land_level||x.level;
    if((end&&Math.hypot(x.to_px[0]-end[0],x.to_px[1]-end[1])<160&&lvOK(lv,end[2]))||(S1&&Math.hypot(x.to_px[0]-S1[0],x.to_px[1]-S1[1])<170&&lvOK(lv,S1g.level)))return "site";
    if(near(x.to_px,50,lv))return "way";
    if(oth&&Math.hypot(x.to_px[0]-oth[0],x.to_px[1]-oth[1])<160&&lvOK(lv,othG.level))return "off";
    return near(x.from_px,60,x.level)?"from":null};
  const bonus={site:.06,way:.04,from:.02,off:-.06};
  const eff0=eff,effW=x=>eff0(x)+(bonus[way(x)]||0)+(x.pop?.03:0),   // a pop flash: you peek behind it yourself
tag=x=>x&&Object.assign({},x,{way:way(x)});
  const FX=focusN(g),noOff=l=>l.filter(x=>FX?["site","way","from"].includes(way(x)):way(x)!=="off");   // a throw toward the other site only helps a fake: never shown; with a focus, only the throws of that path
  const picks=t=>{if(w==="post")return (E.types[t].post||[]).slice(0,2);
    if(el==null||!w){const L0=noOff(src(t).slice().sort((a,b)=>effW(b)-effW(a)));
      const rushL=RF&&/^rush/.test(RF.k)?L0.filter(x=>x.t_med!=null&&x.t_med<=28):[];   // a rush: the throws made in its first seconds
      return (rushL.length?rushL:L0).slice(0,2).map(tag)}   // buy time: the best ones of the round, for your way
    const fit=x=>x.best===w||x.usual===w||(x.t_med!=null&&x.t_med>=el-8&&x.t_med<=el+25);
    return noOff(all(t).filter(fit).sort((a,b)=>effW(b)-effW(a)||Math.abs((a.t_med??el)-el)-Math.abs((b.t_med??el)-el))).slice(0,2).map(tag)};
  return Object.entries(g.nades||{}).filter(([t,v])=>v>0&&E.types[t]).map(([t,v])=>{const ps=picks(t);return {type:t,n:v,x:ps[0]||null,alt:ps[1]||null,el:g.round_phase==="live"?el:null}})}
function vNades(list){if(!list.length)return "";
  const when=(x,el)=>x.t_med!=null&&el!=null&&x.t_med>el+3?clock(x.t_med):x.t_med!=null&&el==null?clock(x.t_med):tl("now");
  return `<div class="vnades">${list.map(o=>`<span class="vnade${o.x?(o.now?" now":""):" keep"}" style="--c:${NADE_C[o.type]||"#ccc"}"><i>${vLetter[o.type]||"?"}</i>${o.x?`${vShort(o.x.to||o.x.land)}${o.x.pop?" ↯":""}<small>${when(o.x,o.el)}</small>${o.alt?`<em>${vShort(o.alt.to||o.alt.land)} ${when(o.alt,o.el)}</em>`:""}`:`<small>${tl("keep")}</small>`}</span>`).join("")}</div>`}
// a rule as icons and two numbers: what your side wins when you do it / when you don't
const vRule=(icon,label,bad,good)=>`<div class="vrule"><i>${icon}</i><span>${label}</span><b class="bad">${bad}%</b><em>→</em><b class="good">${good}%</b></div>`;
// T side: the round as a strip from 1:55 to 0:00, each tempo window colored by how often the Ts win with it here;
// what is past fades, a cursor marks now
function vTimeline(p,g){const TS=(p.advice.plan||{}).tside,M=TS&&TS.maps&&TS.maps[g.map],TP=(M&&M.tplan)||{},rt=advisedType(g);
  const tp=(TP.tempo||{})[rt==="pistol"?"pistol":rt]||(TP.tempo||{}).full||{},L=RLEN(),el=g.round_phase==="live"?(g.elapsed||0):0;
  const seg=[["rush",0,30],["exec",30,75],["late",75,L]].filter(s=>s[2]>s[1]);
  const SEGL={rush:tl("rush"),exec:tl("exec"),late:tl("late")};
  return vHead(tl("ROUNDS WON · BY TEMPO"))+`<div class="vtl">${seg.map(([k,a,b])=>{const v=(tp[k]||[])[1];
      return `<div class="vseg ${vTone(v)}${el>b?" past":""}" style="flex:${b-a}"><span>${SEGL[k]} ${a===0?`›${clock(b)}`:b>=L?`‹${clock(a)}`:`${clock(a)}-${clock(b)}`}</span>${v!=null?`<b>${v}%</b>`:""}</div>`}).join("")}
    ${g.round_phase==="live"?`<i class="vcur" style="left:${Math.min(100,100*el/L)}%"></i>`:""}</div>`}
// T: when to be on the site with your paths: rounds won by the moment the play is on the site (game clock, 1:55 on the
// left, 0:00 on the right), path 1 filled, paths 2 and 3 as dashed lines in their colors; the band is path 1's best
// window (its "on site" on the map), the white line is now. The same rounds as the window on the map
function vPathCurve(p,g){const W=typeof winsRank==="function"?winsRank(p,g):null;if(!W)return "";
  const rows=W.rows.slice(0,3).filter(r=>r.timing&&r.timing.curve&&r.timing.curve.length>=3);if(!rows.length||rows[0].rank!==1)return "";
  const site1=(rows[0].k.match(/[AB]$/)||rows[0].k.match(/^[AB]/)||[])[0],UW=((((((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{}).util_war||{})[site1])||null;
  const ew=econW(p,g),wsh=u=>u.ctx&&Object.keys(u.ctx).length?Object.entries(ew).reduce((a,[c,w])=>a+w*(u.ctx[c]??u.share),0):u.share;
  const ub=((UW&&UW.util)||[]).map(u=>({...u,share:Math.round(wsh(u))})).filter(u=>u.share>=15).sort((a,b)=>b.share-a.share).slice(0,3);   // their usual blocking utility there, for their buy
  const Wd=320,H=86+ub.length*7,L=RLEN(),all=rows.flatMap(r=>r.timing.curve.map(c=>c[1])),lo=Math.min(...all)-4,hi=Math.max(...all)+6;
  const X=c=>Math.round(Wd*c/L),Y=v=>Math.round(6+(H-20)*(1-(v-lo)/Math.max(1,hi-lo)));
  const line=r=>r.timing.curve.map(([c,v],i)=>`${i?"L":"M"}${X(c)} ${Y(v)}`).join("");
  const r1=rows[0],c1=r1.timing.curve,t1=r1.timing,base=H-14-ub.length*7,area=`${line(r1)}L${X(c1[c1.length-1][0])} ${base}L${X(c1[0][0])} ${base}Z`;
  const now=g.round_phase==="live"?(g.elapsed||0):null,pk=c1.reduce((a,b)=>b[1]>a[1]?b:a);
  const ticks=[[25,"1:30"],[55,"1:00"],[85,"0:30"]].map(([c,t])=>`<line x1="${X(c)}" y1="${base}" x2="${X(c)}" y2="${base+4}" stroke="var(--muted)"/><text x="${X(c)}" y="${H-1}" text-anchor="middle" class="vct">${t}</text>`).join("");
  const svg=`<svg class="vcurve" viewBox="0 0 ${Wd} ${H}" width="100%" height="${H}" role="img" aria-label="${tl("Rounds won by the moment the play is on the site")}">
    <line x1="0" y1="${base}" x2="${Wd}" y2="${base}" stroke="var(--line)"/>
    ${t1.win-t1.mean>=3?`<rect x="${X(t1.lo)}" y="0" width="${Math.max(2,X(t1.hi)-X(t1.lo))}" height="${base}" fill="${r1.col}" fill-opacity=".2"/>`:""}
    <path d="${area}" fill="${r1.col}" fill-opacity=".22"/><path d="${line(r1)}" fill="none" stroke="${r1.col}" stroke-width="2.4" stroke-linejoin="round"/>
    ${rows.slice(1).map(r=>`<path d="${line(r)}" fill="none" stroke="${r.col}" stroke-width="1.6" stroke-dasharray="4 3" opacity=".85"/>`).join("")}
    <text x="${Math.min(Wd-14,Math.max(14,X(pk[0])))}" y="${Math.max(10,Y(pk[1])-4)}" text-anchor="middle" class="vcv">${pk[1]}%</text>
    ${ub.map((u,i)=>`<rect x="${X(u.t)}" y="${base+2+i*7}" width="${Math.max(3,X(u.end)-X(u.t))}" height="5" rx="2" fill="${u.type==="molotov"?"var(--molotov)":"var(--smoke)"}" opacity=".9"><title>${esc(tl("Their {nade} {zone}: {p}% of rounds, {a} to {b}",{nade:NSHORT[u.type]||u.type,zone:u.land,p:u.share,a:clock(u.t),b:clock(u.end)}))}</title></rect>`).join("")}
    ${ticks}${now!=null?`<line x1="${X(now)}" y1="0" x2="${X(now)}" y2="${base}" stroke="#fff" stroke-width="1.6"/>`:""}</svg>`;
  const hz=(UW&&UW.hits)||{},act=hz.active,aft=hz.spent||hz.kept,into=act&&aft&&aft[1]-act[1]>=5?vRule(IC("triangle-alert"),tl("into their utility {site}",{site:site1}),act[1],aft[1]):"";
  return vHead(rows.length>1?tl("ON THE SITE AT · ROUNDS WON · PATHS 1-{n}",{n:rows.length}):tl("ON THE SITE AT · ROUNDS WON · PATH 1"))+svg+(ub.length?`<div class="vleg">${ub.map(u=>`<span><i style="background:${u.type==="molotov"?"var(--molotov)":"var(--smoke)"}"></i>${u.type==="molotov"?NSHORT.molotov:NSHORT.smoke} ${esc(vShort(u.land||"?"))} ${clock(u.t)}-${clock(u.end)}</span>`).join("")}</div>`:"")+into}
// the other team's economy as weights over the kinds of round of the base: their pistol, eco or force ("low"), full
function econW(p,g){if(g.round===halfStart(g.round))return {pistol:1};const eb=enemyBuy(p,g)||{},lo=(eb.eco||0)+(eb.force||0),fu=eb.full||0,s=lo+fu;
  return s>0?{low:lo/s,full:fu/s}:{full:1}}
// CT: when the Ts are on each site for their buy (A and B, share of rounds around each moment, game clock), their
// smokes and mollies on that side before they come, the moment to throw the one you held (green:
// just before their usual arrival) and now
const UCOL={smoke:"var(--smoke)",flash:"var(--flash)",molotov:"var(--molotov)",he:"var(--he)"};
function vCTline(p,g,r){const M=(((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{},TT=M.t_timeline;if(!TT)return "";const ew=econW(p,g);
  const mix=site=>{const acc={};let any=false;for(const [c,w] of Object.entries(ew)){const X=TT[c]&&TT[c][site];if(!X||!w)continue;any=true;X.curve.forEach(([t,v])=>acc[t]=(acc[t]||0)+w*v)}
    return any?Object.entries(acc).map(([t,v])=>[+t,v]).sort((a,b)=>a[0]-b[0]):null};
  const A=mix("A"),B=mix("B");if(!A&&!B)return "";
  // the site you hold (numpad 7 / 9 or said: your stuff, your molly's moment), else the likely one
  const site=mySite(g)||(r&&r.A!==r.B?(r.A>r.B?"A":"B"):((A||[]).reduce((s,x)=>s+x[1],0)>=(B||[]).reduce((s,x)=>s+x[1],0)?"A":"B"));
  const UT={};for(const [c,w] of Object.entries(ew)){((TT[c]&&TT[c][site]&&TT[c][site].util)||[]).forEach(u=>{const k=u.type+"|"+u.land,o=UT[k]||(UT[k]={...u,share:0});o.share+=w*u.share})}
  const ut=Object.values(UT).filter(u=>u.share>=10&&(u.type==="smoke"||u.type==="molotov")&&u.t>=5).sort((a,b)=>b.share-a.share).slice(0,2);   // their smokes and mollies on that side, not the spawn ones
  // your stuff on the line (06/10, the user: "la timeline CT: quand ils arrivent sur chaque site, et quand lancer ton
  // stuff"): your site's lineups (numpad 7 / 9 or said; else the likely site) at the moment the base throws them
  const ms=mySite(g)||site,LL=((((((p.advice.plan||{}).nades||{}).maps||{})[g.map]||{}).CT)||{}).lanes||{},myU=[];
  Object.entries(LL).filter(([k])=>k[0]===ms).forEach(([,o])=>["molotov","smoke","flash","he"].forEach(t=>{const x=o[t],m=x&&/^(\d+):(\d\d)$/.exec(x.timer||"");
    if(!m||myU.length>=4||myU.some(y=>y.type===t&&y.to===x.to))return;const el=RLEN()-(+m[1]*60+ +m[2]);if(el>=0&&el<=RLEN())myU.push({...x,type:t,el})}));
  const Wd=320,L=RLEN(),mrow=myU.length?16:0,H=78+ut.length*7+mrow,base=H-14-ut.length*7-mrow,mx=Math.max(1,...(A||[]).map(x=>x[1]),...(B||[]).map(x=>x[1]));
  const X=t=>Math.round(Wd*t/L),Y=v=>Math.round(4+(base-6)*(1-v/mx));
  const path=c=>c.map(([t,v],i)=>`${i?"L":"M"}${X(t)} ${Y(v)}`).join(""),area=c=>`${path(c)}L${X(c[c.length-1][0])} ${base}L${X(c[0][0])} ${base}Z`;
  const S=site==="A"?A:B,pk=S?S.reduce((a,b)=>b[1]>a[1]?b:a):null,now=g.round_phase==="live"?(g.elapsed||0):null;
  const ticks=[[25,"1:30"],[55,"1:00"],[85,"0:30"]].map(([c,t])=>`<line x1="${X(c)}" y1="${base}" x2="${X(c)}" y2="${base+4}" stroke="var(--muted)"/><text x="${X(c)}" y="${H-1}" text-anchor="middle" class="vct">${t}</text>`).join("");
  const svg=`<svg class="vcurve" viewBox="0 0 ${Wd} ${H}" width="100%" height="${H}" role="img" aria-label="${tl("When the Ts are on each site")}">
    <line x1="0" y1="${base}" x2="${Wd}" y2="${base}" stroke="var(--line)"/>
    ${pk?`<rect x="${X(Math.max(0,pk[0]-6))}" y="0" width="${X(8)}" height="${base}" fill="var(--good)" fill-opacity=".22"/>`:""}
    ${[["B",B],["A",A]].filter(([,c])=>c).map(([s_,c])=>`<path d="${area(c)}" fill="${SITE_C[s_]}" fill-opacity="${s_===site?.28:.12}"/><path d="${path(c)}" fill="none" stroke="${SITE_C[s_]}" stroke-width="${s_===site?2.4:1.4}" stroke-linejoin="round" opacity="${s_===site?1:.7}"/>`).join("")}
    ${ut.map((u,i)=>`<rect x="${X(u.t)}" y="${base+2+i*7}" width="${Math.max(3,X(u.end)-X(u.t))}" height="5" rx="2" fill="${UCOL[u.type]||"#ccc"}"/>`).join("")}
    ${(()=>{const pk2=[["A",A],["B",B]].filter(([,c])=>c&&c.length).map(([s_,c])=>[s_,c.reduce((a,b)=>b[1]>a[1]?b:a)]);   // each site's peak, named; the second one a line lower when they meet
      return pk2.map(([s_,q],i)=>{const x=Math.min(Wd-30,Math.max(2,X(q[0])-12)),near=i&&Math.abs(X(pk2[0][1][0])-X(q[0]))<44;
        return `<text x="${x}" y="${Math.min(base-3,Math.max(10,Y(q[1])-3)+(near?11:0))}" class="vctl" style="fill:${SITE_C[s_]}">${s_} ${clock(q[0])}</text>`}).join("")})()}
    ${myU.map(u=>{const yy=base+ut.length*7+11;return `<circle cx="${X(u.el)}" cy="${yy}" r="6.5" fill="${NADE_C[u.type]||"#ccc"}"/><text x="${X(u.el)}" y="${yy+3.5}" text-anchor="middle" class="vctm">${vLetter[u.type]||"?"}</text>`}).join("")}
    ${ticks}${now!=null?`<line x1="${X(now)}" y1="0" x2="${X(now)}" y2="${base}" stroke="#fff" stroke-width="1.6"/>`:""}</svg>`;
  // the one to hold (the hold card's best: your rounds won when it meets their hit, and when thrown early)
  // only the grenades you have (bought at the buy time: the best one to buy, marked so); none in the round: the window alone
  const held=["molotov","smoke","he"].filter(t=>((g.nades||{})[t]||0)>0),live_=g.round_phase==="live",NM=NSHORT;
  const UW=(M.util_war||{})[site],cand=((UW&&UW.util)||[]).filter(u=>u.met_t_won!=null&&(!held.length||held.includes(u.type))).sort((a,b)=>a.met_t_won-b.met_t_won);
  const h=held.length||!live_?cand[0]:null,sp=((UW&&UW.hits)||{}).spent,win=pk?`${clock(Math.max(0,pk[0]-6))}-${clock(pk[0]+2)}`:"";
  const what=h?`${NM[h.type]||h.type} ${esc(vShort(h.land||"?"))}${held.length?"":" "+tl("(buy)")}`:held.length?held.map(t=>NM[t]).join("/"):"";
  const mine=what?tl("your {nade} {t}",{nade:what,t:win})+(h?" · "+tl("won {p}%",{p:100-h.met_t_won})+(sp?" "+tl("vs {p}% early",{p:100-sp[1]}):""):""):tl("their arrival {t}",{t:win});
  return vHead(tl("WHEN THEY'RE ON A · B")+(r?` · ${Math.round(r.A)}% · ${Math.round(r.B)}%`:""))+svg+`<div class="vleg"><span><i style="background:var(--good)"></i>${mine}</span>${ut.map(u=>`<span><i style="background:${UCOL[u.type]||"#ccc"}"></i>${tl("their {nade}",{nade:NSHORT[u.type]||u.type})} ${esc(vShort(u.land||"?"))} ${clock(u.t)}</span>`).join("")}${myU.map(u=>`<span><i style="background:${NADE_C[u.type]||"#ccc"}"></i>${vLetter[u.type]||"?"} ${esc(vShort(u.to))} ${esc(u.timer)}</span>`).join("")}</div>`}
// CT: what to keep for their hit on the likely site: your rounds won when it meets their hit, and what thrown-early
// utility gives
function vHold(p,g,r){const M=(((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{},site=r&&r.A!==r.B?(r.A>r.B?"A":"B"):null,UW=site&&(M.util_war||{})[site];if(!UW)return "";
  const held=["molotov","smoke","he"].filter(t=>((g.nades||{})[t]||0)>0);
  const rows=(UW.util||[]).filter(u=>u.met_t_won!=null&&(!held.length||held.includes(u.type))).sort((a,b)=>a.met_t_won-b.met_t_won).slice(0,2);   // the grenades you have
  const sp=(UW.hits||{}).spent;if(!rows.length&&!sp)return "";
  return vHead("⏳ "+tl("HOLD FOR THEIR HIT · {site} · WON",{site}))+vRows([...rows.map(u=>({l:`${u.type==="molotov"?NSHORT.molotov:NSHORT.smoke} ${vShort(u.land||"?")}`,v:100-u.met_t_won,c:"var(--good)"})),
    ...(sp?[{l:tl("thrown early"),v:100-sp[1],c:"var(--bad)",o:.7}]:[])])}
function vCTdots(p,g){const TS=(p.advice.plan||{}).tside,M=TS&&TS.maps&&TS.maps[g.map],TP=(M&&M.tplan)||{},rt=advisedType(g);
  const su=(TP.setup||{})[rt==="pistol"?"pistol":rt]||(TP.setup||{}).all;if(!su||!su.top||!su.top.length)return "";const t=su.top[0];
  const dots=n=>"●".repeat(n)||"○";
  return vHead(tl("CT SETUP · MOST USED"))+`<div class="vdots"><span>A</span><b>${dots(t[0])}</b><em>|</em><span>B</span><b>${dots(t[1])}</b>${t[2]?`<em>|</em><span>${tl("mid")}</span><b>${dots(t[2])}</b>`:""}<small>${tl("{p}% of rounds",{p:t[3]})}</small></div>`}
function vTchips(p,g){const TS=(p.advice.plan||{}).tside,M=TS&&TS.maps&&TS.maps[g.map],TP=(M&&M.tplan)||{},P_=M&&M.plays,out=[];
  // a fake (first contact on one side, the hit on the other) against going straight: rounds won, both, always
  const fk=TP.fake||{};if(fk.switch&&fk.direct){const d=fk.switch[1]-fk.direct[1];out.push(`<span class="vchip ${d>=5?"good":d<=-5?"bad":""}">${tl("FAKE {p}% won",{p:fk.switch[1]})} <small>${tl("direct {p}%",{p:fk.direct[1]})}</small></span>`)}
  return out.length?`<div class="vchips">${out.join("")}</div>`:""}
// one option per line: the label, a bar (the longest is the most likely), the number. Fixed order for the sites,
// so the eye finds A and B at the same place every time
const SITE_C={A:"var(--siteA)",B:"var(--siteB)"};
const vHead=t=>`<div class="vhead">${t}</div>`;
function vRows(rows){const mx=Math.max(...rows.map(r=>r.v),1);
  return `<div class="vrows">${rows.map(r=>`<div class="vrow" style="--c:${r.c||"var(--ink)"}${r.o!=null&&r.o<1?`;opacity:${r.o}`:""}"><span>${r.l}</span><i><u style="width:${Math.max(4,Math.round(100*r.v/mx))}%"></u></i><b>${Math.round(r.v)}%</b></div>`).join("")}</div>`}
// CT: what this team did this half, by their buy (06/10, the user: "avant le round, une seule ligne sur les habitudes des
// T dans ce match, selon leur éco: B 3/4, rush sur éco"): the rounds you know (the bomb's site, else your calls), their
// buy each of those rounds rebuilt like enemyBuy (eco: pistol, eco or force; full), their rushes (your calls, the plant)
function buyLow(p,g,n){const x=enemyBuy(p,{...g,round:n})||{};return !!(x.pistol||(x.eco||0)+(x.force||0)>=(x.full||0))}
function vHabits(p,g){if(g.side!=="CT"||isHostage(g.map))return "";const TS=(p.advice.plan||{}).tside,H=g.hist||{},SI=H.sites||{},MK=H.marks||{},cur=g.round_phase==="over"?g.round+1:g.round;
  const rows=[];for(let n=halfStart(cur);n<cur;n++){const mk=MK[n]||{},s=mk.bomb_site||SI[n],d=roundDyn(TS,H,n);
    if(((H.rounds||{})[n]||{}).side!=="CT"||(s!=="A"&&s!=="B"&&!(d&&d.dyn)))continue;   // your CT rounds only (a team switched mid-half)
    rows.push({site:s==="A"||s==="B"?s:null,rush:!!(d&&d.dyn==="rush"),low:buyLow(p,g,n)})}
  if(rows.length<2)return "";
  const kn=rows.filter(r=>r.site),nA=kn.filter(r=>r.site==="A").length,nB=kn.length-nA,top=nA>=nB?"A":"B";
  const lowR=rows.filter(r=>r.low),fullR=rows.filter(r=>!r.low),rl=lowR.filter(r=>r.rush).length,rf=fullR.filter(r=>r.rush).length,bits=[];
  if(kn.length)bits.push(`<b style="color:${SITE_C[top]}">${top} ${Math.max(nA,nB)}/${kn.length}</b>`);
  if(rl)bits.push(tl("rush on eco {a}/{b}",{a:rl,b:lowR.length}));if(rf)bits.push(tl("rush on full buy {a}/{b}",{a:rf,b:fullR.length}));
  if(!bits.length)return "";
  return `<div class="vhab"><span>${tl("THEM THIS HALF")}</span>${bits.join(" · ")}<em>${buyLow(p,g,cur)?tl("now: eco"):tl("now: full buy")}</em></div>`}
function vOdds(r,h){return vHead(h||tl("WHERE THEY GO · LIKELY"))+`<div class="vodds">${vRows([{l:"A",v:r.A,c:SITE_C.A},{l:"B",v:r.B,c:SITE_C.B},{l:"?",v:r.none,c:"var(--muted)"}])}</div>`}
// a rush: how likely, and where it goes (the most likely in big, the second smaller and fainter)
function vRush(TS,g,r){const PLs=tsidePlays(TS,g.map,g,evFor(g),r);if(!PLs)return "";
  const rn=r.live?Math.round(100*calRush(PLs.rush)):r.rush,rs=(PLs.list||[]).filter(x=>/^rush/.test(x.p)).sort((a,b)=>b.v-a.v);
  if(rn<15||!rs.length)return "";
  const lab=x=>`${x.site} · ${vShort(String(x.label||"").replace(/^Rush [AB]( through )?/,""))}`;
  const lead=rs[0].v-((rs[1]||{}).v||0)>=.1;   // where it goes: only when one destination stands out (close numbers only overload)
  return `<div class="vbig ${rn>=40?"bad":"warn"}"><b>${tl("RUSH {p}%",{p:rn})}</b><span>${tl("likely · until {t}",{t:clock(32)})}${lead?` · ${esc(lab(rs[0]))}`:""}</span></div>`}
// where the fights are at this moment of the round (deaths of both sides in the base, on the likely site when the
// read leans one way): three zones, fainter as they get less likely
function vFights(M,g,r){const D=((M&&M.evidence)||{}).deaths;if(!D)return "";const w=WIN_OF(g.elapsed||0);
  const lean=r&&Math.abs(r.A-r.B)>=12?(r.A>r.B?"A":"B"):"all",acc={};let tot=0;
  for(const side of ["CT","T"]){const src=((D[side]||{})[lean]||{})[w]||((D[side]||{}).all||{})[w];if(!src)continue;
    src.zones.forEach(z=>{acc[z.zone]=(acc[z.zone]||0)+z.pct*src.n});tot+=src.n}
  const top=Object.entries(acc).sort((a,b)=>b[1]-a[1]).slice(0,3);if(!top.length||!tot)return "";
  return vHead(IC("swords")+" "+tl("FIGHTS NOW · SHARE OF DUELS"))+vRows(top.map(([z,v],i)=>({l:vShort(z),v:v/tot,c:"var(--ink)",o:[1,.75,.5][i]})))}
// before the round (CT): where the Ts come from, one entrance per line
function vEntries(TS,g,r){const PLs=tsidePlays(TS,g.map,g,evFor(g),r);if(!PLs)return "";
  const top=PLs.lanes.filter(L=>L.p>=0.05).sort((a,b)=>b.p-a.p);if(!top.length||top[0].p-((top[1]||{}).p||0)<.12)return "";   // one entrance stands out, or nothing
  return vHead("⇢ "+tl("ENTRY · LIKELY"))+vRows([{l:`${top[0].site} · ${vShort(top[0].name)}`,v:100*top[0].p,c:SITE_C[top[0].site]}])}
// the call you just made, as the coach understood it (it counts like a tap on the T read)
function vCall(g){const c=g&&g.call;if(!c||c.round!==g.round||Date.now()/1000-c.t>12)return "";
  const bits=[c.rush?tl("rush"):"",c.n?String(c.n):"",c.site||"",c.zone?vShort(c.zone):"",c.bomb?"💣":""].filter(Boolean);
  return bits.length?`<span class="vchip good">${IC("mic")} ${esc(bits.join(" · "))}</span>`:""}
// your teammates' money, seen while you watched them last round: what they'll have now (≈: their kills not counted)
function vMates(g){const M=g.mates||{},prev=(g.round||0)-1;if(prev<1||halfStart(g.round)===g.round)return "";
  const R=((g.hist||{}).rounds||{})[prev]||{},won=R.win===g.side,L=g.losses||0,gain=won?ECON.win:ECON.bonus[Math.max(0,Math.min(L-1,4))],need=g.side==="CT"?3900:3700;
  const xs=Object.values(M).filter(m=>m.money!=null&&m.money_round===prev).map(m=>({n:m.name||tl("mate"),v:Math.min(ECON.cap,m.money+gain)})).slice(0,3);
  return xs.map(x=>`<span class="vchip ${x.v>=need?"good":"bad"}">${IC("users")} ${esc(vShort(x.n))} ≈${kMoney(x.v)} ${x.v>=need?"✓":"✕"}</span>`).join("")}
// T: CTs pushing past a neutral zone, one line per zone (share of rounds, when); red: the push often gets a kill;
// once its moment is past, the line fades
// this match: the zones you called in the first 40 s of the rounds of this half, the ones seen in 2 rounds or more (the
// other team's habit: "they retake the banana every round"), share of the rounds of the half
function vEarlyMatch(g){const H=g.hist||{},Mk=H.marks||{},R=H.rounds||{},hs=halfStart(g.round||1),n=[];
  for(let r=hs;r<(g.round||0);r++)if((R[r]||{}).side===g.side||!(R[r]||{}).side)n.push(r);if(n.length<3)return "";
  const c={};n.forEach(r=>((Mk[r]||{}).early||[]).forEach(z=>c[z]=(c[z]||0)+1));
  const top=Object.entries(c).filter(([,k])=>k>=2).sort((a,b)=>b[1]-a[1]).slice(0,2);if(!top.length)return "";
  return vHead(IC("eye")+" "+tln(n.length,"THIS MATCH · EARLY CONTACT · {n} ROUND","THIS MATCH · EARLY CONTACT · {n} ROUNDS"))+vRows(top.map(([z,k],i)=>({l:`${vShort(z)} · ${k}/${n.length}`,v:100*k/n.length,c:"var(--bad)",o:i?.75:1})))}
function vPush(p,g){const E=typeof ctPush==="function"?ctPush(p,g):null;if(!E||!E.gates.length)return "";const el=g.round_phase==="live"?(g.elapsed||0):0;
  const rows=E.gates.map((x,i)=>({l:`${vShort(x.gate||"?")} · ${clock(x.t)}`,v:x.share,c:x.kill>=30?"var(--bad)":"var(--ct)",o:el>x.t+6?.35:[1,.85,.7,.6][i]}));
  return vHead(IC("arrow-right")+" "+tl("CT PUSHES · {buy} · OF ROUNDS",{buy:E.label}))+vRows(rows)}
// after a frustrated moment (said "coach, énervé", a shout after your death or a lost round) or two rounds lost dead
// without a kill: one thing to do this round, from your own data (an early death: no dry peek; otherwise: the trade)
function resetWhy(g){if(g.round_phase!=="freezetime"||!g.hist)return null;const R=g.hist.rounds||{},Mk=g.hist.marks||{},cur=g.round,prev=cur-1;if(!(prev>=1))return null;
  const mk=n=>Mk[n]||{},frus=[prev,cur].some(n=>mk(n).mood==="frustration"||mk(n).heat),doubt=[prev,cur].some(n=>mk(n).mood==="doubt");
  const bad=n=>{const x=R[n]||{};return !!(x.win&&x.side&&x.win!==x.side&&x.dead!=null&&!(x.kills||[]).length)};
  const early=[prev,prev-1].some(n=>{const x=R[n]||{};return x.dead!=null&&x.dead<30});
  // the game before was a bad one, in the same session: the first rounds (2 to 5) are where it costs, from your matches
  const C=typeof P==="function"&&P()?(((P().advice||{}).plan||{}).carry):null,last=C&&C.last;
  const carry=last&&last.kind==="bad"&&g.round>=2&&g.round<=5&&halfStart(g.round)===1&&Date.now()-Date.parse(last.end)<3*3600e3&&C.bad.adr_first<C.bad.adr_rest-5;
  return frus?{k:"frus",early}:bad(prev)&&bad(prev-1)?{k:"bad",early}:doubt?{k:"doubt",early}:carry?{k:"carry",early:true,C}:null}
// the simple plan of the round: T, path 1 and when to be on the site; CT, your spot of the buy card
function simplePlan(p,g){if(g.side==="T"){const W=typeof winsRank==="function"?winsRank(p,g):null,r=W&&W.rows[0];if(!r)return null;
    const ps=pathShort(p,g,r),pts=(r.route||{}).pts,end=pts&&pts[pts.length-1],tm=r.timing,win=tm&&tm.win-tm.mean>=3;
    return {head:ps.head,ps,via:ps.via,lo:win?tm.lo:null,hi:win?tm.hi:null,at:!win&&end&&end[3]!=null?end[3]:null}}
  const KB=(((((p.advice.plan||{}).buys||{}).maps||{})[g.map]||{})[g.side]||{}),k=KB[advisedType(g)]||KB.full||{};
  return k.zone?{spot:k.zone.key}:null}
function vReset(p,g){const w=resetWhy(g);if(!w)return "";
  if(w.k==="doubt"){const sp=simplePlan(p,g);if(!sp)return "";
    return `<div class="vreset plan"><b>${tl("PLAN")}</b><span>${sp.spot?`${IC("map-pin")} ${vShort(sp.spot)} · ${tl("molly for their arrival")}`:`${esc(sp.head)}${sp.via?" "+tl("via {way}",{way:esc(sp.via)}):""} · ${sp.lo!=null?tl("on site {a}-{b}",{a:clock(sp.lo),b:clock(sp.hi)}):sp.at!=null?tl("on site ~{t}",{t:clock(sp.at)}):""}`}</span></div>`}
  if(w.k==="carry")return `<div class="vreset"><b>${tl("CALM START")}</b><span>${IC("users")} ${tl("play the trade")} · ✕ ${tl("no dry peek before {t}",{t:clock(30)})}</span><small>${tl("after a bad game · ADR rounds 2-5 {a} vs {b} later",{a:w.C.bad.adr_first,b:w.C.bad.adr_rest})}</small></div>`;
  const MS=(p.advice.plan||{}).mood,A_=MS&&MS.after,O_=MS&&MS.other;   // what a tilt costs you: rounds won first, else damage
  const data=A_&&O_?(O_.won-A_.won>=3?`<small>${tl("after a tilt · won {a}% vs {b}%",{a:A_.won,b:O_.won})}</small>`:O_.adr-A_.adr>=5?`<small>${tl("after a tilt · ADR {a} vs {b}",{a:A_.adr,b:O_.adr})}</small>`:""):"";
  return `<div class="vreset"><b>${tl("RESET")}</b><span>${w.early?"✕ "+tl("no dry peek before {t}",{t:clock(30)}):IC("users")+" "+tl("play the trade: next to a mate")}</span>${data}</div>`}
// 20/10, the user: "enlève le TTS sur le module live": the coach no longer speaks (the buy time's lines, "call it!"
// after your death, Wily's answers read out); the cards above say it all on the panel
// T: the site left open by what you called in the last 25 s (two CTs or more on one side and none on the other, or a
// site said clear): where the bomb should go
function vOpen(g){if(g.side!=="T"||g.bomb==="planted"||!g.seen||g.seen.round!==g.round)return "";
  const now=Date.now()/1000,cs=(g.seen.calls||[]).filter(c=>now-c.t<=25);if(!cs.length)return "";
  const n={A:0,B:0},clear={A:false,B:false};
  cs.forEach(c=>{if(c.clear&&c.site){clear[c.site]=true;return}
    const regs=c.regs&&c.regs.length?c.regs:(c.site?[c.site]:[]);
    if(regs.length===1)n[regs[0]]+=c.n||1;else regs.forEach(x=>n[x]+=1)});
  const open=["A","B"].find(s=>{const o=s==="A"?"B":"A";return (clear[s]||(n[o]>=2&&n[s]===0))&&!clear[o]&&!n[s]});
  if(!open)return "";const o=open==="A"?"B":"A",age=Math.round(now-Math.max(...cs.map(c=>c.t)));
  return `<div class="vbig good"><b>${tl("{site} OPEN",{site:open})}</b><span>${tl("go {site}",{site:open})} · ${n[o]?tl("{n} seen {site}",{n:n[o],site:o}):tl("{site} clear",{site:open})} · ${tl("{s}s ago",{s:age})}</span></div>`}
// T: when the CTs push past a neutral zone, the Ts' rounds won by their answer (the site, fast or late), at equal
// economy. Buy time: the most likely push (15% of rounds or more); in the round: the zone you just called
function vPushAns(p,g,live){if(g.side!=="T")return "";const PA=((((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{}).push_answers;if(!PA)return "";
  const called=(g.seen&&g.seen.round===g.round?g.seen.calls||[]:[]).map(c=>c.zone).filter(Boolean);
  let A=called.length?PA.find(a=>called.some(z=>z===a.gate||String(a.gate).includes(z)||String(z).includes(a.gate))):null;
  if(!A&&!live){const E=typeof ctPush==="function"?ctPush(p,g):null,top=E&&E.gates[0];if(top&&top.share>=15)A=PA.find(a=>a.gate===top.gate)}
  if(!A)return "";
  return vHead(tl("IF THEY PUSH {zone} · WON",{zone:vShort(A.gate)}))+vRows(A.answers.slice(0,2).map((a,i)=>({l:`${a.site} ${a.tempo==="fast"?`${tl("fast")} ›${clock(45)}`:`${tl("late")} ‹${clock(45)}`}`,v:a.won,c:SITE_C[a.site],o:i?.7:1})))}
// the zones to check on a path: the enemy spots within 90 px of its way (bomb maps: where the CTs stand and the angles
// they kill from at that moment; hostage maps: where the Ts hold and the spots they kill CTs from), kill spots first
function focusChecks(p,g,r){if(!r||!r.route||!r.route.pts)return [];const pts=r.route.pts,near=s=>s&&s.px&&pts.some(q=>Math.hypot(q[0]-s.px[0],q[1]-s.px[1])<90&&(!s.level||!q[2]||s.level===q[2]));
  let hold=[],dang=[];
  if(isHostage(g.map)){const H=((p.advice.plan||{}).hostage||{})[g.map]||{};hold=H.holds||[];dang=H.danger||[]}
  else{const CS=((((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{}).ct_spots||{},el=g.round_phase==="live"?(g.elapsed||0):0,tt=Math.max(el+15,20),W=CS[tt<20?"early":tt<40?"setup":tt<70?"hit":"late"]||CS.setup||{};hold=W.hold||[];dang=W.danger||[]}
  const out=[],seen=new Set();
  [...dang.filter(near).map(s=>({zone:s.zone,d:true})),...hold.filter(near).map(s=>({zone:s.zone,d:false}))].forEach(z=>{if(z.zone&&!/spawn/i.test(z.zone)&&!seen.has(z.zone)){seen.add(z.zone);out.push(z)}});
  return out.slice(0,4)}
// the focus on the path you pressed: the path, when to be there, your grenades for it, the zones to check
function vFocus(p,g){const n=focusN(g);if(!n)return "";const H=isHostage(g.map),W=H?hostageRank(p,g):typeof winsRank==="function"?winsRank(p,g):null,r=W&&W.rows.find(x=>x.rank===n);if(!r)return "";
  let head,when;
  if(H){head=tl("Hostages via {way}",{way:r.route.zones.slice(-2).join(" > ")});when=tl("there ~{t}",{t:clock(r.t_end)})}
  else{const ps=pathShort(p,g,r),pts=(r.route||{}).pts,end=pts&&pts[pts.length-1];head=`${ps.head}${ps.via?" "+tl("via {way}",{way:ps.via}):""}`;when=onSite(r.timing,end)}
  const nd=vNades(vNadePicks(p,g)),chk=focusChecks(p,g,r),ps=vPathStuff(p,g,r);
  return `<div class="vfocus" style="--c:${r.col}"><b>${n}</b><div><span>${esc(head)}</span><small>${esc(when||"")}${r.wr!=null?" · "+tl("{p}% won",{p:Math.round(r.wr)}):""}</small></div><em title="${tl("numpad minus drops the focus")}">− ${tl("off")}</em></div>
    ${nd}${ps}${chk.length?`<div class="vchips">${chk.map(z=>`<span class="vchip ${z.d?"bad":""}">${z.d?IC("triangle-alert"):IC("eye")} ${vShort(z.zone)}</span>`).join("")}</div>`:""}`}
// the path you pressed: every lineup of the base that lands on its site or along it, the best first (6 at most)
function vPathStuff(p,g,r){const E=((((p.advice.plan||{}).nades||{}).maps||{})[g.map]||{})[g.side],P=(E&&E.pool)||[];const pts=r&&r.route&&r.route.pts;if(!P.length||!pts)return "";
  const GEO=((((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{}).geo,sk=(r.k.match(/[AB]$/)||r.k.match(/^[AB]/)||[])[0],S=GEO&&GEO.sites&&sk?GEO.sites[sk]:null,end=pts[pts.length-1];
  const lvOK=(a,b)=>!a||!b||a===b,near=(a,d,lv)=>a&&pts.some(q=>Math.hypot(q[0]-a[0],q[1]-a[1])<d&&lvOK(lv,q[2]));
  const fit=x=>{if(!x.to_px||x.post>=50)return 0;const lv=x.land_level||x.level;
    if((S&&Math.hypot(x.to_px[0]-S.px[0],x.to_px[1]-S.px[1])<190&&lvOK(lv,S.level))||(end&&Math.hypot(x.to_px[0]-end[0],x.to_px[1]-end[1])<170&&lvOK(lv,end[2])))return 2;
    return near(x.to_px,60,lv)&&near(x.from_px,140,x.level)?1:0};
  const L=P.map(x=>({x,f:fit(x)})).filter(o=>o.f).sort((a,b)=>b.f-a.f||b.x.score-a.x.score).slice(0,6).map(o=>o.x);if(!L.length)return "";
  return `<div class="vstuff">${L.map(x=>`<span style="--c:${NADE_C[x.type]||"#ccc"}"><i>${vLetter[x.type]||"?"}</i>${vShort(x.to)}<small>${esc(x.from||"")} · ${esc(HOWL(x.how||""))}${x.timer?` · ${x.timer}`:""}</small></span>`).join("")}</div>`}
// hostage maps: the CTs' ways (attack: rounds won; defense: share of the CT walks, where they come from)
function vHostRoutes(p,g,def){const W=hostageRank(p,g);if(!W)return "";
  return vHead(def?tl("THEY COME FROM · OF CT WALKS"):tl("YOUR WAYS · ROUNDS WON"))+vRows(W.rows.map((r,i)=>({l:`${r.rank} · ${vShort(r.route.zones.slice(-2).join(" > "))} · ${clock(r.t_end)}`,v:def?r.share:r.wr,c:r.col,o:[1,.8,.65][i]})))}
// a lineup book of the map (made by a player: where to stand, where to aim): the lineups of the site you go to for the
// grenades you have (none yet at the buy time: the site's), two at most, as the aim picture and the title
function bookFor(p,g,r){const B=((p.advice.plan||{}).lineups||{})[g.map];if(!B||!(B.lineups||[]).length)return null;let sites=[];
  if(g.side==="T"){const W=typeof winsRank==="function"?winsRank(p,g):null,RF=W&&(W.rows.find(x=>x.rank===focusN(g))||W.rows[0]);
    const s=RF?(RF.k.match(/[AB]$/)||RF.k.match(/^[AB]/)||[])[0]:null;if(s)sites.push(s);if(RF&&((RF.route||{}).zones||[]).some(z=>/mid/i.test(z)))sites.push("Mid")}
  else{if(r&&r.A!==r.B)sites.push(r.A>r.B?"A":"B");else sites.push("A","B")}
  const held=Object.entries(g.nades||{}).filter(([t,v])=>v>0).map(([t])=>t);
  const L=B.lineups.filter(x=>x.side===g.side&&sites.includes(x.site)&&(!held.length||held.includes(x.type)));
  const pri=g.side==="CT"?["molotov","smoke","flash","he"]:["smoke","flash","molotov","he"];   // CT: the molly first (it buys time), T: the smoke
  return L.length?{book:B,list:L.sort((a,b)=>sites.indexOf(a.site)-sites.indexOf(b.site)||pri.indexOf(a.type)-pri.indexOf(b.type)).slice(0,2)}:null}
function vBook(p,g,r){const F=bookFor(p,g,r);if(!F)return "";
  return vHead(IC("book-open")+" "+tl("LINEUPS · {author}",{author:esc(F.book.author)}))+`<div class="vbook">${F.list.map(x=>`<a href="${esc(x.link)}" target="_blank" rel="noopener" title="${esc([x.position,x.aim].filter(Boolean).join(" · "))}"><img src="${esc(x.img_aim||x.img_position||"")}" alt="" loading="lazy"><span><b style="color:${NADE_C[x.type]||"#ccc"}">${vLetter[x.type]||"?"}</b> ${esc(x.title.replace(/\s*(smoke|flash|molly)$/i,""))}${x.throw?` <em>${esc(HOWL(x.throw.toLowerCase()))}</em>`:""}</span><small>${esc(x.position||"")}</small></a>`).join("")}</div>`}
// you just died: the info, now (where, how many, how hurt). Your rounds with a call before your death are won far
// more often; a few seconds of a big reminder, and the voice once per round (setting "Say 'info' when I die")
function deadAgo(g){const R=(((g.hist||{}).rounds||{})[g.round])||{};return g.round_phase==="live"&&R.dead!=null?(g.elapsed||0)-R.dead:null}
function calledSince(g,a){const c=g&&g.call;return !!(c&&c.round===g.round&&c.t>=Date.now()/1000-a-.5)}   // you gave an info after your death
// CT: numpad 7 (A) / 9 (B): the site you play this round
const mySite=g=>{const s=(((g.hist||{}).marks||{})[g.round]||{}).me_site;return s==="A"||s==="B"?s:null};
function vMySite(p,g,onLine){const s=mySite(g);if(!s)return "";const E=(((p.advice.plan||{}).nades||{}).maps||{})[g.map],C=E&&E.CT,L=(C&&C.lanes)||{};
  const TS=(p.advice.plan||{}).tside,M=((TS||{}).maps||{})[g.map]||{},GS=(M.geo||{}).sites||{},S=GS[s];
  // the stuff of the site, entrance by entrance (the grenades that close each entrance of the Ts)
  const st=[];Object.entries(L).filter(([k])=>k[0]===s).forEach(([k,o])=>["smoke","molotov","flash","he"].forEach(t=>{const x=o[t];if(x&&st.length<5&&!st.some(y=>y.to===x.to&&y.type===t))st.push({...x,type:t})}));
  const holds=(((M.ct_spots||{}).early||{}).hold||[]).filter(h=>S&&Math.hypot(h.px[0]-S.px[0],h.px[1]-S.px[1])<260&&(!h.level||!S.level||h.level===S.level)).slice(0,3);
  return `<div class="vfocus" style="--c:#5ab4ff"><b>${s}</b><div><span>${tl("You hold {site}",{site:s})}</span><small>${tl("numpad 7 A · 9 B")}</small></div></div>
   ${st.length&&!onLine?`<div class="vchips">${st.map(x=>`<span class="vchip" style="border-color:${NADE_C[x.type]||"#ccc"}">${vLetter[x.type]||"?"} ${vShort(x.to)} <small>${esc(x.from||"")}${x.timer?` · ${x.timer}`:""}</small></span>`).join("")}</div>`:""}
   ${holds.length?`<div class="vchips">${holds.map(h=>`<span class="vchip">${IC("shield")} ${vShort(h.zone)}</span>`).join("")}</div>`:""}`}
// the post-plant / retake grenades of a side that land on that site (the base's: every lineup thrown after a plant)
function postStuff(p,g,side,site){const E=((((p.advice.plan||{}).nades||{}).maps||{})[g.map]||{})[side],S=(((((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{}).geo||{}).sites||{},c=S[site],held=g.nades||{};
  if(!E||!c)return [];const at=x=>x.to_px&&Math.hypot(x.to_px[0]-c.px[0],x.to_px[1]-c.px[1])<230&&(!x.land_level||!c.level||x.land_level===c.level);
  const L=[];Object.entries(E.types||{}).forEach(([t,v])=>(v.post||[]).forEach(x=>L.push({...x,type:t})));(E.pool||[]).filter(x=>(x.post||0)>=30).forEach(x=>L.push(x));
  return L.filter(at).filter(x=>(held[x.type]||0)>0).filter((x,i,a)=>a.findIndex(y=>y.type===x.type&&y.to===x.to&&y.from===x.from)===i).sort((a,b)=>(b.score||0)-(a.score||0)).slice(0,3)}   // the grenades you hold (07/10)
// after the plant (09/10, the user: CT "vu que j'ai encore du stuff, propose-moi du stuff de retake: la smoke, la molo, la
// grenade ninja"; T "j'ai une grenade, propose-moi du stuff de défense"): the base's throws after a plant on that site
// (4 or more, by 3 players or more), with the grenades you hold. CT: landing on the site, thrown from outside it (from
// your way in first); T: thrown from the site or around it, landing where the CTs come from. One place, its stack
function postPlan(p,g,side,site,way){const TD=tdirsOf(g.map)||{},L=(TD.lineups||{})[side]||[],held=g.nades||{};if(!site||!L.length)return null;
  const S=((((((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{}).geo||{}).sites||{})[site];if(!S)return null;
  if(!Object.values(held).some(v=>v>0))return {stacks:[],why:tl("no grenade left"),post:true};
  const RS=1.15*Math.max(60,...(TD.gates||[]).filter(x=>x.site===site&&!x.mid&&(!x.level||!S.level||x.level===S.level)).map(x=>Math.hypot(x.px[0]-S.px[0],x.px[1]-S.px[1])));
  const d=(xy,lv)=>!lv||!S.level||lv===S.level?Math.hypot(xy[0]-S.px[0],xy[1]-S.px[1]):1e9;
  const C=L.filter(u=>u.from_px&&u.to_px&&(held[u.type]||0)>0&&((u.w||[])[4]||0)>=4&&(u.players||0)>=3
      &&(side==="CT"?d(u.to_px,u.land_level)<RS*1.3&&d(u.from_px,u.level)>RS*.6:d(u.from_px,u.level)<RS*1.6))
    .map(u=>({...u,s:(u.w||[])[4]}));
  if(!C.length)return {stacks:[],why:tl("none for your grenades"),post:true};
  const A=[];C.sort((a,b)=>b.s-a.s).forEach(u=>{const a=A.find(x=>x.lv===(u.level||null)&&Math.hypot(x.c[0]-u.from_px[0],x.c[1]-u.from_px[1])<55);if(a)a.L.push(u);else A.push({c:u.from_px,lv:u.level||null,L:[u]})});
  const pick=a=>{const left={...held},out=[];a.L.forEach(u=>{if((left[u.type]||0)>0&&!out.some(x=>x.type===u.type&&x.to_key===u.to_key)){left[u.type]--;out.push(u)}});return out};
  const onWay=a=>!!(way&&way.length&&way.some(q=>Math.hypot(q[0]-a.c[0],q[1]-a.c[1])<90));
  const B=A.map(a=>({a,out:pick(a)})).sort((x,y)=>(y.out.length*1000+(onWay(y.a)?500:0)+y.out.reduce((s_,u)=>s_+u.s,0))-(x.out.length*1000+(onWay(x.a)?500:0)+x.out.reduce((s_,u)=>s_+u.s,0)))[0];
  const st=B.out.sort((a,b)=>NADE_ORDER.indexOf(a.type)-NADE_ORDER.indexOf(b.type));
  return {stacks:[st],buy:false,prac:u=>(TD.practiced||[]).includes(pracKey(side,u)),SH:TD.shots||{},side,tempo:null,post:true}}
// T after the plant on a site you gave (numpad 7 / 9, or said): where to hold, the post-plant stuff (09/10: no rotation
// on T, "la rotation de là où c'est planté par rapport à là où je suis en T, ça ne me sert à rien")
function vPostPlant(p,g,site){const M=(((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{},PP=(M.postplant||{})[site];
  const P=postPlan(p,g,"T",site,null),hs=((PP||{}).holds||[]).slice(0,3);if(!hs.length&&!(P&&P.stacks.length))return "";
  // where to hold: the spots alone (07/10: their rounds won are near 100 % for every spot the Ts stay alive on, so no
  // bars; the map circles them)
  return `${hs.length?`<div class="vchips"><span class="vchip good">${IC("shield-check")} ${tl("HOLD {site}",{site})} · ${hs.map((h,i)=>`${vShort(h.zone||"?")}${i?"":" ★"}`).join(" · ")}</span></div>`:""}
   ${P&&P.stacks.length?vBombLine(P,g)+vStuff(P,tl("POST-PLANT UTILITY · {site}",{site})):""}`}
// CT after the plant: the retake. The spots to check (where Ts hold after a plant there), the way from your site, the stuff
function vRetake(p,g,site){const TS=(p.advice.plan||{}).tside,M=((TS||{}).maps||{})[g.map]||{},PP=((M.postplant||{})[site]||{}).holds||[];
  const dir=tdirSel(g).dir||mySite(g),RX=rotFromDir(M,site,dir,g.map),rot=vRotLine(RX,dir,site,g.map);   // where you said you play this round (numpad 1-2-3, 7 / 9 before the plant)
  const P=postPlan(p,g,"CT",site,RX&&RX.routes[0]?RX.routes[0].pts:null);   // the retake stuff, from your way in first
  const zs=[...new Set(PP.slice(0,4).map(h=>h.zone).filter(Boolean))];
  return (`${rot}
   ${zs.length?`<div class="vchips">${zs.map(z=>`<span class="vchip bad">${IC("triangle-alert")} ${tl("check {zone}",{zone:vShort(z)})}</span>`).join("")}</div>`:""}
   ${P&&P.stacks.length?vStuff(P,tl("RETAKE UTILITY · {site}",{site})):""}`).trim()}
// this match's peek timings: the zones you called at the same moment (±8 s) in two rounds or more of this half and side;
// el: now (live: only the ones still to come), null at the buy time
function vPeekTimes(g,el){const H=g.hist||{},Mk=H.marks||{},R=H.rounds||{},hs=halfStart(g.round||1),by={};
  for(let r=hs;r<(g.round||0);r++){if((R[r]||{}).side&&(R[r]||{}).side!==g.side)continue;((Mk[r]||{}).seen_t||[]).forEach(([z,e])=>{if(e!=null)(by[z]=by[z]||[]).push(e)})}
  const out=[];Object.entries(by).forEach(([z,ts])=>{ts.sort((a,b)=>a-b);let best=null;
    ts.forEach(t=>{const near=ts.filter(u=>Math.abs(u-t)<=8);if(near.length>=2&&(!best||near.length>best.n))best={n:near.length,t:near[Math.floor(near.length/2)]}});
    if(best&&(el==null||best.t>el-3))out.push({z,...best})});
  if(!out.length)return "";out.sort((a,b)=>a.t-b.t);
  return `<div class="vchips">${out.slice(0,3).map(o=>`<span class="vchip warn">⏱ ${vShort(o.z)} ~${clock(o.t)} ×${o.n}</span>`).join("")}</div>`}
// the round after this one, at the round's end: the buy the money calls for (the only look ahead of the panel, 05/10)
function nextBuy(p,g){if(!g||g.round==null||!g.side||g.practice)return null;const n=g.round+1;
  if(n===halfStart(n))return tl("pistol round");
  const pl=econPlan(p,Object.assign({},g,{round:n,round_phase:"freezetime"}));
  return pl&&pl.best?({eco:tl("eco"),half:tl("half buy"),force:tl("force buy"),full:tl("full buy")}[pl.best.k]||esc(pl.best.k)):null}
function vInfo(g){const a=deadAgo(g);return a!=null&&a>=2.5&&a<=9&&!calledSince(g,a)?`<div class="vbig warn"><b>${IC("megaphone")} ${tl("INFO")}</b><span>${tl("where · how many · how hurt")}</span></div>`:""}
const expOn=(p,t)=>(((((p||{}).advice||{}).plan||{}).experiments||{}).experiments||[]).some(e=>e.status==="active"&&e.template===t);
// the panel's slots, top to bottom. One slot per kind of info: the ones that never show together share it (before the
// plant your site, after it the retake; T plant timer / bomb down / CT rotation), the ones that can show together have
// their own (a call understood and "l'info")
const SLOTS=["call","info","alert","reset","key","focus","read","play","hold","book","peek","early","eco","evid","tchips"];
// the height each slot reached in this phase (buy time, live, end), for this map and side: kept the whole half, so after
// a round nothing moves any more
const SLOTH={key:"",h:{}};
const SLOT_EMPTY={call:IC("mic")+" "+tl("call"),info:IC("megaphone")+" "+tl("info"),alert:IC("bomb")+" "+tl("bomb · rotation")};   // a reserved slot waiting: a faint frame
function slotted(g,P){const k=`${g.map}|${g.side}|${g.round_phase}`;if(SLOTH.key!==k){SLOTH.key=k;SLOTH.h={}}
  // live: the alerts keep their room from the start of the round (a call when the mic listens, l'info while alive)
  const R=g.round_phase==="live"?{alert:68,info:68,call:g.mic?40:0}:{};
  return SLOTS.map(s=>{const html=(P[s]||[]).filter(Boolean).join(""),mh=Math.max(SLOTH.h[s]||0,R[s]||0);
    if(!html&&!mh)return "";
    return `<div class="vslot${html?"":" wait"}" data-slot="${s}" style="min-height:${mh}px">${html?`<div class="vslot-in">${html}</div>`:SLOT_EMPTY[s]?`<span>${SLOT_EMPTY[s]}</span>`:""}</div>`}).join("")}
// after the page is drawn: each slot's height in this phase (its room for the next draws)
function slotMeasure(root){(root?root.querySelectorAll(".vslot:not(.wait)"):[]).forEach(el=>{const s=el.dataset.slot,h=el.firstElementChild?el.firstElementChild.offsetHeight:0;
  if(h>(SLOTH.h[s]||0))SLOTH.h[s]=h})}
function nowVisual(p,g,following){
  if(!following)return nowPanel(p,g,following,{noBuy:true});
  if(g.practice)return `<div id="steps-live">${typeof stepsCard==="function"?stepsCard():""}</div><div class="vz"><div class="vsit"><span>${tl("PRACTICE")}</span></div></div>`;
  if(g.map_phase==="warmup"&&typeof briefVisual==="function")return briefVisual(p,g);   // the map loads: the 60-second brief
  const ph=g.round_phase,ct=g.side==="CT",P={},put=(s,...h)=>{(P[s]=P[s]||[]).push(...h)};
  const TS=(p.advice.plan||{}).tside,r=ct?tsidePredict(TS,g.map,g,evFor(g)):null;
  put("call",vWily(g));   // what Wily understood (06/10)
  const WF=vWilyFocus(p,g);   // the order's card (stuff, fake, post-plant, cover, counter, fake defense, retake): the round's main card
  if(ph==="freezetime"){put("reset",vReset(p,g));put("key",vKey(p,g));
    if(typeof antiEco==="function"&&antiEco(p,g))put("eco",`<span class="vchip bad">! ${tl("eco kill spots on the map: clear them, no close duel")}</span>`);
    // CT, a site said (numpad 1 or 3, 07/10): its card has its arrival curve and its stuff, the timeline and the book go
    const CD=ct&&!WF?vCTDir(p,g,r):"",CDs=!!CD&&tdirSel(g).dir!=="MID",CTL=ct&&r&&!CDs?vCTline(p,g,r):"";
    if(ct)put("focus",WF||CD||vMySite(p,g,!!CTL));
    put("peek",vPeekTimes(g,null));
    if(ct&&r){put("read",vHabits(p,g),vOdds(r));put("play",vRush(TS,g,r)||vEntries(TS,g,r));put("hold",CDs?"":CTL||vHold(p,g,r));if(!CD)put("book",vBook(p,g,r))}
    const HM=isHostage(g.map);if(HM)put("focus",ct?(vFocus(p,g)||vHostRoutes(p,g,false)):vHostRoutes(p,g,true));
    if(!ct&&!HM&&!tdirsLoading(g.map)){const DV=WF||vDir(p,g);put("focus",DV||vFocus(p,g)||vPathCurve(p,g)||vTimeline(p,g));if(!DV)put("book",vBook(p,g,null));put("early",vEarlyMatch(g));   // the way's card has its stuff: no second list
      if(!tdirsOf(g.map)){put("play",vPush(p,g));put("hold",vPushAns(p,g,false));put("tchips",vTchips(p,g))}}}   // the ways' grenades in the card; the CT pushes on the map only (06/10)
  else if(ph==="live"){const el=g.elapsed||0,planted=g.bomb==="planted",dead=deadAgo(g)!=null;put("call",vCall(g));   // dead (05/10): what helps to call stays, your own path and spot go
    put("info",vInfo(g)||(dead&&!planted?`<div class="vsit dead"><span>${tl("YOU'RE OUT")}</span><b>${tl("call what your teammate can't see")}</b></div>`:""));
    if(planted){const left=g.phase_left!=null?g.phase_left:Math.max(0,40-(g.since_plant||0)),as=typeof autoSite==="function"?autoSite(p,g):null;
      put("alert",`<div class="vbig ${ct?"bad":"good"}"><b>${IC("bomb")} ${Math.ceil(left)}s</b><span>${ct?tl("retake together"):tl("hold the bomb")}${as?" · "+(as.said?tl("{site} site, you said it",{site:as.site}):tl("{site} site, {p}% sure",{site:as.site,p:as.p})):" · "+tl("numpad 7 A / 9 B")}</span></div>`);
      if(WF)put("focus",WF);else if(as&&(as.said||as.p>=50))put("focus",ct?vRetake(p,g,as.site):vPostPlant(p,g,as.site))}
    else if(isHostage(g.map))put("focus",ct?(vFocus(p,g)||(el<45?vHostRoutes(p,g,false):"")):(el<45?vHostRoutes(p,g,true):""));
    else if(ct){const CD=!WF&&!dead?vCTDir(p,g,r):"",CDs=!!CD&&tdirSel(g).dir!=="MID",CTL=r&&el<75&&!dead&&!CDs?vCTline(p,g,r):"";if(!dead)put("focus",WF||CD||vMySite(p,g,!!CTL));
      const WM=g.wily_match||{};if(WM.fake||WM.rush||WM.slow)put("evid",`<span class="vchip warn">${IC("mic")} ${tl("they {what} · you said",{what:[WM.fake?tl("fake"):"",WM.rush?tl("rush"):"",WM.slow?tl("play slow"):""].filter(Boolean).join(", ")})}</span>`);
      if(g.call&&g.call.round===g.round&&g.call.nobomb&&g.call.site)put("alert",`<div class="vbig warn"><b>${g.call.n||""} ${esc(g.call.site)} · ${tl("NO BOMB")}</b><span>${tl("likely a fake: hold {site}, don't rotate yet",{site:g.call.site==="A"?"B":"A"})}</span></div>`);put("peek",vPeekTimes(g,el));if(r){put("read",el<20?vHabits(p,g):"",vOdds(r));
        const M=TS&&TS.maps&&TS.maps[g.map];
        put("play",(el<32?vRush(TS,g,r):"")||vFights(M,g,r));
        if(el>=15&&el<=80&&Math.max(r.A,r.B)>=70&&typeof rotationFor==="function"){const X=r.A>r.B?"A":"B",o=X==="A"?"B":"A",R=rotationFor(M,X,`${o} Site`,M.geo),rt=R&&R.routes&&R.routes[0];
          const me=mySite(g);   // where you said you are this round (numpad 7 / 9, or said)
          if(rt&&me!==X)put("alert",`<div class="vbig warn"><b>${o} → ${X}</b><span>${me===o?tl("you're {site}: rotate now",{site:o}):tl("if you hold {site}: rotate",{site:o})} · ${rt.travel!=null?`${Math.round(rt.travel)} s · `:""}${tl("{p}% die on the way",{p:rt.died})}</span></div>`)}   // the hit leans hard to one site
        if(el<75&&!dead&&!CDs)put("hold",CTL||(el<60?vHold(p,g,r):""));
        (r.sev||[]).slice(0,2).forEach(ev=>put("evid",`<span class="vchip ${ev.fight?"bad":""}">● ${esc(ev.t)}</span>`))}}
    else{const TDm=tdirsOf(g.map)||tdirsLoading(g.map);put("read",vOpen(g));put("peek",vPeekTimes(g,el));if(!dead&&!tdirsLoading(g.map))put("focus",WF||vDir(p,g)||vFocus(p,g)||vPathCurve(p,g)||vTimeline(p,g));
      put("play",(el<45&&!dead&&!TDm&&vPush(p,g))||vFights(TS&&TS.maps&&TS.maps[g.map],g,null));if(!dead&&!TDm)put("hold",el<50?vPushAns(p,g,true):"");
      const left=g.phase_left!=null?g.phase_left:Math.max(0,RLEN()-el);
      if(left<=45)put("alert",`<div class="vbig bad"><b>${tl("PLANT")} ${Math.floor(left/60)}:${String(Math.floor(left%60)).padStart(2,"0")}</b><span>${left>20?tl("commit now"):tl("plant or save")}</span></div>`);
      else if(!dead&&!TDm)put("tchips",vTchips(p,g))}}
  else if(ph==="over"){const nx=nextBuy(p,g);put("call",`<div class="vsit"><span>${tl("ROUND {n}",{n:g.round})}</span>${g.win_team?`<b class="${g.win_team===g.side?"good":"bad"}">${g.win_team===g.side?tl("WON"):tl("LOST")}</b>`:""}</div>${nx?`<div class="vnext">${tl("Next round")} · <b>${nx}</b></div>`:""}`)}
  const html=slotted(g,P);
  return `<div class="vz">${html||`<div class="vsit"><span>${tl("ROUND {n}",{n:g.round||""})}</span></div>`}</div>`}
// the buy notification of the full-screen view: one compact card, no paragraph, never scrolls
// the grenades to buy, for the two economies. CT: molly and smoke first (a hit that meets one still burning or
// standing costs the Ts 10 to 20 points of rounds won, every map together), the molly ahead when a rush is likely, with
// what it does to a rush; T against eco CTs: flash and molly first, for the close spots where they wait
function nadeCtx(p,g,E){if(!E||!E.order||!E.order.length)return {E,chip:""};
  const TS=(p.advice.plan||{}).tside||{},UE=TS.util_econ||{},ew=econW(p,g),low=(ew.pistol||0)+(ew.low||0);
  const re=first=>({...E,order:[...first.map(t=>E.order.find(o=>o.type===t)).filter(Boolean),...E.order.filter(o=>!first.includes(o.type))]});
  if(g.side==="CT"){const r=TS.maps?tsidePredict(TS,g.map,g,evFor(g)):null,rush=r?r.rush>=30:low>=.5,U=UE.rush;
    const chip=rush&&U&&U.active&&U.kept?`<span class="vchip good">${IC("flame")} ${tl("molly/smoke on the rush · won {a}% · {b}% without",{a:100-U.active[1],b:100-U.kept[1]})}</span>`:"";
    return {E:re(rush?["molotov","smoke"]:["smoke","molotov"]),chip}}   // against a full buy, the hold card says when
  const ae=typeof antiEco==="function"&&antiEco(p,g);
  return {E:ae||(ew.low||0)>=.6?re(["flash","molotov"]):E,chip:""}}
function buyVisual(p,g){if(g.money==null||!g.side||g.practice)return "";const rt=advisedType(g),PL=p.advice.plan||{},N=PL.nades,NC=nadeCtx(p,g,N&&((N.maps||{})[g.map]||{})[g.side]),E=NC.E;
  const KB=((((PL.buys||{}).maps||{})[g.map]||{})[g.side]||{}),sk=sitKey(p,g),kit=(sk&&sk.endsWith("anti_eco")&&KB["anti-eco"])||KB[rt]||{};
  const full=g.side==="CT"?3900:3700,bonus=[1400,1900,2400,2900,3400][Math.min(g.losses||0,4)];
  const haveRifle=g.primary&&FULL_W.has(g.primary),tags=[];
  const plan=typeof econPlan==="function"?econPlan(p,g):null,bk=plan&&plan.best?plan.best.k:null;
  const ae=typeof antiEco==="function"&&antiEco(p,g);
  const wb=typeof wilyBuy==="function"?wilyBuy(g):null;
  const BT={force:tl("FORCE"),eco:tl("ECO · SAVE"),full:tl("FULL BUY"),pistol:tl("PISTOL"),half:tl("HALF BUY")};
  const RT=wb?(BT[wb]+" "+IC("mic")):ae&&bk!=="eco"?tl("ANTI-ECO"):(bk?BT[bk]:BT[rt])||tl("BUY");
  // a key round: the card's weapon (the same as the key-round card of the panel), never another one
  const ks=typeof keySit==="function"?keySit(p,g):null,kw=ks?keyWeapons(p,g,ks):null,kp=kw&&kw.list.find(w=>!DEF_PISTOL.has(w.w)&&(W_PRICE[w.w]??99999)<=(ks==="force_full"?g.money:kw.budget));
  if(ks==="pistol"){const top=kw&&kw.list[0];tags.push(top&&!DEF_PISTOL.has(top.w)?`<span class="vtag">${IC("key-round")} ${esc(W_SHORT[top.w]||top.w.toUpperCase())}</span>`:`<span class="vtag">${tl("kevlar")}</span>`)}
  else if(ks&&kp&&!haveRifle)tags.push(`<span class="vtag">${IC("key-round")} ${esc(W_SHORT[kp.w]||kp.w.toUpperCase())}${kp.exp?" "+IC("flask-conical"):""}</span>`,...(ks==="force_full"?[`<span class="vtag">${tl("kevlar")}</span>`]:[]));
  else if(bk==="eco")tags.push(`<span class="vtag">${tl("save: buy nothing")}</span>`);   // the plan says save: no weapon to tempt you
  else if(g.side==="CT"&&rt==="full"&&!haveRifle&&expOn(p,"full_rifle_ct"))tags.push(`<span class="vtag">M4 ${IC("flask-conical")}</span><span class="vtag">${tl("kevlar + helmet")}</span>`);   // the experiment: no MAG-7 on a full buy
  else if(kit.kit&&!haveRifle)tags.push(...String(expSwapTxt(p,kit.kit.key)).split(" + ").filter(x=>!/grenade/i.test(x)).map(x=>`<span class="vtag">${esc(KIT_L(x))}</span>`));
  else if(rt==="full"&&!haveRifle)tags.push(`<span class="vtag">${tl("rifle")}</span><span class="vtag">${tl("kevlar + helmet")}</span>`);
  if(haveRifle)tags.push(`<span class="vtag got">${esc(g.primary)} ✓</span>`);
  let nd="",left=g.money;
  if(E&&E.order&&E.order.length&&rt!=="pistol"&&rt!=="eco"){const maxN=rt==="full"?4:2,main=rt==="full"&&!haveRifle?(g.side==="T"?2700:2900)+(g.helmet?0:g.armor>0?350:1000):0;
    const r=nadePlan(E,Math.max(0,g.money-main),g.nades||{},maxN);left=r.left;
    nd=r.plan.length?`<div class="vnades">${r.plan.map(o=>`<span class="vnade now" style="--c:${NADE_C[o.type]||"#ccc"}"><i>${vLetter[o.type]}</i><small>$${o.price}</small></span>`).join("")}</div>`:""}
  const next=(rt==="eco"?g.money:left)+bonus,okNext=next>=full;
  const said=typeof tdirSel==="function"&&!!tdirSel(g).dir;   // a site said (numpad 1-3): its card replaces the usual spot
  const T_=g.side==="T",spot=!T_&&!said&&kit.zone?`<span class="vchip">${IC("map-pin")} ${vShort(kit.zone.key)}</span>`:"",avoid=!T_&&!said&&kit.avoid?`<span class="vchip bad">✕ ${vShort(kit.avoid.key)}</span>`:"";
  const awp=sk&&sk.endsWith("anti_eco")?`<span class="vchip bad">✕ AWP</span>`:"";
  const tc=typeof theirCash==="function"?theirCash(g):null,eb=(typeof enemyBuyW==="function"?enemyBuyW(p,g):enemyBuy(p,g))||{},ebk=["full","force","eco"].filter(k=>(eb[k]||0)>=.5)[0]||(tc&&tc.buy);
  const them=tc?`<div class="vthem"><span>${tl("THEM")}</span><b>~${money(tc.cash)}</b>${ebk&&ebk!=="pistol"?`<em class="${ebk==="full"?"bad":ebk==="eco"?"good":"warn"}">${{full:tl("FULL BUY"),force:tl("FORCE"),eco:tl("ECO")}[ebk]}</em>`:""}</div>`:"";
  return `<div class="vbuy"><div class="vbuy-h"><b>${RT}</b><span>${money(g.money)}</span></div>
    ${them}${tags.length?`<div class="vtags">${tags.join("")}</div>`:""}${nd}${spot||avoid||awp?`<div class="vchips">${spot}${avoid}${awp}</div>`:""}</div>`}
