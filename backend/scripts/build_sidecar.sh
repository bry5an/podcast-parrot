#!/usr/bin/env bash
# Builds the kotoba-backend PyInstaller sidecar: frontend assets first (so
# frontend/dist is fresh for bundling), then the one-dir PyInstaller build.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend_dir="$(dirname "$script_dir")"
repo_root="$(dirname "$backend_dir")"

echo "==> Building frontend"
(cd "$repo_root/frontend" && npm run build)

echo "==> Building backend sidecar with PyInstaller"
(cd "$backend_dir" && uv run pyinstaller kotoba-backend.spec --noconfirm)

bundle_dir="$backend_dir/dist/kotoba-backend"
echo "==> Bundle built at $bundle_dir"
du -sh "$bundle_dir"
