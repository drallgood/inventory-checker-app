#!/bin/bash
set -euo pipefail

FAMILIES=(iphone watch mac ipad airpods homepod avp)
PIDS=()

for family in "${FAMILIES[@]}"; do
    echo "[$(date +%H:%M:%S)] Starting ${family}..."
    python3 scrape_models.py --family "$family" --all-models > "scrape_${family}.log" 2>&1 &
    PIDS+=($!)
done

echo "All families launched (PIDs: ${PIDS[*]}). Waiting for completion..."
wait "${PIDS[@]}"
echo "[$(date +%H:%M:%S)] All families complete."