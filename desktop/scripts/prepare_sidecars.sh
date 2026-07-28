#!/usr/bin/env bash
# Builds the two externalBin sidecars Tauri expects at
# desktop/src-tauri/binaries/<name>-aarch64-apple-darwin:
#   - kotoba-backend: PyInstaller one-dir build via backend/scripts/build_sidecar.sh
#   - whisper-cli: vendored from the Homebrew whisper-cpp install (see README's
#     "ASR (whisper.cpp)" section) since we don't build it ourselves, made
#     self-contained (dylibs + ggml backend plugins rpath-rewritten into
#     binaries/libs/ via dylibbundler) so it doesn't depend on Homebrew at
#     runtime — requires `brew install dylibbundler`
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

echo "==> Vendoring whisper-cli"
whisper_cli="${KOTOBA_WHISPER_CLI:-$(brew --prefix)/bin/whisper-cli}"
if [ ! -x "$whisper_cli" ]; then
  echo "whisper-cli not found at $whisper_cli — install with 'brew install whisper-cpp' or set KOTOBA_WHISPER_CLI" >&2
  exit 1
fi
cp -L "$whisper_cli" "$binaries_dir/whisper-cli-aarch64-apple-darwin"
chmod +x "$binaries_dir/whisper-cli-aarch64-apple-darwin"

# whisper-cli dynamically links libwhisper/libggml/libggml-base (and,
# transitively, libomp) by absolute /opt/homebrew path or an @loader_path
# rpath that only resolves correctly sitting inside a Homebrew prefix — copied
# bare like above, it dyld-crashes anywhere else (#48). dylibbundler rewrites
# those load commands to @executable_path/libs/... and re-signs (ad-hoc).
echo "==> Bundling whisper-cli's dynamic libraries"
if ! command -v dylibbundler >/dev/null 2>&1; then
  echo "dylibbundler not found — install with 'brew install dylibbundler'" >&2
  exit 1
fi
whisper_cpp_prefix="$(brew --prefix whisper-cpp)"
ggml_prefix="$(brew --prefix ggml)"
libomp_prefix="$(brew --prefix libomp)"
libs_dir="$binaries_dir/libs"

dylibbundler -od -b \
  -x "$binaries_dir/whisper-cli-aarch64-apple-darwin" \
  -d "$libs_dir" \
  -p "@executable_path/libs/" \
  -s "$whisper_cpp_prefix/lib" -s "$ggml_prefix/lib" -s "$libomp_prefix/lib" \
  < /dev/null

# ggml's actual compute backends (CPU/BLAS/Metal) are a second, separate
# portability gap: they're loaded via dlopen from a *hardcoded* absolute
# Homebrew path baked into libggml-base at build time (confirmed via
# `strings`/sandbox-exec testing — overriding GGML_BACKEND_PATH doesn't stop
# it from also trying that hardcoded path), invisible to `otool -L` since
# it's runtime dlopen, not a linked dependency. Without vendoring these too,
# even the CPU backend wouldn't load on a machine without Homebrew's ggml —
# not just lost acceleration, but no working backend at all. Vendor all three
# Apple Silicon CPU variants (GGML_BACKEND_PATH only accepts a single file, so
# `desktop/src-tauri/src/sidecar.rs` picks the right one for the *running*
# machine at launch, not the machine this script happens to build on) plus
# BLAS/Metal, and dylibbundler-fix each one's own internal dependency on
# libggml-base the same way.
echo "==> Vendoring ggml backend plugins (CPU variants + BLAS + Metal)"
for plugin in libggml-cpu-apple_m1.so libggml-cpu-apple_m2_m3.so libggml-cpu-apple_m4.so libggml-blas.so libggml-metal.so; do
  src="$ggml_prefix/libexec/$plugin"
  if [ ! -f "$src" ]; then
    echo "expected ggml backend plugin not found at $src (ggml version/layout changed?)" >&2
    exit 1
  fi
  cp "$src" "$libs_dir/$plugin"
  dylibbundler -of -b \
    -x "$libs_dir/$plugin" \
    -d "$libs_dir" \
    -p "@executable_path/libs/" \
    -s "$whisper_cpp_prefix/lib" -s "$ggml_prefix/lib" -s "$libomp_prefix/lib" \
    < /dev/null
done

echo "==> Sidecars staged at $binaries_dir"
ls -la "$binaries_dir" "$libs_dir"
