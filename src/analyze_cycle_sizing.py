"""Can we run 5x leverage on the cycle strategy with NO liquidation, via size control?
Liquidation triggers when effective_exposure x intraday_adverse_move >= ~100%. BTC's worst intraday
move caps the safe exposure. Test: (a) max CONSTANT leverage with 0 liq, (b) vol-targeted sizing with
a 5x cap (size control), (c) hard effective-exposure cap. Report value, DD, liq, avg/max exposure.
"""
import numpy as np, pandas as pd
import compare_m1m5 as cm
ANN = 365
df = cm.prep(cm.build_combined())
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
dates = pd.to_datetime(df["Date"]); n = len(df); i0 = 260
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)

# worst intraday adverse move in history (down move; the liquidation threat for longs)
dn = -(low[1:] / close[:-1] - 1)
print(f"BTC worst intraday DOWN move (vs prior close): {np.nanmax(dn)*100:.0f}%  -> a 5x long needs only a {100/5:.0f}% gap to liquidate")
print(f"  => guaranteed-safe constant exposure ceiling ~ {1/np.nanmax(dn):.1f}x\n")

# cycle direction (calendar only)
genesis = pd.Timestamp("2009-01-03")
halv = [pd.Timestamp(x) for x in ["2012-11-28","2016-07-09","2020-05-11","2024-04-20"]]
dsh = np.array([min([(d-h).days for h in halv if h<=d] or [9999]) for d in dates],float)
phase = (dsh/1458.0) % 1.0
cyc = np.where((phase<0.42)|(phase>0.62), 1.0, -1.0)

def sim(expo, slip=0.005, fee=0.0005, maint=0.01):
    """expo[i] = effective exposure (signed, x equity) to hold on day i."""
    equity=peak=500.0; held=0.0; liq=0; eq=np.full(n,500.0); exps=[]
    for i in range(i0,n):
        e=expo[i-1]
        if not np.isfinite(e): e=0.0
        adv=(-(low[i]/close[i-1]-1)) if e>0 else ((high[i]/close[i-1]-1) if e<0 else 0.0)
        if e!=0 and abs(e)*max(adv,0)>=(1-maint):
            equity*=0.01; liq+=1; held=0.0; eq[i]=equity; peak=max(peak,equity); continue
        equity*=(1+e*(close[i]/close[i-1]-1)); equity-=equity*abs(e-held)*(fee+slip)
        held=e; eq[i]=max(equity,1e-9); peak=max(peak,equity); exps.append(abs(e))
    s=pd.Series(eq[i0:],index=dates.iloc[i0:].values); r=s.pct_change().dropna(); yrs=len(s)/ANN
    cagr=(s.iloc[-1]/500)**(1/yrs)-1 if s.iloc[-1]>0 else -1
    dd=(s/s.cummax()-1).min()
    return s.iloc[-1],cagr,dd,liq,np.mean(exps),np.max(exps)

print("(A) CONSTANT leverage — find max with 0 liquidations:")
print(f"{'lev':>5s} {'$500->':>15s} {'CAGR':>6s} {'maxDD':>7s} {'liq':>4s}")
for lev in [2.0,2.5,2.7,2.9,3.0,5.0]:
    f,cagr,dd,liq,ae,me=sim(cyc*lev)
    print(f"{lev:>4.1f}x ${f:>14,.0f} {cagr*100:>5.0f}% {dd*100:>6.0f}% {liq:>4d}{'  <-- NO-LIQ' if liq==0 else '  LIQUIDATED'}")

print("\n(B) SIZE CONTROL = vol-targeted, capped at 5x nominal (effective = dir x min(5, vt/realised_vol)):")
print(f"{'vol_tgt':>8s} {'$500->':>15s} {'CAGR':>6s} {'maxDD':>7s} {'liq':>4s} {'avgExp':>7s} {'maxExp':>7s}")
for vt in [0.40,0.50,0.60,0.80]:
    size=np.clip(vt/rv,0,5.0); expo=cyc*size
    f,cagr,dd,liq,ae,me=sim(expo)
    print(f"{vt*100:>6.0f}% ${f:>14,.0f} {cagr*100:>5.0f}% {dd*100:>6.0f}% {liq:>4d} {ae:>6.2f}x {me:>6.2f}x{'  NO-LIQ' if liq==0 else '  LIQUIDATED'}")

print("\n(C) SIZE CONTROL + hard effective cap (5x nominal but never let exposure exceed CAP -> guarantee):")
print(f"{'cap':>5s} {'vt':>5s} {'$500->':>15s} {'CAGR':>6s} {'maxDD':>7s} {'liq':>4s} {'avgExp':>7s}")
for cap in [2.0,2.5]:
    for vt in [0.50,0.80]:
        size=np.clip(np.minimum(vt/rv,5.0),0,cap); expo=cyc*size
        f,cagr,dd,liq,ae,me=sim(expo)
        print(f"{cap:>4.1f}x {vt*100:>4.0f}% ${f:>14,.0f} {cagr*100:>5.0f}% {dd*100:>6.0f}% {liq:>4d} {ae:>6.2f}x")
