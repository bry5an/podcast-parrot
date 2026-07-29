#!/usr/bin/env bash
# Builds the two externalBin sidecars Tauri expects at
# desktop/src-tauri/binaries/<name>-aarch64-apple-darwin:
#   - kotoba-backend: PyInstaller one-dir build via backend/scripts/build_sidecar.sh
#   - whisper-cli: built from whisper.cpp source, statically (see #62) —
#     cached under .cache/whisper-cpp/ so re-running this script only
#     re-links unless the pinned ref changes
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

# whisper-cli, built from source instead of vendored from Homebrew (#62):
# Homebrew's binary dlopens ggml backend plugins from a hardcoded compiled-in
# path *before* ever consulting @executable_path, so a bundled copy of
# libggml-base/libomp sitting alongside it loads as a second, distinct image
# with its own globals — two OpenMP runtimes stepping on each other's TLS
# segfaulted on every single transcription. Building statically removes the
# whole bug class rather than working around it:
#   -DGGML_BACKEND_DL=OFF   no dlopen plugin scan, so there's nothing to load twice
#   -DGGML_OPENMP=OFF       no second OpenMP runtime to collide with Homebrew's
#   -DBUILD_SHARED_LIBS=OFF + -DGGML_METAL_EMBED_LIBRARY=ON
#                           one self-contained executable, no dylibs to bundle
#                           at all (dylibbundler is gone)
#   -DGGML_NATIVE=OFF       load-bearing: without it cmake compiles -mcpu=native,
#                           and a binary built on an M4 CI runner would fault on
#                           an M1 user's machine
whisper_cpp_ref="v1.9.1"
cache_dir="$repo_root/.cache/whisper-cpp"
src_dir="$cache_dir/src"
build_dir="$cache_dir/build"

echo "==> Fetching whisper.cpp $whisper_cpp_ref"
if [ ! -d "$src_dir/.git" ] || [ "$(git -C "$src_dir" describe --tags 2>/dev/null)" != "$whisper_cpp_ref" ]; then
  rm -rf "$src_dir" "$build_dir"
  git clone --depth 1 --branch "$whisper_cpp_ref" https://github.com/ggml-org/whisper.cpp.git "$src_dir"
fi

echo "==> Building whisper-cli statically"
if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake not found — install with 'brew install cmake'" >&2
  exit 1
fi
cmake -B "$build_dir" -S "$src_dir" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DGGML_BACKEND_DL=OFF \
  -DGGML_OPENMP=OFF \
  -DGGML_METAL_EMBED_LIBRARY=ON \
  -DGGML_NATIVE=OFF
cmake --build "$build_dir" --config Release --target whisper-cli -j"$(sysctl -n hw.ncpu)"

cp "$build_dir/bin/whisper-cli" "$binaries_dir/whisper-cli-aarch64-apple-darwin"
chmod +x "$binaries_dir/whisper-cli-aarch64-apple-darwin"

echo "==> Sidecars staged at $binaries_dir"
ls -la "$binaries_dir"
