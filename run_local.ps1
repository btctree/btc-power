# BTC Power — LOCAL runner (the single notifier + future trade executor).
# Runs hourly via Windows Task Scheduler. Refreshes data + signal, then telegram watch
# (entry / add / reduce / exit / flip / cut-loss + daily report). Reads secrets from .env.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\user\OneDrive\Desktop\New setup for BTC\btc_signal"
Set-Location $repo
if (-not (Test-Path logs)) { New-Item -ItemType Directory logs | Out-Null }
$log = Join-Path $repo "logs\local_runner.log"
$ts  = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$env:STATE_FILE = "../state_local.json"     # local-only state (no clash with CI's state.json)
$env:PYTHONIOENCODING = "utf-8"
"[$ts] === local runner start ===" | Out-File -Append -Encoding utf8 $log
python src\fetch_data.py            *>> $log      # refresh BTC daily data
python src\growth_engine.py         *>> $log      # recompute Max B -> out/results_live.json
python src\telegram_signal.py --mode watch *>> $log   # notify on any required action + daily report
"[$ts] === done ===" | Out-File -Append -Encoding utf8 $log
