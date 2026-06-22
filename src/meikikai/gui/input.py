# meikikai/gui/input.py
import ctypes
import logging
import subprocess
import threading
import time

import Quartz
from pynput import mouse

try:
    import ApplicationServices
except ImportError:
    ApplicationServices = Quartz

from meikikai.config.config import config

logger = logging.getLogger(__name__)

MEDIA_REMOTE_BUNDLE_PATH = "/System/Library/PrivateFrameworks/MediaRemote.framework"
MEDIA_REMOTE_FRAMEWORK_PATH = f"{MEDIA_REMOTE_BUNDLE_PATH}/MediaRemote"
MEDIA_REMOTE_OSASCRIPT_TIMEOUT_SECONDS = 0.35

MR_COMMAND_PLAY = 0
MR_COMMAND_PAUSE = 1
MACOS_KEYCODE_C = 8
MACOS_KEYCODE_J = 38
MACOS_KEYCODE_M = 46

_MEDIA_REMOTE_UNAVAILABLE = object()
_media_remote_framework = None
_media_remote_send_command = None

MEDIA_REMOTE_NOW_PLAYING_JXA = """
ObjC.import('Foundation');
function run() {
  const bundle = $.NSBundle.bundleWithPath('/System/Library/PrivateFrameworks/MediaRemote.framework');
  if (!bundle) return 'unknown';
  bundle.load;

  const requestClass = $.NSClassFromString('MRNowPlayingRequest');
  if (!requestClass) return 'unknown';

  const item = requestClass.localNowPlayingItem;
  if (!item) return 'unknown';

  const info = item.nowPlayingInfo;
  if (!info) return 'unknown';

  const rate = info.valueForKey('kMRMediaRemoteNowPlayingInfoPlaybackRate');
  if (rate === undefined || rate === null) return '0';

  const value = Number(rate.js);
  return isFinite(value) && value > 0 ? '1' : '0';
}
"""


def is_process_trusted_for_accessibility(prompt: bool = False) -> bool:
    """Return whether macOS allows this process to post synthetic input events."""
    try:
        trusted_with_options = getattr(ApplicationServices, 'AXIsProcessTrustedWithOptions', None)
        if trusted_with_options:
            prompt_key = getattr(ApplicationServices, 'kAXTrustedCheckOptionPrompt', 'AXTrustedCheckOptionPrompt')
            return bool(trusted_with_options({prompt_key: prompt}))

        trusted = getattr(ApplicationServices, 'AXIsProcessTrusted', None)
        if trusted:
            return bool(trusted())
    except Exception as e:
        logger.warning(f"Failed to check macOS Accessibility permission: {e}")

    return False


def request_accessibility_access() -> bool:
    """Ask macOS to prompt for Accessibility access if it is not already granted."""
    return is_process_trusted_for_accessibility(prompt=True)


def _load_media_remote_send_command():
    global _media_remote_framework, _media_remote_send_command

    if _media_remote_send_command is not None:
        return _media_remote_send_command
    if _media_remote_framework is _MEDIA_REMOTE_UNAVAILABLE:
        return None

    try:
        framework = ctypes.CDLL(MEDIA_REMOTE_FRAMEWORK_PATH)
        send_command = framework.MRMediaRemoteSendCommand
        send_command.argtypes = [ctypes.c_int, ctypes.c_void_p]
        send_command.restype = ctypes.c_bool
    except OSError as e:
        logger.warning(f"MediaRemote framework unavailable for explicit media controls: {e}")
        _media_remote_framework = _MEDIA_REMOTE_UNAVAILABLE
        return None
    except AttributeError as e:
        logger.warning(f"MediaRemote command API unavailable for explicit media controls: {e}")
        _media_remote_framework = _MEDIA_REMOTE_UNAVAILABLE
        return None

    _media_remote_framework = framework
    _media_remote_send_command = send_command
    return _media_remote_send_command


def _send_macos_media_remote_command(command: int, command_name: str) -> bool:
    send_command = _load_media_remote_send_command()
    if send_command is None:
        return False

    try:
        if not bool(send_command(command, None)):
            logger.warning(f"MediaRemote rejected explicit {command_name} command.")
            return False
        return True
    except Exception as e:
        logger.warning(f"Failed to send MediaRemote {command_name} command: {e}")
        return False


def pause_macos_media() -> bool:
    """Pause macOS media playback with an explicit MediaRemote Pause command."""
    return _send_macos_media_remote_command(MR_COMMAND_PAUSE, "Pause")


def play_macos_media() -> bool:
    """Start macOS media playback with an explicit MediaRemote Play command."""
    return _send_macos_media_remote_command(MR_COMMAND_PLAY, "Play")


