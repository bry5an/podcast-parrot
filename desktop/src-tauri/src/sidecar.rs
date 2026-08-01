use std::collections::VecDeque;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use rand::RngCore;
use tauri::{AppHandle, CloseRequestApi, ExitRequestApi, Manager, Url};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const HEALTH_TIMEOUT: Duration = Duration::from_secs(30);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(250);
const REQUEST_TIMEOUT: Duration = Duration::from_secs(2);
const SIGTERM_GRACE_PERIOD: Duration = Duration::from_secs(5);
const STDERR_TAIL_LINES: usize = 200;

/// Shared state for the backend sidecar's whole lifetime. `startup_decided`
/// arbitrates the one-time race between "became healthy", "timed out" and
/// "exited before either" — whichever happens first wins and the others
/// become no-ops. `shutting_down` is separate: it only means *we* killed the
/// child on purpose, so its normal exit shouldn't be reported as a crash.
pub struct SidecarState {
    child: Mutex<Option<CommandChild>>,
    stderr_tail: Mutex<VecDeque<String>>,
    port: u16,
    token: String,
    startup_decided: AtomicBool,
    shutting_down: AtomicBool,
}

impl SidecarState {
    fn push_stderr(&self, line: String) {
        let mut tail = self.stderr_tail.lock().unwrap();
        if tail.len() >= STDERR_TAIL_LINES {
            tail.pop_front();
        }
        tail.push_back(line);
    }

    fn stderr_tail_text(&self) -> String {
        self.stderr_tail
            .lock()
            .unwrap()
            .iter()
            .cloned()
            .collect::<Vec<_>>()
            .join("\n")
    }
}

/// Launches the kotoba-backend sidecar and starts polling it for health.
/// Called once from `setup()`; everything past this point runs on background
/// threads/tasks and reports back to the main window via `navigate()`.
pub fn launch(app: AppHandle) {
    let port = pick_free_port();
    let token = generate_token();
    let whisper_cli = whisper_cli_path();

    log::info!("starting kotoba-backend sidecar on 127.0.0.1:{port}");

    let sidecar_command = match app.shell().sidecar("kotoba-backend") {
        Ok(cmd) => cmd,
        Err(err) => {
            show_error_window(&app, "Failed to resolve the backend sidecar", err.to_string());
            return;
        }
    };

    let sidecar_command = sidecar_command
        .args(["--port", &port.to_string(), "--auth-token", &token])
        .env("KOTOBA_WHISPER_BIN", &whisper_cli);

    let spawned = sidecar_command.spawn();

    let (rx, child) = match spawned {
        Ok(pair) => pair,
        Err(err) => {
            show_error_window(&app, "Failed to launch the backend process", err.to_string());
            return;
        }
    };

    let state = Arc::new(SidecarState {
        child: Mutex::new(Some(child)),
        stderr_tail: Mutex::new(VecDeque::new()),
        port,
        token,
        startup_decided: AtomicBool::new(false),
        shutting_down: AtomicBool::new(false),
    });
    app.manage(state.clone());

    spawn_event_reader(app.clone(), state.clone(), rx);
    spawn_health_poll(app, state);
}

fn spawn_event_reader(
    app: AppHandle,
    state: Arc<SidecarState>,
    mut rx: tauri::async_runtime::Receiver<CommandEvent>,
) {
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stderr(bytes) => {
                    let line = String::from_utf8_lossy(&bytes).trim_end().to_string();
                    log::warn!("[kotoba-backend] {line}");
                    state.push_stderr(line);
                }
                CommandEvent::Stdout(bytes) => {
                    log::info!("[kotoba-backend] {}", String::from_utf8_lossy(&bytes).trim_end());
                }
                CommandEvent::Error(err) => {
                    log::error!("kotoba-backend command error: {err}");
                }
                CommandEvent::Terminated(payload) => {
                    if state.shutting_down.load(Ordering::SeqCst) {
                        log::info!("kotoba-backend exited during shutdown (code {:?})", payload.code);
                        return;
                    }
                    let already_started = state.startup_decided.swap(true, Ordering::SeqCst);
                    let code = payload
                        .code
                        .map(|c| c.to_string())
                        .unwrap_or_else(|| "unknown".to_string());
                    let message = if already_started {
                        format!("The backend process exited unexpectedly (exit code {code}).")
                    } else {
                        format!("The backend process exited before it became healthy (exit code {code}).")
                    };
                    show_error_window(&app, &message, state.stderr_tail_text());
                    return;
                }
                _ => {}
            }
        }
    });
}

