
// ---------- buys over the rounds left in the half, not just this one ----------
// What a buy wins now AND what it leaves for the next rounds: the base's win rates by buy (full / force / eco on each
// side), CS2's money (win $3,250, loss bonus $1,400 to $3,400 that drops one step after a win, kill rewards, a rifle
// kept when you survive), what the other side probably buys after their win or loss (TS.econ), and a small search
// over the next rounds (up to 3, never past the half): the buy now that wins the most rounds over them.
const ECON={win:3250,bonus:[1400,1900,2400,2900,3400],cap:16000,plant:240};   // plant: the T's loss bonus for a plant, on average
const ECON_K=["eco","half","force","full"],ECON_L={eco:tl("ECO"),half:tl("HALF"),force:tl("FORCE"),full:tl("FULL")};
// T win chance by T buy and CT buy, from the base's situations; a half buy (pistol + kevlar) sits between eco and force
function econTW(SI){const f=(k,d)=>{const x=SI&&SI[k];return x&&x.t_win!=null?x.t_win/100:d};
  const B={full:{full:f("full_full",.47),force:f("ct_force",.66),eco:f("t_anti_eco",.82)},force:{full:f("t_force",.32),force:.47,eco:.68},
    eco:{full:f("t_eco",.14),force:.3,eco:.47}};
  const tw=(t,c)=>t==="half"?tw("eco",c)+.45*(tw("force",c)-tw("eco",c)):c==="half"?tw(t,"eco")+.45*(tw(t,"force")-tw(t,"eco")):B[t][c];
  return tw}
// what you can buy with this money: cost, kill reward expected, whether it is a rifle you can keep
function econOpts(side,m,hasR,armor,helmet){const T=side==="T",rifle=T?2700:2900,arm=helmet?0:armor>0?350:1000,o=[{k:"eco",c:0,kill:90}];
  if(m>=1150)o.push({k:"half",c:1150,kill:120});
  const fc=T?(m>=2450?2450:1700):(m>=2700?2700:1900);if(m>=fc)o.push({k:"force",c:fc,kill:fc<=1900?360:180});
  const full=(hasR?0:rifle)+arm+(T?0:400);if(m>=full)o.push({k:"full",c:full+Math.min(600,m-full),kill:210});
  return o}
// the other side's buy: right after a lost pistol they save, after a won pistol they upgrade; then the base's table
function econEnemy(E,es,r,hs,ePistolWon){if(r===hs+1)return ePistolWon?{eco:0,force:.7,full:.3}:{eco:.9,force:.1,full:0};
  const x=es<=0?E.won:E["lost"+Math.min(es,3)];return x?{eco:x.eco/100,force:x.force/100,full:x.full/100}:{eco:.1,force:.3,full:.6}}
// the other side's losses in a row (0 when they won the last round), from the rounds of the half
function enemyStreak(g){const R=((g.hist||{}).rounds)||{},hs=halfStart(g.round);let es=0,last=null;
  for(let n=g.round-1;n>=hs;n--){const w=(R[n]||{}).win;if(!w)break;if(last===null)last=w;if(w===g.side)es++;else break}
  const pw=(R[hs]||{}).win;return {es,known:last!==null,ePistolWon:pw?pw!==g.side:null}}
const ECON_MEMO=new Map(),kMoney=m=>m>=1000?`$${(m/1000).toFixed(1).replace(/\.0$/,"")}k`:`$${m}`;
function econPlan(p,g){if(!g||g.money==null||!g.side||g.round==null||g.practice)return null;
  const hs=halfStart(g.round);if(g.round===hs)return null;   // pistol round: everyone buys the same
  const last=hs+(hs>24?2:11),H=Math.min(3,last-g.round+1),key=[g.map,g.side,g.round,g.money,g.losses,g.primary,g.armor,g.helmet,JSON.stringify(((g.hist||{}).rounds)||{})].join("|");
  if(ECON_MEMO.has(key))return ECON_MEMO.get(key);
  const TS=(p.advice.plan||{}).tside||{},E=TS.econ||{},tw=econTW(TS.situations),T=g.side==="T";
  // the attack's table for the side that attacks: the T on a bomb map, the CT on a hostage map (it goes for the hostage)
  const A_=typeof isHostage==="function"&&isHostage(g.map)?!T:T,PL_=T&&!(typeof isHostage==="function"&&isHostage(g.map))?ECON.plant:0;
  const pw=(k,ed)=>["eco","force","full"].reduce((a,e)=>a+(ed[e]||0)*(A_?tw(k,e):1-tw(e,k)),0);
  const st0=enemyStreak(g);
  // expected rounds won from a state over `d` rounds, then half the chance of the round after (what the money buys there)
  const V=(m,lc,es,r,hasR,d)=>{if(r>last)return 0;const ed=econEnemy(E,es,r,hs,st0.ePistolWon),os=econOpts(g.side,m,hasR,0,false);
    if(d===0)return .5*Math.max(...os.map(o=>pw(o.k,ed)));
    return Math.max(...os.map(o=>step(m,lc,es,r,hasR,o,ed,d)))};
  const step=(m,lc,es,r,hasR,o,ed,d)=>{const pr=pw(o.k,ed),left=m-o.c+o.kill,rifle=o.k==="full"||(hasR&&o.k!=="eco"&&o.k!=="half");
    const mw=Math.min(ECON.cap,left+ECON.win),ml=Math.min(ECON.cap,left+ECON.bonus[Math.min(lc,4)]+PL_);
    const lw=Math.max(0,lc-1),ll=lc+1,ew=es<=0?1:es+1,sw=rifle?.6:0,sl=rifle?.15:0;
    return pr+pr*(sw*V(mw,lw,ew,r+1,true,d-1)+(1-sw)*V(mw,lw,ew,r+1,false,d-1))+(1-pr)*(sl*V(ml,ll,0,r+1,true,d-1)+(1-sl)*V(ml,ll,0,r+1,false,d-1))};
  const hasR=!!(g.primary&&FULL_W.has(g.primary)),eb=enemyBuy(p,g),ed0=eb&&!eb.pistol?{eco:eb.eco||0,force:eb.force||0,full:eb.full||0}:econEnemy(E,st0.es,g.round,hs,st0.ePistolWon);
  const span=H+(g.round+H<=last?.5:0),lc=g.losses||0;
  const opts=econOpts(g.side,g.money,hasR,g.armor||0,!!g.helmet).map(o=>{const v=step(g.money,lc,st0.es,g.round,hasR,o,ed0,H);
    const left=g.money-o.c,lose=left+ECON.bonus[Math.min(lc,4)],need=T?3700:3900;   // next round after a loss: enough for a rifle + armor?
    return Object.assign({},o,{v,pct:Math.round(100*v/span),now:Math.round(100*pw(o.k,ed0)),lose,fullNext:lose>=need||(hasR&&lose>=1000)})});
  let best=opts.reduce((a,b)=>b.v>a.v+.005?b:a,opts[0]),close=null;
  // a near tie (the model can't tell them apart): the buy that keeps a full buy for the next round, the long game
  const keep=opts.filter(o=>o!==best&&o.fullNext&&best.v-o.v<=.025*span).sort((a,b)=>b.v-a.v)[0];
  if(best.k!=="full"&&!best.fullNext&&keep){close=best;best=keep}   // a full buy stays a full buy
  const res={opts,best,close,H,span,enemy:ed0};ECON_MEMO.set(key,res);if(ECON_MEMO.size>200)ECON_MEMO.clear();return res}
