# meikikai/config/config.py
import configparser
import logging
import sys

from meikikai.utils.paths import paths

logger = logging.getLogger(__name__)

APP_NAME = "MeikiKai"
APP_VERSION = "1.0.0"
MAX_DICT_ENTRIES = 10
MIN_AUTO_SCAN_INTERVAL_SECONDS = 0.1
IS_MACOS = sys.platform == 'darwin'

if not IS_MACOS:
    raise RuntimeError(f"{APP_NAME} is macOS-only.")

CONFIG_PATH = paths.config_path
DICT_PATH = paths.dictionary_path

class Config:
    _instance = None

    _SCHEMA = {
        'Settings': {
            'scan_screen': 1,
            'max_lookup_length': 25,
            'auto_scan_interval_seconds': 0.5,
            'auto_pause_media': False,
            'popup_position_mode': 'visual_novel_mode'
        }
    }

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        parser = configparser.ConfigParser()
        found = parser.read(CONFIG_PATH, encoding='utf-8')

        for section, settings in self._SCHEMA.items():
            for key, default in settings.items():
                source_section = section
                if not parser.has_option(source_section, key):
                    source_section = self._legacy_section_for(key)

                if source_section and parser.has_option(source_section, key):
                    if isinstance(default, bool):
                        val = parser.getboolean(source_section, key)
                    elif isinstance(default, int):
                        val = parser.getint(source_section, key)
                    elif isinstance(default, float):
                        val = parser.getfloat(source_section, key)
                    else:
                        val = parser.get(source_section, key)
                else:
                    val = default
                if key == 'auto_scan_interval_seconds':
                    val = max(MIN_AUTO_SCAN_INTERVAL_SECONDS, val)
                setattr(self, key, val)

        self.is_paused = False
        if found:
            logger.info(f"Configuration loaded from '{CONFIG_PATH}'.")
        else:
            logger.info(f"No configuration found at '{CONFIG_PATH}'. A new one will be created with default values.")

    def _legacy_section_for(self, key: str):
        if key == 'popup_position_mode':
            return 'Theme'
        return None

    def save(self):
        parser = configparser.ConfigParser()
        for section, settings in self._SCHEMA.items():
            parser.add_section(section)
            for key in settings:
                val = getattr(self, key)
                parser.set(section, key, str(val).lower() if isinstance(val, bool) else str(val))

        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            parser.write(f)
        logger.info(f"Settings saved to '{CONFIG_PATH}'.")


config = Config()
