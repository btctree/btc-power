#!/usr/bin/env python3
"""Auto-resume gate for the STOP kill switch.

Semantics:
  * STOP alone (no marker)          -> frozen until a human removes it. Unchanged.
  * STOP + STOP_UNTIL_SIGNAL marker -> frozen only while the model's open trade still
    matches the marker line ("DIRECTION YYYY-MM-DD" = model_growth direction + entry_date).
    On the model's next trade both files are removed and trading resumes the same run.

Runs from run_cloud.sh AFTER growth_engine.py (fresh results_live.json) and BEFORE
binance_trader.py. Any error leaves STOP in place — failing frozen, never failing armed.
"""
import json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
STOP = os.path.join(ROOT, "STOP")
MARKER = os.path.join(ROOT, "STOP_UNTIL_SIGNAL")


def log(msg):
    print(f"[stop-guard] {msg}", flush=True)


def main():
    if not os.path.exists(MARKER):
        return
    if not os.path.exists(STOP):
        os.remove(MARKER)
        log("STOP was removed by hand — clearing stale marker; trading follows the model again.")
        return
    want = open(MARKER, encoding="utf-8").read().strip()
    g = json.load(open(os.path.join(ROOT, "out", "results_live.json"), encoding="utf-8")).get("model_growth") or {}
    cur = f"{g.get('direction')} {g.get('entry_date')}"
    if cur == want:
        log(f"model trade unchanged ({cur}) — STOP stays, no trading.")
    else:
        os.remove(STOP)
        os.remove(MARKER)
        log(f"model trade changed ({want} -> {cur}) — STOP removed, auto-trading resumes this run.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # any failure must leave STOP untouched
        log(f"error ({e}) — leaving STOP in place.")