// the plan as lines: each buy you can afford, the share of the next rounds it wins, and the money left after a loss
function econRows(plan){if(!plan||plan.opts.length<2)return "";const mx=Math.max(...plan.opts.map(o=>o.pct),1);
  const now=plan.best&&plan.best.now!=null?" · "+tl("THIS ROUND {p}%",{p:plan.best.now}):"";   // the round itself, not only the next ones
  return `<div class="vhead">${tln(plan.H,"NEXT ROUND · WON","NEXT {n} ROUNDS · WON")}${now}${plan.close?" · "+tl("close: keep your next buy"):""}</div><div class="vrows econ">${ECON_K.map(k=>plan.opts.find(o=>o.k===k)).filter(Boolean).map(o=>{const b=o===plan.best;
    return `<div class="vrow${b?" best":""}" style="--c:${b?"var(--good)":"var(--muted)"}${b?"":";opacity:.6"}"><span>${ECON_L[o.k]}</span><i><u style="width:${Math.max(4,Math.round(100*o.pct/mx))}%"></u></i><b>${o.pct}%</b><small title="${tl("money next round if this round is lost")}">${o.fullNext?"✓":"✕"} ${kMoney(o.lose)}</small></div>`}).join("")}</div>`}
// T side: the plays that win most here for this kind of round, with how many were played and won (not the usual ones);
// each with its best way from the spawn (the route of the base that wins most, among the ones taken often enough)
const WIN_C=["#ffb347","#ffd9a0","#c9b79c","#a0a8b0"];
const LGT=x=>Math.log(x/(1-x)),SIG=x=>1/(1+Math.exp(-x)),CLP=x=>Math.min(.97,Math.max(.03,x));
// your side's run in the half before this round (same buckets as the base: w2 = won the last 2+, w1, l1, l2, l4 = lost 4+)
function tRun(g){const R=((g.hist||{}).rounds)||{},hs=halfStart(g.round);let run=0;
  for(let n=hs;n<g.round;n++){const w=(R[n]||{}).win;if(!w)continue;run=w===g.side?Math.max(run,0)+1:Math.min(run,0)-1}
  return run>=2?"w2":run===1?"w1":run===-1?"l1":run<=-4?"l4":run<=-2?"l2":"-"}
const RUN_EN={w2:tl("after 2+ wins"),w1:tl("after a win"),l1:tl("after a loss"),l2:tl("after 2-3 losses"),l4:tl("after 4+ losses"),"-":tl("start of the half")};
// a play's chance this round: its rounds in this economy (your buy against each buy they may have), then the effect of
// your run (the map's effect for every play, then this play's own rounds); few rounds pull to the play's average
function playCtx(M,k,tb,eb,run){const P_=M.plays,PC=M.play_ctx||{},base=CLP(((P_.win||{})[k]??45)/100),n=(P_.n||{})[k]||0;
  const mu=(PC.mu||{})[k]||{},E=tb==="pistol"?{pistol:1}:eb&&!eb.pistol?eb:{full:1},A0=PC.all||[1,0],allp0=CLP(A0[1]/Math.max(1,A0[0]));
  // with few rounds of this play in this economy: the map's rate for this economy, moved by how much better the play does
  const prior=e=>{const m=(PC.mx||{})[`${tb}|${e}`];return m&&m[0]?SIG(LGT(CLP((m[1]+10*allp0)/(m[0]+10)))+LGT(base)-LGT(allp0)):base};
  let pm=0,wt=0;for(const [e,pe] of Object.entries(E)){if(!pe)continue;const c=mu[`${tb}|${e}`]||[0,0];pm+=pe*(c[1]+10*prior(e))/(c[0]+10);wt+=pe}
  pm=CLP(wt?pm/wt:base);
  // the run beyond the economy: rounds won against the rounds the two buys predicted (a run of wins mostly means a
  // broke other side, already counted above)
  const res=c=>{if(!c||!c[0]||c[2]==null)return null;const q=CLP(c[2]/c[0]);return {q,n:c[0],o:c[1]}};
  const ga=res((PC.mo_all||{})[run]),G=ga?LGT(CLP((ga.o+20*ga.q)/(ga.n+20)))-LGT(ga.q):0;
  const pa=res(((PC.mo||{})[k]||{})[run]),d=pa?LGT(CLP((pa.o+15*SIG(LGT(pa.q)+G))/(pa.n+15)))-LGT(pa.q):G;
  return {p:SIG(LGT(pm)+d),base,n}}
function winsRank(p,g){const TS=(p.advice.plan||{}).tside,M=TS&&TS.maps&&TS.maps[g.map],P_=M&&M.plays;if(!P_||!P_.win)return null;
  const rt=advisedType(g),C=((P_.win_ctx||{})[rt==="pistol"?"pistol":rt])||{},RT=M.t_routes||{};
  const lb=(w,n)=>{const z=1.28,ph=w/100;return n?(ph+z*z/(2*n)-z*Math.sqrt(ph*(1-ph)/n+z*z/(4*n*n)))/(1+z*z/n):0};   // Wilson lower bound: a small sample doesn't win
  const tb=rt==="pistol"?"pistol":rt==="force"||rt==="full"?rt:"eco",eb=enemyBuy(p,g),run=tRun(g);
  const rows=Object.entries(P_.win).filter(([k])=>k!=="none").map(([k,w])=>{const c=C[k],use=c&&c[0]>=8,n=(P_.n||{})[k]||0;
    const pc=playCtx(M,k,tb,eb,run),wr=Math.round(100*pc.p),shift=LGT(CLP(pc.p))-LGT(pc.base);
    const rs=(RT[k]||[]).filter(x=>x.n>=6),route=rs.sort((a,b)=>lb(b.win,b.n)-lb(a.win,a.n))[0]||(RT[k]||[])[0]||null;
    const rwin=route?Math.round(100*SIG(LGT(CLP(route.win/100))+shift)):null;   // the route's own rounds, moved like its play for this round
    return {k,n,wr,use,route,rwin,won:Math.round(n*w/100)}}).filter(r=>r.n>=8);
  // show one site, hit the other: two Ts or more on the other side before 1:25, then the hit (rounds won at equal economy)
  const LBL=Object.assign({},P_.label||{});
  // on the scale of this round: the site's hits in this situation, plus half the measured edge of showing the other site
  // first (half: the rounds where the Ts had the time to show it are a bit easier)
  const siteOf=k=>(k.match(/[AB]$/)||k.match(/^[AB]/)||[])[0];
  for(const [s,F] of Object.entries(M.fakes||{})){if(!F||!F.route||F.n<20||!F.won_direct)continue;const o=s==="A"?"B":"A",k="fake"+s;
    const same=rows.filter(r=>siteOf(r.k)===s&&!/^rush/.test(r.k)),nn=same.reduce((a,r)=>a+r.n,0);if(!nn)continue;
    const ctx=same.reduce((a,r)=>a+r.wr*r.n,0)/nn,edge=LGT(CLP(F.won/100))-LGT(CLP(F.won_direct/100));
    LBL[k]=tl("Show {a}, hit {b}",{a:o,b:s});const wr=Math.round(100*SIG(LGT(CLP(ctx/100))+.5*edge));
    rows.push({k,n:F.n,wr,use:true,route:F.route,rwin:wr,won:Math.round(F.n*wr/100),fake:true})}
  const nb=rows.reduce((a,r)=>a+r.n,0),mean=nb?rows.reduce((a,r)=>a+r.wr*r.n,0)/nb:50;
  rows.forEach(r=>{r.wr=Math.round((r.wr*r.n+mean*20)/(r.n+20));r.s=r.wr/100+r.n*1e-7;r.wr0=r.wr;r.wr=calPath(r.wr)});   // few rounds: closer to the mean
  rows.sort((a,b)=>b.s-a.s);rows.splice(6);
  const PM=planMemory(g,rows);const rows2=PM.rows.slice(0,4);
  rows2.forEach((r,i)=>{r.rank=i+1;r.col=WIN_C[i];r.rot=rows2.slice(i+1).some(x=>x.wr>r.wr);
    const PT=(M.play_timing||{})[r.k]||{};r.timing=(rt==="pistol"&&PT.pistol)||PT.other||null});   // ↻: ahead of a better % to stay unpredictable
  return {rows:rows2,rt,ctx:true,run,eb,rotated:PM.rotated,label:LBL}}
