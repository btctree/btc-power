"""Interactive iPhone PWA dashboard v2 from results_live.json.
Tabs: Signal | Forecast | Performance (interactive pan/zoom/scale + scenario selector) | Trades.
Recent-20 trades -> tap -> No-leverage/Leverage popup -> jumps to chart, centers the trade.
Self-contained, data embedded.
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
<link rel="manifest" href="manifest.webmanifest"><title>BTC Power Signal</title>
<style>
:root{--bg:#0b0e14;--card:#161b26;--ink:#e8edf4;--mut:#8b98a9;--grn:#2bd576;--red:#ff5d5d;--amb:#ffb84d;--blu:#4da3ff;--line:#242c3a;--safe-t:env(safe-area-inset-top);--safe-b:env(safe-area-inset-bottom)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,SF Pro Text,Segoe UI,Roboto,sans-serif;overscroll-behavior:none}
.app{max-width:480px;margin:0 auto;padding:calc(var(--safe-t) + 8px) 14px calc(74px + var(--safe-b))}
header{position:sticky;top:0;z-index:5;background:linear-gradient(#0b0e14ee,#0b0e14cc);backdrop-filter:blur(10px);padding:8px 2px 10px;margin:0 -2px 6px}
.brand{font-size:13px;color:var(--mut)}.px{font-size:30px;font-weight:800}.px small{font-size:13px;color:var(--mut);margin-left:8px}
.chip{display:inline-block;margin-top:4px;padding:5px 12px;border-radius:30px;font-weight:700;font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:15px;margin-bottom:12px}
.h{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px}
.big{font-size:22px;font-weight:700}.row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--line)}
.row:last-child{border:0}.k{color:var(--mut);font-size:13px}.v{font-weight:600}.pos{color:var(--grn)}.neg{color:var(--red)}.amb{color:var(--amb)}.mut{color:var(--mut)}
.note{color:var(--mut);font-size:11.5px;line-height:1.55;margin-top:8px}
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:6;display:flex;justify-content:space-around;background:#10141ccc;backdrop-filter:blur(14px);border-top:1px solid var(--line);padding:8px 4px calc(8px + var(--safe-b))}
.tab{flex:1;text-align:center;color:var(--mut);font-size:11px;font-weight:600;padding:4px;border-radius:10px}.tab.on{color:var(--blu)}.tab .ic{display:block;font-size:18px}
.pane{display:none}.pane.on{display:block}
.lvl{display:grid;grid-template-columns:1fr 1fr;gap:6px}.lvl div{background:#0e131d;border:1px solid var(--line);border-radius:10px;padding:8px}.lvl .k{font-size:11px}
.scbtns{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.scb{font-size:11px;font-weight:700;padding:6px 9px;border-radius:8px;background:#0e131d;border:1px solid var(--line);color:var(--mut)}
.scb.on{background:#13324a;color:var(--blu);border-color:var(--blu)}
canvas{width:100%;height:300px;display:block;border-radius:10px;touch-action:none;background:#0c1018}
.ctrls{display:flex;gap:6px;margin-top:8px}.ctrls button{flex:1;font-size:12px;font-weight:600;padding:7px;border-radius:8px;background:#0e131d;border:1px solid var(--line);color:var(--ink)}
.warn{background:#2a1416;border:1px solid #5a2730;border-radius:10px;padding:9px;color:#ffc2c2;font-size:11.5px;margin-top:8px}
.trade{background:#0e131d;border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:7px}
.trade .t1{display:flex;justify-content:space-between;font-weight:700;font-size:13px}.trade .t2{font-size:11px;color:var(--mut);margin-top:3px;display:flex;justify-content:space-between}
.ov{position:fixed;inset:0;background:#000a;z-index:20;display:none;align-items:center;justify-content:center}
.ov.on{display:flex}.ovc{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;width:84%;max-width:340px}
.ovc h3{margin:0 0 4px;font-size:15px}.ovc .sub{color:var(--mut);font-size:12px;margin-bottom:12px}
.ovbtn{display:block;width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);font-weight:700;margin-bottom:8px;font-size:14px}
.ovbtn.nl{background:#10381f;color:var(--grn)}.ovbtn.l{background:#3a2410;color:var(--amb)}.ovbtn.x{background:#0e131d;color:var(--mut)}
</style></head><body><div class="app">
<header><div class="brand">⚡ BTC POWER • <span id="asof"></span></div>
<div class="px">$<span id="px"></span><small id="rsi"></small></div><div class="chip" id="chip"></div></header>

<div class="pane on" id="p-signal">
  <div class="card"><div class="h">Today's signal</div><div class="big" id="action"></div>
    <div class="row"><span class="k">Market type</span><span class="v" id="mkt"></span></div>
    <div class="row"><span class="k">Engine</span><span class="v" id="eng"></span></div>
    <div class="row"><span class="k">Confidence</span><span class="v" id="conf"></span></div>
    <div class="row"><span class="k">Size</span><span class="v" id="size"></span></div>
    <div class="row"><span class="k">Margin</span><span class="v" id="margin"></span></div>
    <div class="row"><span class="k">Cut-loss (pre-set this)</span><span class="v amb" id="cut"></span></div>
    <div class="row"><span class="k">Take-profit</span><span class="v" id="tp" style="font-size:11px"></span></div>
  </div>
  <div class="card" id="ntcard"><div class="h">No open position — next action</div>
    <div class="row"><span class="k">Market type</span><span class="v" id="nt_mkt"></span></div>
    <div class="row"><span class="k">Engine on watch</span><span class="v" id="nt_eng"></span></div>
    <div class="row"><span class="k">Bias</span><span class="v" id="nt_bias"></span></div>
    <div class="note" id="nt_next"></div>
  </div>
  <div class="card"><div class="h">Key levels</div><div class="lvl" id="levels"></div></div>
</div>

<div class="pane" id="p-forecast">
  <div class="card"><div class="h">Regime → engine playbook</div><div id="rmap"></div></div>
</div>

<div class="pane" id="p-perf">
  <div class="card"><div class="h">Equity from $500 — pick scenario, pinch/drag to zoom & pan</div>
    <div class="scbtns" id="scbtns"></div>
    <canvas id="chart"></canvas>
    <div class="ctrls"><button onclick="zoomBtn(0.7)">＋ Zoom</button><button onclick="zoomBtn(1.4)">－ Zoom</button>
      <button onclick="toggleScale()" id="scaleBtn">Log</button><button onclick="resetView()">Reset</button></div>
    <div class="row" style="margin-top:8px"><span class="k">Final $500→</span><span class="v" id="m_final"></span></div>
    <div class="row"><span class="k">CAGR / maxDD</span><span class="v" id="m_cd"></span></div>
    <div class="warn" id="levwarn"></div>
  </div>
</div>

<div class="pane" id="p-trades">
  <div class="card"><div class="h">Recent 20 completed trades — tap for no-lev / leverage</div><div id="tradelist"></div></div>
</div>
</div>

<nav class="tabbar">
  <div class="tab on" data-p="signal"><span class="ic">📡</span>Signal</div>
  <div class="tab" data-p="forecast"><span class="ic">🔮</span>Forecast</div>
  <div class="tab" data-p="perf"><span class="ic">📈</span>Returns</div>
  <div class="tab" data-p="trades"><span class="ic">🧾</span>Trades</div>
</nav>

<div class="ov" id="ov"><div class="ovc"><h3 id="ov_t"></h3><div class="sub" id="ov_s"></div>
  <button class="ovbtn nl" id="ov_nl"></button><button class="ovbtn l" id="ov_l"></button>
  <button class="ovbtn x" onclick="closeOv()">Cancel</button></div></div>

<script>
const D=__DATA__;
const f0=x=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:0});
const fp=x=>x==null||isNaN(x)?'—':(x*100).toFixed(1)+'%';const f2=x=>x==null||isNaN(x)?'—':Number(x).toFixed(2);
const $=id=>document.getElementById(id);
$('asof').textContent=D.as_of;$('px').textContent=f0(D.price);$('rsi').textContent='RSI '+D.rsi;
const L=D.live;const col=L.direction==='LONG'?'var(--grn)':(L.direction==='SHORT'?'var(--red)':'var(--mut)');
const chip=$('chip');chip.textContent=L.action;chip.style.background=col+'22';chip.style.color=col;
$('action').textContent=L.action;$('action').style.color=col;$('mkt').textContent=L.regime;$('eng').textContent=L.engine;
$('conf').textContent=L.confidence+' ('+L.confidence_score+')';$('size').textContent=L.size_pct+'%';$('margin').textContent=L.margin;
$('cut').textContent=L.cutloss?('$'+f0(L.cutloss)):'—';$('tp').textContent=L.take_profit;
$('ntcard').style.display=D.in_position?'none':'block';
const NT=D.no_trade_status;$('nt_mkt').textContent=NT.market;$('nt_eng').textContent=NT.engine_on_watch;
$('nt_bias').textContent=NT.bias;$('nt_next').textContent=NT.next_action;
const lv=D.levels;$('levels').innerHTML=[['Price','price'],['SMA20','sma20'],['SMA50','sma50'],['SMA200','sma200'],['BB upper','bb_upper'],['BB lower','bb_lower']].map(([n,k])=>`<div><div class="k">${n}</div><div class="v">$${f0(lv[k])}</div></div>`).join('');
$('rmap').innerHTML=Object.entries(D.regime_map).map(([k,v])=>{const c=v==='STAND ASIDE'?'var(--mut)':'var(--grn)';return `<div class="row"><span class="k">${k}</span><span class="v" style="color:${c}">${v}</span></div>`}).join('');

// ---- Performance interactive chart ----
const SC=Object.keys(D.scenarios);let scenario='Spot 1x';let logScale=true;
let view={a:0,b:D.dates.length-1};let marker=null;
$('scbtns').innerHTML=SC.map(s=>`<div class="scb${s===scenario?' on':''}" data-sc="${s}">${s}</div>`).join('');
document.querySelectorAll('.scb').forEach(b=>b.onclick=()=>{scenario=b.dataset.sc;document.querySelectorAll('.scb').forEach(x=>x.classList.toggle('on',x.dataset.sc===scenario));updMetrics();draw();});
function updMetrics(){const m=D.scenarios[scenario].metrics;$('m_final').textContent='$'+f0(m.final);
 $('m_cd').textContent=fp(m.cagr)+' / '+fp(m.maxdd);
 $('levwarn').style.display=scenario==='Spot 1x'?'none':'block';
 $('levwarn').innerHTML='⚠️ '+scenario+' uses 5×/2× leverage — OPTIMISTIC: assumes the stop fills perfectly. Real fills collapse it (see how Lev 150bp differs). maxDD '+fp(m.maxdd)+'.';}
function zoomBtn(f){const c=(view.a+view.b)/2,w=(view.b-view.a)*f/2;view.a=Math.max(0,c-w);view.b=Math.min(D.dates.length-1,c+w);draw();}
function toggleScale(){logScale=!logScale;$('scaleBtn').textContent=logScale?'Log':'Linear';draw();}
function resetView(){view={a:0,b:D.dates.length-1};marker=null;draw();}
function draw(){const cv=$('chart');if(!cv.clientWidth)return;const dpr=window.devicePixelRatio||1;const W=cv.clientWidth,H=300;
 cv.width=W*dpr;cv.height=H*dpr;const x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,W,H);
 const eq=D.scenarios[scenario].eq;const a=Math.max(0,Math.floor(view.a)),b=Math.min(eq.length-1,Math.ceil(view.b));
 let lo=Infinity,hi=-Infinity;for(let i=a;i<=b;i++){const v=eq[i];if(v>0){if(v<lo)lo=v;if(v>hi)hi=v;}}
 if(!isFinite(lo)){lo=1;hi=10;}
 const PADL=46,PADR=8,PADT=10,PADB=18;
 const px=i=>PADL+(W-PADL-PADR)*(i-a)/Math.max(1,(b-a));
 const ya=logScale?Math.log10(Math.max(lo,1e-6)):lo, yb=logScale?Math.log10(hi):hi;
 const py=v=>{const t=((logScale?Math.log10(Math.max(v,1e-6)):v)-ya)/Math.max(1e-9,(yb-ya));return H-PADB-(H-PADT-PADB)*t;};
 // gridlines
 x.strokeStyle='#1c2433';x.fillStyle='#6b7787';x.font='9px sans-serif';x.lineWidth=1;
 if(logScale){for(let p=Math.ceil(ya);p<=Math.floor(yb);p++){const y=py(Math.pow(10,p));x.beginPath();x.moveTo(PADL,y);x.lineTo(W-PADR,y);x.stroke();x.fillText('$'+f0(Math.pow(10,p)),3,y-2);}}
 else{for(let g=0;g<=4;g++){const v=lo+(hi-lo)*g/4,y=py(v);x.beginPath();x.moveTo(PADL,y);x.lineTo(W-PADR,y);x.stroke();x.fillText('$'+f0(v),3,y-2);}}
 // date labels
 x.fillStyle='#6b7787';[a,Math.floor((a+b)/2),b].forEach(i=>{const t=D.dates[i]||'';x.fillText(t.slice(0,7),Math.min(W-40,Math.max(PADL,px(i)-16)),H-4);});
 // curve
 const colr=scenario==='Spot 1x'?'#2bd576':'#ffb84d';x.strokeStyle=colr;x.lineWidth=1.8;x.beginPath();
 let started=false;for(let i=a;i<=b;i++){const v=eq[i];if(v<=0)continue;const X=px(i),Y=py(v);started?x.lineTo(X,Y):x.moveTo(X,Y);started=true;}
 x.stroke();
 // marker
 if(marker!=null&&marker>=a&&marker<=b){const X=px(marker);x.strokeStyle='#4da3ff';x.lineWidth=1;x.setLineDash([4,3]);x.beginPath();x.moveTo(X,PADT);x.lineTo(X,H-PADB);x.stroke();x.setLineDash([]);
  x.fillStyle='#4da3ff';const v=eq[marker];if(v>0){x.beginPath();x.arc(X,py(v),4,0,7);x.fill();}
  x.fillStyle='#cfe3ff';x.font='10px sans-serif';const lbl=(D.dates[marker]||'').slice(0,10);x.fillText(lbl,Math.min(W-70,X+5),PADT+12);}
}
// gestures
let drag=null,pinch=null;const cv=$('chart');
cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,a:view.a,b:view.b};cv.setPointerCapture(e.pointerId);});
cv.addEventListener('pointermove',e=>{if(!drag||pinch)return;const dpx=e.clientX-drag.x;const span=drag.b-drag.a;const shift=-dpx/cv.clientWidth*span;
 let a=drag.a+shift,b=drag.b+shift;if(a<0){b-=a;a=0;}if(b>D.dates.length-1){a-=(b-(D.dates.length-1));b=D.dates.length-1;}view.a=Math.max(0,a);view.b=b;draw();});
cv.addEventListener('pointerup',()=>drag=null);cv.addEventListener('pointercancel',()=>drag=null);
cv.addEventListener('wheel',e=>{e.preventDefault();const r=cv.getBoundingClientRect();const fx=(e.clientX-r.left-46)/(r.width-54);const fi=view.a+(view.b-view.a)*Math.max(0,Math.min(1,fx));const f=e.deltaY>0?1.15:0.87;let a=fi-(fi-view.a)*f,b=fi+(view.b-fi)*f;view.a=Math.max(0,a);view.b=Math.min(D.dates.length-1,b);draw();},{passive:false});
let lastDist=null;
cv.addEventListener('touchmove',e=>{if(e.touches.length===2){e.preventDefault();const d=Math.abs(e.touches[0].clientX-e.touches[1].clientX);if(lastDist){const f=lastDist/d;const c=(view.a+view.b)/2,w=(view.b-view.a)*f/2;view.a=Math.max(0,c-w);view.b=Math.min(D.dates.length-1,c+w);draw();}lastDist=d;pinch=true;}},{passive:false});
cv.addEventListener('touchend',()=>{lastDist=null;pinch=null;});
// trades
function tradeRow(t,i){const c=t.direction==='LONG'?'var(--grn)':'var(--red)';const rc=t.ret>=0?'pos':'neg';
 return `<div class="trade" data-i="${i}"><div class="t1"><span style="color:${c}">${t.direction} · ${t.strategy}</span><span class="${rc}">${(t.ret*100).toFixed(1)}%</span></div>
 <div class="t2"><span>${t.entry_dt} → ${t.exit_dt}</span><span>${t.market}</span></div>
 <div class="t2"><span>in $${f0(t.entry)} · out $${f0(t.exit)} · cut $${f0(t.cutloss)}</span><span>${t.reason}</span></div></div>`;}
$('tradelist').innerHTML=D.recent_trades.map(tradeRow).join('');
document.querySelectorAll('.trade').forEach(el=>el.onclick=()=>openOv(D.recent_trades[+el.dataset.i]));
let curT=null;
function openOv(t){curT=t;$('ov_t').textContent=t.direction+' '+t.strategy+'  '+(t.ret*100).toFixed(1)+'%';
 $('ov_s').textContent=t.entry_dt+' → '+t.exit_dt+' · '+t.market;
 $('ov_nl').textContent='No-leverage P&L:  $'+f0(t.pnl_nolev);
 $('ov_l').textContent='Leverage P&L:  $'+f0(t.pnl_lev)+'  →  view on chart';
 $('ov').classList.add('on');}
function closeOv(){$('ov').classList.remove('on');}
$('ov_nl').onclick=()=>{closeOv();jumpToTrade(curT,'Spot 1x');};
$('ov_l').onclick=()=>{closeOv();jumpToTrade(curT,'Lev perfect');};
function jumpToTrade(t,sc){scenario=sc;document.querySelectorAll('.scb').forEach(x=>x.classList.toggle('on',x.dataset.sc===scenario));updMetrics();
 const idx=D.dates.indexOf(t.exit_date);marker=idx>=0?idx:null;
 if(idx>=0){const half=Math.max(60,Math.round(D.dates.length*0.06));view.a=Math.max(0,idx-half);view.b=Math.min(D.dates.length-1,idx+half);}
 switchTab('perf');setTimeout(draw,40);}
// tabs
function switchTab(p){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x.dataset.p===p));
 document.querySelectorAll('.pane').forEach(x=>x.classList.remove('on'));$('p-'+p).classList.add('on');if(p==='perf')setTimeout(draw,40);}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>switchTab(t.dataset.p));
updMetrics();window.addEventListener('resize',()=>{if($('p-perf').classList.contains('on'))draw();});
</script></body></html>"""
out = HTML.replace("__DATA__", DATA)
for fn in ["index.html", "dashboard_live.html"]:
    open(os.path.join(OUT, fn), "w", encoding="utf-8").write(out)
print("wrote index.html + dashboard_live.html (", len(out), "bytes )")
