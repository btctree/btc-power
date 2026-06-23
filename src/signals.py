"""The 9 strategy signal engines, ported faithfully from working.xlsm 'Indicators'.
Each emits per-row: 'Buy','Sell','Hold+','Hold-','0', or '' (warmup).
State machine (identical across all 9): counts of prior Buy/Sell decide regime
(flat / long / short); entry & exit logic differ per strategy.
Counts/lookups use PRIOR rows only (matches Excel COUNTIF V$1:V3999 at row t).
"""
import numpy as np
import pandas as pd


def _arr(df, col):
    return df[col].to_numpy()


def compute_single(close, lookahead=True):
    """Excel col D 'Single'. lookahead=True replicates the Excel (uses NEXT 5 closes
    -> look-ahead bias). lookahead=False uses the PAST 5 closes (honest)."""
    n = len(close)
    out = [""] * n
    nb = ns = 0
    for i in range(n):
        if lookahead:
            if i + 5 >= n:
                out[i] = ""
                continue
            fut = close[i + 1:i + 6].mean()
        else:
            if i < 5:
                out[i] = ""
                continue
            fut = close[i - 5:i].mean()
        b = close[i]
        net = nb - ns
        if net == 0:
            s = "Buy" if fut > b * 1.022 else ("Sell" if fut < b * 0.978 else "0")
        elif net == 1:
            s = "Sell" if fut < b * 0.978 else "Hold+"
        elif net == -1:
            s = "Buy" if fut > b * 1.022 else "Hold-"
        else:
            s = "0"
        out[i] = s
        if s == "Buy":
            nb += 1
        elif s == "Sell":
            ns += 1
    return out


