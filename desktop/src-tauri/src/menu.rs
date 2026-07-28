use tauri::menu::{AboutMetadataBuilder, Menu, MenuBuilder, SubmenuBuilder};
use tauri::AppHandle;

/// Builds the native macOS menu bar: an app submenu (About/Hide/Quit, named
/// after the app rather than the binary), a standard Edit submenu (without
/// which Cmd-C/Cmd-V don't reach text inputs in the webview), and a Window
/// submenu (Minimize/Zoom/Close). Tauri's implicit default menu has none of
/// this - see issue #27.
pub fn build(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let app_name = app.package_info().name.clone();

    let about_metadata = AboutMetadataBuilder::new()
        .name(Some(app_name.clone()))
        .version(Some(app.package_info().version.to_string()))
        .build();

    let app_menu = SubmenuBuilder::new(app, &app_name)
        .about(Some(about_metadata))
        .separator()
        .services()
        .separator()
        .hide()
        .hide_others()
        .show_all()
        .separator()
        .quit()
        .build()?;

    let edit_menu = SubmenuBuilder::new(app, "Edit")
        .undo()
        .redo()
        .separator()
        .cut()
        .copy()
        .paste()
        .select_all()
        .build()?;

    let window_menu = SubmenuBuilder::new(app, "Window")
        .minimize()
        .maximize()
        .separator()
        .close_window()
        .build()?;

    MenuBuilder::new(app)
        .items(&[&app_menu, &edit_menu, &window_menu])
        .build()
}
