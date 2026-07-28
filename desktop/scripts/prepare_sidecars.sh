#!/usr/bin/env bash
# Builds the two externalBin sidecars Tauri expects at
# desktop/src-tauri/binaries/<name>-aarch64-apple-darwin:
#   - kotoba-backend: PyInstaller one-dir build via backend/scripts/build_sidecar.sh
#   - whisper-cli: vendored from the Homebrew whisper-cpp install (see README's
#     "ASR (whisper.cpp)" section) since we don't build it ourselves
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
desktop_dir="$(dirname "$script_dir")"
repo_root="$(dirname "$desktop_dir")"
binaries_dir="$desktop_dir/src-tauri/binaries"

mkdir -p "$binaries_dir"

echo "==> Building kotoba-backend sidecar"
"$repo_root/backend/scripts/build_sidecar.sh"
cp "$repo_root/backend/dist/kotoba-backend/kotoba-backend-aarch64-apple-darwin" \
  "$binaries_dir/kotoba-backend-aarch64-apple-darwin"
chmod +x "$binaries_dir/kotoba-backend-aarch64-apple-darwin"

# NOTE: this copies the bare whisper-cli executable only. It dynamically links
# libggml/libggml-base by absolute /opt/homebrew path and libwhisper via an
# @loader_path-relative rpath, none of which are vendored here — so the
# resulting bundle only runs on machines with `brew install whisper-cpp`
# already present at the standard prefix. Fully self-contained (rpath-rewritten
# + bundled dylibs) distribution is offline/native-packaging work for #27, not
# this issue's launch/health/shutdown scope.
echo "==> Vendoring whisper-cli"
whisper_cli="${KOTOBA_WHISPER_CLI:-$(brew --prefix)/bin/whisper-cli}"
if [ ! -x "$whisper_cli" ]; then
  echo "whisper-cli not found at $whisper_cli — install with 'brew install whisper-cpp' or set KOTOBA_WHISPER_CLI" >&2
  exit 1
fi
cp -L "$whisper_cli" "$binaries_dir/whisper-cli-aarch64-apple-darwin"
chmod +x "$binaries_dir/whisper-cli-aarch64-apple-darwin"

echo "==> Sidecars staged at $binaries_dir"
ls -la "$binaries_dir"
