# meikikai/gui/input.py
import ctypes
import logging
import threading
import time

import Quartz
from AppKit import NSEvent
from pynput import mouse

try:
    import ApplicationServices
except ImportError:
    ApplicationServices = Quartz

from meikikai.config.config import config

logger = logging.getLogger(__name__)

NX_KEYTYPE_PLAY = 16
NX_SUBTYPE_AUX_CONTROL_BUTTONS = 8
NS_SYSTEM_DEFINED = 14
KEY_DOWN_STATE = 0xA
KEY_UP_STATE = 0xB

MEDIA_REMOTE_FRAMEWORK_PATH = "/System/Library/PrivateFrameworks/MediaRemote.framework/MediaRemote"
MR_COMMAND_PLAY = 0
MR_COMMAND_PAUSE = 1

_MEDIA_REMOTE_UNAVAILABLE = object()
_media_remote_framework = None
_media_remote_send_command = None


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


def toggle_macos_play_pause_key() -> bool:
    """Toggle macOS media playback using the system Play/Pause key event."""
    if not is_process_trusted_for_accessibility():
        logger.warning(
            "Auto Pause Media requires macOS Accessibility permission for this app or terminal. "
            "Enable it in System Settings > Privacy & Security > Accessibility."
        )
        return False

    try:
        event_tap = getattr(Quartz, 'kCGHIDEventTap', 0)
        for state in (KEY_DOWN_STATE, KEY_UP_STATE):
            event = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
                NS_SYSTEM_DEFINED,
                (0, 0),
                state << 8,
                0,
                0,
                0,
                NX_SUBTYPE_AUX_CONTROL_BUTTONS,
                (NX_KEYTYPE_PLAY << 16) | (state << 8),
                -1,
            )
            cg_event = event.CGEvent()
            if cg_event is None:
                logger.warning("Failed to create macOS Play/Pause CGEvent.")
                return False
            Quartz.CGEventPost(event_tap, cg_event)
        return True
    except Exception as e:
        logger.warning(f"Failed to toggle macOS Play/Pause key: {e}")
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
            if not config.is_enabled:
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
