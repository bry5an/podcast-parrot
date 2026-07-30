# Kotoba

Kotoba is a macOS app for learning a language from podcasts. It plays an episode alongside a synced, scrolling transcript, so you can follow along, tap any word for a definition, and save sentences you want to review later.

It ships with a curated directory of Japanese-learning podcasts, but you can add any podcast RSS feed or YouTube playlist as a source. Episodes that don't already publish a transcript are transcribed automatically on-device.

## Features

- **Synced transcript playback** — the transcript scrolls and highlights in time with the audio, for any episode in your library.
- **Automatic transcription** — episodes without a published transcript are transcribed locally using [whisper.cpp](https://github.com/ggml-org/whisper.cpp); no audio ever leaves your machine.
- **Furigana for Japanese text** — readings are shown above kanji so you can read along even before you know every character.
- **Tap-to-define** — click any word in the transcript to look up its definition (Jisho for Japanese, Wiktionary for English) without leaving the player.
- **Saved sentences** — save sentences you want to revisit and browse them later from one place, with a repeat toggle for focused listening practice.
- **Podcast directory + your own sources** — start from a built-in list of Japanese podcasts, or add any podcast RSS feed or YouTube playlist.
- **Profiles** — multiple people can use the same install, each with their own library and saved sentences.
- **Playback controls tuned for study** — adjustable speed, configurable seek step, and keyboard shortcuts you can remap in Settings.

## Requirements

- macOS on Apple Silicon
- Internet access to browse podcast directories, add feeds, and download episodes (transcription and playback work fully offline once an episode is downloaded and transcribed)

## Getting started

Kotoba doesn't have a signed, notarized release yet, so for now you'll build it from source. This takes a few minutes and only needs to be done once:

```
git clone https://github.com/bry5an/podcast-parrot.git
cd podcast-parrot
make install
make build
```

`make build` produces `Kotoba.app` and a `Kotoba.dmg` under `desktop/src-tauri/target/release/bundle/`. Open the `.dmg` and drag `Kotoba.app` to Applications.

Because the app is only ad-hoc signed (not signed with a paid Apple Developer ID), the first launch needs one extra step to clear the quarantine flag Gatekeeper adds to anything downloaded or built locally:

```
xattr -dr com.apple.quarantine /Applications/Kotoba.app
```

After that, launch Kotoba like any other app. On first run it'll ask you to pick a profile, walk you through setting up transcription, and let you add your first podcast.

## Documentation

Building from source, running the dev servers, and running the test suite are covered in [`docs/`](docs/):

- [`docs/development.md`](docs/development.md) — local dev setup, project layout, running the app during development
- [`docs/testing.md`](docs/testing.md) — running and writing tests, linting, CI
