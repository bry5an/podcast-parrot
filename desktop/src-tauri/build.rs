use std::fs;
use std::path::{Path, PathBuf};

fn main() {
    tauri_build::build();
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
        let file_type = entry.file_type().expect("failed to read entry file type");
        if file_type.is_dir() {
            copy_dir_recursive(&entry.path(), &dest_path);
        } else {
            fs::copy(entry.path(), &dest_path).expect("failed to copy _internal file");
        }
    }
}
