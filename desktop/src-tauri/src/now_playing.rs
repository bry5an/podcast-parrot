use core::ptr::NonNull;

use block2::RcBlock;
use objc2::rc::Retained;
use objc2::runtime::AnyObject;
use objc2_foundation::{NSDictionary, NSNumber, NSString};
use objc2_media_player::{
    MPMediaItemPropertyArtist, MPMediaItemPropertyPlaybackDuration, MPMediaItemPropertyTitle,
    MPNowPlayingInfoCenter, MPNowPlayingInfoPropertyElapsedPlaybackTime,
    MPNowPlayingInfoPropertyPlaybackRate, MPNowPlayingPlaybackState, MPRemoteCommandCenter,
    MPRemoteCommandEvent, MPRemoteCommandHandlerStatus,
};
use tauri::{AppHandle, Emitter};

/// Keeps the `MPRemoteCommand` handler blocks alive for the app's lifetime.
/// `addTargetWithHandler:` retains its own copy on the Objective-C side, but
/// there's no reason to rely on that alone when we can just hold the Rust
/// side's reference too via `app.manage`.
pub struct RemoteCommandHandlers {
    _play: RcBlock<dyn Fn(NonNull<MPRemoteCommandEvent>) -> MPRemoteCommandHandlerStatus>,
    _pause: RcBlock<dyn Fn(NonNull<MPRemoteCommandEvent>) -> MPRemoteCommandHandlerStatus>,
    _toggle: RcBlock<dyn Fn(NonNull<MPRemoteCommandEvent>) -> MPRemoteCommandHandlerStatus>,
}

// SAFETY: these blocks are never invoked from Rust and are only ever held so
// `app.manage` keeps them alive; the only operation performed on them from
// Rust is `Block_release` on drop, which the Objective-C block runtime's ABI
// guarantees is safe to call from any thread.
unsafe impl Send for RemoteCommandHandlers {}
unsafe impl Sync for RemoteCommandHandlers {}

/// Registers macOS media-key / Control Center remote commands once at
/// startup. Presses are forwarded to the frontend as `media-command` events
/// rather than driving playback from Rust, so the `<audio>` element in
/// Player.tsx stays the single source of truth for playback state.
pub fn register_remote_commands(app: &AppHandle) -> RemoteCommandHandlers {
    let center = unsafe { MPRemoteCommandCenter::sharedCommandCenter() };

    let make_handler = |command: &'static str| {
        let app = app.clone();
        RcBlock::new(move |_event: NonNull<MPRemoteCommandEvent>| -> MPRemoteCommandHandlerStatus {
            let _ = app.emit("media-command", command);
            MPRemoteCommandHandlerStatus::Success
        })
    };

    let play = make_handler("play");
    let pause = make_handler("pause");
    let toggle = make_handler("toggle");

    unsafe {
        center.playCommand().addTargetWithHandler(&play);
        center.pauseCommand().addTargetWithHandler(&pause);
        center.togglePlayPauseCommand().addTargetWithHandler(&toggle);
    }

    RemoteCommandHandlers {
        _play: play,
        _pause: pause,
        _toggle: toggle,
    }
}

/// Publishes the current episode's Now Playing metadata and playback state.
/// Only needs to be called on discontinuities (track load, play, pause,
/// seek, speed change) - `MPNowPlayingInfoCenter` interpolates elapsed time
/// on its own using `rate` between updates, per Apple's guidance.
#[tauri::command]
pub fn update_now_playing(title: String, artist: String, duration: f64, elapsed: f64, rate: f64) {
    let keys: [&NSString; 5] = unsafe {
        [
            MPMediaItemPropertyTitle,
            MPMediaItemPropertyArtist,
            MPMediaItemPropertyPlaybackDuration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime,
            MPNowPlayingInfoPropertyPlaybackRate,
        ]
    };
    let values: [Retained<AnyObject>; 5] = [
        NSString::from_str(&title).into(),
        NSString::from_str(&artist).into(),
        NSNumber::new_f64(duration).into(),
        NSNumber::new_f64(elapsed).into(),
        NSNumber::new_f64(rate).into(),
    ];
    let info: Retained<NSDictionary<NSString, AnyObject>> =
        NSDictionary::from_retained_objects(&keys, &values);

    let center = unsafe { MPNowPlayingInfoCenter::defaultCenter() };
    unsafe {
        center.setNowPlayingInfo(Some(&info));
        center.setPlaybackState(if rate > 0.0 {
            MPNowPlayingPlaybackState::Playing
        } else {
            MPNowPlayingPlaybackState::Paused
        });
    }
}

/// Clears Now Playing info when the player view unmounts (e.g. navigating
/// back to the library), so Control Center doesn't keep showing a track
/// that's no longer loaded.
#[tauri::command]
pub fn clear_now_playing() {
    let center = unsafe { MPNowPlayingInfoCenter::defaultCenter() };
    unsafe {
        center.setNowPlayingInfo(None);
        center.setPlaybackState(MPNowPlayingPlaybackState::Stopped);
    }
}