function vWins(p,g){const W=winsRank(p,g);if(!W||!W.rows.length)return "";const rows=W.rows,rt=W.rt,P_={label:W.label};

  const ctx=W.ctx,mx=Math.max(...rows.map(r=>r.wr),1);   // ctx false: too few rounds of this kind, the numbers are for all rounds
  const lab=k=>{const L=String((P_.label||{})[k]||k);return /^Rush/.test(L)?`⚡${L.replace(/^Rush ([AB]) through /,"$1 · ")}`:/^Split/.test(L)?`⇉${L.replace(/^Split ([AB]):.*/,(m,s)=>tl("{site} split",{site:s}))}`:L.replace(/^([AB]) through /,"$1 · ")};
  return `<div class="vhead">✓ ${tl("WHAT WINS")} · ${ctx?esc(RT_EN[rt]||rt||""):tl("all rounds")}</div><div class="vrows">${rows.map((r,i)=>`<div class="vrow" style="--c:${r.col}${i?`;opacity:${[1,.85,.7,.6][i]}`:""}"><span><em class="rk" style="background:${r.col}">${r.rank}</em>${vShort(lab(r.k))}</span><i><u style="width:${Math.max(4,Math.round(100*r.wr/mx))}%"></u></i><b>${r.wr}%</b><small>${r.won}/${r.n}</small></div>`).join("")}</div>`}

// ---------- key rounds: pistol, eco or force-buy against a full buy (the rounds pros prepare) ----------
// What each weapon does there (every map of the base together), the spots that pay on this map for your weapon's family
// (close range, long range, default pistols), and for the T side a plant spot that wins more than the usual ones
const W_PRICE={"Tec-9":500,"Five-SeveN":500,"CZ75-Auto":500,"P250":300,"Desert Eagle":700,"Dual Berettas":300,"R8 Revolver":600,"MAC-10":1050,
  "MP9":1250,"MP7":1500,"UMP-45":1200,"P90":2350,"PP-Bizon":1400,"MP5-SD":1500,"XM1014":2000,"MAG-7":1300,"Nova":1050,"Sawed-Off":1100,"SSG 08":1700,
  "Galil AR":1800,"FAMAS":2050,"AK-47":2700,"M4A1-S":2900,"M4A4":3100,"AWP":4750,"AUG":3300,"SG 553":3000,"Glock-18":0,"USP-S":0,"P2000":0};
const W_GRP=w=>["Tec-9","Five-SeveN","CZ75-Auto","Dual Berettas","MAC-10","MP9","MP7","UMP-45","P90","PP-Bizon","MP5-SD","XM1014","MAG-7","Nova","Sawed-Off"].includes(w)?"close":
  ["Desert Eagle","R8 Revolver","SSG 08","AK-47","M4A1-S","M4A4","Galil AR","FAMAS","AWP","AUG","SG 553"].includes(w)?"long":"default";
const W_SHORT={"Desert Eagle":"DEAGLE","Five-SeveN":"FIVE-7","CZ75-Auto":"CZ","SSG 08":"SCOUT","XM1014":"XM","Galil AR":"GALIL","Dual Berettas":"DUALIES",
  "R8 Revolver":"R8","Glock-18":"GLOCK","USP-S":"USP","M4A1-S":"M4A1-S","PP-Bizon":"BIZON","UMP-45":"UMP","MP5-SD":"MP5"};
const DEF_PISTOL=new Set(["Glock-18","USP-S","P2000"]);
const SIDE_ONLY={T:new Set(["AK-47","Galil AR","SG 553","MAC-10","Tec-9","Glock-18","Sawed-Off","G3SG1"]),CT:new Set(["M4A1-S","M4A4","AUG","FAMAS","MP9","Five-SeveN","USP-S","P2000","MAG-7","SCAR-20"])};
const canBuy=(side,w)=>!SIDE_ONLY[side==="T"?"CT":"T"].has(w);   // the base counts picked-up weapons too: you can only buy your side's
const KEY_L={pistol:tl("PISTOL ROUND"),eco_full:tl("ECO vs FULL"),force_full:tl("FORCE vs FULL"),eco_force:tl("ECO vs SMG")};
const KEY_LOW={pistol:tl("pistol round"),eco_full:tl("eco vs full"),force_full:tl("force vs full"),eco_force:tl("eco vs SMG")};
// the key situation of this round: the pistol round, or your eco / force-buy (what you hold once bought, else the advice)
// against a full buy
function keySit(p,g){if(!g||!g.side||g.round==null||g.practice)return null;if(g.round===halfStart(g.round))return "pistol";
  const eb=enemyBuy(p,g)||{},full=(eb.full||0)>=.5,frc=(eb.force||0)>=.5;if(!full&&!frc)return null;
  const pr=g.primary,pi=g.pistol;let mine=null;
  if(pr)mine=FULL_W.has(pr)?"full":"force";else if(pi&&!DEF_PISTOL.has(pi))mine="eco";
  if(!mine)mine=advisedType(g);
  if(!full)return mine==="eco"?"eco_force":null;   // their SMGs and upgrades after a won pistol
  return mine==="eco"?"eco_full":mine==="force"?"force_full":null}
// the weapons to look at: yours, and while buying the ones you can pay without losing your next buy
function keyWeapons(p,g,k){const W=((((p.advice.plan||{}).tside||{}).setplay_w||{})[g.side]||{})[k]||[],mine=g.primary||(g.pistol&&!DEF_PISTOL.has(g.pistol)?g.pistol:null);
  let budget=g.money||0;
  if(k==="eco_full"||k==="eco_force"){const need=g.side==="T"?3700:3900;budget=Math.max(0,(g.money||0)+ECON.bonus[Math.min(g.losses||0,4)]-need)}   // an eco keeps the next full buy
  const buying=g.round_phase==="freezetime";
  const ok=w=>w.w===mine||(buying&&canBuy(g.side,w.w)&&(W_PRICE[w.w]??99999)<=budget+(mine?W_PRICE[mine]||0:0));
  const lbw=w=>{const z=1.28,p=w.win/100,n=w.n||1;return (p+z*z/(2*n)-z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)};
  const by=k==="pistol"?(a,b)=>lbw(b)-lbw(a):(a,b)=>b.adr-a.adr;   // pistol: kevlar and the round count most; eco / force: what a weapon does
  const list=W.filter(ok).sort(by).slice(0,4);
  expSwaps(p).forEach(x=>{const i=list.findIndex(w=>w.w===x.weapon);if(i<0)return;const j=list.findIndex(w=>w.w===x.alt),a=j>=0?list[j]:W.find(w=>w.w===x.alt);
    if(j>=0)list.splice(j,1);list.splice(j>=0&&j<i?i-1:i,1,Object.assign({},a||{w:x.alt,adr:null,win:null,n:0},{exp:true}))});   // the tested weapon takes the place of the one it replaces, once
  if(mine&&!list.some(w=>w.w===mine)){const m=W.find(w=>w.w===mine);if(m)list.push(m)}
  return {list,mine,budget}}
