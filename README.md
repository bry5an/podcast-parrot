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
