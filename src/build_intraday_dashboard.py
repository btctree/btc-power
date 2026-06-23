"""Self-contained offline dashboard for the intraday regime-switching system.
Embeds results_intraday.json; vanilla canvas; opens from file://."""
import os, json

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out")
with open(os.path.join(OUT, "results_intraday.json")) as f:
    D = json.load(f)
DATA = json.dumps(D)

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BTC Intraday Regime System</title>
<style>
:root{--bg:#0b0e14;--card:#141925;--ink:#e6edf3;--mut:#8b98a9;--grn:#26d07c;--red:#ff5d5d;--amb:#ffb84d;--blu:#4da3ff;--line:#222a38}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:20px}
h1{font-size:20px;margin:0 0 2px}.sub{color:var(--mut);font-size:12px;margin-bottom:14px}
.grid{display:grid;gap:14px}.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:1fr 1fr 1fr}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.k{color:var(--mut);font-size:12px}.v{font-weight:600}.big{font-size:24px;font-weight:700;margin:4px 0}
.row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--line)}
.pos{color:var(--grn)}.neg{color:var(--red)}.mut{color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}th{color:var(--mut)}
canvas{width:100%;height:260px;display:block}
.warn{background:#2a1416;border:1px solid #5a2730;border-radius:10px;padding:12px;margin-bottom:14px;color:#ffc2c2;font-size:13px}
.map{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px}
.map div{background:#0e131d;border:1px solid var(--line);border-radius:6px;padding:6px}
.role{background:#0e131d;border:1px solid var(--line);border-radius:8px;padding:8px;margin-top:8px;font-size:12px}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:#10381f;color:var(--grn)}
.note{color:var(--mut);font-size:11px;margin-top:10px;line-height:1.5}
.legend{font-size:11px;color:var(--mut);margin-top:6px}
</style></head><body><div class="wrap">
<h1>BTC Intraday Regime-Switching System <span class="mut" style="font-size:13px">· $500 · 1-min fills</span></h1>
<div class="sub" id="asof"></div>
<div class="warn" id="verdict"></div>

<div class="grid g3">
  <div class="card"><div class="k">LIVE SIGNAL</div>
    <div class="big" id="action"></div>
    <div class="row" style="margin-top:6px"><span class="k">Price</span><span class="v" id="price"></span></div>
    <div class="row"><span class="k">Market type</span><span class="v" id="regime"></span></div>
    <div class="row"><span class="k">Active strategy</span><span class="v" id="strat"></span></div>
    <div class="row"><span class="k">Confidence</span><span class="v" id="conf"></span></div>
    <div class="row"><span class="k">Take-profit</span><span class="v" id="tp" style="font-size:11px"></span></div>
    <div class="row"><span class="k">Cut-loss</span><span class="v" id="cut" style="font-size:11px"></span></div>
  </div>
  <div class="card"><div class="k">MARKET TYPE → STRATEGY</div><div class="map" id="map" style="margin-top:6px"></div></div>
  <div class="card"><div class="k">EQUITY FROM $500 (log)</div><canvas id="chart"></canvas>
    <div class="legend"><span style="color:#26d07c">■ Conservative</span> <span style="color:#ffb84d">■ Balanced</span> <span style="color:#ff5d5d">■ Aggressive</span></div>
  </div>
</div>

<div class="card" style="margin-top:14px"><div class="k">RISK TIERS — all 0 liquidations, walk-forward robust</div>
  <table id="tiers"><thead><tr><th>Tier</th><th>$500→</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>maxDD</th><th>Calmar</th><th>Win%</th><th>WF H1/H2</th><th>10y proj</th><th>Liq</th></tr></thead><tbody></tbody></table>
  <div class="note">Sizing & leverage scale by confidence (regime-strategy fit). Drawdown kill-switch halves exposure when equity is 25%+ off its peak. Funding & 5bp/side fees included.</div>
</div>

<div class="card" style="margin-top:14px"><div class="k">4-ROLE SIGN-OFF — converged</div><div id="roles"></div></div>
<div class="card" style="margin-top:14px"><div class="note" id="caveat"></div></div>
</div>
<script>
const D=__DATA__;
const f0=x=>x==null?'n/a':Number(x).toLocaleString(undefined,{maximumFractionDigits:0});
const fp=x=>x==null||isNaN(x)?'n/a':(x*100).toFixed(1)+'%';const f2=x=>x==null||isNaN(x)?'n/a':Number(x).toFixed(2);
document.getElementById('asof').textContent='As of '+D.as_of+' · BTCUSDT · daily regime, 1-min intraday entry/exit fills · start $'+f0(D.start);
document.getElementById('verdict').innerHTML='🎯 <b>$80M / 10y target:</b> '+D.verdict_80M;
const L=D.live;const a=document.getElementById('action');a.textContent=L.action;a.style.color=L.in_market?'var(--grn)':'var(--mut)';
document.getElementById('price').textContent='$'+f0(L.price);
document.getElementById('regime').textContent=L.regime;
document.getElementById('strat').textContent=L.active_strategy;
document.getElementById('conf').textContent=L.confidence_bucket+' ('+L.confidence_sharpe+')';
document.getElementById('tp').textContent=L.take_profit;document.getElementById('cut').textContent=L.cut_loss;
document.getElementById('map').innerHTML=Object.entries(D.regime_map).map(([k,v])=>{
 const col=v==='STAND ASIDE'?'var(--mut)':'var(--grn)';
 return `<div><span class="mut">${k}</span><br><b style="color:${col}">${v}</b> <span class="mut">(${D.regime_dist[k]||0}d)</span></div>`;}).join('');
const tb=document.querySelector('#tiers tbody');
Object.entries(D.tiers).forEach(([nm,t])=>{const tr=document.createElement('tr');
 tr.innerHTML=`<td>${nm}</td><td>$${f0(t.final)}</td><td>${fp(t.cagr)}</td><td class="pos">${f2(t.sharpe)}</td><td>${f2(t.sortino)}</td>
 <td class="neg">${fp(t.maxdd)}</td><td>${f2(t.calmar)}</td><td>${(t.winrate*100).toFixed(0)}%</td>
 <td>${f2(t.wf[0])}/${f2(t.wf[1])}</td><td>$${f0(t.proj10y)}</td><td>${t.liquidations}</td>`;tb.appendChild(tr);});
document.getElementById('roles').innerHTML=D.roles.map(r=>`<div class="role"><span class="badge">${r.verdict}</span> <b>${r.role}</b><br><span class="mut">${r.note}</span></div>`).join('');
document.getElementById('caveat').textContent='⚠️ Hypothetical backtest, Binance BTCUSDT 2017–2026, 1-minute intraday fills, 5bp/side fees, perp funding modeled. One strategy active at a time, flat between trades. 0 liquidations by design (stop kept inside liquidation price; leverage capped). Past performance ≠ future results. Not financial advice.';
function chart(){const cv=document.getElementById('chart');const dpr=window.devicePixelRatio||1;const W=cv.clientWidth,H=260;
 cv.width=W*dpr;cv.height=H*dpr;const x=cv.getContext('2d');x.scale(dpr,dpr);
 const C=D.eq.CONSERVATIVE,B=D.eq.BALANCED,A=D.eq.AGGRESSIVE;const n=B.length;
 const all=C.concat(B).concat(A).filter(v=>v>0);const lo=Math.log10(Math.min(...all)),hi=Math.log10(Math.max(...all));
 const px=i=>46+(W-56)*i/(n-1);const py=v=>{const t=(Math.log10(Math.max(v,1e-6))-lo)/(hi-lo);return H-18-(H-32)*t;};
 x.strokeStyle='#1c2433';x.fillStyle='#6b7787';x.font='10px sans-serif';
 for(let p=Math.ceil(lo);p<=Math.floor(hi);p++){const y=py(Math.pow(10,p));x.beginPath();x.moveTo(46,y);x.lineTo(W-8,y);x.stroke();x.fillText('$'+f0(Math.pow(10,p)),4,y+3);}
 const dr=(arr,col,w)=>{x.strokeStyle=col;x.lineWidth=w;x.beginPath();arr.forEach((v,i)=>{i?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v));});x.stroke();};
 dr(A,'#ff5d5d',1.2);dr(B,'#ffb84d',1.4);dr(C,'#26d07c',1.6);
 x.fillStyle='#6b7787';[0,Math.floor(n/2),n-1].forEach(i=>x.fillText(D.dates[i].slice(0,7),px(i)-16,H-3));}
chart();window.addEventListener('resize',chart);
</script></body></html>"""

out = HTML.replace("__DATA__", DATA)
for fn in ["dashboard_intraday.html", "index.html"]:
    with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
        f.write(out)
print("wrote dashboard_intraday.html + index.html (", len(out), "bytes )")
