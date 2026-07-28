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
brew install dylibbundler               # one-time, used to make whisper-cli self-contained
./desktop/scripts/prepare_sidecars.sh   # builds the kotoba-backend sidecar and vendors whisper-cli
cd desktop
npx tauri dev                           # or: npx tauri build -b app dmg
```

`prepare_sidecars.sh` builds the frontend + PyInstaller sidecar (same as `backend/scripts/build_sidecar.sh`) and copies both `kotoba-backend` and a vendored `whisper-cli` into `desktop/src-tauri/binaries/` with the `-aarch64-apple-darwin` suffix Tauri's `externalBin` mechanism expects. Re-run it whenever backend or frontend source changes — `tauri build` does not do this itself, since there's no `beforeBuildCommand` wired up (keeping the Python build and the Rust build as separate, individually-runnable steps).

At launch the Rust shell picks a free port and a random per-launch auth token, spawns `kotoba-backend` with both, resolves the bundled `whisper-cli`'s path and passes it via `KOTOBA_WHISPER_BIN`, resolves the running machine's matching ggml CPU-backend plugin and passes it via `GGML_BACKEND_PATH`, and polls `/api/health` before navigating the window from a local loading page to the live app. If the backend never becomes healthy (or exits at any point), the window shows an error page with the process's stderr tail instead of a blank rectangle. Closing the window or quitting checks `/api/activity` first and warns (native confirm dialog) if a download or transcription is in flight; either way, the backend is sent `SIGTERM` and given a grace period before `SIGKILL`.

**whisper-cli portability:** the vendored `whisper-cli` is made self-contained by `prepare_sidecars.sh` via `dylibbundler`, which copies `libwhisper`/`libggml`/`libggml-base`/`libomp` into `desktop/src-tauri/binaries/libs/` and rewrites whisper-cli's load commands to `@executable_path/libs/...` (re-signed ad-hoc since rewriting invalidates the existing signature). ggml's CPU/BLAS/Metal compute backends are a second, separate mechanism — dlopen'd plugins, not linked dependencies — so all three Apple Silicon CPU variants plus BLAS/Metal are vendored the same way, and `sidecar.rs` picks the right CPU variant for the machine actually running the app via `GGML_BACKEND_PATH` at launch (that env var only accepts a single file, so the choice has to happen at runtime, not at packaging time).

**Code signing:** Tauri ad-hoc signs the `.app` (`codesign -s -`) by default, which is mandatory for any binary to execute on Apple Silicon but is *not* a Developer ID signature. A `.dmg` built and shared this way still needs `xattr -dr com.apple.quarantine Kotoba.app` on the receiving machine before it will open.
