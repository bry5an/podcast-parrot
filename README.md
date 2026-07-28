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
./desktop/scripts/prepare_sidecars.sh   # builds the kotoba-backend sidecar and vendors whisper-cli
cd desktop
npx tauri dev                           # or: npx tauri build -b app dmg
```

`prepare_sidecars.sh` builds the frontend + PyInstaller sidecar (same as `backend/scripts/build_sidecar.sh`) and copies both `kotoba-backend` and a vendored `whisper-cli` into `desktop/src-tauri/binaries/` with the `-aarch64-apple-darwin` suffix Tauri's `externalBin` mechanism expects. Re-run it whenever backend or frontend source changes — `tauri build` does not do this itself, since there's no `beforeBuildCommand` wired up (keeping the Python build and the Rust build as separate, individually-runnable steps).

At launch the Rust shell picks a free port and a random per-launch auth token, spawns `kotoba-backend` with both, resolves the bundled `whisper-cli`'s path and passes it via `KOTOBA_WHISPER_BIN`, and polls `/api/health` before navigating the window from a local loading page to the live app. If the backend never becomes healthy (or exits at any point), the window shows an error page with the process's stderr tail instead of a blank rectangle. Closing the window or quitting checks `/api/activity` first and warns (native confirm dialog) if a download or transcription is in flight; either way, the backend is sent `SIGTERM` and given a grace period before `SIGKILL`.

**Known limitation:** the vendored `whisper-cli` still dynamically links `libggml`/`libggml-base` by absolute `/opt/homebrew` path and `libwhisper` via an `@loader_path`-relative rpath — none of that is bundled, so the packaged app only runs ASR on machines that already have `brew install whisper-cpp` at the standard prefix. Fully self-contained whisper-cli distribution (rewriting rpaths and vendoring its dylibs) is offline-packaging work that fits #27 better than this shell's launch/health/shutdown scope.

**Code signing:** Tauri ad-hoc signs the `.app` (`codesign -s -`) by default, which is mandatory for any binary to execute on Apple Silicon but is *not* a Developer ID signature. A `.dmg` built and shared this way still needs `xattr -dr com.apple.quarantine Kotoba.app` on the receiving machine before it will open.