fn spawn_health_poll(app: AppHandle, state: Arc<SidecarState>) {
    std::thread::spawn(move || {
        let deadline = Instant::now() + HEALTH_TIMEOUT;
        loop {
            if state.startup_decided.load(Ordering::SeqCst) {
                return;
            }

            if let Ok((200, _)) = http_get(state.port, "/api/health", &state.token, REQUEST_TIMEOUT) {
                if state.startup_decided.swap(true, Ordering::SeqCst) {
                    return; // decided elsewhere first (e.g. a crash right at the finish line)
                }
                log::info!("kotoba-backend is healthy, navigating to the live app");
                let url = Url::parse(&format!("http://127.0.0.1:{}/", state.port)).expect("valid url");
                navigate_main_window(&app, url);
                return;
            }

            if Instant::now() >= deadline {
                if state.startup_decided.swap(true, Ordering::SeqCst) {
                    return;
                }
                terminate_child(&state); // hung — not making progress, don't leave it running
                show_error_window(
                    &app,
                    "Timed out waiting for the backend to become healthy",
                    state.stderr_tail_text(),
                );
                return;
            }

            std::thread::sleep(HEALTH_POLL_INTERVAL);
        }
    });
}

/// Handles the main window's close button. Shared with `handle_exit_requested`
/// below since this app has a single window and closing it should shut
/// everything down the same way quitting does.
pub fn handle_close_requested(app: AppHandle, api: CloseRequestApi) {
    let state = app.state::<Arc<SidecarState>>().inner().clone();
    if state.shutting_down.load(Ordering::SeqCst) {
        return; // already on our way out; let this one through
    }
    api.prevent_close();
    begin_shutdown(app, state);
}

/// Handles Cmd-Q / dock quit / `AppHandle::exit`.
pub fn handle_exit_requested(app: AppHandle, api: ExitRequestApi) {
    let state = app.state::<Arc<SidecarState>>().inner().clone();
    if state.shutting_down.load(Ordering::SeqCst) {
        return;
    }
    api.prevent_exit();
    begin_shutdown(app, state);
}

fn begin_shutdown(app: AppHandle, state: Arc<SidecarState>) {
    std::thread::spawn(move || {
        if activity_in_progress(&state)
            && !app
                .dialog()
                .message("A download or transcription is still in progress. Quitting now will stop it.")
                .title("Quit Ausculto?")
                .kind(MessageDialogKind::Warning)
                .buttons(MessageDialogButtons::OkCancelCustom(
                    "Quit Anyway".to_string(),
                    "Cancel".to_string(),
                ))
                .blocking_show()
        {
            return; // user chose not to quit yet
        }

        state.shutting_down.store(true, Ordering::SeqCst);
        terminate_child(&state);
        app.exit(0);
    });
}

fn activity_in_progress(state: &SidecarState) -> bool {
    match http_get(state.port, "/api/activity", &state.token, REQUEST_TIMEOUT) {
        Ok((200, body)) => serde_json::from_slice::<serde_json::Value>(&body)
            .ok()
            .and_then(|v| v.get("active").and_then(|a| a.as_bool()))
            .unwrap_or(false),
        // If the backend is unreachable there's nothing in flight to warn about.
        _ => false,
    }
}

/// SIGTERM first, escalating to the shell plugin's (SIGKILL) `kill()` if the
/// process hasn't exited after a grace period — so a mid-write download or
/// ffmpeg/whisper-cli child gets a chance to unwind before being cut off.
fn terminate_child(state: &SidecarState) {
    let Some(child) = state.child.lock().unwrap().take() else {
        return;
    };
    let pid = child.pid() as i32;

    unsafe {
        libc::kill(pid, libc::SIGTERM);
    }

    if wait_for_exit_or_deadline(pid, Instant::now() + SIGTERM_GRACE_PERIOD) {
        return;
    }

    let _ = child.kill();
}

/// Polls `kill(pid, 0)` (checks whether the process still exists; sends no
/// actual signal) until it reports the process gone or `deadline` passes.
/// Returns whether the process exited before the deadline.
fn wait_for_exit_or_deadline(pid: i32, deadline: Instant) -> bool {
    while Instant::now() < deadline {
        let still_alive = unsafe { libc::kill(pid, 0) == 0 };
        if !still_alive {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    false
}

fn show_error_window(app: &AppHandle, message: &str, detail: String) {
    log::error!("{message}\n{detail}");
    let mut url = Url::parse("tauri://localhost/index.html").expect("valid url");
    url.query_pairs_mut()
        .append_pair("error", "1")
        .append_pair("message", message)
        .append_pair("detail", &detail);
    navigate_main_window(app, url);
}

fn navigate_main_window(app: &AppHandle, url: Url) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    if let Err(err) = window.navigate(url) {
        log::error!("failed to navigate main window: {err}");
    }
    let _ = window.show();
    let _ = window.set_focus();
}

/// Binds an ephemeral port, reads back what the OS assigned, then releases it
/// immediately so the sidecar can bind the same number. A launch-to-launch
/// TOCTOU race is possible in theory but not worth guarding against in
/// practice for a single-user local app.
fn pick_free_port() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("failed to bind an ephemeral port");
    listener
        .local_addr()
        .expect("bound listener has a local address")
        .port()
}

