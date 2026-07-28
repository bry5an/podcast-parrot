use std::fs;
use std::path::{Path, PathBuf};

fn main() {
    let attributes = tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "begin_playback_wake_lock",
            "end_playback_wake_lock",
            "update_now_playing",
            "clear_now_playing",
        ]),
    );
    tauri_build::try_build(attributes).expect("failed to run tauri-build");
    stage_internal_next_to_dev_binary();
}

/// `tauri_build::build()` copies the `kotoba-backend` externalBin into
/// `target/<profile>/` (suffix stripped) so `cargo tauri dev` and plain
/// `cargo build` can run it, but it only copies that one file — not the
/// PyInstaller one-dir build's `_internal/` sibling directory the bootloader
/// also needs. The packaged `.app` gets `_internal` staged separately via
/// `tauri.conf.json`'s `bundle.macOS.files`; this covers the unpackaged
/// `target/<profile>/` case those bundle-time resources never touch.
fn stage_internal_next_to_dev_binary() {
    let manifest_dir = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap());
    let internal_src = manifest_dir.join("../../backend/dist/kotoba-backend/_internal");
    if !internal_src.is_dir() {
        println!("cargo:warning=backend/dist/kotoba-backend/_internal not found — run desktop/scripts/prepare_sidecars.sh before `cargo tauri dev`");
        return;
    }

    // OUT_DIR is target/<profile>/build/<pkg>-<hash>/out; target/<profile> is
    // three levels up. Re-copied on every build.rs rerun, which tauri_build
    // already triggers whenever the sidecar binary in binaries/ changes (it
    // emits its own rerun-if-changed for that file), so re-running
    // prepare_sidecars.sh and rebuilding picks up a fresh _internal too.
    let out_dir = PathBuf::from(std::env::var("OUT_DIR").unwrap());
    let target_dir = out_dir
        .ancestors()
        .nth(3)
        .expect("OUT_DIR should be nested three levels under target/<profile>")
        .to_path_buf();

    let internal_dest = target_dir.join("_internal");
    let _ = fs::remove_dir_all(&internal_dest);
    copy_dir_recursive(&internal_src, &internal_dest);
}

fn copy_dir_recursive(src: &Path, dest: &Path) {
    fs::create_dir_all(dest).expect("failed to create _internal staging directory");
    for entry in fs::read_dir(src).expect("failed to read _internal source directory") {
        let entry = entry.expect("failed to read _internal directory entry");
        let dest_path = dest.join(entry.file_name());
        // `DirEntry::file_type()` doesn't follow symlinks, so it reports a
        // symlinked directory as neither dir nor file — some PyInstaller
        // hidden-import wheels (e.g. fugashi's vendored `.dylibs`) can bundle
        // one, and falling into the `fs::copy` branch below then panics with
        // "the source path is neither a regular file nor a symlink to a
        // regular file" (reproduced and confirmed by this exact message from
        // a from-scratch macOS CI build). `fs::metadata` follows symlinks, so
        // it correctly recurses into a symlinked directory instead.
        let is_dir = fs::metadata(entry.path())
            .unwrap_or_else(|err| panic!("failed to stat {}: {err}", entry.path().display()))
            .is_dir();
        if is_dir {
            copy_dir_recursive(&entry.path(), &dest_path);
        } else {
            fs::copy(entry.path(), &dest_path)
                .unwrap_or_else(|err| panic!("failed to copy {}: {err}", entry.path().display()));
        }
    }
}