def is_macos_media_playing() -> bool:
    """Return whether the current macOS Now Playing app is actively playing."""
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-l", "JavaScript", "-e", MEDIA_REMOTE_NOW_PLAYING_JXA],
            capture_output=True,
            check=False,
            text=True,
            timeout=MEDIA_REMOTE_OSASCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.debug("Timed out querying MediaRemote playback status via osascript.")
        return False
    except Exception as e:
        logger.warning(f"Failed to query MediaRemote playback status via osascript: {e}")
        return False

    if result.returncode != 0:
        logger.debug(
            "osascript MediaRemote playback status query failed: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
        return False

    status = result.stdout.strip().splitlines()[-1:] or ["unknown"]
    if status[0] == "1":
        return True
    if status[0] != "0":
        logger.debug(f"osascript MediaRemote playback status was inconclusive: {status[0]}")
    return False


def pause_macos_media_if_playing() -> bool:
    """Pause macOS media only when Now Playing reports active playback."""
    if not is_macos_media_playing():
        return False
    return pause_macos_media()


class GlobalHotkeyListener:
    ANKI_HOTKEY_LABEL = "Ctrl+Shift+M"
    COPY_HOTKEY_LABEL = "Ctrl+Shift+C"
    JISHO_HOTKEY_LABEL = "Ctrl+Shift+J"

    def __init__(self, on_anki_export, on_copy_to_clipboard, on_jisho_search):
        self.on_anki_export = on_anki_export
        self.on_copy_to_clipboard = on_copy_to_clipboard
        self.on_jisho_search = on_jisho_search
        self._running = False
        self._thread = None
        self._loop = None
        self._tap = None
        self._tap_callback = None
        self._hotkeys_down = set()

    def start(self):
        if self._thread:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_event_tap, daemon=True, name="GlobalHotkeyListener")
        self._thread.start()
        logger.info(
            "Registered global hotkeys: "
            f"{self.ANKI_HOTKEY_LABEL}, {self.COPY_HOTKEY_LABEL}, {self.JISHO_HOTKEY_LABEL}"
        )

    def stop(self):
        self._running = False
        if self._loop is not None:
            Quartz.CFRunLoopStop(self._loop)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._loop = None
        self._tap = None
        self._tap_callback = None
        self._hotkeys_down.clear()

    def _run_event_tap(self):
        try:
            event_mask = (
                Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
                | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
            )
            self._tap_callback = self._handle_event
            self._tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionDefault,
                event_mask,
                self._tap_callback,
                None,
            )
            if self._tap is None:
                logger.warning("Failed to create global hotkey event tap. Check Accessibility permission.")
                return

            source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
            self._loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopDefaultMode)
            Quartz.CGEventTapEnable(self._tap, True)

            while self._running:
                Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.25, False)
        except Exception:
            logger.exception("Global hotkey listener failed.")
        finally:
            self._loop = None
            self._tap = None
            self._tap_callback = None
            self._running = False

    def _handle_event(self, proxy, event_type, event, refcon):
        if event_type in (
            Quartz.kCGEventTapDisabledByTimeout,
            Quartz.kCGEventTapDisabledByUserInput,
        ):
            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, True)
            return event

        try:
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            if keycode not in (MACOS_KEYCODE_C, MACOS_KEYCODE_J, MACOS_KEYCODE_M):
                return event

            if event_type == Quartz.kCGEventKeyUp and keycode in self._hotkeys_down:
                self._hotkeys_down.remove(keycode)
                return None

            if event_type != Quartz.kCGEventKeyDown:
                return event

            if keycode in self._hotkeys_down:
                return None

            if not self._has_ctrl_shift(event):
                return event

            if not self._handle_hotkey(keycode):
                return event

            self._hotkeys_down.add(keycode)
            return None
        except Exception:
            logger.exception("Global hotkey handler failed.")
            return None

    def _has_ctrl_shift(self, event) -> bool:
        flags = Quartz.CGEventGetFlags(event)
        return bool(
            flags & Quartz.kCGEventFlagMaskControl
            and flags & Quartz.kCGEventFlagMaskShift
        )

    def _handle_hotkey(self, keycode):
        try:
            if keycode == MACOS_KEYCODE_M:
                return bool(self.on_anki_export())
            if keycode == MACOS_KEYCODE_C:
                return bool(self.on_copy_to_clipboard())
            if keycode == MACOS_KEYCODE_J:
                return bool(self.on_jisho_search())
        except Exception:
            logger.exception("Global hotkey handler failed.")
            return True
        return False


class InputLoop(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="InputLoop")
        self.shared_state = shared_state
        self.mouse_controller = mouse.Controller()

    def run(self):
        logger.debug("Input thread started.")
        last_mouse_pos = (0, 0)
        self.shared_state.screenshot_trigger_event.set()

        while self.shared_state.running:
            if config.is_paused or not self.shared_state.ocr_available_event.is_set():
                time.sleep(0.1)
                continue
            try:
                current_mouse_pos = self.mouse_controller.position

                # trigger hit_scans + lookups
                if current_mouse_pos != last_mouse_pos:
                    self.shared_state.hit_scan_queue.trigger()

                last_mouse_pos = current_mouse_pos
            except:
                logger.exception("An unexpected error occurred in the input loop. Continuing...")
            finally:
                time.sleep(0.01)
        logger.debug("Input thread stopped.")

    @staticmethod
    def get_mouse_pos():
        pos = mouse.Controller().position
        return (int(pos[0]), int(pos[1]))
