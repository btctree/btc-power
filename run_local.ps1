# BTC Power — LOCAL runner. *** DORMANT / EMERGENCY FALLBACK ONLY — DO NOT SCHEDULE. ***
#
# The live system runs on the Oracle VM (ubuntu@193.123.188.8) via run_cloud.sh, cron '5 * * * *'.
# This script does the SAME job against the SAME real Binance account. Running both would make the
# laptop and the VM fight over one position, each undoing the other's orders (that churn cost $20
# on 2026-07-16/17). Its Windows scheduled task 'BTC-Signal-Local' was deleted 2026-08-11
# (restorable from logs\BTC-Signal-Local.task.xml.bak).
#
# Two independent guards keep this copy inert: btc_signal\STOP exists (binance_trader.py exits on
# it), and the local .env has LIVE_TRADING=0. To use this as a fallback if the VM is truly dead:
#   1) confirm the VM is NOT trading (ssh ... 'ls ~/btc-power/STOP' or the VM is unreachable)
#   2) delete btc_signal\STOP   3) set LIVE_TRADING=1 in .env   4) run this script by hand first
# and read logs\trader.log before scheduling anything.
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path   # was a hardcoded path that no longer exists
Set-Location $repo
if (-not (Test-Path logs)) { New-Item -ItemType Directory logs | Out-Null }
$log = Join-Path $repo "logs\local_runner.log"
$ts  = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$env:STATE_FILE = "../state_local.json"     # local-only state (no clash with CI's state.json)
$env:PYTHONIOENCODING = "utf-8"
"[$ts] === local runner start ===" | Out-File -Append -Encoding utf8 $log
python src\fetch_data.py            *>> $log      # refresh BTC daily data
python src\growth_engine.py         *>> $log      # recompute Max B -> out/results_live.json
$env:ORDER_TYPE = "MARKET"                        # reliable fills so the position tracks the model
python src\binance_trader.py        *>> $log      # AUTOTRADE: reconcile Binance account to target
python src\telegram_signal.py --mode watch *>> $log   # notify on any required action + daily report
"[$ts] === done ===" | Out-File -Append -Encoding utf8 $log
