import os
import sys
from pathlib import Path


class MeikiPaths:
    """Centralized macOS path resolution for meikipop."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
            cls._instance._app_support_dir = Path.home() / "Library" / "Application Support" / "meikipop"
            cls._instance._cache_dir = Path.home() / "Library" / "Caches" / "meikipop"
            cls._instance._app_support_dir.mkdir(parents=True, exist_ok=True)
            cls._instance._cache_dir.mkdir(parents=True, exist_ok=True)
        return cls._instance

    @property
    def is_frozen(self):
        """Check if running as PyInstaller bundle."""
        return getattr(sys, 'frozen', False)

    @property
    def data_dir(self):
        """Location of dictionary.pkl."""
        return str(self._app_support_dir)

    @property
    def config_path(self):
        """Full path to config.ini."""
        return str(self._app_support_dir / 'config.ini')

    @property
    def dictionary_path(self):
        """Location of dictionary.pkl."""
        return str(self._app_support_dir / 'dictionary.pkl')

    @property
    def cache_dir(self):
        """Location for cached downloads."""
        return str(self._cache_dir)

    @property
    def main_dir(self):
        """Location of bundled resources (icons, etc.)."""
        if self.is_frozen:
            return os.path.join(sys._MEIPASS, 'meikipop')
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def get_resource_path(self, relative_path):
        """Get full path to a bundled resource."""
        return os.path.join(self.main_dir, 'resources', relative_path)


paths = MeikiPaths()