function vKey(p,g){const k=keySit(p,g);if(!k)return "";const M=(((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{},SP=((M.setplays||{})[g.side]||{})[k];
  const {list,mine,budget}=keyWeapons(p,g,k),pis=k==="pistol",val=w=>pis?w.win:w.adr,mx=Math.max(...list.map(val).filter(v=>v!=null),1);
  const rows=list.map((w,i)=>`<div class="vrow${w.w===mine?" best":""}" style="--c:${w.w===mine?"var(--good)":"var(--flash)"}${w.w===mine||!i?"":";opacity:.7"}"><span>${w.w===mine?"✓ ":""}${esc(W_SHORT[w.w]||w.w.toUpperCase())}${w.exp?" "+IC("flask-conical"):""}</span><i><u style="width:${val(w)==null?0:Math.max(4,Math.round(100*val(w)/mx))}%"></u></i><b>${val(w)==null?tl("test"):pis?w.win+"%":w.adr}</b><small>${w.exp&&val(w)==null?tl("your experiment"):pis?tl("{n} dmg",{n:w.adr}):tl("{p}% won",{p:w.win})}</small></div>`).join("");
  const dup=(typeof sitKey==="function"&&!!sitKey(p,g))||(pis&&g.side==="CT");   // the situation card above has the header and its %
  return `<div class="vsit key"><span>${IC("key-round")} ${dup?tl("WEAPONS"):KEY_L[k]}</span>${SP&&SP.n>=15&&!dup?`<b class="${vTone(SP.win)}">${SP.win}%</b>`:""}</div>
    ${rows?`<div class="vhead">${pis?tl("ROUNDS WON"):tl("DAMAGE / ROUND")} · ${(k==="eco_full"||k==="eco_force")&&g.round_phase==="freezetime"?tl("budget {m}",{m:kMoney(budget)}):tl("base, every map")}</div><div class="vrows">${rows}</div>`:""}`}
// the spots of a key round for a weapon family: this situation's, else every weapon in it, else the same family in the
// other "against a full buy" situation (an eco and a force-buy hold the same angles with the same weapons)
function keySpots(p,g,map,k,grp){const M=(((p.advice.plan||{}).tside||{}).maps||{})[map]||{},S_=(M.setplays||{})[g.side]||{},a=S_[k]||{};
  const o=k==="eco_full"?S_.force_full:k==="force_full"?S_.eco_full:k==="eco_force"?S_.eco_full:null;
  const pi=(k==="eco_full"||k==="eco_force")?S_.pistol:null;   // an eco plays pistols: the pistol rounds' spots on this side
  return ((a.groups||{})[grp]||[]).length?a.groups[grp]:(a.spots||[]).length?a.spots:o&&((o.groups||{})[grp]||[]).length?o.groups[grp]:
    o&&(o.spots||[]).length?o.spots:pi&&((pi.groups||{})[grp]||[]).length?pi.groups[grp]:pi&&(pi.spots||[]).length?pi.spots:[]}
// on the radar: the spots that pay for your weapon's family in this kind of round, and (T) a plant that wins more
function keyRadar(p,g,map,level,lay,top,legend,here){const k=keySit(p,g);if(!k)return;const M=(((p.advice.plan||{}).tside||{}).maps||{})[map]||{};
  const SP=((M.setplays||{})[g.side]||{})[k];if(!SP)return;const {list,mine}=keyWeapons(p,g,k),w=mine||(list[0]||{}).w,grp=w?W_GRP(w):"default";
  const sp=keySpots(p,g,map,k,grp).filter(here).slice(0,3),lab=W_SHORT[w]||(w||"").toUpperCase();
  sp.forEach(z=>{const [x,y]=z.px,gg=el("g",{},top);
    obstacle(top,x,y,22,24);el("path",{d:`M${x} ${y-11}L${x+10} ${y-5}L${x+10} ${y+5}L${x} ${y+11}L${x-10} ${y+5}L${x-10} ${y-5}Z`,style:"fill:var(--good);fill-opacity:.85;stroke:#0b0f14;stroke-width:1.6"},gg);
    qLabel(top,x,y,11,`${lab}${z.surprise?" ★":""}`,"kwt",3);
    tip(gg,(grp==="close"?tl("{zone}: {k} kills for {d} deaths with a close-range weapon in {kind} rounds, around {t}",{zone:z.zone||tl("Spot"),k:z.k,d:z.d,kind:KEY_LOW[k],t:clock(z.t_med)})
      :grp==="long"?tl("{zone}: {k} kills for {d} deaths with a long-range weapon in {kind} rounds, around {t}",{zone:z.zone||tl("Spot"),k:z.k,d:z.d,kind:KEY_LOW[k],t:clock(z.t_med)})
      :tl("{zone}: {k} kills for {d} deaths with a default pistol in {kind} rounds, around {t}",{zone:z.zone||tl("Spot"),k:z.k,d:z.d,kind:KEY_LOW[k],t:clock(z.t_med)}))+(z.surprise?" — "+tl("rarely played: a surprise"):""))});
  if(sp.length)legend.push(`<span>${SW.key}${tl("{kind}: spots that pay with your {weapon} (★ = rarely played, a surprise)",{kind:KEY_LOW[k],weapon:esc(lab||tl("weapon"))})}</span>`);
  if(g.side==="T"){const W_=winsRank(p,g),r1=W_&&W_.rows[0],site=r1?(r1.k.match(/[AB]$/)||r1.k.match(/^[AB]/)||[])[0]:null,PL=site&&((M.evidence||{}).plants||{})[site];
    if(PL&&PL.spots&&PL.spots.length){const base=PL.t_win??50,best=PL.spots.slice().sort((a,b)=>(b.t_win*b.n+base*10)/(b.n+10)-(a.t_win*a.n+base*10)/(a.n+10))[0];
      if(best&&here(best)&&best.t_win>base){const [x,y]=best.px,gg=el("g",{},top);
        obstacle(top,x,y,30,20);el("rect",{x:x-15,y:y-10,width:30,height:20,rx:4,style:"fill:var(--bad);stroke:#ffd24a;stroke-width:2"},gg);
        el("text",{x,y:y+4,"text-anchor":"middle",class:"c4t"},gg).textContent="C4";
        qLabel(top,x,y,15,`★ ${best.t_win}%`,"kwt",4);
        tip(gg,tl("Plant here on {site}: the Ts win {w}% after it ({p}% of plants), vs {b}% on the site",{site,w:best.t_win,p:best.share,b:base}));
        legend.push(`<span>${SW.c4}${tl("a plant on site {site} that wins more than the usual ones",{site})}</span>`)}}}}

// ---------- the bomb site after the plant, without a click: the read before the plant and when it went down ----------
// CT: the A / B read of the round at the plant time; T: your path 1's site. Then the plant time against each site's
// usual plant times (TS evidence.plants t_q). Returns the site and how sure.
function autoSite(p,g){if(!g||g.bomb!=="planted")return null;const TS=(p.advice.plan||{}).tside,M=((TS||{}).maps||{})[g.map]||{},PL=(M.evidence||{}).plants||{};
  const tp=g.elapsed!=null&&g.since_plant!=null?Math.max(0,g.elapsed-g.since_plant):null;let pr={A:.5,B:.5};
  // where you stood when it went down (10/10: on Nuke the plan alone said A for a bomb on B, twice): you planted it, that
  // site; T alive on a site (its level, within its size), that site
  const GEO=M.geo,pp=g.plant_pos&&GEO&&typeof worldPx==="function"?worldPx(GEO,g.plant_pos):null;
  if(pp&&GEO.sites){const d=k=>{const s_=GEO.sites[k];return s_&&s_.px&&(!s_.level||!pp.level||s_.level===pp.level)?Math.hypot(s_.px[0]-pp.px[0],s_.px[1]-pp.px[1]):1e9};
    const dA=d("A"),dB=d("B"),k=dA<dB?"A":"B",dk=Math.min(dA,dB);
    if(g.plant_mine&&dk<260)return {site:k,p:99,tp,mine:true}}   // you planted it: over a 7 / 9 said before
  const said=(((g.hist||{}).marks||{})[g.round]||{}).bomb_site;if(said==="A"||said==="B")return {site:said,p:95,tp,said:true};
  if(pp&&GEO.sites){const d=k=>{const s_=GEO.sites[k];return s_&&s_.px&&(!s_.level||!pp.level||s_.level===pp.level)?Math.hypot(s_.px[0]-pp.px[0],s_.px[1]-pp.px[1]):1e9},dk=Math.min(d("A"),d("B")),k=d("A")<d("B")?"A":"B";
    if(g.side==="T"&&dk<130)return {site:k,p:90,p0:90,tp}}
  if(g.side==="CT"){const r=tsidePredict(TS,g.map,Object.assign({},g,{bomb:null,elapsed:tp}),evFor(g));if(r&&r.A+r.B>0)pr={A:r.A/(r.A+r.B),B:r.B/(r.A+r.B)}}
  else if(typeof tdirSel==="function"&&["A","B"].includes(tdirSel(g).dir)){const s=tdirSel(g).dir;pr={A:s==="A"?.8:.2,B:s==="B"?.8:.2}}   // T: the way you said, before the plan's
  else{const W=winsRank(p,Object.assign({},g,{bomb:null})),r1=W&&W.rows[0],s=r1?(r1.k.match(/[AB]$/)||r1.k.match(/^[AB]/)||[])[0]:null;if(s)pr={A:s==="A"?.7:.3,B:s==="B"?.7:.3}}
  const lik=s=>{const q=(PL[s]||{}).t_q;if(!q||tp==null)return 1;const sd=Math.max(6,(q[2]-q[0])/1.35);return Math.exp(-((tp-q[1])**2)/(2*sd*sd))/sd};
  const a=pr.A*lik("A"),b=pr.B*lik("B"),pa=a/((a+b)||1),pc=calPlant(pa);return {site:pc>=.5?"A":"B",p:Math.round(100*Math.max(pc,1-pc)),p0:Math.round(100*Math.max(pa,1-pa)),tp}}
// T after the plant: where the Ts hold in the rounds they win (each T's spot 3 to 30 s after the plant)
function postplantRadar(p,g,map,level,top,legend,here,site,ct){const PP=((((((p.advice.plan||{}).tside||{}).maps||{})[map])||{}).postplant||{})[site];if(!PP)return;
  const hs=(PP.holds||[]).filter(here).slice(0,ct?4:3),c=ct?"var(--bad)":"var(--good)";   // CT: the same spots, to check on the retake
  hs.forEach((h,i)=>{const [x,y]=h.px,gg=el("g",{style:i?"opacity:.75":""},top);
    obstacle(top,x,y,24,24);el("circle",{cx:x,cy:y,r:11,style:`fill:${c};fill-opacity:.25;stroke:${c};stroke-width:2.6`},gg);
    qLabel(top,x,y,12,ct?tl("check"):i?tl("hold"):"★ "+tl("hold"),"kwt",3);
    tip(gg,ct?tl("{zone}: Ts hold here after a plant on {site} ({n} times): check it on the retake",{zone:h.zone||tl("Spot"),site,n:h.n}):tl("{zone} after the plant on {site}: {w}% of rounds won from here ({n} times), {b}% on average",{zone:h.zone||tl("Hold"),site,w:h.win,n:h.n,b:PP.base}))});
  if(hs.length)legend.push(ct?`<span>${SW.spot}${tl("retake: where the Ts hold after a plant there (check them)")}</span>`:`<span>${SW.spot}${tl("after the plant: where the Ts hold in the rounds they win")}</span>`)}
// anti-eco (your full buy against their eco): the spots their ecos kill from, read from their side of the key rounds
const antiEco=(p,g)=>{if(!g||g.round==null||g.round===halfStart(g.round))return false;const eb=enemyBuy(p,g)||{};return (eb.eco||0)>=.6&&advisedType(g)!=="eco"};   // your buy against their eco
function antiEcoRadar(p,g,map,level,top,legend,here){if(!antiEco(p,g))return;
  const other=g.side==="T"?"CT":"T",S_=(((((p.advice.plan||{}).tside||{}).maps||{})[map]||{}).setplays||{})[other]||{};
  const all=[];["eco_full","eco_force"].forEach(k=>{const a=S_[k]||{};[...(a.spots||[]),...Object.values(a.groups||{}).flat()].forEach(z=>all.push(z))});
  const pick=[];all.sort((a,b)=>b.k-a.k).forEach(z=>{if(here(z)&&!pick.some(q=>q.level===z.level&&Math.hypot(q.px[0]-z.px[0],q.px[1]-z.px[1])<50))pick.push(z)});
  pick.slice(0,4).forEach(z=>{const [x,y]=z.px,gg=el("g",{},top);
    obstacle(top,x,y,24,22);el("path",{d:`M${x} ${y-12}L${x+11} ${y+8}L${x-11} ${y+8}Z`,style:"fill:var(--warn);stroke:#0b0f14;stroke-width:1.6"},gg);
    el("text",{x,y:y+6,"text-anchor":"middle",class:"pbt"},gg).textContent="!";
    qLabel(top,x,y,12,tl("eco"),"kwt",2,"fill:#ffd9a0");
    tip(gg,tl("{zone}: their ecos kill from here ({k} kills for {d} deaths in the base): clear it or avoid the close angle",{zone:z.zone||tl("Spot"),k:z.k,d:z.d}))});
  if(pick.length)legend.push(`<span>${SW.eco}${tl("anti-eco: where their ecos kill from (clear it, don't take the close duel)")}</span>`)}
// the 60-second brief while the map loads (warmup): the round of a full buy against a full buy for your side, and the
// key rounds in one line each
function briefState(g){const T=g.side==="T";return Object.assign({},g,{round:4,round_phase:"freezetime",map_phase:"live",money:6000,primary:T?"AK-47":"M4A1-S",pistol:null,armor:100,helmet:true,nades:T?{smoke:1,flash:1,molotov:1}:{smoke:1,flash:1,molotov:1},hist:{rounds:{}},losses:0,elapsed:null,bomb:null})}
function briefVisual(p,g){const TS=(p.advice.plan||{}).tside||{},M=(TS.maps||{})[g.map]||{},T=g.side==="T",b=briefState(g),out=[];
  out.push(`<div class="vsit key" data-brief><span>${tl("BRIEF")} · ${esc(MAPN(g.map))} · ${tl("YOU START {side}",{side:g.side||"?"})}</span></div>`);
  if(T){const W=winsRank(p,b);if(W&&W.rows.length)out.push(vHead(tl("FULL vs FULL · PATHS ON THE MAP")),`<div class="vchips">${W.rows.slice(0,3).map(r=>`<span class="vchip"><em class="rk" style="background:${r.col};display:inline-grid;place-items:center;width:16px;height:16px;border-radius:8px;color:#1a1206;font:800 11px var(--f-mono);font-style:normal;margin-right:4px">${r.rank}</em>${vShort(String((M.plays.label||{})[r.k]||r.k).replace(/^([AB]) through /,"$1 · ").replace(/^Rush ([AB]) through /,"⚡$1 · "))}</span>`).join("")}</div>`)}
  else{const r=tsidePredict(TS,g.map,b,{});if(r)out.push(vOdds(r,tl("THEIR FULL BUYS · WHERE THEY GO")))}
  // the typical money of each key round: R2 after a lost pistol, an eco after 2 lost rounds, a force after 3
  const TYP={pistol:{round:1,money:800,losses:0},eco_force:{round:2,money:1900,losses:1},eco_full:{round:4,money:2400,losses:2},force_full:{round:5,money:3300,losses:3}};
  const first=k=>{const kw=keyWeapons(p,{...b,...TYP[k],side:g.side,round_phase:"freezetime",primary:null,pistol:null},k),L=kw.list;
    if(k==="pistol")return L[0]&&!DEF_PISTOL.has(L[0].w)?L[0].w:"kevlar";
    const w=L.find(w=>!DEF_PISTOL.has(w.w));return w?w.w:"save"};
  const WL={kevlar:tl("KEVLAR"),save:tl("SAVE")};
  const kr=[["pistol",tl("PISTOL")],["eco_force",tl("R2 ECO")],["eco_full",tl("ECO")],["force_full",tl("FORCE")]].map(([k,l])=>{const w=first(k);return w?`<span class="vchip"><b>${l}</b> ${esc(WL[w]||W_SHORT[w]||w.toUpperCase())}</span>`:""}).join("");
  if(kr)out.push(vHead(tl("KEY ROUNDS · WEAPON")),`<div class="vchips">${kr}</div>`);
  if(T){const d=(((M.ct_spots||{}).setup||{}).danger||[]).filter(z=>z.sneaky).slice(0,2).map(z=>esc(z.zone||"?"));if(d.length)out.push(`<span class="vchip bad">! ${tl("check {zones}",{zones:d.join(", ")})}</span>`);
    const cp=((M.ct_push||{}).full||{}).gates||[],zs=cp.filter(x=>x.share>=5).map(x=>x.gate).filter(Boolean).slice(0,2);if(zs.length)out.push(`<span class="vchip">${IC("arrow-right")} ${tl("CT pushes: {zones}",{zones:zs.map(esc).join(", ")})}</span>`)}
  else{const mine=(((p.advice.plan||{}).multi||{})[g.map]||{}).CT||[];if(mine.length)out.push(`<span class="vchip good">★ ${tl("your multi-kills: {zones}",{zones:[...new Set(mine.map(s=>s.zone))].slice(0,3).map(esc).join(", ")})}</span>`)}
  return `<div class="vz">${out.join("")}</div>`}
// predictability: the plays shown as path 1 this half (kept in this browser), the ones that lost go down, a play
// shown again and again goes down a little: the other side reads you too
function planMemory(g,rows){if(!g||!g.map||g.round==null||!rows||!rows.length)return {rows,rotated:false};
  const hs=halfStart(g.round),key=`pp|${g.map}|${g.side}|${hs}`;let mem={};try{mem=JSON.parse(localStorage.getItem(key)||"{}")||{}}catch(e){}
  if(g.round===hs&&Object.keys(mem).some(n=>+n>hs))mem={};   // a new match on this map
  const R=((g.hist||{}).rounds)||{},used={},lost={};
  for(const [n,k] of Object.entries(mem)){if(+n>=g.round)continue;used[k]=(used[k]||0)+1;const w=(R[n]||{}).win;if(w&&w!==g.side)lost[k]=(lost[k]||0)+1}
  const recent=new Set(Object.entries(mem).filter(([n])=>+n<g.round&&+n>=g.round-2).map(([,k])=>k));   // played in the last 2 rounds
  const top0=rows[0].k,adj=r=>-.08*(lost[r.k]||0)-.02*Math.max(0,(used[r.k]||0)-1)-(recent.has(r.k)?.04:0);
  const sorted=rows.slice().sort((a,b)=>(b.s+adj(b))-(a.s+adj(a))),out=[],rest=[];
  sorted.forEach(r=>{const rush=/^rush/.test(r.k);if(rush&&out.some(x=>/^rush/.test(x.k))&&out.length<4)rest.push(r);else out.push(r)});   // one rush at most among the paths shown
  out.push(...rest);
  const f=g.focus,fn=f&&f.round===g.round&&f.n>=1&&f.n<=3?f.n:0;   // the path you pressed is the one you played
  if((g.round_phase==="freezetime"||g.round_phase==="live")&&(fn&&out[fn-1]?mem[g.round]!==out[fn-1].k:!mem[g.round])){mem[g.round]=(fn&&out[fn-1]?out[fn-1]:out[0]).k;try{localStorage.setItem(key,JSON.stringify(mem))}catch(e){}}
  return {rows:out,rotated:out[0].k!==top0,lost:lost[top0]||0}}

// ---------- what the page shows, sent to the app a few times per round (buy time, 0:20, 0:40, after the plant): the
// app checks it against the match's demo afterwards (livecheck.py) ----------
const LIVE_SENT=new Set();
function liveLog(p,g){if(!D.local||!g||!g.map||g.round==null||g.practice||!g.side||g.map_phase==="warmup")return;
  const ph=g.round_phase,el=g.elapsed||0,b=g.bomb==="planted"?"plant":ph==="freezetime"?"fz":ph==="live"&&el>=18&&el<26?"t20":ph==="live"&&el>=38&&el<46?"t40":null;
  if(!b||(b==="fz"&&g.money==null))return;const key=`${g.map}|${g.round}|${b}|${g.side}`;if(LIVE_SENT.has(key))return;LIVE_SENT.add(key);
  const TS=(p.advice.plan||{}).tside,body={map:g.map,round:g.round,side:g.side,bucket:b,elapsed:g.elapsed,money:g.money,score:[g.score_ct,g.score_t]};
  try{
    if(g.side==="CT"&&b!=="plant"){const r=tsidePredict(TS,g.map,g,evFor(g));if(r){const PLs=r.live?tsidePlays(TS,g.map,g,evFor(g),r):null;const R0=r.raw||r;body.read={A:R0.A,B:R0.B,none:R0.none,rush:PLs?Math.round(100*PLs.rush):R0.rush}}}
    if(g.side==="T"&&b==="fz"){const W=winsRank(p,g);if(W)body.paths=W.rows.slice(0,3).map(x=>({k:x.k,wr:x.wr0??x.wr}))}
    if(g.side==="T"&&typeof dirRank==="function"&&tdirsOf(g.map)){const DR=dirRank(p,g,tdirsOf(g.map));if(DR){body.dirs=DR.rows.map(x=>({k:x.k,wr:x.wr}));if(DR.sel.dir||DR.sel.tempo)body.sel={dir:DR.sel.dir,tempo:DR.sel.tempo}}}   // 06/10: the ways shown
    if(b==="fz"){const pl=econPlan(p,g);body.buy=pl&&pl.best?pl.best.k:advisedType(g);body.key=keySit(p,g)}
    if(b==="plant"){const as=autoSite(p,g);if(as){body.site=as.site;if(!as.said)body.p_site=as.p0??as.p}}
  }catch(e){}
  fetch("/api/live/log",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).catch(()=>{})}
// a running "replace X with Y" experiment (Progress tab): the advice says Y wherever it would say X, marked 🧪
function expSwaps(p){const E=((((p||{}).advice||{}).plan||{}).experiments||{}).experiments||[];
  return E.filter(e=>e.status==="active"&&e.template==="weapon_swap"&&e.params&&e.params.weapon&&e.params.alt).map(e=>e.params)}
function expSwapTxt(p,s){if(s==null)return s;let t=String(s);expSwaps(p).forEach(x=>{if(t.includes(x.weapon)&&!t.includes(x.alt))t=t.split(x.weapon).join(`${x.alt} 🧪`)});return t}
// ---------- the automatic calibration (live check after each match): how sure the read should be, from your matches.
// A temperature above 1 flattens a read that was too sure of itself, below 1 sharpens a shy one; few rounds checked:
// close to no change ----------
function CAL(){let p=null;try{p=P()}catch(e){}return ((((p||{}).advice||{}).plan||{}).livecheck||{}).calib||null}
function calSite(map,a,b,n){const c=CAL();if(!c)return [a,b,n];const T=((c.maps||{})[map]||{}).site_T||c.site_T||1;if(Math.abs(T-1)<.01)return [a,b,n];
  const w=[a,b,n].map(x=>Math.pow(Math.max(1e-4,x),1/T)),s=w[0]+w[1]+w[2];return w.map(x=>x/s)}
function calRush(p){const c=CAL(),r=c&&c.rush;if(!r||(r[0]===1&&r[1]===0))return p;return SIG(r[0]*LGT(CLP(p))+r[1])}
function calPlant(pa){const c=CAL(),T=c&&c.plant_T;if(!T||Math.abs(T-1)<.01)return pa;return SIG(LGT(CLP(pa))/T)}
function calPath(wr){const c=CAL(),d=c&&c.path_d;if(!d)return wr;return Math.round(100*SIG(LGT(CLP(wr/100))+d))}
// ---------- T side: CTs pushing past the neutral zones (where both sides arrive at the same time when they run),
// for the CTs' buy this round ----------
const PUSH_L={pistol:tl("PISTOL"),eco:tl("THEIR ECO"),force:tl("THEIR FORCE"),full:tl("THEIR FULL BUY"),anti_eco:tl("YOUR ECO vs FULL")};
function ctPush(p,g){const M=(((p.advice.plan||{}).tside||{}).maps||{})[g.map],CP=M&&M.ct_push;if(!CP||!g||g.side!=="T")return null;
  let W;if(g.round===halfStart(g.round))W={pistol:1};
  else{const eb=enemyBuy(p,g)||{};W={eco:eb.eco||0,force:eb.force||0,full:eb.full||0};if(advisedType(g)==="eco"&&W.full&&CP.anti_eco){W.anti_eco=W.full;W.full=0}}
  const acc={};let ws=0;
  for(const [c,w] of Object.entries(W)){const X=CP[c];if(!X||!w)continue;ws+=w;
    X.gates.forEach(x=>{const k=`${x.gate}|${x.level}`,o=acc[k]||(acc[k]={gate:x.gate,level:x.level,share:0,t:0,kill:0,from:x.from,to:x.to,best:0});
      const v=w*x.share;o.share+=v;o.t+=v*x.t_med;o.kill+=v*x.kill;if(v>o.best){o.best=v;o.from=x.from;o.to=x.to}})}
  if(!ws)return null;
  const gates=Object.values(acc).map(o=>({...o,t:o.t/o.share,kill:Math.round(o.kill/o.share),share:o.share/ws})).filter(o=>o.share>=3).sort((a,b)=>b.share-a.share).slice(0,4);
  const top=Object.entries(W).sort((a,b)=>b[1]-a[1])[0][0];
  return {gates,ctx:top,label:PUSH_L[top]||""}}
// ---------- numpad 1-2-3 in CS2 say path 1-2-3 in the team chat: the page sends its paths, the app writes them for
// the keys (chatcalls.py). The chat lines stay in English whatever the app's language (13/10): the keys' files are
// ASCII (chatcalls.clean) and a team of strangers shares English callouts. T side, buy time and the first 40 s; anything else: the keys only print a note ----------
const CALL_SENT={k:null};
function pathCalls(p,g){if(!D.local||!g||!g.map||g.round==null||g.practice)return;let paths=[];
  if(g.side===attackSide(g.map)&&g.map_phase!=="warmup"&&(g.round_phase==="freezetime"||(g.round_phase==="live"&&(g.elapsed||0)<40))){
    if(isHostage(g.map)){const H=hostageRank(p,g);if(H)paths=H.rows.map(r=>({rank:r.rank,site:null,text:`Hostages via ${r.route.zones.slice(-2).join(" > ")} - there ~${clock(r.t_end)}`}))}
    const W=isHostage(g.map)?null:winsRank(p,g),L=(((((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{}).plays||{}).label||{};
    if(W)paths=W.rows.slice(0,3).map(r=>{const ps=pathShort(p,g,r),pts=(r.route||{}).pts,end=pts&&pts[pts.length-1],os_=onSite(r.timing,end,"en");
      return {rank:r.rank,site:ps.site,text:`${psHead(ps,"en")}${ps.via?` via ${ps.via}`:""}${os_?` - ${os_}`:""}`}})}
  const DT=!isHostage(g.map)&&g.side===attackSide(g.map)&&typeof dirTexts==="function"?dirTexts(p,g):null,tempo=DT?DT.tempo:{};
  if(DT)paths=DT.paths;   // 06/10: numpad 1-2-3 = A / mid / B (the best way onto each this round), 4-5-6 = the tempo
  const extra=g.map_phase!=="warmup"&&(g.round_phase==="freezetime"||g.round_phase==="live")?{eco:ecoText(p,g),sit:sitText(p,g)}:{};
  const key=JSON.stringify([g.map,g.round,g.side,paths.map(x=>x.text),extra,tempo]);if(CALL_SENT.k===key)return;CALL_SENT.k=key;
  fetch("/api/coach/paths",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({paths,extra,tempo})}).catch(()=>{})}
// numpad ".": the economy plan of the round for the team chat (the buy that wins most over the next rounds, their buy)
function ecoText(p,g){if(!g.side||g.round==null)return null;if(g.round===halfStart(g.round))return "Pistol round";
  const pl=typeof econPlan==="function"?econPlan(p,g):null,k=pl&&pl.best?pl.best.k:advisedType(g),eb=enemyBuy(p,g)||{},ae=typeof antiEco==="function"&&antiEco(p,g);
  const T={eco:"Eco: save, full buy next round",half:"Half buy: pistol and kevlar, full buy next round",force:"Force buy this round",full:ae?"Full buy, anti-eco: no AWP, play close, trade":"Full buy"}[k];
  const them=eb.full>=.6?" - they full buy":(eb.eco||0)>=.6?" - they eco":(eb.eco||0)+(eb.force||0)>=.6?" - they force or eco":"";
  return T?T+them:null}
// numpad 0: the situation, recent and global. CT: the Ts' last rounds (site, rush, won or lost) and the read; T: their
// buy, the push to watch, our last results
function sitText(p,g){if(!g.side||g.round==null)return null;const H=g.hist||{},R=H.rounds||{},TS=(p.advice.plan||{}).tside,hs=halfStart(g.round),res=[],seq=[];
  for(let n=Math.max(hs,g.round-5);n<g.round;n++){const w=(R[n]||{}).win,s=(H.sites||{})[n],d=typeof roundDyn==="function"?roundDyn(TS,H,n):null;
    res.push(w?(w===g.side?"W":"L"):"?");seq.push(`${s&&s!=="-"?s:"?"}${d&&d.dyn==="rush"?" rush":""}`)}
  if(g.side==="CT"&&!isHostage(g.map)){const r=tsidePredict(TS,g.map,g,evFor(g));
    return `Ts last rounds: ${seq.join(", ")||"-"}${r?` - now A ${r.A}% B ${r.B}%${r.rush>=20?` rush ${r.rush}%`:""}`:""}`}
  const eb=enemyBuy(p,g)||{},E=g.side==="T"&&typeof ctPush==="function"?ctPush(p,g):null,top=E&&E.gates[0];
  const buy=eb.pistol?"Pistol":eb.full>=.6?"They full buy":(eb.eco||0)>=.6?"They eco":(eb.eco||0)+(eb.force||0)>=.6?"They force or eco":"Their buy unclear";
  return `${buy}${top&&top.share>=15?` - watch ${top.gate} push (${Math.round(top.share)}% of rounds)`:""}${res.length?` - last rounds ${res.join(" ")}`:""}`}
// a path in a few words: the play (rush, split, the site) and only the zones that tell it apart, the rarest of the
// map's T routes (the spawn, the area just out of it and the corridors almost every route takes are left out: on Nuke,
// not "T Spawn > Outside > Lobby" every time, but "A via Squeaky"); two at most, in the order walked
// hostage maps (cs_*): the CTs attack (they get a hostage and bring it back), the Ts defend
const isHostage=m=>/^cs_/.test(m||""),attackSide=m=>isHostage(m)?"CT":"T";
// the path you pressed (numpad 1, 2 or 3, the last one wins) for this round, on the attacking side; 0: none
function focusN(g){const f=g&&g.focus;return f&&f.n>=1&&f.n<=3&&f.round===g.round&&g.side===attackSide(g.map)?f.n:0}
// hostage maps: the CTs' ways out of their spawn as the paths of the attack, in the map's order (10/10: numpad 1, 2, 3 =
// left, middle, right from the CT spawn, the same keys every day), rounds won, when there
function hostageRank(p,g){const H=((p.advice.plan||{}).hostage||{})[g.map];if(!H||!(H.routes||[]).length)return null;const tot=H.routes.reduce((a,r)=>a+r.n,0)||1;
  return {rows:H.routes.map((r,i)=>({rank:r.key||i+1,name:r.name,k:"h"+i,route:{zones:r.zones,pts:r.pts},col:WIN_C[i],wr:r.won,share:Math.round(100*r.n/tot),timing:{at:r.t_end},t_end:r.t_end,n:r.n})),hostage:true}}
// hostage maps: a hostage taken this round (numpad 7 / 9, 10/10, the bomb maps' "after the plant"): the ways back to the
// rescue seen in the base (CT: the one from where you pressed the key; T: the most seen) and the zones they cross, where
// the Ts cut them, with when on the game clock (the key's moment + the carrier's usual time to get there)
function hostageCarry(p,g){const H=((p.advice.plan||{}).hostage||{})[g.map],mk=(((g.hist||{}).marks||{})[g.round]||{}).hostage;
  if(!H||!mk||!(H.carry||[]).length)return null;let rows=H.carry,w=null;
  if(g.side==="CT"&&mk.pos&&H.geo&&typeof worldPx==="function")w=worldPx(H.geo,mk.pos);
  if(w){const d=s=>Math.hypot(s.pts[0][0]-w.px[0],s.pts[0][1]-w.px[1]);rows=[...rows].sort((a,b)=>d(a)-d(b)).slice(0,1)}else rows=rows.slice(0,g.side==="CT"?1:3);
  const at=mk.t!=null?mk.t:null;
  return {n:mk.n,at,you:w,rows:rows.map(s=>({...s,back:at!=null?at+s.s:null,cut:(s.cut||[]).map(c=>({...c,by:at!=null?at+c.after:null}))}))}}
function pathShort(p,g,r){const M=(((p.advice.plan||{}).tside||{}).maps||{})[g.map]||{},lab=String(((M.plays||{}).label||{})[r.k]||r.k);   // fakes: their label is made below
  const all=Object.values(M.t_routes||{}).flat().map(x=>x.zones||[]),freq={};all.forEach(zs=>new Set(zs).forEach(z=>freq[z]=(freq[z]||0)+1));
  const zs=(r.route||{}).zones||[],i0=zs.findIndex(z=>/spawn/i.test(z));
  let cand=zs.filter((z,i)=>!/spawn/i.test(z)&&!/^([AB] Site|Bombsite)/i.test(z)&&!(i===i0+1&&/^outside$/i.test(z))&&(freq[z]||0)<0.7*Math.max(1,all.length));
  const keep=new Set([...cand].sort((a,b)=>(freq[a]||0)-(freq[b]||0)||cand.indexOf(b)-cand.indexOf(a)).slice(0,2));cand=cand.filter((z,i)=>keep.has(z)&&cand.indexOf(z)===i);   // rarest, then nearest the site
  const fk=/^fake[AB]$/.test(r.k)?r.k.slice(4):null,m=fk?null:lab.match(/^(Rush|Split)?\s*([AB])\b/i),site=fk||(m?m[2].toUpperCase():null);
  const kind=fk?"fake":m&&m[1]?m[1].toLowerCase():m?"site":"label",label=lab.replace(/ through .*$/,"");
  const via=cand.length?cand.join(" > "):(/ through /.test(lab)?lab.replace(/^.* through /,"").split(" / ")[0]:"");
  const ps={site,kind,label,via,zones:cand};ps.head=psHead(ps,LANG);return ps}
// a path's head in a language (the page's, the voice's, or "en" for the team chat): "Show B, hit A", "Rush A", "A"
function psHead(ps,l){const s=ps.site,o=s==="A"?"B":"A";
  return ps.kind==="fake"?tlv("Show {a}, hit {b}",l,{a:o,b:s}):ps.kind==="rush"?tlv("Rush {site}",l,{site:s}):ps.kind==="split"?tlv("Split {site}",l,{site:s}):ps.kind==="site"?s:ps.label}
// when to be on the site with a play: its window that wins the most rounds ("on site 1:31-1:21"); when no moment wins
// more than another (under 3 points over the play's average), the usual arrival, with a ~
// hostage maps: "there ~1:41", when the CTs get to the end of their way
// l: the language ("en" for the team chat), else the page's
function onSite(tm,end,l){const L_=l||LANG;if(tm&&tm.at!=null)return tlv("there ~{t}",L_,{t:clock(tm.at)});if(tm&&tm.win-tm.mean>=3)return tlv("on site {a}-{b}",L_,{a:clock(tm.lo),b:clock(tm.hi)});return end&&end[3]!=null?tlv("on site ~{t}",L_,{t:clock(end[3])}):""}
