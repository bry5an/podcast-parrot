mod menu;
mod now_playing;
mod power;
mod sidecar;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri_plugin_window_state::Builder::new()
                .with_state_flags(tauri_plugin_window_state::StateFlags::POSITION)
                .build(),
        )
        .manage(power::WakeLock::new())
        .invoke_handler(tauri::generate_handler![
            power::begin_playback_wake_lock,
            power::end_playback_wake_lock,
            now_playing::update_now_playing,
            now_playing::clear_now_playing,
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            app.set_menu(menu::build(app.handle())?)?;
            app.manage(now_playing::register_remote_commands(app.handle()));
            sidecar::launch(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    sidecar::handle_close_requested(window.app_handle().clone(), api.clone());
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building the Ausculto desktop shell")
        .run(|app_handle, event| match event {
            tauri::RunEvent::ExitRequested { api, .. } => {
                sidecar::handle_exit_requested(app_handle.clone(), api.clone());
            }
            tauri::RunEvent::Exit => {
                app_handle.state::<power::WakeLock>().release();
            }
            _ => {}
        });
}
