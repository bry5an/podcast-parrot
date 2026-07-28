use std::process::{Child, Command};
use std::sync::Mutex;

/// Holds the `caffeinate` child process (if any) keeping the display and
/// system awake during playback. `-w <our pid>` is a crash safety net: if
/// this app is killed or crashes without running the normal shutdown path,
/// caffeinate notices its watched pid is gone and exits on its own instead
/// of leaking a wake lock forever.
pub struct WakeLock(Mutex<Option<Child>>);

impl WakeLock {
    pub fn new() -> Self {
        Self(Mutex::new(None))
    }

    fn release_locked(guard: &mut Option<Child>) {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    pub fn release(&self) {
        Self::release_locked(&mut self.0.lock().unwrap());
    }
}

#[tauri::command]
pub fn begin_playback_wake_lock(state: tauri::State<WakeLock>) -> Result<(), String> {
    let mut guard = state.0.lock().unwrap();
    if guard.is_some() {
        return Ok(());
    }
    let pid = std::process::id().to_string();
    let child = Command::new("/usr/bin/caffeinate")
        .args(["-d", "-i", "-s", "-w", &pid])
        .spawn()
        .map_err(|err| err.to_string())?;
    *guard = Some(child);
    Ok(())
}

#[tauri::command]
pub fn end_playback_wake_lock(state: tauri::State<WakeLock>) -> Result<(), String> {
    WakeLock::release_locked(&mut state.0.lock().unwrap());
    Ok(())
}