fn generate_token() -> String {
    let mut bytes = [0u8; 24];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// whisper-cli is bundled as an externalBin sidecar alongside kotoba-backend
/// (same directory as the running Tauri executable in both `tauri dev` and
/// the packaged .app), but it's invoked by the *Python* process via
/// `KOTOBA_WHISPER_BIN`, not spawned by Rust — so we only need its path.
fn whisper_cli_path() -> PathBuf {
    std::env::current_exe()
        .expect("failed to resolve the running executable's path")
        .parent()
        .expect("executable path has no parent directory")
        .join("whisper-cli")
}

fn http_get(port: u16, path: &str, token: &str, timeout: Duration) -> std::io::Result<(u16, Vec<u8>)> {
    let addr = format!("127.0.0.1:{port}")
        .parse()
        .expect("127.0.0.1 with a valid port always parses");
    let mut stream = TcpStream::connect_timeout(&addr, timeout)?;
    stream.set_read_timeout(Some(timeout))?;
    stream.set_write_timeout(Some(timeout))?;

    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nx-kotoba-token: {token}\r\nConnection: close\r\n\r\n"
    );
    stream.write_all(request.as_bytes())?;

    let mut response = Vec::new();
    stream.read_to_end(&mut response)?;

    const SEP: &[u8; 4] = b"\r\n\r\n";
    let header_end = response
        .windows(SEP.len())
        .position(|w| w == SEP)
        .unwrap_or(response.len());
    let status = String::from_utf8_lossy(&response[..header_end])
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse().ok())
        .unwrap_or(0);
    let body_start = (header_end + SEP.len()).min(response.len());

    Ok((status, response[body_start..].to_vec()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::BufRead;

    #[test]
    fn pick_free_port_returns_a_bindable_port() {
        let port = pick_free_port();
        assert_ne!(port, 0);
        // The port must actually be free again immediately after picking it.
        assert!(TcpListener::bind(("127.0.0.1", port)).is_ok());
    }

    #[test]
    fn generate_token_is_random_and_hex() {
        let a = generate_token();
        let b = generate_token();
        assert_eq!(a.len(), 48);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b);
    }

    #[test]
    fn wait_for_exit_or_deadline_detects_a_terminated_process() {
        // A signaled child stays visible to kill(pid, 0) as a zombie until
        // something reaps it via wait() — exactly what the shell plugin's own
        // spawn() does concurrently in production, so this test does the same
        // rather than asserting on an artificially unreaped zombie.
        let mut child = std::process::Command::new("sleep").arg("30").spawn().unwrap();
        let pid = child.id() as i32;
        std::thread::spawn(move || {
            let _ = child.wait();
        });
        unsafe {
            libc::kill(pid, libc::SIGTERM);
        }
        assert!(wait_for_exit_or_deadline(pid, Instant::now() + Duration::from_secs(5)));
    }

    #[test]
    fn wait_for_exit_or_deadline_times_out_on_a_live_process() {
        let mut child = std::process::Command::new("sleep").arg("30").spawn().unwrap();
        let pid = child.id() as i32;
        assert!(!wait_for_exit_or_deadline(pid, Instant::now() + Duration::from_millis(200)));
        let _ = child.kill();
        let _ = child.wait();
    }

    /// Spawns a minimal one-shot HTTP server on an ephemeral port so `http_get`
    /// can be exercised against a real socket instead of just eyeballing the
    /// hand-rolled request/response parsing.
    fn serve_once(response: &'static str) -> u16 {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut reader = std::io::BufReader::new(&stream);
                let mut request_line = String::new();
                let _ = reader.read_line(&mut request_line);
                // Drain headers so the client's write() doesn't block on us.
                loop {
                    let mut line = String::new();
                    if reader.read_line(&mut line).unwrap_or(0) == 0 || line == "\r\n" {
                        break;
                    }
                }
                let _ = stream.write_all(response.as_bytes());
            }
        });
        port
    }

    #[test]
    fn http_get_parses_status_and_body() {
        let port = serve_once("HTTP/1.1 200 OK\r\nContent-Length: 15\r\n\r\n{\"status\":\"ok\"}");
        let (status, body) = http_get(port, "/api/health", "tok", Duration::from_secs(2)).unwrap();
        assert_eq!(status, 200);
        assert_eq!(body, b"{\"status\":\"ok\"}");
    }

    #[test]
    fn http_get_parses_non_200_status() {
        let port = serve_once("HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n");
        let (status, _) = http_get(port, "/api/activity", "wrong", Duration::from_secs(2)).unwrap();
        assert_eq!(status, 401);
    }
}
