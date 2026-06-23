"""Build a self-contained offline dashboard.html with results_final.json embedded.
No external libraries (vanilla canvas) so it renders from file:// by double-click."""
import os, json

HERE = os.path.dirname(__file__)
with open(os.path.join(HERE, "..", "out", "results_final.json")) as f:
    data = json.load(f)

DATA_JSON = json.dumps(data)

HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC Consensus Signal</title>
<style>
:root{--bg:#0b0e14;--card:#141925;--ink:#e6edf3;--mut:#8b98a9;--grn:#26d07c;--red:#ff5d5d;
--amb:#ffb84d;--line:#222a38;--accent:#4da3ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:20px}
h1{font-size:20px;margin:0 0 2px}.sub{color:var(--mut);font-size:12px;margin-bottom:16px}
.grid{display:grid;gap:14px}.g3{grid-template-columns:repeat(3,1fr)}.g2{grid-template-columns:2fr 1fr}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.big{font-size:30px;font-weight:700;margin:4px 0}
.tag{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
.k{color:var(--mut);font-size:12px}.v{font-weight:600}
.row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--line)}
.votes{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px}
.vote{padding:8px;border-radius:8px;background:#0e131d;border:1px solid var(--line);font-size:12px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}th{color:var(--mut);font-weight:600}
.pos{color:var(--grn)}.neg{color:var(--red)}.mut{color:var(--mut)}
canvas{width:100%;height:260px;display:block}
.note{color:var(--mut);font-size:11px;margin-top:10px;line-height:1.5}
.barwrap{height:10px;background:#0e131d;border-radius:6px;overflow:hidden;margin-top:6px}
.bar{height:100%;background:linear-gradient(90deg,#26d07c,#4da3ff)}
.legend{font-size:11px;color:var(--mut)}.legend b{color:var(--accent)}.legend i{color:var(--mut);font-style:normal}
</style></head><body><div class="wrap">
<h1>BTC Consensus Signal <span class="mut" style="font-size:13px">· 9-strategy ensemble</span></h1>
<div class="sub" id="asof"></div>

<div class="grid g3">
  <div class="card"><div class="k">SIGNAL (next session)</div>
    <div class="big" id="action"></div>
    <div id="delta" class="mut"></div>
    <div class="k" style="margin-top:10px">Confidence (net-long consensus)</div>
    <div class="barwrap"><div class="bar" id="confbar"></div></div>
    <div id="conftxt" class="v" style="margin-top:4px"></div>
  </div>
  <div class="card"><div class="k">MARKET STATE</div>
    <div class="big" id="regime" style="font-size:20px"></div>
    <div class="row"><span class="k">Price</span><span class="v" id="price"></span></div>
    <div class="row"><span class="k">RSI(14)</span><span class="v" id="rsi"></span></div>
    <div class="row"><span class="k">BB width</span><span class="v" id="bbw"></span></div>
    <div class="row"><span class="k">vs SMA20</span><span class="v" id="ext"></span></div>
  </div>
  <div class="card"><div class="k">KEY LEVELS</div><div id="levels"></div></div>
</div>

<div class="grid g2" style="margin-top:14px">
  <div class="card"><div class="k">EQUITY CURVE — log scale (5bp fees, no look-ahead)</div>
    <canvas id="chart"></canvas>
    <div class="legend"><b>■ Consensus ensemble</b> &nbsp; <i>■ Buy &amp; Hold</i></div>
    <div id="perf"></div>
  </div>
  <div class="card"><div class="k">STRATEGY VOTES (today)</div>
    <div class="votes" id="votes"></div>
  </div>
</div>

<div class="card" style="margin-top:14px"><div class="k">PER-STRATEGY HONEST BACKTEST (Binance daily 2017–2026, 5bp/side, no look-ahead)</div>
  <table id="tbl"><thead><tr><th>Strategy</th><th>Tot.Ret</th><th>CAGR</th><th>Sharpe</th>
  <th>maxDD</th><th>Calmar</th><th>Win%</th><th>PF</th><th>#Tr</th><th>Verdict</th></tr></thead>
  <tbody></tbody></table>
  <div class="note" id="caveat"></div>
</div>
</div>
<script>
const D = __DATA__;
const f0=x=>x==null?'n/a':x.toLocaleString(undefined,{maximumFractionDigits:0});
const fp=x=>x==null||isNaN(x)?'n/a':(x*100).toFixed(1)+'%';
const f2=x=>x==null||isNaN(x)?'n/a':x.toFixed(2);
document.getElementById('asof').textContent='As of '+D.as_of+'  ·  BTCUSDT spot  ·  daily close';
const colors={'STRONG LONG':'var(--grn)','LONG (scaled)':'var(--grn)','LIGHT LONG':'var(--amb)','FLAT / STAND ASIDE':'var(--mut)'};
const a=document.getElementById('action');a.textContent=D.action;a.style.color=colors[D.action]||'var(--ink)';
document.getElementById('delta').textContent=D.delta;
document.getElementById('confbar').style.width=(D.confidence*100).toFixed(0)+'%';
document.getElementById('conftxt').textContent=(D.confidence*100).toFixed(0)+'%  ('+D.votes_long+' long / '+D.votes_flat+' flat / '+D.votes_short+' short of 9)';
const reg=document.getElementById('regime');reg.textContent=D.regime;
reg.style.color=D.regime.includes('TREND ▲')||D.regime.includes('UP')?'var(--grn)':(D.regime.includes('TOXIC')||D.regime.includes('▼')||D.regime.includes('DOWN')?'var(--red)':'var(--amb)');
document.getElementById('price').textContent='$'+f0(D.price);
document.getElementById('rsi').textContent=D.rsi;
document.getElementById('bbw').textContent=D.bb_width_pct+'%';
const ext=document.getElementById('ext');ext.textContent=(D.ext_from_sma20_pct>0?'+':'')+D.ext_from_sma20_pct+'%';
ext.className='v '+(D.ext_from_sma20_pct>=0?'pos':'neg');
const L=D.levels;const lv=document.getElementById('levels');
const order=[['Spot','price'],['SMA20','sma20'],['SMA50','sma50'],['BB upper','bb_upper'],['BB lower','bb_lower'],['20d high','swing_high_20d'],['20d low','swing_low_20d']];
lv.innerHTML=order.map(([n,k])=>`<div class="row"><span class="k">${n}</span><span class="v">$${f0(L[k])}</span></div>`).join('');
// votes
const vmap={LONG:['var(--grn)','🟢'],SHORT:['var(--red)','🔴'],FLAT:['var(--mut)','⚪']};
document.getElementById('votes').innerHTML=Object.entries(D.votes).map(([n,v])=>
 `<div class="vote"><span class="dot" style="background:${vmap[v][0]}"></span>${n}<br><b style="color:${vmap[v][0]}">${v}</b></div>`).join('');
// perf line
const mf=D.ensemble_metrics.full,bh=D.buyhold;
document.getElementById('perf').innerHTML=
 `<div class="row" style="margin-top:8px"><span class="k">Ensemble</span><span class="v">${fp(mf.total)} · Sharpe ${f2(mf.sharpe)} · maxDD ${fp(mf.maxdd)} · Calmar ${f2(mf.calmar)}</span></div>`+
 `<div class="row"><span class="k">Buy & Hold</span><span class="v mut">${fp(bh.total_return)} · Sharpe ${f2(bh.sharpe)} · maxDD ${fp(bh.maxdd)} · Calmar ${f2(bh.calmar)}</span></div>`;
// table
const verdict=(k,m,h1,h2)=>{return D.verdicts?D.verdicts[k]:''};
const tb=document.querySelector('#tbl tbody');
const VJ=D.verdicts||{};
Object.entries(D.per_strategy).forEach(([k,m])=>{
 const tr=document.createElement('tr');
 const sh=m.sharpe;const shc=sh>=0.8?'pos':(sh>=0.5?'':'neg');
 tr.innerHTML=`<td>${D.names[k]}</td><td>${fp(m.total_return)}</td><td>${fp(m.cagr)}</td>
 <td class="${shc}">${f2(m.sharpe)}</td><td class="neg">${fp(m.maxdd)}</td><td>${f2(m.calmar)}</td>
 <td>${(m.winrate*100).toFixed(0)}%</td><td>${f2(m.profit_factor)}</td><td>${m.n_trades}</td>
 <td>${VJ[k]||''}</td>`;
 tb.appendChild(tr);
});
document.getElementById('caveat').textContent=
 '⚠️ Hypothetical daily-close backtest on Binance BTCUSDT spot. Fees 5bp/side; funding & slippage not modeled (slippage stress-tested separately: edge holds to ~25bp/side). DSAM shown honest (no look-ahead). The final signal is LONG-ONLY consensus of all 9. Not financial advice — validate before risking capital.';
// chart
function chart(){
 const c=document.getElementById('chart');const dpr=window.devicePixelRatio||1;
 const W=c.clientWidth,H=260;c.width=W*dpr;c.height=H*dpr;const x=c.getContext('2d');x.scale(dpr,dpr);
 const eq=D.equity,bhq=D.bh_equity,n=eq.length;
 const all=eq.concat(bhq).filter(v=>v>0);const lo=Math.log10(Math.min(...all)),hi=Math.log10(Math.max(...all));
 const px=i=>40+(W-50)*i/(n-1);const py=v=>{const t=(Math.log10(v)-lo)/(hi-lo);return H-20-(H-35)*t;};
 // gridlines (powers of 10)
 x.strokeStyle='#1c2433';x.fillStyle='#6b7787';x.font='10px sans-serif';x.lineWidth=1;
 for(let p=Math.ceil(lo);p<=Math.floor(hi);p++){const y=py(Math.pow(10,p));x.beginPath();x.moveTo(40,y);x.lineTo(W-10,y);x.stroke();x.fillText((Math.pow(10,p))+'x',4,y+3);}
 const draw=(arr,col,w)=>{x.strokeStyle=col;x.lineWidth=w;x.beginPath();arr.forEach((v,i)=>{i?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v));});x.stroke();};
 draw(bhq,'#5a6678',1.2);draw(eq,'#26d07c',1.8);
 // date ticks
 x.fillStyle='#6b7787';[0,Math.floor(n/2),n-1].forEach(i=>{x.fillText(D.dates[i].slice(0,7),px(i)-18,H-4);});
}
chart();window.addEventListener('resize',chart);
</script></body></html>"""

# verdicts per strategy (from walk-forward analysis)
verdicts = {
    "OBV": "weak", "DSAM": "look-ahead infl.", "MACD": "✓ robust", "RSI": "overfit (fails H1)",
    "EMA": "✓ trend, decays", "BB": "overfit (few trades)", "MFI": "✓ robust",
    "OBV_ROC": "weak", "MACD_SIG": "✓ robust",
}
data["verdicts"] = verdicts
DATA_JSON = json.dumps(data)

out = HTML.replace("__DATA__", DATA_JSON)
path = os.path.join(HERE, "..", "out", "dashboard.html")
with open(path, "w", encoding="utf-8") as f:
    f.write(out)
print("wrote", path, "(", len(out), "bytes )")
