import logging
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from meikikai.utils.paths import paths

logger = logging.getLogger(__name__)

LIB_NAME = "libchromescreenai.so"
STAMP_FILE_NAME = ".screen_ai_package"
CIPD_SOURCE_LABEL = "Google/Chromium public CIPD infrastructure"
CIPD_CLIENT_BASE_URL = "https://chrome-infra-packages.appspot.com/client"
CIPD_PACKAGE_PREFIX = "chromium/third_party/screen-ai"
CIPD_REQUESTED_VERSION = "latest"
NOTICE_FILE_NAME = "THIRD_PARTY_LICENSES"
README_FILE_NAME = "README.md"

ProgressCallback = Callable[[str], None]


class ScreenAiComponentError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScreenAiComponentStatus:
    installed: bool
    install_dir: Path
    component_dir: Path | None = None
    source: str = CIPD_SOURCE_LABEL
    package: str = ""
    requested_version: str = CIPD_REQUESTED_VERSION
    resolved_version: str = ""
    instance_id: str = ""
    stamp_path: Path | None = None
    notices_path: Path | None = None
    readme_path: Path | None = None

    @property
    def version_display(self) -> str:
        return self.resolved_version or self.requested_version or "Unknown"

    @property
    def location_display(self) -> str:
        return str(self.component_dir or self.install_dir)


def screen_ai_install_dir() -> Path:
    return Path(paths.data_dir) / "screen_ai"


def get_cipd_platform() -> str:
    arch = platform.machine().lower()
    if arch in ("arm64", "aarch64"):
        return "mac-arm64"
    if arch in ("x86_64", "amd64"):
        return "mac-amd64"
    raise ScreenAiComponentError(f"Unsupported macOS architecture for Chrome Screen AI: {arch}")


def screen_ai_package(cipd_platform: str | None = None) -> str:
    return f"{CIPD_PACKAGE_PREFIX}/{cipd_platform or get_cipd_platform()}"


def find_screen_ai_dir() -> Path:
    component_dir = find_component_dir(screen_ai_install_dir())
    if component_dir:
        return component_dir

    raise FileNotFoundError(
        "Chrome Screen AI is not installed for MeikiKai. Open Settings > OCR Engine to install it explicitly."
    )


def find_component_dir(base_dir: Path | str) -> Path | None:
    base_dir = Path(base_dir).expanduser()
    if not base_dir.exists():
        return None

    if (base_dir / LIB_NAME).exists():
        return base_dir
    if (base_dir / "resources" / LIB_NAME).exists():
        return base_dir / "resources"

    try:
        children = sorted((child for child in base_dir.iterdir() if child.is_dir()), reverse=True)
    except OSError:
        return None

    for candidate in children:
        if (candidate / LIB_NAME).exists():
            return candidate
        if (candidate / "resources" / LIB_NAME).exists():
            return candidate / "resources"
    return None


def get_screen_ai_status() -> ScreenAiComponentStatus:
    install_dir = screen_ai_install_dir()
    component_dir = find_component_dir(install_dir)
    default_package = _default_package_name()
    if not component_dir:
        return ScreenAiComponentStatus(
            installed=False,
            install_dir=install_dir,
            package=default_package,
        )

    metadata, stamp_path = _read_metadata(component_dir, install_dir)
    notices_path = _existing_file(component_dir, install_dir, NOTICE_FILE_NAME)
    readme_path = _existing_file(component_dir, install_dir, README_FILE_NAME)

    return ScreenAiComponentStatus(
        installed=True,
        install_dir=install_dir,
        component_dir=component_dir,
        source=metadata.get("source") or CIPD_SOURCE_LABEL,
        package=metadata.get("package") or default_package,
        requested_version=metadata.get("requested_version") or metadata.get("version") or CIPD_REQUESTED_VERSION,
        resolved_version=metadata.get("resolved_version") or metadata.get("version_tag") or "",
        instance_id=metadata.get("instance_id") or "",
        stamp_path=stamp_path,
        notices_path=notices_path,
        readme_path=readme_path,
    )


