"""Interactive iPhone PWA dashboard from results_live.json.
Tabs: Signal | Forecast | Returns | Trades.
- 8B model card at TOP (neutral), with accurate liquidation note.
- CORE (spot 1x) shares the SAME ensemble direction as 8B (always consistent).
- Live BTC price fetched client-side hourly (separate from the daily-close signal price).
- Forecast: colour-coded bias (green up / red down / grey aside) + playbook.
- Returns chart: pan/zoom/scale + hover tooltip (date, equity, BTC price).
Self-contained; data embedded.
"""
import os, json
HERE = os.path.dirname(__file__); OUT = os.path.join(HERE, "..", "out")
D = json.load(open(os.path.join(OUT, "results_live.json")))
DATA = json.dumps(D)
json.dump({"name": "BTC Power Signal", "short_name": "BTC Power", "display": "standalone",
           "background_color": "#0b0e14", "theme_color": "#0b0e14", "start_url": "./index.html"},
          open(os.path.join(OUT, "manifest.webmanifest"), "w"))

HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="BTC Power"><meta name="theme-color" content="#0b0e14">
<meta http-equiv="Cache-Control" content="no-cache, must-revalidate"><meta http-equiv="Pragma" content="no-cache">
<link rel="manifest" href="manifest.webmanifest"><title>BTC Power Signal</title>
<style>
:root{--bg:#0b0e14;--card:#161b26;--ink:#e8edf4;--mut:#8b98a9;--grn:#2bd576;--red:#ff5d5d;--amb:#ffb84d;--blu:#4da3ff;--line:#242c3a;--safe-t:env(safe-area-inset-top);--safe-b:env(safe-area-inset-bottom)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,SF Pro Text,Segoe UI,Roboto,sans-serif;overscroll-behavior:none}
.app{max-width:480px;margin:0 auto;padding:calc(var(--safe-t) + 8px) 14px calc(74px + var(--safe-b))}
header{position:sticky;top:0;z-index:5;background:linear-gradient(#0b0e14ee,#0b0e14cc);backdrop-filter:blur(10px);padding:8px 2px 10px;margin:0 -2px 6px}
.brand{font-size:13px;color:var(--mut)}.px{font-size:30px;font-weight:800}.px small{font-size:12px;color:var(--mut);margin-left:8px}
.sub2{font-size:11px;color:var(--mut);margin-top:2px}
.chip{display:inline-block;margin-top:5px;padding:5px 12px;border-radius:30px;font-weight:700;font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:15px;margin-bottom:12px}
.card.feat{border-color:#3a4458;background:#171d2b}
.h{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px}
.big{font-size:22px;font-weight:700}.row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--line)}
.row:last-child{border:0}.k{color:var(--mut);font-size:13px}.v{font-weight:600;text-align:right}.pos{color:var(--grn)}.neg{color:var(--red)}.amb{color:var(--amb)}.mut{color:var(--mut)}
.note{color:var(--mut);font-size:11.5px;line-height:1.55;margin-top:8px}
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:6;display:flex;justify-content:space-around;background:#10141ccc;backdrop-filter:blur(14px);border-top:1px solid var(--line);padding:8px 4px calc(8px + var(--safe-b))}
.tab{flex:1;text-align:center;color:var(--mut);font-size:11px;font-weight:600;padding:4px;border-radius:10px}.tab.on{color:var(--blu)}.tab .ic{display:block;font-size:18px}
.pane{display:none}.pane.on{display:block}
.lvl{display:grid;grid-template-columns:1fr 1fr;gap:6px}.lvl div{background:#0e131d;border:1px solid var(--line);border-radius:10px;padding:8px}.lvl .k{font-size:11px}
.biasbig{font-size:26px;font-weight:800;margin:2px 0}
.legend{display:flex;gap:14px;font-size:12px;color:var(--mut);margin:6px 0 10px}.legend b{font-weight:600}
.scbtns{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.scb{font-size:11px;font-weight:700;padding:6px 9px;border-radius:8px;background:#0e131d;border:1px solid var(--line);color:var(--mut)}.scb.on{background:#13324a;color:var(--blu);border-color:var(--blu)}
canvas{width:100%;height:300px;display:block;border-radius:10px;touch-action:none;background:#0c1018;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}
#p-perf,#p-perf *{user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}
.ctrls{display:flex;gap:6px;margin-top:8px}.ctrls button{flex:1;font-size:12px;font-weight:600;padding:7px;border-radius:8px;background:#0e131d;border:1px solid var(--line);color:var(--ink)}
.trade{background:#0e131d;border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:7px;font-size:12px}
.trade .t1{display:flex;justify-content:space-between;font-weight:700;font-size:13px}.trade .t2{color:var(--mut);margin-top:3px;display:flex;justify-content:space-between}
.risknote{background:#23200f;border:1px solid #4a431d;border-radius:10px;padding:9px;color:#ffe39a;font-size:11.5px;margin-top:8px}
.trade{cursor:pointer;transition:border-color .15s}.trade:active{border-color:var(--blu)}
.modal{position:fixed;inset:0;z-index:20;background:#000c;backdrop-filter:blur(3px);display:none;align-items:center;justify-content:center;padding:22px}
.modal.on{display:flex}
.sheet{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;max-width:360px;width:100%}
.sheet h3{margin:0 0 4px;font-size:16px}.sheet .sub{color:var(--mut);font-size:11.5px;margin-bottom:8px}
.acts{display:flex;gap:8px;margin-top:14px}
.acts button{flex:1;padding:10px;border-radius:10px;font-weight:700;font-size:13px;border:1px solid var(--line)}
.btn-pri{background:#13324a;color:var(--blu);border-color:var(--blu)}.btn-sec{background:#0e131d;color:var(--ink)}
</style></head><body><div class="app">
<header><div class="brand">⚡ BTC POWER • signal <span id="asof"></span></div>
<div class="px">$<span id="pxlive">…</span><small id="pxsig"></small></div>
<div class="sub2" id="livenote">live price · updates hourly</div>
<div class="chip" id="chip"></div></header>

<div class="pane on" id="p-signal">
  <div class="card feat"><div class="h">⚡ Max B Model · 5× vol-targeted + cycle shields</div>
    <div class="big" id="b8_action"></div>
    <div class="row"><span class="k">Market type</span><span class="v" id="b8_regime"></span></div>
    <div class="row"><span class="k">Engines</span><span class="v" id="b8_eng"></span></div>
    <div class="row"><span class="k">Confidence</span><span class="v" id="b8_conf"></span></div>
    <div class="row"><span class="k">Position entry</span><span class="v" id="b8_entry"></span></div>
    <div class="row"><span class="k">Margin used (setting 5×)</span><span class="v" id="b8_margin"></span></div>
    <div class="row"><span class="k">Cut-loss (entry −15%)</span><span class="v amb" id="b8_cut"></span></div>
    <div class="row"><span class="k">Liquidation (from entry)</span><span class="v" id="b8_liq"></span></div>
    <div class="risknote" id="b8_note"></div>
  </div>
  <div class="card"><div class="h">Core · spot 1× (safer, same direction)</div>
    <div class="big" id="c_action" style="font-size:18px"></div>
    <div class="row"><span class="k">Size</span><span class="v" id="c_size"></span></div>
    <div class="row"><span class="k">Margin</span><span class="v" id="c_margin" style="font-size:12px"></span></div>
    <div class="row"><span class="k">Cut-loss</span><span class="v amb" id="c_cut"></span></div>
  </div>
  <div class="card"><div class="h">Key levels</div><div class="lvl" id="levels"></div></div>
  <div class="card"><div class="h">⏱ When signals happen</div>
    <div class="note" style="margin-top:0">The signal is decided on the <b>daily close (00:00 UTC)</b> and the action price = that close — the position and its cut-loss/liquidation are <b>fixed from entry</b> and do not re-price each day. Entry/exit alerts go out within ~1h of the close; the <b>cut-loss is watched hourly intraday</b> (an alert fires if the live price breaches it). The header's live price is for reference only.</div>
  </div>
</div>

<div class="pane" id="p-forecast">
  <div class="card"><div class="h">Market forecast</div>
    <div class="biasbig" id="f_bias"></div>
    <div class="note" id="f_head" style="font-size:14px;color:var(--ink)"></div>
    <div class="row" style="margin-top:8px"><span class="k">Market type</span><span class="v" id="f_regime"></span></div>
    <div class="row"><span class="k">Engines active</span><span class="v" id="f_eng"></span></div>
  </div>
  <div class="card"><div class="h">Playbook — what each market type means</div>
    <div class="legend"><span><b style="color:var(--grn)">● up</b> go long</span><span><b style="color:var(--red)">● down</b> go short</span><span><b style="color:var(--mut)">● aside</b> no trade</span></div>
    <div id="rmap"></div>
  </div>
</div>

<div class="pane" id="p-perf">
  <div class="card"><div class="h">Equity from $500 — drag to pan · pinch/wheel zoom · tap a point</div>
    <div class="scbtns" id="scbtns"></div>
    <canvas id="chart"></canvas>
    <div class="legend" style="margin-top:6px;flex-wrap:wrap"><span><b style="color:var(--grn)">▲</b> enter long</span><span><b style="color:var(--red)">▼</b> enter short</span><span><b style="color:var(--grn)">△</b><b style="color:var(--red)">▽</b> exit</span><span class="mut">tap a Trade to pin</span></div>
    <div class="ctrls"><button onclick="setRange(365)">1Y</button><button onclick="setRange(1095)">3Y</button><button onclick="setRange(1825)">5Y</button><button onclick="setRange(0)">All</button></div>
    <div class="ctrls"><button onclick="zoomBtn(0.7)">＋</button><button onclick="zoomBtn(1.4)">－</button><button onclick="toggleScale()" id="scaleBtn">Log</button><button onclick="toggleMarks()" id="markBtn">Marks ●</button><button onclick="resetView()">Reset</button></div>
    <div class="row" style="margin-top:8px"><span class="k">Final $500→</span><span class="v" id="m_final"></span></div>
    <div class="row"><span class="k">CAGR / maxDD</span><span class="v" id="m_cd"></span></div>
  </div>
</div>

<div class="pane" id="p-trades">
  <div class="card"><div class="h">Max B — recent 20 positions (entry → exit)</div>
    <div class="note" style="margin:0 0 8px">Each = a position Max B held until its direction changed. % = the live model's realized equity return (after slippage). The top row is the <b>current open position</b> — it shows the latest price and a running return, no exit yet.</div>
    <div id="tradelist"></div></div>
</div>
<div class="note" style="text-align:center;opacity:.55;margin-top:2px" id="footgen"></div>
</div>
<div class="modal" id="tmodal"><div class="sheet">
  <h3 id="tm_title"></h3><div class="sub" id="tm_sub"></div>
  <div id="tm_body"></div>
  <div class="acts"><button class="btn-pri" id="tm_jump">📈 Jump to chart</button><button class="btn-sec" onclick="closeModal()">Close</button></div>
</div></div>
<nav class="tabbar">
  <div class="tab on" data-p="signal"><span class="ic">📡</span>Signal</div>
  <div class="tab" data-p="forecast"><span class="ic">🔮</span>Forecast</div>
  <div class="tab" data-p="perf"><span class="ic">📈</span>Returns</div>
  <div class="tab" data-p="trades"><span class="ic">🧾</span>Trades</div>
</nav>
<script>
const D=__DATA__;
const f0=x=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:0});
const fp=x=>x==null||isNaN(x)?'—':(x*100).toFixed(1)+'%';const f2=x=>x==null||isNaN(x)?'—':Number(x).toFixed(2);
const $=id=>document.getElementById(id);
$('asof').textContent=D.as_of;$('pxsig').textContent='signal close $'+f0(D.price);
$('pxlive').textContent=f0(D.price);
// live price (hourly+) client-side
async function livePrice(){try{const r=await fetch('https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT');const j=await r.json();const p=Number(j.price);$('pxlive').textContent=f0(p);
 const t=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});$('livenote').textContent='live $'+f0(p)+' · '+t+' · signal updates daily';try{updOpen(p);}catch(e){}}catch(e){$('livenote').textContent='live price unavailable · showing signal close';}}
livePrice();setInterval(livePrice,3600000);
// auto-refresh: PWAs cache the HTML — detect a newer deployed build and hard-reload to a
// cache-busted URL so the home-screen app updates itself (on open, on re-focus, hourly).
$('footgen').textContent='data built '+(D.generated||'—')+' · auto-updates';
const EMBED_GEN=D.generated;let _checking=false;
async function checkFresh(){if(_checking)return;_checking=true;
 try{const r=await fetch('results_live.json?t='+Date.now(),{cache:'no-store'});const j=await r.json();
  if(j.generated&&j.generated!==EMBED_GEN){const u=new URL(location.href);
   if(u.searchParams.get('v')!==j.generated){u.searchParams.set('v',j.generated);location.replace(u.toString());return;}}}
 catch(e){}finally{_checking=false;}}
checkFresh();
document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkFresh();});
window.addEventListener('focus',checkFresh);setInterval(checkFresh,1800000);
// header chip = 8B direction
const dirc=d=>d==='LONG'?'var(--grn)':(d==='SHORT'?'var(--red)':'var(--mut)');
const B=D.model_growth||D.model_apex||D.model_8b,C=D.live,F=D.forecast;
const chip=$('chip');chip.textContent='Max B: '+B.action;chip.style.background=dirc(B.direction)+'22';chip.style.color=dirc(B.direction);
// 8B card
$('b8_action').textContent=B.action;$('b8_action').style.color=dirc(B.direction);
$('b8_regime').textContent=B.regime;$('b8_eng').textContent=(B.engines||[]).join(', ')||'—';
$('b8_conf').textContent=B.confidence+(B.conviction_ok?'':' (below 0.40 → flat)');
$('b8_entry').textContent=B.entry_price?('$'+f0(B.entry_price)+' · '+(B.entry_date||'')):'—';
$('b8_margin').textContent=B.margin_pct+'% of equity';$('b8_cut').textContent=B.cutloss?('$'+f0(B.cutloss)):'—';
$('b8_liq').textContent=B.liquidation?('$'+f0(B.liquidation)):'—';$('b8_note').textContent='ℹ️ '+B.note;
// core card
$('c_action').textContent=C.action;$('c_action').style.color=dirc(C.direction);
$('c_size').textContent=C.size_pct+'% of equity';$('c_margin').textContent=C.margin;$('c_cut').textContent=C.cutloss?('$'+f0(C.cutloss)):'—';
// levels
const lv=D.levels;$('levels').innerHTML=[['Price','price'],['SMA20','sma20'],['SMA50','sma50'],['SMA200','sma200'],['BB upper','bb_upper'],['BB lower','bb_lower']].map(([n,k])=>`<div><div class="k">${n}</div><div class="v">$${f0(lv[k])}</div></div>`).join('');
// forecast
const bc=F.bias==='POTENTIAL UP'?'var(--grn)':(F.bias==='POTENTIAL DOWN'?'var(--red)':'var(--mut)');
$('f_bias').textContent=(F.bias==='POTENTIAL UP'?'▲ ':(F.bias==='POTENTIAL DOWN'?'▼ ':'■ '))+F.bias;$('f_bias').style.color=bc;
$('f_head').textContent=F.headline;$('f_regime').textContent=F.regime;$('f_eng').textContent=(F.engines||[]).join(', ')||'—';
const BCOL={UP:'var(--grn)',DOWN:'var(--red)',ASIDE:'var(--mut)'};const BTXT={UP:'long',DOWN:'short',ASIDE:'stand aside'};
$('rmap').innerHTML=Object.entries(D.regime_bias).map(([k,b])=>`<div class="row"><span class="k">${k}</span><span class="v" style="color:${BCOL[b]}">● ${BTXT[b]}</span></div>`).join('');
// trades (tap a row -> detail popup + jump to chart)
const tret=t=>(t.apex_ret!=null?t.apex_ret:t.ret);
$('tradelist').innerHTML=D.recent_trades.map((t,k)=>{const c=t.direction==='LONG'?'var(--grn)':'var(--red)';const r=tret(t);const rc=r>=0?'pos':'neg';
 if(t.open) return `<div class="trade" onclick="openTrade(${k})" style="border-color:var(--blu)"><div class="t1"><span style="color:${c}">● CURRENT · ${t.direction} · ${t.strategy}</span><span class="${rc}" id="open_ret">${(r*100).toFixed(1)}%</span></div>
 <div class="t2"><span>open since ${t.entry_dt}</span><span>${t.market}</span></div>
 <div class="t2"><span>in $${f0(t.entry)} · now $<span id="open_now">${f0(D.price)}</span></span><span>running · open ›</span></div></div>`;
 return `<div class="trade" onclick="openTrade(${k})"><div class="t1"><span style="color:${c}">${t.direction} · ${t.strategy}</span><span class="${rc}">${(r*100).toFixed(1)}%</span></div>
 <div class="t2"><span>${t.entry_dt} → ${t.exit_dt}</span><span>${t.market}</span></div>
 <div class="t2"><span>in $${f0(t.entry)} · out $${f0(t.exit)}</span><span>${t.reason} ›</span></div></div>`}).join('');
// keep the open position's "now" price + running return fresh with the live price
function updOpen(p){const t=D.recent_trades.find(x=>x.open);if(!t)return;const nb=$('open_now');if(nb)nb.textContent=f0(p);
 const rb=$('open_ret');if(!rb)return;const dir=t.direction==='LONG'?1:-1;const MM=D.model_growth||D.model_apex;const expm=(MM&&MM.exposure_mult)||1;
 const base=(t.apex_ret!=null?t.apex_ret:0),since=(p/D.price-1)*dir*expm,r=(1+base)*(1+since)-1;
 rb.textContent=(r*100).toFixed(1)+'%';rb.className=r>=0?'pos':'neg';}
updOpen(D.price);
// trade detail popup: 1x (spot) vs 5x (8B) return + jump-to-chart
function tradeIdx(t){if(t.idx!=null)return t.idx;const i=D.dates.indexOf(t.entry_dt);return i>=0?i:null;}
function openTrade(k){const t=D.recent_trades[k];const c=t.direction==='LONG'?'var(--grn)':'var(--red)';
 const r1=t.ret,ra=(t.apex_ret!=null?t.apex_ret:t.ret);
 $('tm_title').innerHTML=`<span style="color:${c}">${t.open?'● CURRENT · ':''}${t.direction} · ${t.strategy}</span>`;
 $('tm_sub').textContent=t.market+' · '+t.entry_dt+(t.open?' → now (open)':' → '+t.exit_dt);
 $('tm_body').innerHTML=[
   ['Entry',`$${f0(t.entry)} · ${t.entry_dt}`],
   [t.open?'Now (last close)':'Exit',t.open?`$${f0(D.price)} · ${D.as_of}`:`$${f0(t.exit)} · ${t.exit_dt}`],
   ['Spot 1× move',`<span class="${r1>=0?'pos':'neg'}">${(r1*100).toFixed(1)}%</span>`],
   [t.open?'Max B return (running)':'Max B return (realized)',`<span class="${ra>=0?'pos':'neg'}">${(ra*100).toFixed(1)}%</span>`],
   ['Status',t.reason]
 ].map(([a,b])=>`<div class="row"><span class="k">${a}</span><span class="v">${b}</span></div>`).join('');
 const ix=tradeIdx(t);$('tm_jump').onclick=()=>{closeModal();jumpToTrade(ix);};
 $('tm_jump').style.opacity=ix==null?0.4:1;
 $('tmodal').classList.add('on');}
function closeModal(){$('tmodal').classList.remove('on');}
$('tmodal').addEventListener('click',e=>{if(e.target.id==='tmodal')closeModal();});
function jumpToTrade(idx){if(idx==null)return;pinned=idx;const half=120,L=D.dates.length-1;
 view.a=Math.max(0,idx-half);view.b=Math.min(L,idx+half);switchTab('perf');}
// ---- interactive chart ----
const SC=Object.keys(D.scenarios);let scenario=SC.includes('Max B @50bp')?'Max B @50bp':(SC.includes('Growth A @50bp')?'Growth A @50bp':SC[0]);
let logScale=true,view={a:0,b:D.dates.length-1},hover=null,showMarks=true,pinned=null;
$('scbtns').innerHTML=SC.map(s=>`<div class="scb${s===scenario?' on':''}" data-sc="${s}">${s}</div>`).join('');
document.querySelectorAll('.scb').forEach(b=>b.onclick=()=>{scenario=b.dataset.sc;document.querySelectorAll('.scb').forEach(x=>x.classList.toggle('on',x.dataset.sc===scenario));updM();draw();});
function updM(){const m=D.scenarios[scenario].metrics;$('m_final').textContent='$'+f0(m.final);$('m_cd').textContent=fp(m.cagr)+' / '+fp(m.maxdd);}
function zoomBtn(f){const c=(view.a+view.b)/2,w=(view.b-view.a)*f/2;view.a=Math.max(0,c-w);view.b=Math.min(D.dates.length-1,c+w);draw();}
function toggleScale(){logScale=!logScale;$('scaleBtn').textContent=logScale?'Log':'Lin';draw();}
function toggleMarks(){showMarks=!showMarks;$('markBtn').textContent=showMarks?'Marks ●':'Marks ○';draw();}
function resetView(){view={a:0,b:D.dates.length-1};hover=null;pinned=null;draw();}
function setRange(d){const L=D.dates.length-1;view=d?{a:Math.max(0,L-d),b:L}:{a:0,b:L};hover=null;draw();}
function draw(){const cv=$('chart');if(!cv.clientWidth)return;const dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=300;
 cv.width=W*dpr;cv.height=H*dpr;const x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,W,H);
 const eq=D.scenarios[scenario].eq,a=Math.max(0,Math.floor(view.a)),b=Math.min(eq.length-1,Math.ceil(view.b));
 let lo=Infinity,hi=-Infinity;for(let i=a;i<=b;i++){const v=eq[i];if(v>0){if(v<lo)lo=v;if(v>hi)hi=v;}}if(!isFinite(lo)){lo=1;hi=10;}
 const PL=46,PR=8,PT=10,PB=18;const px=i=>PL+(W-PL-PR)*(i-a)/Math.max(1,b-a);
 const ya=logScale?Math.log10(Math.max(lo,1e-6)):lo,yb=logScale?Math.log10(hi):hi;
 const py=v=>{const t=((logScale?Math.log10(Math.max(v,1e-6)):v)-ya)/Math.max(1e-9,yb-ya);return H-PB-(H-PT-PB)*t;};
 x.strokeStyle='#1c2433';x.fillStyle='#6b7787';x.font='9px sans-serif';
 const fk=v=>v>=1e9?'$'+(Math.round(v/1e8)/10)+'B':v>=1e6?'$'+(Math.round(v/1e5)/10)+'M':v>=1e3?'$'+(Math.round(v/100)/10)+'k':'$'+Math.round(v);
 const span=yb-ya;
 if(logScale&&span>=1){
  // adaptive 1-2-5 log ticks: fills the big visual gaps between powers of 10
  const mults=span>=3?[1,5]:[1,2,5];
  for(let p=Math.floor(ya)-1;p<=Math.ceil(yb);p++)for(const m of mults){const v=m*Math.pow(10,p);
   if(v<lo*0.999||v>hi*1.001)continue;const y=py(v);x.beginPath();x.moveTo(PL,y);x.lineTo(W-PR,y);x.stroke();x.fillText(fk(v),3,y-2);}}
 else{for(let g=0;g<=4;g++){const v=lo+(hi-lo)*g/4,y=py(v);x.beginPath();x.moveTo(PL,y);x.lineTo(W-PR,y);x.stroke();x.fillText(fk(v),3,y-2);}}
 x.fillStyle='#6b7787';[a,Math.floor((a+b)/2),b].forEach(i=>x.fillText((D.dates[i]||'').slice(0,7),Math.min(W-40,Math.max(PL,px(i)-16)),H-4));
 x.strokeStyle='#2bd576';x.lineWidth=1.8;x.beginPath();let st=false;for(let i=a;i<=b;i++){const v=eq[i];if(v<=0)continue;i&&st?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v));st=true;}x.stroke();
 // Apex markers — solid ▲/▼ = ENTER (green long / red short), hollow △/▽ = EXIT (paired); de-cluttered
 if(showMarks&&D.trade_markers){let lin=-99,lout=-99;D.trade_markers.forEach(mk=>{const ix=mk.i;if(ix<a||ix>b)return;const v=eq[ix];if(v<=0)return;const X=px(ix);const out=mk.t==='out';
   if(out){if(X-lout<12)return;lout=X;}else{if(X-lin<12)return;lin=X;}
   const Y=py(v),col=mk.d>0?'#2bd576':'#ff5d5d';x.beginPath();
   if(mk.d>0){x.moveTo(X,Y-12);x.lineTo(X-5,Y-3);x.lineTo(X+5,Y-3);}else{x.moveTo(X,Y+12);x.lineTo(X-5,Y+3);x.lineTo(X+5,Y+3);}
   x.closePath();if(out){x.fillStyle='#0c1018';x.fill();x.strokeStyle=col;x.lineWidth=1.6;x.stroke();}else{x.fillStyle=col;x.fill();}});}
 // pinned trade (from the Trades tab) — amber dashed line + dot, always shown
 if(pinned!=null&&pinned>=a&&pinned<=b){const v=eq[pinned];if(v>0){const X=px(pinned),Y=py(v);x.strokeStyle='#ffb84d';x.lineWidth=1.5;x.setLineDash([3,3]);x.beginPath();x.moveTo(X,PT);x.lineTo(X,H-PB);x.stroke();x.setLineDash([]);x.fillStyle='#ffb84d';x.beginPath();x.arc(X,Y,5,0,7);x.fill();x.strokeStyle='#0c1018';x.lineWidth=2;x.stroke();}}
 // hover tooltip
 if(hover!=null&&hover>=a&&hover<=b){const X=px(hover),v=eq[hover];x.strokeStyle='#4da3ff';x.lineWidth=1;x.setLineDash([4,3]);x.beginPath();x.moveTo(X,PT);x.lineTo(X,H-PB);x.stroke();x.setLineDash([]);
  if(v>0){x.fillStyle='#4da3ff';x.beginPath();x.arc(X,py(v),3.5,0,7);x.fill();}
  const lines=[(D.dates[hover]||'').slice(0,10),'Equity $'+f0(v),'BTC $'+f0(D.close[hover])];
  x.font='11px sans-serif';const tw=Math.max(...lines.map(s=>x.measureText(s).width))+12;const tx=Math.min(W-tw-4,Math.max(4,X+8));
  x.fillStyle='#0e1622ee';x.strokeStyle='#2a3650';x.lineWidth=1;x.beginPath();x.rect(tx,PT+2,tw,46);x.fill();x.stroke();
  x.fillStyle='#cfe3ff';lines.forEach((s,k)=>x.fillText(s,tx+6,PT+16+k*14));}
}
const cv=$('chart');let drag=null,lastDist=null;
function idxFromX(clientX){const r=cv.getBoundingClientRect();const fx=(clientX-r.left-46)/(r.width-54);return Math.round(view.a+(view.b-view.a)*Math.max(0,Math.min(1,fx)));}
cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,a:view.a,b:view.b,moved:false};cv.setPointerCapture(e.pointerId);hover=idxFromX(e.clientX);draw();});
cv.addEventListener('pointermove',e=>{hover=idxFromX(e.clientX);if(drag&&!lastDist){const dpx=e.clientX-drag.x;if(Math.abs(dpx)>3)drag.moved=true;const span=drag.b-drag.a;let a=drag.a-dpx/cv.clientWidth*span,b=drag.b-dpx/cv.clientWidth*span;if(a<0){b-=a;a=0;}if(b>D.dates.length-1){a-=(b-(D.dates.length-1));b=D.dates.length-1;}view.a=Math.max(0,a);view.b=b;}draw();});
cv.addEventListener('pointerup',()=>drag=null);cv.addEventListener('pointercancel',()=>drag=null);
cv.addEventListener('pointerleave',()=>{hover=null;draw();});
cv.addEventListener('wheel',e=>{e.preventDefault();const fi=idxFromX(e.clientX),f=e.deltaY>0?1.15:0.87;view.a=Math.max(0,fi-(fi-view.a)*f);view.b=Math.min(D.dates.length-1,fi+(view.b-fi)*f);draw();},{passive:false});
cv.addEventListener('touchmove',e=>{if(e.touches.length===2){e.preventDefault();const d=Math.abs(e.touches[0].clientX-e.touches[1].clientX);if(lastDist){const f=lastDist/d,c=(view.a+view.b)/2,w=(view.b-view.a)*f/2;view.a=Math.max(0,c-w);view.b=Math.min(D.dates.length-1,c+w);draw();}lastDist=d;}},{passive:false});
cv.addEventListener('touchend',()=>lastDist=null);
function switchTab(p){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.p===p));document.querySelectorAll('.pane').forEach(x=>x.classList.remove('on'));$('p-'+p).classList.add('on');if(p==='perf')setTimeout(draw,40);}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>switchTab(t.dataset.p));
updM();window.addEventListener('resize',()=>{if($('p-perf').classList.contains('on'))draw();});
</script></body></html>"""
out = HTML.replace("__DATA__", DATA)
for fn in ["index.html", "dashboard_live.html"]:
    open(os.path.join(OUT, fn), "w", encoding="utf-8").write(out)
print("wrote index.html + dashboard_live.html (", len(out), "bytes )")
