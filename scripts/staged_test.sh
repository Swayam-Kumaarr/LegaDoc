#!/usr/bin/env bash
# Staged, memory-bounded end-to-end test run for machines that cannot hold the
# whole stack in RAM at once (8 GB laptops, or a Docker VM shared with other
# projects' containers).
#
# Each stage starts only the containers it needs, runs real HTTP flows against
# the API (scripts/e2e_flows.py), records the peak memory of every container,
# then stops what it started. Nothing is lost between stages: Postgres, Redis
# (AOF) and MinIO keep their volumes, so jobs queued while a worker is down are
# picked up when that worker's stage starts — the same hand-off production
# relies on, exercised deliberately.
#
# Runs under its own compose project (legadoc_staged), so its volumes are
# separate from your dev database: no schema drift from old volumes, and no
# test data mixed into dev data. Containers belonging to other projects are
# never stopped.
#
# Usage:
#   scripts/staged_test.sh preflight        # memory + stale-image check, starts nothing
#   scripts/staged_test.sh build <service>  # rebuild one image at a time (RAM-friendly)
#   scripts/staged_test.sh unit             # pytest inside the api image (SQLite, no services)
#   scripts/staged_test.sh core             # db+redis+minio+api: auth, RBAC, every case flow
#   scripts/staged_test.sh redaction        # + ai_parser_worker: FIR tagging, redaction contrast
#   scripts/staged_test.sh ocr              # upload via API, then OCR worker with the API stopped
#   scripts/staged_test.sh ocr-drain        # + ai_parser_worker: finishes what OCR queued
#   scripts/staged_test.sh chain            # + chain_worker: Track A hash writes
#   scripts/staged_test.sh web              # + web only: SPA and /api proxy
#   scripts/staged_test.sh all              # every stage above, in order
#   scripts/staged_test.sh stop             # stop everything in the test project
#   scripts/staged_test.sh reset --yes      # delete the TEST project's volumes (never dev data)
#
# Reports land in .staged-test/ (gitignored): results.json, mem-peaks.json.

set -uo pipefail
cd "$(dirname "$0")/.."

