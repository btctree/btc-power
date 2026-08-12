#!/usr/bin/env bash
# Publish out/real_pnl.json to the repo so CI can embed REAL account P&L in the public dashboard.
#
# Why this exists: api.binance.com returns HTTP 451 to GitHub-hosted runners, so CI can never read
# the account itself. The VM can, so the VM publishes the file and CI just embeds it.
#
# Safety: uses an ISOLATED git index (GIT_INDEX_FILE) and commit-tree, so it never touches the
# working tree, never stages anything else, and can only ever change that one path. It exits 0 on
# every failure path — publishing is cosmetic and must never disturb the trading pipeline.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 0
F="out/real_pnl.json"
[ -f "$F" ] || { echo "[publish] no $F yet — nothing to publish"; exit 0; }

git fetch -q origin main 2>/dev/null || { echo "[publish] fetch failed — skipping"; exit 0; }

for attempt in 1 2; do
  blob=$(git hash-object -w "$F" 2>/dev/null) || { echo "[publish] hash-object failed"; exit 0; }
  IDX=$(mktemp) || exit 0
  export GIT_INDEX_FILE="$IDX"
  if ! git read-tree origin/main 2>/dev/null; then rm -f "$IDX"; echo "[publish] read-tree failed"; exit 0; fi
  git update-index --add --cacheinfo "100644,$blob,$F" 2>/dev/null
  tree=$(git write-tree 2>/dev/null)
  rm -f "$IDX"; unset GIT_INDEX_FILE
  [ -n "$tree" ] || { echo "[publish] write-tree failed"; exit 0; }

  if [ "$tree" = "$(git rev-parse origin/main^{tree} 2>/dev/null)" ]; then
    echo "[publish] real_pnl.json unchanged — nothing to push"; exit 0
  fi

  commit=$(git commit-tree "$tree" -p "$(git rev-parse origin/main)" \
      -m "publish real account P&L snapshot [skip ci]" 2>/dev/null)
  [ -n "$commit" ] || { echo "[publish] commit-tree failed"; exit 0; }

  if git push -q origin "$commit:refs/heads/main" 2>/dev/null; then
    echo "[publish] pushed ${commit:0:7} (real_pnl.json)"; exit 0
  fi
  echo "[publish] push rejected (attempt $attempt) — refetching"
  git fetch -q origin main 2>/dev/null || exit 0
done
echo "[publish] could not publish this run — will retry next hour"
exit 0
