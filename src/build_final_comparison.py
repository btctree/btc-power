"""FINAL conclusion: every model discussed, optimized with the size-control logic, same metrics.
Columns: $@0bp / $@50bp / $@1x ... Calmar / Sharpe / maxDD / Win% (at the realistic 50bp).
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le
ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"])
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
HERE = os.path.dirname(os.path.abspath(__file__))
def lmap(p, col):
    if not os.path.exists(p): return {}
    f = pd.read_csv(p); return dict(zip(f.iloc[:, 0].astype(str), f[col]))
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trail_rank(a, w=365):
    return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vol_rank = trail_rank(rv); fund_rank = trail_rank(funding)
gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vol_rank[i] == vol_rank[i] and vol_rank[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fund_rank[i] == fund_rank[i]:
        if fund_rank[i] > 0.90: gl[i] *= 0.5
        if fund_rank[i] < 0.10: gs[i] *= 0.5
# cycle direction (calendar)
halv = [pd.Timestamp(x) for x in ["2012-11-28","2016-07-09","2020-05-11","2024-04-20"]]
dsh = np.array([min([(d-h).days for h in halv if h<=d] or [9999]) for d in dates],float)
phase = (dsh/1458.0) % 1.0
cyc = np.where((phase<0.42)|(phase>0.62), 1.0, -1.0)
# conditional leverage cap per day
REGF={"STRONG_UP":1.0,"TREND_UP":1.0,"PULLBACK_UP":0.7,"BOUNCE_DOWN":0.7,"STRONG_DOWN":0.8,"TREND_DOWN":0.9,"CHOP_HIVOL":0.5,"RANGE":0.5,"NEUTRAL":0.5}
def conf_f(a):
    a=abs(a); return 1.0 if a>=0.75 else (0.85 if a>=0.5 else 0.7)
esm = pd.Series(expf).ewm(span=5,adjust=False).mean().to_numpy()
condcap=np.array([ (3.0 if esm[i]>0 else 2.0)*REGF.get(reg[i],0.5)*conf_f(esm[i]) for i in range(n)])

def sim(signal, cap, vt, smooth, band, slip, gates=True, dd_kill=0.30, legacy=None, fee=0.0005, maint=0.01):
    e_in = pd.Series(signal).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth>1 else np.array(signal,float)
    cap_arr = cap if hasattr(cap,'__len__') else None
    equity=peak=500.0; held=0.0; eq=np.full(n,500.0); E=np.zeros(n); liq=0
    for i in range(i0,n):
        sig=e_in[i-1]; g=(gl[i-1] if sig>0 else (gs[i-1] if sig<0 else 1.0)) if gates else 1.0
        if not (rv[i-1]==rv[i-1] and rv[i-1]>0): eq[i]=equity; E[i]=held; continue
        if legacy: mult=legacy*min(1.0,0.60/rv[i-1])
        else:
            capv=cap_arr[i-1] if cap_arr is not None else cap
            mult=min(capv, vt/rv[i-1])
        e=sig*g*mult
        if dd_kill>0 and equity<peak*(1-dd_kill): e*=0.5
        if band>0 and abs(e-held)<band and not (e==0 and held!=0): e=held
        adv=(-(low[i]/close[i-1]-1)) if e>0 else ((high[i]/close[i-1]-1) if e<0 else 0.0)
        if e!=0 and abs(e)*max(adv,0)>=(1-maint):
            equity*=0.01; liq+=1; held=0.0; eq[i]=equity; E[i]=0.0; peak=max(peak,equity); continue
        equity*=(1+e*(close[i]/close[i-1]-1)); equity-=equity*abs(e-held)*(fee+slip)
        held=e; eq[i]=max(equity,1e-9); E[i]=e; peak=max(peak,equity)
    return eq, E, liq
def met(eq):
    s=pd.Series(eq[i0:]); r=s.pct_change().dropna(); yrs=len(s)/ANN
    cagr=(s.iloc[-1]/500)**(1/yrs)-1 if s.iloc[-1]>0 else -1
    sh=r.mean()*ANN/(r.std(ddof=1)*np.sqrt(ANN)) if r.std()>0 else float('nan')
    dd=(s/s.cummax()-1).min()
    return s.iloc[-1], sh, (cagr/abs(dd) if dd<0 else float('nan')), dd
def winrate(E,eq):
    i=i0; w=0; tot=0
    while i<n:
        sgn=1 if E[i]>0 else (-1 if E[i]<0 else 0)
        if sgn==0: i+=1; continue
        j=i
        while j+1<n and (1 if E[j+1]>0 else (-1 if E[j+1]<0 else 0))==sgn: j+=1
        f0=eq[i-1] if i>0 else 500.0
        if eq[j]/f0-1>0: w+=1
        tot+=1; i=j+1
    return (w/tot if tot else 0), tot

# (name, signal, cap, vt, smooth, band, gates, legacy)
M=[("Buy & Hold (BTC)", np.ones(n),1,999,0,0.0,False,None),
   ("Raw 8B 5x (original)", expf,5,0.6,0,0.0,True,5),
   ("Core 1x (cap1,vt1.5)", expf,1,1.5,5,0.15,True,None),
   ("Balanced 2x (cap2)", expf,2,1.5,5,0.15,True,None),
   ("Balanced 8B (cap3) *rec", expf,3,1.5,5,0.15,True,None),
   ("Million-A (cap5)", expf,5,1.5,5,0.15,True,None),
   ("Conditional-lev (size)", expf,condcap,1.5,5,0.15,True,None),
   ("Cycle math (cap5,size)", cyc,5,0.8,5,0.15,False,None)]
print(f"{'MODEL':24s} {'$@0bp':>14s} {'$@50bp':>13s} {'$@1x':>11s} {'Calmar':>6s} {'Sharpe':>6s} {'maxDD':>6s} {'Win%':>5s} {'liq':>3s}")
rows=[]
for nm,sig,cap,vt,smt,bd,gt,lg in M:
    eq0,_,_=sim(sig,cap,vt,smt,bd,0.0,gt,0.30,lg)
    eq5,E5,liq=sim(sig,cap,vt,smt,bd,0.005,gt,0.30,lg)
    eq1,_,_=sim(sig,1,vt,smt,bd,0.005,gt,0.30,(1 if lg else None))
    f0=eq0[-1]; f5,sh,cal,dd=met(eq5); f1=eq1[-1]; wr,tot=winrate(E5,eq5)
    print(f"{nm:24s} ${f0:>13,.0f} ${f5:>12,.0f} ${f1:>10,.0f} {cal:>6.2f} {sh:>6.2f} {dd*100:>5.0f}% {wr*100:>4.0f}% {liq:>3d}")
    rows.append((nm,f0,f5,f1,cal,sh,dd,wr,liq))