PROJECT=legadoc_staged
COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.yml -f docker-compose.test.yml)
STATE_DIR=.staged-test
CORE=(db redis minio api)
WORKERS=(ocr_worker ai_parser_worker chain_worker web)
API_URL=${API_URL:-http://127.0.0.1:8000}
mkdir -p "$STATE_DIR"

bold() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
warn() { printf '\033[33mWARN\033[0m %s\n' "$*"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------- memory ----

SAMPLER_PID=""

start_sampler() {
  local out="$STATE_DIR/mem-$1.log"
  : > "$out"
  (
    while :; do
      docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null >> "$out"
      sleep 2
    done
  ) &
  SAMPLER_PID=$!
}

stop_sampler() {
  local stage=$1
  [ -n "$SAMPLER_PID" ] && kill "$SAMPLER_PID" 2>/dev/null && wait "$SAMPLER_PID" 2>/dev/null
  SAMPLER_PID=""
  # One synchronous sample before parsing. A stage shorter than one sampling
  # round (docker stats itself takes ~2s) otherwise records nothing: the loop
  # is killed mid-sample and its orphaned write lands after the parse below.
  docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' 2>/dev/null >> "$STATE_DIR/mem-$stage.log"
  python3 - "$STATE_DIR/mem-$stage.log" "$STATE_DIR/mem-peaks.json" "$stage" "$PROJECT" <<'EOF'
import json, re, sys
log, peaks_path, stage, project = sys.argv[1:5]
unit = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
peak = {}
for line in open(log):
    parts = line.split()
    if len(parts) < 2 or not parts[0].startswith(project):
        continue
    m = re.match(r"([\d.]+)(B|KiB|MiB|GiB)", parts[1])
    if m:
        v = float(m.group(1)) * unit[m.group(2)]
        peak[parts[0]] = max(peak.get(parts[0], 0), v)
try:
    allp = json.load(open(peaks_path))
except Exception:
    allp = {}
allp[stage] = {k: round(v / 1024**2) for k, v in peak.items()}
json.dump(allp, open(peaks_path, "w"), indent=2)
if allp[stage]:
    print(f"\nPeak memory during '{stage}' (MiB):")
    for k, v in sorted(allp[stage].items(), key=lambda kv: -kv[1]):
        print(f"  {k:45} {v:>6}")
EOF
}

oom_snapshot() {
  for c in $("${COMPOSE[@]}" ps -a -q 2>/dev/null); do
    [ "$(docker inspect -f '{{.State.OOMKilled}}' "$c")" = "true" ] && docker inspect -f '{{.Name}}' "$c"
  done | sort
}

check_oom() {
  # Only kills from THIS stage count. A container OOM-killed earlier stays in
  # `ps -a` with OOMKilled still true, and used to fail every later stage too.
  local before=$1 any=0 name
  while read -r name; do
    [ -z "$name" ] && continue
    grep -qxF "$name" <<<"$before" && continue
    fail "$name was OOM-killed — raise its mem_limit or free VM memory"
    any=1
  done <<<"$(oom_snapshot)"
  return $any
}

# ------------------------------------------------------------- lifecycle ----

up() { "${COMPOSE[@]}" up -d --no-build "$@" >/dev/null || { fail "compose up $*"; exit 1; }; }

stop_services() { [ $# -gt 0 ] && "${COMPOSE[@]}" stop "$@" >/dev/null 2>&1; return 0; }

wait_api() {
  for _ in $(seq 1 60); do
    curl -fsS "$API_URL/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  fail "API never became healthy at $API_URL"; "${COMPOSE[@]}" logs --tail 40 api; exit 1
}

bootstrap_db() {
  # init_db only creates tables; seed_all has no runnable entrypoint on main,
  # so without this step no persona can log in at all.
  for _ in $(seq 1 15); do
    "${COMPOSE[@]}" exec -T api python -c "
from app.database import Base, engine, SessionLocal
from app import models  # noqa: F401
from app.seed_data import seed_all
Base.metadata.create_all(bind=engine)
db = SessionLocal(); seed_all(db); db.close()
print('schema created + personas seeded')" && return 0
    sleep 2
  done
  fail "DB bootstrap"; exit 1
}

flows() { python3 scripts/e2e_flows.py --api "$API_URL" --state "$STATE_DIR/state.json" "$@"; }

run_stage() {  # run_stage <name> <function>
  local name=$1; shift
  bold "Stage: $name"
  local oom_before; oom_before=$(oom_snapshot)
  start_sampler "$name"
  "$@"; local rc=$?
  stop_sampler "$name"
  check_oom "$oom_before" || rc=1
  return $rc
}

# ----------------------------------------------------------------- stages ---

preflight() {
  bold "Preflight"
  local total
  total=$(docker info --format '{{.MemTotal}}')
  printf 'Docker VM memory: %s MiB\n' $((total / 1024 / 1024))
  echo "Other running containers (left untouched — they share that memory):"
  docker ps --format '{{.Names}}' | grep -v "^${PROJECT}-" | while read -r n; do
    printf '  %-40s %s\n' "$n" "$(docker stats --no-stream --format '{{.MemUsage}}' "$n" | cut -d/ -f1)"
  done
  echo "Image freshness (image build time vs last commit touching what the image bakes in):"
  python3 - "$PROJECT" <<'EOF'
import subprocess, sys, datetime
project = sys.argv[1]
# Only sources COPY'd into the image count. api/app and web/src are
# bind-mounted by docker-compose.yml, so edits there never need a rebuild;
# the workers mount nothing, so any change to their code or api/app does.
srcs = {
    "api": ["api/requirements.txt", "api/Dockerfile"],
    "web": ["web/package.json", "web/Dockerfile", "web/index.html", "web/public"],
    "ocr_worker": ["workers/ocr_worker", "api/app"],
    "ai_parser_worker": ["workers/ai_parser_worker", "api/app"],
    "chain_worker": ["workers/chain_worker", "api/app"],
}
for svc, paths in srcs.items():
    img = f"{project}-{svc}"
    r = subprocess.run(["docker", "image", "inspect", img, "--format", "{{.Created}}"], capture_output=True, text=True)
    if r.returncode:
        print(f"  {svc:18} NOT BUILT  -> scripts/staged_test.sh build {svc}")
        continue
    built = datetime.datetime.fromisoformat(r.stdout.strip()[:19]).replace(tzinfo=datetime.timezone.utc).timestamp()
    commit = int(subprocess.run(["git", "log", "-1", "--format=%ct", "--", *paths], capture_output=True, text=True).stdout.strip() or 0)
    state = "ok" if built >= commit else "STALE      -> scripts/staged_test.sh build " + svc
    print(f"  {svc:18} {state}")
EOF
}

stage_build() {
  local svc=${1:?service name required}
  bold "Build: $svc (this project's containers stopped first to leave RAM for the build)"
  "${COMPOSE[@]}" stop >/dev/null 2>&1
  "${COMPOSE[@]}" build "$svc"
}

stage_unit() {
  "${COMPOSE[@]}" run --rm --no-deps -T api pytest -q -p no:cacheprovider
}

stage_core() {
  stop_services "${WORKERS[@]}"
  up "${CORE[@]}"; wait_api; bootstrap_db
  flows core
}

stage_redaction() {
  stop_services ocr_worker chain_worker web
  up "${CORE[@]}" ai_parser_worker; wait_api
  flows redaction
  local rc=$?
  stop_services ai_parser_worker
  return $rc
}

stage_ocr() {
  # Phase 1: queue a real scanned FIR through the API.
  stop_services ai_parser_worker chain_worker web
  up "${CORE[@]}"; wait_api
  # Both committed fixtures in workers/ocr_worker/test_firs are WebP (the .jpg
  # one included), and the upload allowlist has no image/webp — so convert one
  # to PNG, the format a scanner or phone export actually hands the officer.
  local sample="$STATE_DIR/haryana_fir.png"
  if [ -z "${OCR_SAMPLE:-}" ] && [ ! -s "$sample" ]; then
    sips -s format png workers/ocr_worker/test_firs/haryana_fir.jpg --out "$sample" >/dev/null 2>&1 \
      || python3 -c "from PIL import Image; Image.open('workers/ocr_worker/test_firs/haryana_fir.jpg').save('$sample')" 2>/dev/null \
      || { fail "could not convert the WebP fixture to PNG (needs macOS sips or Pillow) — set OCR_SAMPLE to a PNG/JPEG scan"; return 1; }
  fi
  flows ocr-upload || return 1

  # Phase 2: OCR with the API stopped too. OCR is the one module that does not
  # fit next to everything else, and the job is already safe in Redis. Its
  # output (Document.raw_text + a queued ai_parser job) waits in Postgres and
  # Redis for the ocr-drain stage.
  stop_services api
  up db redis minio ocr_worker
  local since rc=1 cid logs
  since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "Waiting for ocr_worker (first task loads the English + Hindi models; up to 15 min)..."
  local received finished queued
  for _ in $(seq 1 180); do
    logs=$("${COMPOSE[@]}" logs --since "$since" ocr_worker 2>&1)
    grep -qE "WorkerLostError|MemoryError" <<<"$logs" && break
    # Done only when the queue is empty AND every task the worker took has
    # finished. Stopping at the first "succeeded" line ended the stage after
    # an older queued job, before the scan itself had been processed.
    received=$(grep -cE "Task ocr_worker\.[a-z_]+\[[^]]*\] received" <<<"$logs")
    finished=$(grep -cE "Task ocr_worker\.[a-z_]+\[[^]]*\] (succeeded|raised|failed)" <<<"$logs")
    queued=$("${COMPOSE[@]}" exec -T redis redis-cli -n 0 llen ocr_worker 2>/dev/null | tr -dc '0-9')
    if [ "${received:-0}" -gt 0 ] && [ "$received" -eq "$finished" ] && [ "${queued:-1}" = "0" ]; then rc=0; break; fi
    cid=$("${COMPOSE[@]}" ps -q ocr_worker)
    [ -n "$cid" ] && [ "$(docker inspect -f '{{.State.Running}}' "$cid")" = "true" ] || break
    sleep 5
  done
  "${COMPOSE[@]}" logs --since "$since" ocr_worker 2>&1 | grep -E "succeeded|ERROR|WARNING|Killed|Initializing" | tail -15
  [ $rc -eq 0 ] || fail "ocr_worker did not report a finished task (see log lines above)"
  stop_services ocr_worker
  return $rc
}

stage_ocr_drain() {
  stop_services ocr_worker chain_worker web
  up "${CORE[@]}" ai_parser_worker; wait_api
  flows ocr-drain
  local rc=$?
  stop_services ai_parser_worker
  return $rc
}

stage_chain() {
  stop_services ocr_worker ai_parser_worker web
  docker network inspect fabric_test >/dev/null 2>&1 || docker network create fabric_test >/dev/null
  up "${CORE[@]}" chain_worker; wait_api
  flows chain
  local rc=$?
  stop_services chain_worker
  return $rc
}

stage_web() {
  stop_services ocr_worker ai_parser_worker chain_worker
  up "${CORE[@]}" web; wait_api
  for _ in $(seq 1 30); do curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1 && break; sleep 2; done
  flows web --web http://127.0.0.1:5173
}

case "${1:-}" in
  preflight) preflight ;;
  build)     stage_build "${2:-}" ;;
  unit)      run_stage unit stage_unit ;;
  core)      run_stage core stage_core ;;
  redaction) run_stage redaction stage_redaction ;;
  ocr)       run_stage ocr stage_ocr ;;
  ocr-drain) run_stage ocr-drain stage_ocr_drain ;;
  chain)     run_stage chain stage_chain ;;
  web)       run_stage web stage_web ;;
  all)
    preflight
    rc=0
    for s in unit core redaction ocr ocr-drain chain web; do
      "$0" "$s" || { rc=1; warn "stage $s failed — continuing so later stages still report"; }
    done
    "${COMPOSE[@]}" stop >/dev/null 2>&1
    bold "Summary: $STATE_DIR/results.json, $STATE_DIR/mem-peaks.json"
    exit $rc ;;
  stop)  "${COMPOSE[@]}" stop ;;
  reset)
    [ "${2:-}" = "--yes" ] || { echo "This deletes the $PROJECT volumes (test data only). Re-run with: reset --yes"; exit 1; }
    "${COMPOSE[@]}" down -v && rm -f "$STATE_DIR"/state.json "$STATE_DIR"/results.json ;;
  *) sed -n '2,33p' "$0"; exit 1 ;;
esac
