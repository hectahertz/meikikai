# meikipop/gui/input.py
import logging
import sys
import threading
import time

import Quartz
from AppKit import NSEvent
from pynput import mouse

from meikipop.config.config import config

logger = logging.getLogger(__name__)

NX_KEYTYPE_PLAY = 16
NX_SUBTYPE_AUX_CONTROL_BUTTONS = 8
NS_SYSTEM_DEFINED = 14
KEY_DOWN_STATE = 0xA
KEY_UP_STATE = 0xB


class MacOSKeyboardController:
    MODIFIER_FLAGS = {
        'shift': (1 << 17) | (1 << 18),
        'ctrl': 1 << 12,
        'alt': 1 << 19,
        'cmd': 1 << 20,
    }

    def __init__(self, hotkey_str):
        self.hotkey_str = hotkey_str.lower()
        self.modifiers = self.hotkey_str.split('+')

        for mod in self.modifiers:
            if mod not in self.MODIFIER_FLAGS:
                logger.critical(
                    f"Unsupported hotkey '{self.hotkey_str}' for macOS. Use 'shift', 'ctrl', 'alt', or 'cmd'.")
                sys.exit(1)

    def is_hotkey_pressed(self) -> bool:
        try:
            flags = NSEvent.modifierFlags()
            return all(flags & self.MODIFIER_FLAGS[mod] for mod in self.modifiers)
        except Exception as e:
            logger.warning(f"Error checking hotkey state: {e}")
            return False


def toggle_macos_play_pause_key() -> bool:
    """Toggle macOS media playback using the system Play/Pause key event."""
    try:
        for state in (KEY_DOWN_STATE, KEY_UP_STATE):
            event = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
                NS_SYSTEM_DEFINED,
                (0, 0),
                state << 8,
                0,
                0,
                None,
                NX_SUBTYPE_AUX_CONTROL_BUTTONS,
                (NX_KEYTYPE_PLAY << 16) | (state << 8),
                -1,
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event.CGEvent())
        return True
    except Exception as e:
        logger.warning(f"Failed to toggle macOS Play/Pause key: {e}")
        return False


class InputLoop(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="InputLoop")
        self.shared_state = shared_state
        self.mouse_controller = mouse.Controller()

        self.hotkey_str = config.hotkey.lower()
        self.keyboard_controller = MacOSKeyboardController(self.hotkey_str)

        self.started_auto_mode = False

    def run(self):
        logger.debug("Input thread started.")
        last_mouse_pos = (0, 0)
        hotkey_was_pressed = False

        while self.shared_state.running:
            if not config.is_enabled:
                time.sleep(0.1)
                continue
            try:
                current_mouse_pos = self.mouse_controller.position
                try:
                    hotkey_is_pressed = self.keyboard_controller.is_hotkey_pressed()
                except Exception:
                    hotkey_is_pressed = False

                # trigger screenshots + ocr in manual mode
                if hotkey_is_pressed and not hotkey_was_pressed and not config.auto_scan_mode:
                    logger.info(f"Input: Hotkey '{config.hotkey}' pressed. Triggering screenshot.")
                    self.shared_state.screenshot_trigger_event.set()

                # trigger initial screenshots + ocr in auto mode
                if not self.started_auto_mode and config.auto_scan_mode:
                    self.shared_state.screenshot_trigger_event.set()
                self.started_auto_mode = config.auto_scan_mode

                # trigger screenshots + ocr in auto-on-mouse-move mode
                if config.auto_scan_mode and config.auto_scan_on_mouse_move and current_mouse_pos != last_mouse_pos:
                    self.shared_state.screenshot_trigger_event.set()

                # trigger hit_scans + lookups
                if current_mouse_pos != last_mouse_pos:
                    self.shared_state.hit_scan_queue.trigger()

                if hotkey_was_pressed and not hotkey_is_pressed:
                    logger.info(f"Input: Hotkey '{config.hotkey}' released.")

                last_mouse_pos = current_mouse_pos
                hotkey_was_pressed = hotkey_is_pressed
                self.hotkey_is_pressed = hotkey_is_pressed
            except:
                logger.exception("An unexpected error occurred in the input loop. Continuing...")
            finally:
                time.sleep(0.01)
        logger.debug("Input thread stopped.")

    def is_virtual_hotkey_down(self):
        return self.keyboard_controller.is_hotkey_pressed() or (
                config.auto_scan_mode and config.auto_scan_mode_lookups_without_hotkey)

    def reapply_settings(self):
        logger.debug(f"InputLoop: Re-applying settings. New hotkey: '{config.hotkey}'.")
        self.hotkey_str = config.hotkey.lower()
        self.keyboard_controller = MacOSKeyboardController(self.hotkey_str)

    @staticmethod
    def get_mouse_pos():
        pos = mouse.Controller().position
        return (int(pos[0]), int(pos[1]))
