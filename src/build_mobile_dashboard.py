"""Build an iPhone-optimized, app-like PWA dashboard from results_production.json.
Outputs out/index.html (+ manifest). Installable via Safari 'Add to Home Screen' so it
opens full-screen like a native app. Self-contained (data embedded)."""
import os, json
HERE = os.path.dirname(__file__); OUT = os.path.join(HERE, "..", "out")
D = json.load(open(os.path.join(OUT, "results_production.json")))
DATA = json.dumps(D)

MANIFEST = {
    "name": "BTC Signal", "short_name": "BTC Signal", "display": "standalone",
    "background_color": "#0b0e14", "theme_color": "#0b0e14", "start_url": "./index.html",
    "icons": [{"src": "icon.png", "sizes": "512x512", "type": "image/png"}],
}
with open(os.path.join(OUT, "manifest.webmanifest"), "w") as f:
    json.dump(MANIFEST, f)

HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="BTC Signal">
<meta name="theme-color" content="#0b0e14">
<link rel="manifest" href="manifest.webmanifest">
<title>BTC Signal</title>
<style>
:root{--bg:#0b0e14;--card:#161b26;--ink:#e8edf4;--mut:#8b98a9;--grn:#2bd576;--red:#ff5d5d;--amb:#ffb84d;--blu:#4da3ff;--line:#242c3a;
--safe-t:env(safe-area-inset-top);--safe-b:env(safe-area-inset-bottom)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,SF Pro Text,Segoe UI,Roboto,sans-serif;
overscroll-behavior:none}
.app{max-width:460px;margin:0 auto;padding:calc(var(--safe-t) + 8px) 14px calc(72px + var(--safe-b))}
header{position:sticky;top:0;z-index:5;background:linear-gradient(#0b0e14ee,#0b0e14cc);backdrop-filter:blur(10px);
padding:8px 2px 10px;margin:0 -2px 6px}
.brand{font-size:13px;color:var(--mut);letter-spacing:.5px}
.px{font-size:30px;font-weight:800;letter-spacing:-.5px}
.px small{font-size:13px;font-weight:600;color:var(--mut);margin-left:8px}
.sigchip{display:inline-block;margin-top:4px;padding:5px 12px;border-radius:30px;font-weight:700;font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:15px;margin-bottom:12px}
.h{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px}
.big{font-size:22px;font-weight:700}
.row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid var(--line)}
.row:last-child{border:0}.k{color:var(--mut);font-size:13px}.v{font-weight:600}
.pos{color:var(--grn)}.neg{color:var(--red)}.amb{color:var(--amb)}.blu{color:var(--blu)}.mut{color:var(--mut)}
canvas{width:100%;height:200px;display:block}
.note{color:var(--mut);font-size:12px;line-height:1.55;margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:12.5px}td,th{padding:7px 4px;text-align:right;border-bottom:1px solid var(--line)}
td:first-child,th:first-child{text-align:left}th{color:var(--mut);font-weight:600}
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:6;display:flex;justify-content:space-around;
background:#10141ccc;backdrop-filter:blur(14px);border-top:1px solid var(--line);padding:8px 4px calc(8px + var(--safe-b))}
.tab{flex:1;text-align:center;color:var(--mut);font-size:11px;font-weight:600;padding:4px;border-radius:10px}
.tab.on{color:var(--blu)}.tab .ic{display:block;font-size:18px;margin-bottom:2px}
.pane{display:none}.pane.on{display:block;animation:f .25s}
@keyframes f{from{opacity:.4;transform:translateY(4px)}to{opacity:1;transform:none}}
.warn{background:#2a1416;border:1px solid #5a2730;border-radius:12px;padding:11px;color:#ffc2c2;font-size:12.5px;line-height:1.5}
.gentag{font-size:11px;color:var(--mut);text-align:center;margin-top:6px}
.lvl{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.lvl div{background:#0e131d;border:1px solid var(--line);border-radius:10px;padding:8px}
.lvl .k{font-size:11px}.lvl .v{font-size:15px}
</style></head><body><div class="app">
<header>
  <div class="brand">BTC • <span id="asof"></span></div>
  <div class="px">$<span id="px"></span><small id="rsi"></small></div>
  <div class="sigchip" id="chip"></div>
</header>

<!-- SIGNAL -->
<div class="pane on" id="p-signal">
  <div class="card"><div class="h">Today's signal</div>
    <div class="big" id="action"></div>
    <div class="row"><span class="k">Market type</span><span class="v" id="regime"></span></div>
    <div class="row"><span class="k">Strategy</span><span class="v" id="strat"></span></div>
    <div class="row"><span class="k">Confidence</span><span class="v" id="conf"></span></div>
    <div class="row"><span class="k">Size (of equity)</span><span class="v" id="size"></span></div>
    <div class="row"><span class="k">Margin</span><span class="v" id="margin"></span></div>
    <div class="row"><span class="k">Trailing stop</span><span class="v" id="stop"></span></div>
    <div class="row"><span class="k">Take-profit</span><span class="v" id="tp" style="font-size:12px;max-width:60%;text-align:right"></span></div>
  </div>
  <div class="card"><div class="h">Key levels</div><div class="lvl" id="levels"></div></div>
</div>

<!-- FORECAST -->
<div class="pane" id="p-forecast">
  <div class="card"><div class="h">Market forecast</div>
    <div class="big" id="bias"></div>
    <div class="note" id="fnote" style="font-size:14px;color:var(--ink)"></div>
    <div class="row" style="margin-top:8px"><span class="k">Arms LONG above</span><span class="v pos" id="armL"></span></div>
    <div class="row"><span class="k">Arms SHORT below</span><span class="v neg" id="armS"></span></div>
  </div>
  <div class="card"><div class="h">Regime → strategy playbook</div><div id="rmap"></div></div>
</div>

<!-- PERFORMANCE -->
<div class="pane" id="p-perf">
  <div class="card"><div class="h">Equity from $500 — log (2017→, ~30bp slippage)</div>
    <canvas id="chart"></canvas>
    <div class="note"><span class="pos">■ CORE 1×</span> &nbsp; <span class="amb">■ GROWTH 1×</span> &nbsp; <span class="blu">■ Modest 2×</span></div>
  </div>
  <div class="card"><div class="h">Production results (real fills, 0 liquidations)</div>
    <table id="prod"></table>
    <div class="note">CORE = safest (conf-scaled). GROWTH = full deploy. These are the numbers to actually trade on.</div>
  </div>
</div>

<!-- TRUTH -->
<div class="pane" id="p-truth">
  <div class="card"><div class="h">Optimistic vs realistic — the $80M question</div>
    <table id="cmp"></table>
    <div class="warn" id="truthnote" style="margin-top:10px"></div>
  </div>
</div>

</div>
<nav class="tabbar">
  <div class="tab on" data-p="signal"><span class="ic">📡</span>Signal</div>
  <div class="tab" data-p="forecast"><span class="ic">🔮</span>Forecast</div>
  <div class="tab" data-p="perf"><span class="ic">📈</span>Returns</div>
  <div class="tab" data-p="truth"><span class="ic">⚖️</span>Truth</div>
</nav>
<script>
const D=__DATA__;
const f0=x=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:0});
const fp=x=>x==null||isNaN(x)?'—':(x*100).toFixed(0)+'%';const f2=x=>x==null||isNaN(x)?'—':Number(x).toFixed(2);
const $=id=>document.getElementById(id);
$('asof').textContent=D.as_of; $('px').textContent=f0(D.price); $('rsi').textContent='RSI '+D.live.rsi;
const L=D.live; const dir=L.direction;
const chip=$('chip'); chip.textContent=L.action;
const col=dir==='LONG'?'var(--grn)':(dir==='SHORT'?'var(--red)':'var(--mut)');
chip.style.background=col+'22'; chip.style.color=col;
$('action').textContent=L.action; $('action').style.color=col;
$('regime').textContent=L.regime; $('strat').textContent=L.active_strategy;
$('conf').textContent=L.confidence+' ('+L.confidence_score+')';
$('size').textContent=L.size_pct_equity+'%'; $('margin').textContent=L.margin_note;
$('stop').textContent=L.trailing_stop?('$'+f0(L.trailing_stop)):'—'; $('tp').textContent=L.take_profit;
const lv=D.levels;
$('levels').innerHTML=[['Price','price'],['SMA20','sma20'],['SMA50','sma50'],['SMA200','sma200'],
['BB upper','bb_upper'],['BB lower','bb_lower'],['20d high','swing_high_20d'],['20d low','swing_low_20d']]
.map(([n,k])=>`<div><div class="k">${n}</div><div class="v">$${f0(lv[k])}</div></div>`).join('');
const F=D.forecast;
$('bias').textContent=F.bias; $('bias').style.color=F.bias==='BULLISH'?'var(--grn)':(F.bias==='BEARISH'?'var(--red)':'var(--amb)');
$('fnote').textContent=F.note; $('armL').textContent='$'+f0(F.arms_long_above); $('armS').textContent='$'+f0(F.arms_short_below);
$('rmap').innerHTML=Object.entries(D.regime_map).map(([k,v])=>{
 const c=v==='STAND ASIDE'?'var(--mut)':'var(--grn)';
 return `<div class="row"><span class="k">${k}</span><span class="v" style="color:${c}">${v}</span></div>`}).join('');
const P=D.production;
$('prod').innerHTML='<tr><th>Config</th><th>$500→</th><th>CAGR</th><th>Sharpe</th><th>maxDD</th></tr>'+
Object.entries(P).map(([k,p])=>`<tr><td>${k.replace(/_/g,' ')}</td><td>$${f0(p.final)}</td><td>${fp(p.cagr)}</td><td>${f2(p.sharpe)}</td><td class="neg">${fp(p.maxdd)}</td></tr>`).join('');
const C=D.comparison;
$('cmp').innerHTML='<tr><th>Scenario (5×/2× lev, from 2014)</th><th>Result</th></tr>'+
`<tr><td>M1vM5 unleveraged</td><td>$${f0(C.m1m5.unlev)}</td></tr>`+
`<tr><td>M1vM5 leveraged <span class="amb">(optimistic)</span></td><td class="amb">$${f0(C.m1m5.lev_optimistic)}</td></tr>`+
`<tr><td>Ours leveraged — perfect fills</td><td class="amb">$${f0(C.ours.lev_2014.perfect.final)}</td></tr>`+
`<tr><td>Ours leveraged — 50bp slippage</td><td>$${f0(C.ours.lev_2014.slip_50bp.final)}</td></tr>`+
`<tr><td>Ours leveraged — <span class="red">150bp (real crash)</span></td><td class="red">$${f0(C.ours.lev_2014.slip_150bp.final)}</td></tr>`+
`<tr><td>Ours <b>unleveraged</b> (tradeable)</td><td class="pos">$${f0(C.ours.unlev_2014)}</td></tr>`;
$('truthnote').innerHTML='The $71–80M figure assumes a leveraged stop fills <b>perfectly even in a crash</b> — M1vM5’s own notes call it “optimistic”. With realistic crash fills it collapses to ~$35k (−95% drawdown). The honest, tradeable number is the <b>unleveraged</b> curve.';
// tabs
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
 document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
 document.querySelectorAll('.pane').forEach(x=>x.classList.remove('on'));
 t.classList.add('on'); $('p-'+t.dataset.p).classList.add('on');
 if(t.dataset.p==='perf') setTimeout(chart,30);
});
function chart(){const cv=$('chart');if(!cv.clientWidth)return;const dpr=window.devicePixelRatio||1;const W=cv.clientWidth,H=200;
 cv.width=W*dpr;cv.height=H*dpr;const x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,W,H);
 const series=[['CORE_1x_2017','#2bd576'],['GROWTH_1x_2017','#ffb84d'],['MODEST_2x_2017','#4da3ff']]
   .map(([k,c])=>[D.production[k]&&D.production[k].eq,c]).filter(s=>s[0]);
 const all=[].concat(...series.map(s=>s[0])).filter(v=>v>0);if(!all.length)return;
 const lo=Math.log10(Math.min(...all)),hi=Math.log10(Math.max(...all));const n=series[0][0].length;
 const px=i=>40+(W-48)*i/(n-1),py=v=>{const t=(Math.log10(Math.max(v,1e-6))-lo)/(hi-lo);return H-16-(H-26)*t;};
 x.strokeStyle='#222a38';x.fillStyle='#6b7787';x.font='9px sans-serif';
 for(let p=Math.ceil(lo);p<=Math.floor(hi);p++){const y=py(Math.pow(10,p));x.beginPath();x.moveTo(40,y);x.lineTo(W-6,y);x.stroke();x.fillText('$'+f0(Math.pow(10,p)),3,y-2);}
 series.forEach(([arr,c])=>{x.strokeStyle=c;x.lineWidth=1.6;x.beginPath();arr.forEach((v,i)=>i?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v)));x.stroke();});}
</script></body></html>"""
out = HTML.replace("__DATA__", DATA)
for fn in ["index.html", "dashboard_mobile.html"]:
    with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
        f.write(out)
print("wrote index.html + dashboard_mobile.html + manifest.webmanifest (", len(out), "bytes )")
