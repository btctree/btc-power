"""Multi-asset dashboard from results_multi.json. Tabs: Basket | Returns | About.
- Basket: today's holdings table (per-coin direction/size/regime/running %) + summary.
- Returns: scenario toggle (Basket top-8 / equal-wt / BTC 1x) + pan/zoom chart + metrics.
- About: the honest note + universe + caveats. Self-contained PWA; data embedded.
"""
import os, json
HERE = os.path.dirname(__file__); OUT = os.path.join(HERE, "..", "out")
D = json.load(open(os.path.join(OUT, "results_multi.json")))
DATA = json.dumps(D)

HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta http-equiv="Cache-Control" content="no-cache"><title>BTC Power · Basket</title>
<style>
:root{--bg:#0b0e14;--card:#161b26;--ink:#e8edf4;--mut:#8b98a9;--grn:#2bd576;--red:#ff5d5d;--amb:#ffb84d;--blu:#4da3ff;--line:#242c3a;--safe-t:env(safe-area-inset-top);--safe-b:env(safe-area-inset-bottom)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,SF Pro Text,Segoe UI,Roboto,sans-serif;overscroll-behavior:none}
.app{max-width:520px;margin:0 auto;padding:calc(var(--safe-t) + 8px) 14px calc(74px + var(--safe-b))}
header{position:sticky;top:0;z-index:5;background:linear-gradient(#0b0e14ee,#0b0e14cc);backdrop-filter:blur(10px);padding:8px 2px 10px;margin:0 -2px 6px}
.brand{font-size:13px;color:var(--mut)}.px{font-size:26px;font-weight:800}.px small{font-size:12px;color:var(--mut);margin-left:8px}
.chip{display:inline-block;margin-top:6px;padding:5px 12px;border-radius:30px;font-weight:700;font-size:13px;background:#13324a;color:var(--blu)}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin-bottom:12px}
.h{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px}
.row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--line)}.row:last-child{border:0}
.k{color:var(--mut);font-size:13px}.v{font-weight:600;text-align:right}.pos{color:var(--grn)}.neg{color:var(--red)}.mut{color:var(--mut)}
.note{color:var(--mut);font-size:11.5px;line-height:1.55;margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:13px}th{color:var(--mut);font-size:11px;text-transform:uppercase;text-align:right;padding:6px 4px;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}td{padding:8px 4px;border-bottom:1px solid var(--line)}
.pill{font-weight:700;font-size:11px;padding:2px 7px;border-radius:20px}
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:6;display:flex;justify-content:space-around;background:#10141ccc;backdrop-filter:blur(14px);border-top:1px solid var(--line);padding:8px 4px calc(8px + var(--safe-b))}
.tab{flex:1;text-align:center;color:var(--mut);font-size:11px;font-weight:600;padding:4px;border-radius:10px}.tab.on{color:var(--blu)}.tab .ic{display:block;font-size:18px}
.pane{display:none}.pane.on{display:block}
.scbtns{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.scb{font-size:11px;font-weight:700;padding:6px 9px;border-radius:8px;background:#0e131d;border:1px solid var(--line);color:var(--mut)}.scb.on{background:#13324a;color:var(--blu);border-color:var(--blu)}
canvas{width:100%;height:300px;display:block;border-radius:10px;touch-action:none;background:#0c1018;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}
#p-perf,#p-perf *{user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}
.ctrls{display:flex;gap:6px;margin-top:8px}.ctrls button{flex:1;font-size:12px;font-weight:600;padding:7px;border-radius:8px;background:#0e131d;border:1px solid var(--line);color:var(--ink)}
.legend{display:flex;gap:14px;font-size:12px;color:var(--mut);margin:6px 0 2px}
</style></head><body><div class="app">
<header><div class="brand">⚡ BTC POWER • <span id="prod"></span> <span id="asof"></span></div>
<div class="px">BTC $<span id="btcpx">…</span></div>
<div class="chip" id="chip"></div></header>

<div class="pane on" id="p-basket">
  <div class="card"><div class="h">Today's basket — 8 most-liquid majors (no leverage)</div>
    <table><thead><tr><th>Coin</th><th>Position</th><th>Size</th><th>Market</th><th>Running</th></tr></thead>
    <tbody id="hold"></tbody></table>
    <div class="note" id="bnote"></div>
  </div>
  <div class="card"><div class="h">Why a basket</div>
    <div class="note" style="font-size:12.5px;color:var(--ink)">Diversified trend-following across majors roughly <b>doubles BTC's risk-adjusted return at about half the drawdown</b> (validated across 2017–20 and 2021–26). Each coin uses the same 1× vol-targeted ensemble; correlations are low (0.2–0.4), so the blend is smoother than any single coin. No leverage — cannot be liquidated.</div>
  </div>
</div>

<div class="pane" id="p-perf">
  <div class="card"><div class="h">Equity from $500 — drag to pan · pinch/wheel zoom · tap a point</div>
    <div class="scbtns" id="scbtns"></div>
    <canvas id="chart"></canvas>
    <div class="legend"><span class="mut">log scale · the basket line is smoother than BTC alone</span></div>
    <div class="ctrls"><button onclick="zoomBtn(0.7)">＋</button><button onclick="zoomBtn(1.4)">－</button><button onclick="toggleScale()" id="scaleBtn">Log</button><button onclick="resetView()">Reset</button></div>
    <div class="row" style="margin-top:8px"><span class="k">Final $500→</span><span class="v" id="m_final"></span></div>
    <div class="row"><span class="k">CAGR / maxDD</span><span class="v" id="m_cd"></span></div>
    <div class="row"><span class="k">Sharpe / Calmar</span><span class="v" id="m_sc"></span></div>
    <div class="note" id="m_desc"></div>
  </div>
</div>

<div class="pane" id="p-about">
  <div class="card"><div class="h">About this product</div><div class="note" style="font-size:12.5px;color:var(--ink)" id="about"></div>
    <div class="row" style="margin-top:8px"><span class="k">Universe</span><span class="v" id="uni" style="font-size:11px"></span></div>
  </div>
  <div class="card"><div class="h">Honest caveats</div>
    <div class="note" style="font-size:12px">• Underperforms BTC-only in pure <b>alt-bear years (2018, 2022)</b> — alts fall harder.<br>• Alt fills cost more than BTC; figures use tiered slippage (50–120 bp).<br>• Hypothetical backtest, daily close, $500 start. <b>Not financial advice.</b></div>
  </div>
</div>
<div class="note" style="text-align:center;opacity:.55" id="footgen"></div>
</div>
<nav class="tabbar">
  <div class="tab on" data-p="basket"><span class="ic">🧺</span>Basket</div>
  <div class="tab" data-p="perf"><span class="ic">📈</span>Returns</div>
  <div class="tab" data-p="about"><span class="ic">ℹ️</span>About</div>
</nav>
<script>
const D=__DATA__;const $=id=>document.getElementById(id);
const f0=x=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:0});
const fp=x=>x==null||isNaN(x)?'—':(x*100).toFixed(1)+'%';const f2=x=>x==null||isNaN(x)?'—':Number(x).toFixed(2);
const dirc=d=>d==='LONG'?'var(--grn)':(d==='SHORT'?'var(--red)':'var(--mut)');
$('prod').textContent=D.product;$('asof').textContent='· '+D.as_of;$('btcpx').textContent=f0(D.btc_price);
const bt=D.basket_today;$('chip').textContent=`Basket: ${bt.long} long · ${bt.short} short · ${bt.flat} flat`;
$('hold').innerHTML=D.holdings_top8.map(h=>`<tr><td><b>${h.sym}</b></td>
 <td style="text-align:right"><span class="pill" style="background:${dirc(h.direction)}22;color:${dirc(h.direction)}">${h.direction}</span></td>
 <td class="v">${h.size_pct}%</td><td class="v" style="font-size:11px;color:var(--mut)">${h.regime}</td>
 <td class="v ${h.running_ret>=0?'pos':'neg'}">${(h.running_ret*100).toFixed(1)}%</td></tr>`).join('');
$('bnote').textContent='“Running” = the current open position\'s return since it was entered (1× price move). Selected monthly by trailing liquidity — no hindsight.';
$('about').textContent=D.note;$('uni').textContent=D.universe.join(' · ');
$('footgen').textContent='data built '+(D.generated||'—');
// live BTC price
(async()=>{try{const r=await fetch('https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT');const j=await r.json();$('btcpx').textContent=f0(Number(j.price));}catch(e){}})();
// ---- chart ----
const SC=Object.keys(D.scenarios);let scenario=SC[0],logScale=true,view={a:0,b:D.dates.length-1},hover=null;
$('scbtns').innerHTML=SC.map(s=>`<div class="scb${s===scenario?' on':''}" data-sc="${s}">${s}</div>`).join('');
document.querySelectorAll('.scb').forEach(b=>b.onclick=()=>{scenario=b.dataset.sc;document.querySelectorAll('.scb').forEach(x=>x.classList.toggle('on',x.dataset.sc===scenario));updM();draw();});
function updM(){const s=D.scenarios[scenario],m=s.metrics;$('m_final').textContent='$'+f0(m.final);$('m_cd').textContent=fp(m.cagr)+' / '+fp(m.maxdd);$('m_sc').textContent=f2(m.sharpe)+' / '+f2(m.calmar);$('m_desc').textContent=s.desc||'';}
function zoomBtn(f){const c=(view.a+view.b)/2,w=(view.b-view.a)*f/2;view.a=Math.max(0,c-w);view.b=Math.min(D.dates.length-1,c+w);draw();}
function toggleScale(){logScale=!logScale;$('scaleBtn').textContent=logScale?'Log':'Lin';draw();}
function resetView(){view={a:0,b:D.dates.length-1};hover=null;draw();}
const COL={'Basket top-8':'#2bd576','Basket equal-wt':'#4da3ff','BTC 1x':'#ffb84d'};
function draw(){const cv=$('chart');if(!cv.clientWidth)return;const dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=300;
 cv.width=W*dpr;cv.height=H*dpr;const x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,W,H);
 const eq=D.scenarios[scenario].eq,a=Math.max(0,Math.floor(view.a)),b=Math.min(eq.length-1,Math.ceil(view.b));
 let lo=Infinity,hi=-Infinity;for(let i=a;i<=b;i++){const v=eq[i];if(v>0){if(v<lo)lo=v;if(v>hi)hi=v;}}if(!isFinite(lo)){lo=1;hi=10;}
 const PL=48,PR=8,PT=10,PB=18,px=i=>PL+(W-PL-PR)*(i-a)/Math.max(1,b-a);
 const ya=logScale?Math.log10(Math.max(lo,1e-6)):lo,yb=logScale?Math.log10(hi):hi;
 const py=v=>{const t=((logScale?Math.log10(Math.max(v,1e-6)):v)-ya)/Math.max(1e-9,yb-ya);return H-PB-(H-PT-PB)*t;};
 x.strokeStyle='#1c2433';x.fillStyle='#6b7787';x.font='9px sans-serif';
 if(logScale){for(let p=Math.ceil(ya);p<=Math.floor(yb);p++){const y=py(Math.pow(10,p));x.beginPath();x.moveTo(PL,y);x.lineTo(W-PR,y);x.stroke();x.fillText('$'+f0(Math.pow(10,p)),3,y-2);}}
 else{for(let g=0;g<=4;g++){const v=lo+(hi-lo)*g/4,y=py(v);x.beginPath();x.moveTo(PL,y);x.lineTo(W-PR,y);x.stroke();x.fillText('$'+f0(v),3,y-2);}}
 x.fillStyle='#6b7787';[a,Math.floor((a+b)/2),b].forEach(i=>x.fillText((D.dates[i]||'').slice(0,7),Math.min(W-40,Math.max(PL,px(i)-16)),H-4));
 x.strokeStyle=COL[scenario]||'#2bd576';x.lineWidth=1.8;x.beginPath();let st=false;for(let i=a;i<=b;i++){const v=eq[i];if(v<=0)continue;st?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v));st=true;}x.stroke();
 if(hover!=null&&hover>=a&&hover<=b){const X=px(hover),v=eq[hover];x.strokeStyle='#4da3ff';x.lineWidth=1;x.setLineDash([4,3]);x.beginPath();x.moveTo(X,PT);x.lineTo(X,H-PB);x.stroke();x.setLineDash([]);
  const lines=[(D.dates[hover]||'').slice(0,10),'$'+f0(v),'BTC $'+f0(D.btc_close[hover])];x.font='11px sans-serif';
  const tw=Math.max(...lines.map(s=>x.measureText(s).width))+12,tx=Math.min(W-tw-4,Math.max(4,X+8));
  x.fillStyle='#0e1622ee';x.strokeStyle='#2a3650';x.beginPath();x.rect(tx,PT+2,tw,46);x.fill();x.stroke();
  x.fillStyle='#cfe3ff';lines.forEach((s,k)=>x.fillText(s,tx+6,PT+16+k*14));}}
const cv=$('chart');let drag=null,lastDist=null;
function idxFromX(cx){const r=cv.getBoundingClientRect();const fx=(cx-r.left-48)/(r.width-56);return Math.round(view.a+(view.b-view.a)*Math.max(0,Math.min(1,fx)));}
cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,a:view.a,b:view.b};cv.setPointerCapture(e.pointerId);hover=idxFromX(e.clientX);draw();});
cv.addEventListener('pointermove',e=>{hover=idxFromX(e.clientX);if(drag&&!lastDist){const dpx=e.clientX-drag.x,span=drag.b-drag.a;let a=drag.a-dpx/cv.clientWidth*span,b=drag.b-dpx/cv.clientWidth*span;if(a<0){b-=a;a=0;}if(b>D.dates.length-1){a-=(b-(D.dates.length-1));b=D.dates.length-1;}view.a=Math.max(0,a);view.b=b;}draw();});
cv.addEventListener('pointerup',()=>drag=null);cv.addEventListener('pointercancel',()=>drag=null);cv.addEventListener('pointerleave',()=>{hover=null;draw();});
cv.addEventListener('wheel',e=>{e.preventDefault();const fi=idxFromX(e.clientX),f=e.deltaY>0?1.15:0.87;view.a=Math.max(0,fi-(fi-view.a)*f);view.b=Math.min(D.dates.length-1,fi+(view.b-fi)*f);draw();},{passive:false});
cv.addEventListener('touchmove',e=>{if(e.touches.length===2){e.preventDefault();const d=Math.abs(e.touches[0].clientX-e.touches[1].clientX);if(lastDist){const f=lastDist/d,c=(view.a+view.b)/2,w=(view.b-view.a)*f/2;view.a=Math.max(0,c-w);view.b=Math.min(D.dates.length-1,c+w);draw();}lastDist=d;}},{passive:false});
cv.addEventListener('touchend',()=>lastDist=null);
function switchTab(p){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.p===p));document.querySelectorAll('.pane').forEach(x=>x.classList.remove('on'));$('p-'+p).classList.add('on');if(p==='perf')setTimeout(draw,40);}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>switchTab(t.dataset.p));
updM();window.addEventListener('resize',()=>{if($('p-perf').classList.contains('on'))draw();});
</script></body></html>"""
out = HTML.replace("__DATA__", DATA)
open(os.path.join(OUT, "index_multi.html"), "w", encoding="utf-8").write(out)
print("wrote index_multi.html (", len(out), "bytes )")
