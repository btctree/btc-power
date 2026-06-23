"""Self-contained offline dashboard for the $500 real-trade product.
Embeds results_realtrade.json; vanilla canvas; opens from file:// by double-click."""
import os, json

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out")
with open(os.path.join(OUT, "results_realtrade.json")) as f:
    D = json.load(f)
DATA_JSON = json.dumps(D)

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BTC $500 Real-Trade Signal</title>
<style>
:root{--bg:#0b0e14;--card:#141925;--ink:#e6edf3;--mut:#8b98a9;--grn:#26d07c;--red:#ff5d5d;
--amb:#ffb84d;--blu:#4da3ff;--line:#222a38}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:20px}
h1{font-size:20px;margin:0 0 2px}.sub{color:var(--mut);font-size:12px;margin-bottom:16px}
.grid{display:grid;gap:14px}.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:1.3fr 1fr 1fr}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.k{color:var(--mut);font-size:12px}.v{font-weight:600}
.big{font-size:28px;font-weight:700;margin:4px 0}
.row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--line)}
.pos{color:var(--grn)}.neg{color:var(--red)}.mut{color:var(--mut)}.blu{color:var(--blu)}
table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}th{color:var(--mut)}
canvas{width:100%;height:280px;display:block}
.note{color:var(--mut);font-size:11px;margin-top:10px;line-height:1.5}
.barwrap{height:10px;background:#0e131d;border-radius:6px;overflow:hidden;margin-top:6px}
.bar{height:100%;background:linear-gradient(90deg,#26d07c,#4da3ff)}
.role{padding:8px;border-radius:8px;background:#0e131d;border:1px solid var(--line);margin-top:8px;font-size:12px}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:#10381f;color:var(--grn)}
.legend{font-size:11px;color:var(--mut);margin-top:6px}.legend b{color:var(--grn)}.legend i{color:var(--blu);font-style:normal}.legend s{color:var(--mut);text-decoration:none}
.pill{font-size:11px;color:var(--mut);border:1px solid var(--line);border-radius:20px;padding:2px 8px;margin-left:6px}
</style></head><body><div class="wrap">
<h1>BTC Real-Trade Signal <span class="pill">$500 start</span> <span class="pill">1-min execution</span></h1>
<div class="sub" id="asof"></div>

<div class="grid g3">
  <div class="card"><div class="k">LIVE SIGNAL · CORE (spot, vol-targeted)</div>
    <div class="big" id="action"></div>
    <div class="k" style="margin-top:6px">Confidence index</div>
    <div class="barwrap"><div class="bar" id="confbar"></div></div>
    <div class="v" id="conftxt" style="margin-top:4px"></div>
    <div class="row" style="margin-top:8px"><span class="k">Regime</span><span class="v" id="regime"></span></div>
    <div class="row"><span class="k">Leverage today</span><span class="v" id="lev"></span></div>
    <div class="row"><span class="k">Position size</span><span class="v" id="size"></span></div>
    <div class="row"><span class="k">Margin used</span><span class="v" id="margin"></span></div>
    <div class="row"><span class="k">Cash reserve</span><span class="v" id="cash"></span></div>
  </div>
  <div class="card"><div class="k">TRADE PLAN</div>
    <div class="row"><span class="k">Price</span><span class="v" id="price"></span></div>
    <div class="row"><span class="k">RSI(14)</span><span class="v" id="rsi"></span></div>
    <div class="row"><span class="k">Leave-market</span><span class="v" id="leave"></span></div>
    <div class="row"><span class="k">Take-profit</span><span class="v" id="tp" style="font-size:11px"></span></div>
    <div class="row"><span class="k">Cut-loss</span><span class="v" id="cut" style="font-size:11px"></span></div>
    <div class="k" style="margin-top:8px">Key levels</div>
    <div id="levels"></div>
  </div>
  <div class="card"><div class="k">GROWTH alt (trend-gated 1.5x)</div>
    <div class="big blu" id="gaction" style="font-size:20px"></div>
    <div class="row" style="margin-top:6px"><span class="k">Leverage today</span><span class="v" id="glev"></span></div>
    <div class="row"><span class="k">Position size</span><span class="v" id="gsize"></span></div>
    <div class="row"><span class="k">Cut-loss</span><span class="v" id="gcut" style="font-size:11px"></span></div>
    <div class="note">Use only with a growth mandate; deeper drawdowns. Leverage applies only in confirmed up-trends.</div>
  </div>
</div>

<div class="grid g2" style="margin-top:14px">
  <div class="card"><div class="k">EQUITY FROM $500 — log scale (1-min fills, fees, funding, no look-ahead)</div>
    <canvas id="chart"></canvas>
    <div class="legend"><b>■ CORE</b> &nbsp; <i>■ GROWTH</i> &nbsp; <s>■ Buy &amp; Hold</s></div>
  </div>
  <div class="card"><div class="k">PERFORMANCE — iteration 1 (rejected) vs final</div>
    <table id="perf"><thead><tr><th>Config</th><th>$500→</th><th>CAGR</th><th>Sharpe</th><th>maxDD</th><th>Calmar</th><th>H1/H2</th><th>Liq</th></tr></thead><tbody></tbody></table>
    <div class="note" id="it1note"></div>
  </div>
</div>

<div class="card" style="margin-top:14px"><div class="k">4-ROLE SIGN-OFF — loop converged when all APPROVE</div>
  <div id="roles"></div>
</div>
<div class="card" style="margin-top:14px"><div class="note" id="caveat"></div></div>
</div>
<script>
const D=__DATA__;
const f0=x=>x==null?'n/a':Number(x).toLocaleString(undefined,{maximumFractionDigits:0});
const fp=x=>x==null||isNaN(x)?'n/a':(x*100).toFixed(1)+'%';
const f2=x=>x==null||isNaN(x)?'n/a':Number(x).toFixed(2);
const c=D.core.live, g=D.growth.live;
document.getElementById('asof').textContent='As of '+D.as_of+' · BTCUSDT · start $'+f0(D.start_funds)+' · daily-close decisions, intraday 1-min management';
const a=document.getElementById('action');a.textContent=c.action;a.style.color=c.confidence<0.1?'var(--mut)':'var(--grn)';
document.getElementById('confbar').style.width=Math.max(2,c.confidence*100).toFixed(0)+'%';
document.getElementById('conftxt').textContent=(c.confidence*100).toFixed(0)+'%  ('+c.bucket+')';
document.getElementById('regime').textContent=c.regime;
document.getElementById('lev').textContent=c.leverage_today+'x';
document.getElementById('size').textContent=c.size_pct_equity+'%  = $'+f0(c.position_value);
document.getElementById('margin').textContent='$'+f0(c.margin_used);
document.getElementById('cash').textContent='$'+f0(c.cash_reserve);
document.getElementById('price').textContent='$'+f0(c.price);
document.getElementById('rsi').textContent=c.rsi;
document.getElementById('leave').textContent='consensus < '+c.leave_market_below_confidence;
document.getElementById('tp').textContent=c.take_profit;
document.getElementById('cut').textContent=c.cut_loss;
const L=c.levels;
document.getElementById('levels').innerHTML=
 [['SMA20','sma20'],['SMA50','sma50'],['BB upper','bb_upper'],['BB lower','bb_lower']]
 .map(([n,k])=>`<div class="row"><span class="k">${n}</span><span class="v">$${f0(L[k])}</span></div>`).join('');
document.getElementById('gaction').textContent=g.action;
document.getElementById('glev').textContent=g.leverage_today+'x';
document.getElementById('gsize').textContent=g.size_pct_equity+'% = $'+f0(g.position_value);
document.getElementById('gcut').textContent=g.cut_loss;
// perf table
const tb=document.querySelector('#perf tbody');
const rows=[['CORE',D.core.metrics,D.core.wf],['GROWTH',D.growth.metrics,D.growth.wf]];
rows.forEach(([nm,m,wf])=>{const tr=document.createElement('tr');
 tr.innerHTML=`<td>${nm}</td><td>$${f0(m.final)}</td><td>${fp(m.cagr)}</td><td class="pos">${f2(m.sharpe)}</td>
 <td class="neg">${fp(m.maxdd)}</td><td>${f2(m.calmar)}</td><td>${f2(wf[0])}/${f2(wf[1])}</td><td>${m.liquidations}</td>`;
 tb.appendChild(tr);});
const i1=D.iteration1;
document.getElementById('it1note').textContent=
 `❌ ${i1.label}: $500→$${f0(i1.final)} (${(i1.total*100).toFixed(0)}%), Sharpe ${f2(i1.sharpe)}, maxDD ${(i1.maxdd*100).toFixed(0)}%, funding $${f0(i1.funding)}, fees $${f0(i1.fees)} — leverage+tight-stop+funding destroyed the edge.`;
// roles
document.getElementById('roles').innerHTML=D.roles.map(r=>
 `<div class="role"><span class="badge">${r.verdict}</span> <b>${r.role}</b><br><span class="mut">${r.note}</span></div>`).join('');
document.getElementById('caveat').textContent=
 '⚠️ Hypothetical backtest on Binance BTCUSDT, 2017–2026. Daily-close signal (validated 9-strategy consensus), '+
 'managed intraday on real 1-minute bars; fees 5bp/side; perp funding modeled where used; spot configs pay no funding. '+
 'Findings: tight intraday stops and high leverage both reduce risk-adjusted return; spot/low-leverage is best. '+
 'Past performance is not indicative of future results. Not financial advice — validate before risking capital.';
// chart
function chart(){const cv=document.getElementById('chart');const dpr=window.devicePixelRatio||1;
 const W=cv.clientWidth,H=280;cv.width=W*dpr;cv.height=H*dpr;const x=cv.getContext('2d');x.scale(dpr,dpr);
 const core=D.core.eq,grow=D.growth.eq,cl=D.close;const n=core.length;
 const bh=cl.map(v=>D.start_funds*v/cl[0]);
 const all=core.concat(grow).concat(bh).filter(v=>v>0);
 const lo=Math.log10(Math.min(...all)),hi=Math.log10(Math.max(...all));
 const px=i=>46+(W-56)*i/(n-1);const py=v=>{const t=(Math.log10(Math.max(v,1e-6))-lo)/(hi-lo);return H-20-(H-34)*t;};
 x.strokeStyle='#1c2433';x.fillStyle='#6b7787';x.font='10px sans-serif';
 for(let p=Math.ceil(lo);p<=Math.floor(hi);p++){const y=py(Math.pow(10,p));x.beginPath();x.moveTo(46,y);x.lineTo(W-10,y);x.stroke();x.fillText('$'+f0(Math.pow(10,p)),4,y+3);}
 const draw=(arr,col,w)=>{x.strokeStyle=col;x.lineWidth=w;x.beginPath();arr.forEach((v,i)=>{i?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v));});x.stroke();};
 draw(bh,'#5a6678',1);draw(grow,'#4da3ff',1.4);draw(core,'#26d07c',1.8);
 x.fillStyle='#6b7787';[0,Math.floor(n/2),n-1].forEach(i=>{x.fillText(D.dates[i].slice(0,7),px(i)-16,H-4);});}
chart();window.addEventListener('resize',chart);
</script></body></html>"""

out = HTML.replace("__DATA__", DATA_JSON)
path = os.path.join(OUT, "dashboard_realtrade.html")
with open(path, "w", encoding="utf-8") as f:
    f.write(out)
# also refresh index.html to the new product
with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
    f.write(out)
print("wrote", path, f"({len(out)} bytes)")
