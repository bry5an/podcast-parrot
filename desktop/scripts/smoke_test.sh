#!/usr/bin/env bash
# Smoke-tests a built Ausculto.app by launching its embedded kotoba-backend
# binary directly with --port/--data-dir (bypassing the Tauri shell/GUI,
# which CI runners can't drive) and asserting /api/health responds. This is
# what actually catches a broken kotoba-backend.spec / bundle.macOS.files
# mapping in CI instead of only surfacing when someone launches the packaged
# .app by hand (see the #26 "PyInstaller one-dir + real .app bundle" gotcha).
set -euo pipefail

app_path="${1:?usage: smoke_test.sh <path-to-Ausculto.app>}"
backend_bin="$app_path/Contents/MacOS/kotoba-backend"
port=18420

if [ ! -x "$backend_bin" ]; then
  echo "expected an executable at $backend_bin" >&2
  exit 1
fi

data_dir="$(mktemp -d)"
backend_pid=""
cleanup() {
  [ -n "$backend_pid" ] && kill "$backend_pid" 2>/dev/null || true
  rm -rf "$data_dir"
}
trap cleanup EXIT

"$backend_bin" --port "$port" --data-dir "$data_dir" &
backend_pid=$!

deadline=$((SECONDS + 30))
until curl -sf "http://127.0.0.1:$port/api/health" >/dev/null; do
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    echo "kotoba-backend exited before becoming healthy" >&2
    exit 1
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "timed out waiting for /api/health" >&2
    exit 1
  fi
  sleep 1
done

echo "kotoba-backend inside $app_path is healthy"
