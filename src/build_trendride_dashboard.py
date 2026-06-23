"""Self-contained offline dashboard for the trend-ride system. Embeds
results_trendride.json; vanilla canvas; opens from file://."""
import os, json
HERE = os.path.dirname(__file__); OUT = os.path.join(HERE, "..", "out")
with open(os.path.join(OUT, "results_trendride.json")) as f:
    D = json.load(f)
DATA = json.dumps(D)

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BTC Trend-Ride System</title>
<style>
:root{--bg:#0b0e14;--card:#141925;--ink:#e6edf3;--mut:#8b98a9;--grn:#26d07c;--red:#ff5d5d;--amb:#ffb84d;--blu:#4da3ff;--line:#222a38}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:20px}h1{font-size:20px;margin:0 0 2px}.sub{color:var(--mut);font-size:12px;margin-bottom:14px}
.grid{display:grid;gap:14px}.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:1fr 1fr 1fr}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.k{color:var(--mut);font-size:12px}.v{font-weight:600}.big{font-size:24px;font-weight:700;margin:4px 0}
.row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--line)}
.pos{color:var(--grn)}.neg{color:var(--red)}.mut{color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}th{color:var(--mut)}
canvas{width:100%;height:250px;display:block}
.warn{background:#2a1416;border:1px solid #5a2730;border-radius:10px;padding:12px;margin-bottom:14px;color:#ffc2c2;font-size:13px}
.role{background:#0e131d;border:1px solid var(--line);border-radius:8px;padding:8px;margin-top:8px;font-size:12px}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:#10381f;color:var(--grn)}
.note{color:var(--mut);font-size:11px;margin-top:10px;line-height:1.5}.cred{color:var(--blu);font-size:12px}
.mirage td.bad{color:var(--red)}.legend{font-size:11px;color:var(--mut);margin-top:6px}
</style></head><body><div class="wrap">
<h1>BTC Trend-Ride System <span class="mut" style="font-size:13px">· $500 · 1-min fills · let-winners-run</span></h1>
<div class="sub" id="asof"></div>
<div class="cred" id="cred"></div>
<div class="warn" id="verdict" style="margin-top:10px"></div>

<div class="grid g3">
  <div class="card"><div class="k">LIVE SIGNAL</div>
    <div class="big" id="action"></div>
    <div class="row" style="margin-top:6px"><span class="k">Price</span><span class="v" id="price"></span></div>
    <div class="row"><span class="k">Market type</span><span class="v" id="regime"></span></div>
    <div class="row"><span class="k">Active strategy</span><span class="v" id="strat"></span></div>
    <div class="row"><span class="k">Trailing stop</span><span class="v" id="stop"></span></div>
    <div class="row"><span class="k">Take-profit</span><span class="v" id="tp" style="font-size:11px"></span></div>
  </div>
  <div class="card"><div class="k">CORE vs GROWTH (spot 1x, 0 liquidations)</div>
    <table><thead><tr><th></th><th>CORE</th><th>GROWTH-1x</th></tr></thead><tbody id="cmp"></tbody></table>
    <div class="note">CORE = confidence-scaled (lower DD). GROWTH = full deployment.</div>
  </div>
  <div class="card"><div class="k">EQUITY FROM $500 (log)</div><canvas id="chart"></canvas>
    <div class="legend"><span style="color:#26d07c">■ CORE</span> <span style="color:#ffb84d">■ GROWTH-1x</span></div>
  </div>
</div>

<div class="card" style="margin-top:14px"><div class="k">⚠️ LEVERAGE IS A SLIPPAGE MIRAGE — final $ (and maxDD) at increasing stop-fill cost</div>
  <table class="mirage" id="frag"><thead><tr><th>Leverage</th><th>perfect fill (0bp)</th><th>50bp slip</th><th>150bp slip</th></tr></thead><tbody></tbody></table>
  <div class="note">High leverage only reaches $1M–$11M assuming stops fill perfectly. With realistic gap/slippage it collapses to near-ruin (4× → $2k). Only 1× survives. The $80M target requires fills that don't exist in a crash.</div>
</div>

<div class="card" style="margin-top:14px"><div class="k">4-ROLE SIGN-OFF</div><div id="roles"></div></div>
<div class="card" style="margin-top:14px"><div class="note" id="caveat"></div></div>
</div>
<script>
const D=__DATA__;const f0=x=>x==null?'n/a':Number(x).toLocaleString(undefined,{maximumFractionDigits:0});
const fp=x=>x==null||isNaN(x)?'n/a':(x*100).toFixed(1)+'%';const f2=x=>x==null||isNaN(x)?'n/a':Number(x).toFixed(2);
document.getElementById('asof').textContent='As of '+D.as_of+' · BTCUSDT · daily regime → 1-min intraday fills · start $'+f0(D.start);
document.getElementById('cred').textContent='💡 Inspiration applied: '+D.inspiration;
document.getElementById('verdict').innerHTML='🎯 <b>$80M / 10y:</b> '+D.verdict_80M;
const L=D.live;const a=document.getElementById('action');a.textContent=L.action;
a.style.color=L.direction==='LONG'?'var(--grn)':(L.direction==='SHORT'?'var(--red)':'var(--mut)');
document.getElementById('price').textContent='$'+f0(L.price);
document.getElementById('regime').textContent=L.regime;
document.getElementById('strat').textContent=L.active_strategy;
document.getElementById('stop').textContent=L.trailing_stop?('$'+f0(L.trailing_stop)):'—';
document.getElementById('tp').textContent=L.take_profit;
const cm=D.core.metrics,gm=D.growth.metrics;
const rows=[['$500 →',`$${f0(cm.final)}`,`$${f0(gm.final)}`],['Multiple',`${f0(cm.mult)}x`,`${f0(gm.mult)}x`],
 ['CAGR',fp(cm.cagr),fp(gm.cagr)],['Sharpe',f2(cm.sharpe),f2(gm.sharpe)],['maxDD',fp(cm.maxdd),fp(gm.maxdd)],
 ['Calmar',f2(cm.calmar),f2(gm.calmar)],['WF H1/H2',`${f2(cm.wf[0])}/${f2(cm.wf[1])}`,`${f2(gm.wf[0])}/${f2(gm.wf[1])}`],
 ['10y proj',`$${f0(cm.proj10y)}`,`$${f0(gm.proj10y)}`],['Liq',cm.liquidations,gm.liquidations]];
document.getElementById('cmp').innerHTML=rows.map(r=>`<tr><td class="mut">${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td></tr>`).join('');
const fb=document.querySelector('#frag tbody');
Object.entries(D.fragility).forEach(([lev,row])=>{const tr=document.createElement('tr');
 const c=s=>`$${f0(row[s].final)} <span class="mut">(${(row[s].maxdd*100).toFixed(0)}%)</span>`;
 const bad=lev!=='1.0x'?'class="bad"':'';
 tr.innerHTML=`<td>${lev}</td><td>${c('0.0')}</td><td ${bad}>${c('0.005')}</td><td ${bad}>${c('0.015')}</td>`;fb.appendChild(tr);});
document.getElementById('roles').innerHTML=D.roles.map(r=>`<div class="role"><span class="badge">${r.verdict}</span> <b>${r.role}</b><br><span class="mut">${r.note}</span></div>`).join('');
document.getElementById('caveat').textContent='⚠️ Hypothetical backtest, Binance BTCUSDT 2017–2026, 1-min intraday stop fills, 5bp/side fees. CORE/GROWTH are SPOT (no funding, no leverage, no liquidation). Inspired by the M1-vs-M5 system. Convex profile: many small losses, few big winners — expect deep drawdowns. Past performance ≠ future results. Not financial advice.';
function chart(){const cv=document.getElementById('chart');const dpr=window.devicePixelRatio||1;const W=cv.clientWidth,H=250;
 cv.width=W*dpr;cv.height=H*dpr;const x=cv.getContext('2d');x.scale(dpr,dpr);
 const C=D.core.eq,G=D.growth.eq,n=C.length;const all=C.concat(G).filter(v=>v>0);
 const lo=Math.log10(Math.min(...all)),hi=Math.log10(Math.max(...all));
 const px=i=>48+(W-58)*i/(n-1);const py=v=>{const t=(Math.log10(Math.max(v,1e-6))-lo)/(hi-lo);return H-18-(H-32)*t;};
 x.strokeStyle='#1c2433';x.fillStyle='#6b7787';x.font='10px sans-serif';
 for(let p=Math.ceil(lo);p<=Math.floor(hi);p++){const y=py(Math.pow(10,p));x.beginPath();x.moveTo(48,y);x.lineTo(W-8,y);x.stroke();x.fillText('$'+f0(Math.pow(10,p)),4,y+3);}
 const dr=(arr,col,w)=>{x.strokeStyle=col;x.lineWidth=w;x.beginPath();arr.forEach((v,i)=>{i?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v));});x.stroke();};
 dr(G,'#ffb84d',1.4);dr(C,'#26d07c',1.7);
 x.fillStyle='#6b7787';[0,Math.floor(n/2),n-1].forEach(i=>x.fillText(D.dates[i].slice(0,7),px(i)-16,H-3));}
chart();window.addEventListener('resize',chart);
</script></body></html>"""
out = HTML.replace("__DATA__", DATA)
for fn in ["dashboard_trendride.html", "index.html"]:
    with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
        f.write(out)
print("wrote dashboard_trendride.html + index.html (", len(out), "bytes )")
