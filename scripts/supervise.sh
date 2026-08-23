#!/usr/bin/env bash
# supervise.sh · 长任务监督器(OPERATIONS.md 纪律:任何 >10min 的任务必须经它)
# 用法: scripts/supervise.sh <任务名> <命令...>
# 行为: pipefail;失败自动重试 ≤5 次(退避);状态机写 out/<任务名>.status.json;
#       全程日志 out/<任务名>.log。断点续跑由被监督命令自身保证(如 pairs --llm-mid)。
set -o pipefail
NAME=$1; shift
mkdir -p out
STATUS="out/${NAME}.status.json"
LOG="out/${NAME}.log"
attempt=0
max=5
while [ "$attempt" -lt "$max" ]; do
  attempt=$((attempt + 1))
  printf '{"state":"running","attempt":%d,"ts":%s}\n' "$attempt" "$(date +%s)" > "$STATUS"
  echo "=== attempt $attempt $(date -Is) ===" >> "$LOG"
  if "$@" >> "$LOG" 2>&1; then
    printf '{"state":"ok","attempt":%d,"ts":%s}\n' "$attempt" "$(date +%s)" > "$STATUS"
    exit 0
  fi
  rc=$?
  echo "=== attempt $attempt failed rc=$rc $(date -Is) ===" >> "$LOG"
  sleep $((attempt * 30))
done
printf '{"state":"failed","attempt":%d,"ts":%s}\n' "$attempt" "$(date +%s)" > "$STATUS"
exit 1