def install_screen_ai_from_cipd(progress: ProgressCallback | None = None) -> ScreenAiComponentStatus:
    progress = progress or _ignore_progress
    cipd_platform = get_cipd_platform()
    package = screen_ai_package(cipd_platform)
    client_url = f"{CIPD_CLIENT_BASE_URL}?platform={cipd_platform}&version=latest"

    with tempfile.TemporaryDirectory(prefix="meikikai-screen-ai-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        cipd_bin = temp_dir / "cipd"
        package_root = temp_dir / "package"
        ensure_file = temp_dir / "screen_ai.ensure"

        progress("Downloading the CIPD client from Google/Chromium infrastructure…")
        with urllib.request.urlopen(client_url, timeout=60) as response, cipd_bin.open("wb") as output:
            shutil.copyfileobj(response, output)
        cipd_bin.chmod(0o755)

        package_root.mkdir(parents=True, exist_ok=True)
        ensure_file.write_text(f"{package} {CIPD_REQUESTED_VERSION}\n", encoding="utf-8")

        progress("Downloading Chrome Screen AI from Google/Chromium CIPD…")
        _run_command(
            [str(cipd_bin), "export", "-root", str(package_root), "-ensure-file", str(ensure_file)],
            "Chrome Screen AI CIPD download",
        )

        resources_dir = package_root / "resources"
        if not (resources_dir / LIB_NAME).exists():
            raise ScreenAiComponentError(f"Chrome Screen AI package did not contain resources/{LIB_NAME}")

        describe_metadata = _describe_package(cipd_bin, package)
        metadata = {
            "source": CIPD_SOURCE_LABEL,
            "package": package,
            "platform": cipd_platform,
            "requested_version": CIPD_REQUESTED_VERSION,
            "cipd_client_url": client_url,
            "installed_at": _utc_now(),
            **describe_metadata,
        }

        progress(f"Installing Chrome Screen AI into {screen_ai_install_dir()}…")
        _replace_install_dir(resources_dir, screen_ai_install_dir(), metadata)

    return get_screen_ai_status()


def uninstall_screen_ai() -> None:
    install_dir = screen_ai_install_dir()
    if install_dir.exists():
        _remove_path(install_dir)


def _default_package_name() -> str:
    try:
        return screen_ai_package()
    except ScreenAiComponentError:
        return f"{CIPD_PACKAGE_PREFIX}/<unsupported-architecture>"


def _read_metadata(*candidate_dirs: Path | str) -> tuple[dict[str, str], Path | None]:
    for candidate_dir in candidate_dirs:
        stamp_path = Path(candidate_dir).expanduser() / STAMP_FILE_NAME
        if not stamp_path.exists():
            continue
        try:
            text = stamp_path.read_text(encoding="utf-8")
        except OSError:
            continue
        return _parse_metadata(text), stamp_path
    return {}, None


def _parse_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if "=" in line:
            key, value = line.split("=", 1)
            metadata[key.strip()] = value.strip()

    if not metadata and lines:
        legacy_match = re.match(r"^(?P<package>\S+)\s+(?P<version>\S+)$", lines[0])
        if legacy_match:
            metadata["package"] = legacy_match.group("package")
            metadata["requested_version"] = legacy_match.group("version")
            metadata["source"] = CIPD_SOURCE_LABEL

    return metadata


def _existing_file(component_dir: Path, install_dir: Path, file_name: str) -> Path | None:
    for base_dir in (component_dir, install_dir):
        path = base_dir / file_name
        if path.exists():
            return path
    return None


def _describe_package(cipd_bin: Path, package: str) -> dict[str, str]:
    try:
        output = _run_command(
            [str(cipd_bin), "describe", package, "-version", CIPD_REQUESTED_VERSION],
            "Chrome Screen AI CIPD metadata lookup",
        )
    except ScreenAiComponentError as e:
        logger.warning("Could not read Chrome Screen AI CIPD metadata: %s", e)
        return {}

    metadata: dict[str, str] = {}
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Instance ID:"):
            metadata["instance_id"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("version:"):
            metadata["resolved_version"] = stripped
    return metadata


def _replace_install_dir(source_dir: Path, install_dir: Path, metadata: dict[str, str]) -> None:
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_parent = Path(tempfile.mkdtemp(prefix=f".{install_dir.name}-", dir=str(install_dir.parent)))
    temp_install_dir = temp_parent / "resources"
    try:
        _run_command(["/usr/bin/ditto", str(source_dir), str(temp_install_dir)], "Chrome Screen AI copy")
        _write_metadata(temp_install_dir, metadata)
        _remove_path(install_dir)
        temp_install_dir.rename(install_dir)
    except Exception:
        _remove_path(temp_parent)
        raise
    else:
        _remove_path(temp_parent)


def _write_metadata(component_dir: Path, metadata: dict[str, str]) -> None:
    component_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in metadata.items() if value]
    (component_dir / STAMP_FILE_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_command(command: list[str], description: str) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as e:
        raise ScreenAiComponentError(f"{description} failed: {e}") from e

    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise ScreenAiComponentError(f"{description} failed: {output or f'exit code {result.returncode}'}")
    return result.stdout


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ignore_progress(_message: str) -> None:
    pass