def run_all(df, single_lookahead=True):
    """Return dict {strategy_name: list_of_signals}."""
    n = len(df)
    C = _arr(df, "close")
    V = _arr(df, "volume")
    E = _arr(df, "RSI")
    F = _arr(df, "SMA20")
    G = _arr(df, "SMA21")
    H = _arr(df, "EMA12")
    I = _arr(df, "EMA26")
    J = _arr(df, "EMA_fast")
    K = _arr(df, "EMA_slow")
    L = _arr(df, "MACD")
    M = _arr(df, "SignalLine")
    Nu = _arr(df, "BB_Upper")
    O = _arr(df, "BB_Lower")
    P = _arr(df, "MFI")
    Q = _arr(df, "OBV")          # vol-direction label
    R = _arr(df, "ROC")
    S = _arr(df, "MACD_tailor")
    T = _arr(df, "Sig_tailor")
    D = compute_single(C, lookahead=single_lookahead)

    out = {}

    # ---- helper to run a sequential strategy given a decide(i, st) ----
    def run(decide, warmup):
        sig = [""] * n
        st = dict(nb=0, ns=0, lbp=None, lbi=None, lsp=None, lsi=None,
                  lbr=None, lsr=None, prev=None)
        for i in range(warmup, n):
            s = decide(i, st)
            sig[i] = s
            st["prev"] = s
            if s == "Buy":
                st["nb"] += 1; st["lbp"] = C[i]; st["lbi"] = i; st["lbr"] = E[i]
            elif s == "Sell":
                st["ns"] += 1; st["lsp"] = C[i]; st["lsi"] = i; st["lsr"] = E[i]
        return sig

    # ===== 1. OBV trend reversal (V) warmup row<241 -> i<239
    def s_obv(i, st):
        net = st["nb"] - st["ns"]
        if net == 0:
            if Q[i] == "UP" and E[i] > 40 and P[i] > 52:
                return "Buy"
            if Q[i] == "DOWN" and E[i] < 40 and P[i] < 52:
                return "Sell"
            return "0"
        if net > 0:
            lb = st["lbp"]
            if C[i] < lb * (0.7 + (1 - C[i] / lb) * 0.2):
                return "Sell"
            if Q[i] == "DOWN" and Q[i - 1] == "DOWN":
                return "Sell"
            return "Hold+"
        else:
            ls = st["lsp"]
            if C[i] > ls * (1.3 - (C[i] / ls - 1) * 0.4):
                return "Buy"
            if Q[i] == "UP" and Q[i - 1] == "UP":
                return "Buy"
            return "Hold-"
    out["OBV"] = run(s_obv, 239)

    # ===== 2. DSAM (W) warmup row<260 -> i<258 ; uses D (Single)
    def s_dsam(i, st):
        net = st["nb"] - st["ns"]
        jk = J[i] > K[i]; jkp = J[i - 1] >= K[i - 1]; jkpl = J[i - 1] <= K[i - 1]
        if net > 0:
            if D[i] == "Sell" or S[i] < T[i] or C[i] < F[i]:
                return "Sell"
            if J[i] < K[i] and J[i - 1] >= K[i - 1] and P[i] < 71:
                return "Sell"
            if J[i] > K[i] and J[i - 1] <= K[i - 1] and P[i] < 71:
                return "Sell"
            if ((J[i] > K[i] and G[i] > K[i] and P[i] < 71) or
                (J[i] < K[i] and G[i] < K[i] and P[i] < 71) or
                (J[i] > 70 and J[i - 1] <= K[i - 1] and P[i] < 71) or
                (J[i] < K[i] and J[i - 1] >= K[i - 1] and P[i] < 71)):
                return "Sell"
            return "Hold+"
        if net < 0:
            if D[i] == "Buy" or S[i] > T[i] or C[i] > F[i]:
                return "Buy"
            if J[i] > K[i] and J[i - 1] <= K[i - 1] and P[i] > 50:
                return "Buy"
            if J[i] < K[i] and J[i - 1] >= K[i - 1] and P[i] > 50:
                return "Buy"
            if ((J[i] > K[i] and G[i] > K[i] and P[i] > 50) or
                (J[i] < K[i] and G[i] < K[i] and P[i] > 50) or
                (J[i] > K[i] and J[i - 1] <= K[i - 1] and P[i] > 50) or
                (J[i] < K[i] and J[i - 1] >= K[i - 1] and P[i] > 50)):
                return "Buy"
            return "Hold-"
        # flat
        if J[i] > K[i] and J[i - 1] <= K[i - 1] and P[i] > 20:
            return "Buy"
        if J[i] < K[i] and J[i - 1] >= K[i - 1] and P[i] < 42:
            return "Sell"
        if J[i] > K[i] and G[i] > K[i] and P[i] > 20:
            return "Buy"
        if J[i] < K[i] and G[i] < K[i] and P[i] < 42:
            return "Sell"
        return "0"
    out["DSAM"] = run(s_dsam, 258)

    # ===== 3. MACD reversal (X) warmup row<262 -> i<260
    def s_macdrev(i, st):
        net = st["nb"] - st["ns"]
        bw = Nu[i] - O[i]  # band width (N-O)
        # ratio depends on previous signal direction
        prev = st["prev"]
        if prev == "Buy" and st["lbp"]:
            ratio = bw / st["lbp"]
        elif prev == "Sell" and st["lsp"]:
            ratio = bw / st["lsp"]
        else:
            ratio = 0.0
        if net > 0:
            lb = st["lbp"]
            cond = (
                C[i] >= lb * (1 + 0.25 * ratio) or
                C[i] <= lb * (1 - 0.4 * ratio) or
                (L[i] < M[i] and L[i - 1] >= M[i - 1] and L[i] < 0 and (H[i] < I[i] or F[i] < G[i]))
            )
            if not cond and (C[i] - lb) / lb > 0.002:
                hi = np.max(H[st["lbi"]:i + 1])
                cond = C[i] <= hi * 0.9
            return "Sell" if cond else "Hold+"
        if net < 0:
            ls = st["lsp"]
            cond = (
                C[i] <= ls * (1 - 0.25 * ratio) or
                C[i] >= ls * (1 + 0.4 * ratio) or
                (L[i] > M[i] and L[i - 1] <= M[i - 1] and L[i] > 0 and (H[i] > I[i] or F[i] > G[i]))
            )
            if not cond and (ls - C[i]) / ls > 0.002:
                lo = np.min(I[st["lsi"]:i + 1])
                cond = C[i] >= lo * 1.1
            return "Buy" if cond else "Hold-"
        # flat. NOTE: Excel uses 'RSI4000', an UNDEFINED name that resolves to 0,
        # so 'RSI>70' is always False (up -> always Buy) and 'RSI<30' is always
        # True (dn -> always "0"). Net effect: this strategy is LONG-ONLY from flat.
        up = ((L[i] > M[i] and L[i - 1] <= M[i - 1] and L[i] > 0 and (H[i] > I[i] or F[i] > G[i]))
              or (L[i] > 0 and L[i - 1] > 0 and L[i] > M[i]))
        if up:
            return "Buy"   # RSI4000>70 is always False
        # dn branch always yields "0" because RSI4000<30 is always True
        return "0"
    out["MACD"] = run(s_macdrev, 260)

    # ===== 4. RSI breakout (Y) warmup row<241 -> i<239
    def s_rsi(i, st):
        net = st["nb"] - st["ns"]
        if net > 0:
            max20 = np.max(E[max(0, i - 20):i])  # E[t-20..t-1]
            cond = (
                (E[i] < st["lbr"] and (
                    L[i] < 0.16 or
                    (E[i] < E[i - 1] and E[i - 1] < E[i - 2] and L[i - 1] < L[i] and abs(E[i] - E[i - 3]) >= 5)
                )) or
                (E[i] < max20 and E[i - 1] > max20)
            )
            return "Sell" if cond else "Hold+"
        if net < 0:
            cond = (
                (E[i] > st["lsr"] and (
                    L[i] > -0.16 or
                    (E[i] > E[i - 1] and E[i - 1] > E[i - 2] and L[i - 1] > L[i] and abs(E[i] - E[i - 3]) >= 5)
                )) or
                (E[i] > 30.13 and E[i - 1] < 30.13)
            )
            return "Buy" if cond else "Hold-"
        if E[i] > 30.13 and E[i - 1] < 30.13:
            return "Buy"
        if E[i] < 60.55 and E[i - 1] > 60.55:
            return "Sell"
        return "0"
    out["RSI"] = run(s_rsi, 239)

    # ===== 5. EMA12 vs EMA26 (Z) warmup row<241 -> i<239
    def s_ema(i, st):
        net = st["nb"] - st["ns"]
        if net > 0:
            cond = (
                (E[i] < st["lbr"] - 2.13535 and L[i] < M[i]) or
                (E[i] < st["lbr"] and L[i] < M[i] and abs(E[i] - E[i - 1]) > 4.2707)
            )
            return "Sell" if cond else "Hold+"
        if net < 0:
            cond = (
                (E[i] > st["lsr"] + 2.13535 and L[i] > M[i]) or
                (E[i] > st["lsr"] and L[i] > M[i] and abs(E[i] - E[i - 1]) > 4.2707)
            )
            return "Buy" if cond else "Hold-"
        up = ((H[i] > I[i] and H[i - 1] < I[i - 1]) or (E[i] > 36.95 and E[i - 1] < 36.95) or
              (L[i] > M[i] and L[i - 1] < M[i - 1]) or (C[i] > G[i] and C[i - 1] < G[i - 1]))
        if up:
            return "Buy"
        dn = ((H[i] < I[i] and H[i - 1] > I[i - 1]) or (E[i] < 66.68 and E[i - 1] > 66.68) or
              (L[i] < M[i] and L[i - 1] > M[i - 1]) or (C[i] < G[i] and C[i - 1] > G[i - 1]))
        if dn:
            return "Sell"
        return "0"
    out["EMA"] = run(s_ema, 239)

    # ===== 6. BB breakout (AA) warmup row<244 -> i<242
    def s_bb(i, st):
        net = st["nb"] - st["ns"]
        if net == 0:
            if C[i] > Nu[i] * 1.01:
                return "Buy"
            if C[i] < O[i] * 0.995:
                return "Sell"
            return "0"
        if net > 0:
            thr = (0.995 + 0.002) if C[i] < st["lbp"] else 0.995
            return "Sell" if C[i] < O[i] * thr else "Hold+"
        else:
            thr = (1.01 - 0.002) if C[i] > st["lsp"] else 1.01
            return "Buy" if C[i] > Nu[i] * thr else "Hold-"
    out["BB"] = run(s_bb, 242)

    # ===== 7. MFI reversal (AB) warmup row<261 -> i<259
    def s_mfi(i, st):
        net = st["nb"] - st["ns"]
        if net == 0:
            if P[i] > 24:
                return "Buy"
            if P[i] < 60:
                return "Sell"
            return "0"
        if net > 0:
            if C[i] < st["lbp"]:
                if (C[i - 1] > C[i - 2] and C[i] > C[i - 1] and
                        V[i - 1] > V[i - 2] and V[i] > V[i - 1]):
                    return "Hold+"
                return "Sell" if C[i] < st["lbp"] * 0.9 else "Hold+"
            return "Sell" if P[i] < 60 else "Hold+"
        else:
            if C[i] > st["lsp"]:
                if (C[i - 1] < C[i - 2] and C[i] < C[i - 1] and
                        V[i - 1] > V[i - 2] and V[i] > V[i - 1]):
                    return "Hold-"
                return "Buy" if C[i] > st["lsp"] * 0.9 else "Hold-"
            return "Buy" if P[i] > 24 else "Hold-"
    out["MFI"] = run(s_mfi, 259)

    # ===== 8. OBV vs ROC (AC) warmup row<260 -> i<258
    def s_obvroc(i, st):
        net = st["nb"] - st["ns"]
        chg = (C[i] - C[i - 1]) / C[i - 1]
        if net > 0:
            mx = np.max(C[st["lbi"]:i])  # entry..t-1
            if F[i] > F[i - 1] and H[i] > I[i] and L[i] > M[i]:
                trail = C[i] < mx * 0.94
            else:
                trail = C[i] < mx * 0.97
            cond = (
                chg < -0.03 or
                (F[i] < F[i - 1] and H[i] < I[i] and L[i] < M[i] and chg < -0.01) or
                trail or
                (R[i] < R[i - 1] and Q[i] == "DOWN")
            )
            return "Sell" if cond else "Hold+"
        if net < 0:
            mn = np.min(C[st["lsi"]:i])
            cond = (
                chg > 0.04 or
                (F[i] > F[i - 1] and H[i] > I[i] and L[i] > M[i] and chg > 0.01) or
                C[i] > mn * 1.06 or
                (R[i] > R[i - 1] and Q[i] == "UP")
            )
            return "Buy" if cond else "Hold-"
        if F[i] > F[i - 1] and H[i] > I[i] and J[i] > K[i] and L[i] > M[i] and Q[i] == "UP":
            return "Buy"
        if F[i] < F[i - 1] and H[i] < I[i] and J[i] < K[i] and L[i] < M[i] and Q[i] == "DOWN":
            return "Sell"
        return "0"
    out["OBV_ROC"] = run(s_obvroc, 258)

    # ===== 9. MACD vs Signal Line (AD) warmup row<260 -> i<258 ; uses S/T (tailor)
    def s_macdsig(i, st):
        net = st["nb"] - st["ns"]
        cross_up = S[i] > T[i] and S[i - 1] < T[i - 1] and abs(S[i] - T[i]) > 0.2
        cross_dn = S[i] < T[i] and S[i - 1] > T[i - 1] and abs(S[i] - T[i]) > 0.2
        if net > 0:
            cond = cross_dn or C[i] < st["lbp"] * 0.91
            return "Sell" if cond else "Hold+"
        if net < 0:
            cond = cross_up or C[i] > st["lsp"] * 1.09
            return "Buy" if cond else "Hold-"
        if cross_up:
            return "Buy"
        if cross_dn:
            return "Sell"
        return "0"
    out["MACD_SIG"] = run(s_macdsig, 258)

    return out


# map our keys -> Excel column header (for validation)
EXCEL_COL = {
    "OBV": "OBV 趨勢反轉", "DSAM": "DSAM 連續up/down", "MACD": "MACD反轉",
    "RSI": "RSI突破", "EMA": "EMA12 vs EMA26", "BB": "BB突破",
    "MFI": "MFI反轉", "OBV_ROC": "OBV vs ROC", "MACD_SIG": "MACD vs Signal Line",
}
