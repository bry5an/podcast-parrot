# podcast-parrot

## Backend dev server

```
cd backend
uv run uvicorn app.main:app --reload --port 8420
```

## ASR (whisper.cpp)

The ASR fallback shells out to `whisper-cli` from [whisper.cpp](https://github.com/ggml-org/whisper.cpp). For local dev:

```
brew install whisper-cpp
export KOTOBA_WHISPER_BIN=$(brew --prefix)/bin/whisper-cli
curl -L -o ggml-base.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
export KOTOBA_WHISPER_MODEL=$PWD/ggml-base.bin
```

Without those overrides, the binary resolves to `backend/bin/whisper-cli` (gitignored — a packaging step vendors it there) and the model to `<Application Support>/Kotoba/models/ggml-base.bin` (see #23 for model management). `backend/app/ggml-silero-v5.1.2.bin` is a vendored [Silero VAD](https://huggingface.co/ggml-org/whisper-vad) model (MIT), small enough to commit directly.

## Packaged backend sidecar

```
cd backend
./scripts/build_sidecar.sh
```

Produces a one-dir PyInstaller bundle at `backend/dist/kotoba-backend/`, whose entrypoint binary — `kotoba-backend-aarch64-apple-darwin`, matching Tauri's `externalBin` target-triple naming — boots the whole app (API + built SPA) with no Python installed:

```
./dist/kotoba-backend/kotoba-backend-aarch64-apple-darwin --port 8420 --data-dir /tmp/kotoba-data --auth-token secret
```

`--data-dir` overrides `KOTOBA_DATA_DIR`; `--auth-token`, when set, is required (as an `x-kotoba-token` header) on every `/api/*` request except `/api/health` — the packaged app injects it into `index.html` at serve time (`window.KOTOBA_AUTH_TOKEN`) so the SPA can attach it automatically. Neither flag is required for local dev (`uv run uvicorn ...`), which never sets a token.

## Desktop app (Tauri)

```
brew install cmake                      # one-time, used to build whisper-cli from source
./desktop/scripts/prepare_sidecars.sh   # builds the kotoba-backend sidecar and whisper-cli
cd desktop
npx tauri dev                           # or: npx tauri build -b app dmg
```

`prepare_sidecars.sh` builds the frontend + PyInstaller sidecar (same as `backend/scripts/build_sidecar.sh`) and stages both `kotoba-backend` and `whisper-cli` into `desktop/src-tauri/binaries/` with the `-aarch64-apple-darwin` suffix Tauri's `externalBin` mechanism expects. Re-run it whenever backend or frontend source changes — `tauri build` does not do this itself, since there's no `beforeBuildCommand` wired up (keeping the Python build and the Rust build as separate, individually-runnable steps).

At launch the Rust shell picks a free port and a random per-launch auth token, spawns `kotoba-backend` with both, resolves the bundled `whisper-cli`'s path and passes it via `KOTOBA_WHISPER_BIN`, and polls `/api/health` before navigating the window from a local loading page to the live app. If the backend never becomes healthy (or exits at any point), the window shows an error page with the process's stderr tail instead of a blank rectangle. Closing the window or quitting checks `/api/activity` first and warns (native confirm dialog) if a download or transcription is in flight; either way, the backend is sent `SIGTERM` and given a grace period before `SIGKILL`.

**whisper-cli is built from source, statically (#62):** vendoring Homebrew's `whisper-cli` bundled a second copy of `libggml-base`/`libomp` alongside Homebrew's own, and ggml's dlopen plugin scan loaded both into one process — two OpenMP runtimes stepping on each other's thread-local state segfaulted on every transcription. `prepare_sidecars.sh` instead clones `ggml-org/whisper.cpp` at a pinned tag into `.cache/whisper-cpp/` and builds it with `-DBUILD_SHARED_LIBS=OFF -DGGML_BACKEND_DL=OFF -DGGML_OPENMP=OFF -DGGML_METAL_EMBED_LIBRARY=ON -DGGML_NATIVE=OFF`: no dlopen plugin scan and no second OpenMP runtime make the whole bug class structurally impossible, and the resulting binary is a single self-contained executable (`otool -L` shows only system frameworks) with nothing left to bundle or rpath-rewrite. `-DGGML_NATIVE=OFF` is load-bearing — without it cmake compiles `-mcpu=native`, and a binary built on one Apple Silicon generation would fault on another.

**Code signing:** Tauri ad-hoc signs the `.app` (`codesign -s -`) by default, which is mandatory for any binary to execute on Apple Silicon but is *not* a Developer ID signature. A `.dmg` built and shared this way still needs `xattr -dr com.apple.quarantine Kotoba.app` on the receiving machine before it will open.
