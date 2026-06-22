import ctypes
import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from meikikai.ocr.providers.chrome_screen_ai._protobuf import LineResult, parse_visual_annotation
from meikikai.ocr.providers.chrome_screen_ai.component import LIB_NAME, find_screen_ai_dir

logger = logging.getLogger(__name__)

_model_dir: Path | None = None
_file_cache: dict[str, bytes] = {}
_output_suppression_lock = threading.RLock()

_GetFileSizeFn = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_char_p)
_GetFileContentFn = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_void_p)


@_GetFileSizeFn
def _get_file_size(path: ctypes.c_char_p) -> int:
    relative_path = path.decode("utf-8") if isinstance(path, bytes) else str(path)
    return len(_read_model_file(relative_path))


@_GetFileContentFn
def _get_file_content(path: ctypes.c_char_p, buffer_size: int, buffer: ctypes.c_void_p) -> None:
    relative_path = path.decode("utf-8") if isinstance(path, bytes) else str(path)
    data = _read_model_file(relative_path)
    ctypes.memmove(buffer, data[:buffer_size], min(len(data), buffer_size))


def _flush_standard_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.flush()
        except Exception:
            pass


@contextmanager
def suppress_native_output():
    """Temporarily redirect C-level stdout/stderr during noisy native calls."""
    with _output_suppression_lock:
        _flush_standard_streams()
        devnull_fd = stdout_fd = stderr_fd = None
        try:
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            stdout_fd = os.dup(1)
            stderr_fd = os.dup(2)
        except OSError:
            _close_fds(stdout_fd, stderr_fd, devnull_fd)
            yield
            return

        try:
            os.dup2(devnull_fd, 1)
            os.dup2(devnull_fd, 2)
        except OSError:
            _restore_standard_fds(stdout_fd, stderr_fd)
            _close_fds(stdout_fd, stderr_fd, devnull_fd)
            yield
            return

        try:
            yield
        finally:
            _flush_standard_streams()
            _restore_standard_fds(stdout_fd, stderr_fd)
            _close_fds(stdout_fd, stderr_fd, devnull_fd)


def _restore_standard_fds(stdout_fd: int, stderr_fd: int) -> None:
    try:
        os.dup2(stdout_fd, 1)
        os.dup2(stderr_fd, 2)
    except OSError:
        pass


def _close_fds(*fds: int | None) -> None:
    for fd in fds:
        if fd is None:
            continue
        try:
            os.close(fd)
        except OSError:
            pass


def _read_model_file(relative_path: str) -> bytes:
    if relative_path in _file_cache:
        return _file_cache[relative_path]

    if _model_dir is None:
        return b""

    file_path = _model_dir / relative_path
    if not file_path.exists():
        logger.warning("Chrome Screen AI model file not found: %s", file_path)
        return b""

    data = file_path.read_bytes()
    _file_cache[relative_path] = data
    return data


class _SkImageInfo(ctypes.Structure):
    _fields_ = [
        ("fColorSpace", ctypes.c_void_p),
        ("fColorType", ctypes.c_int32),
        ("fAlphaType", ctypes.c_int32),
        ("fWidth", ctypes.c_int32),
        ("fHeight", ctypes.c_int32),
    ]


class _SkPixmap(ctypes.Structure):
    _fields_ = [
        ("fPixels", ctypes.c_void_p),
        ("fRowBytes", ctypes.c_size_t),
        ("fInfo", _SkImageInfo),
    ]


class _SkBitmap(ctypes.Structure):
    _fields_ = [
        ("fPixelRef", ctypes.c_void_p),
        ("fPixmap", _SkPixmap),
        ("fFlags", ctypes.c_uint8),
    ]


class _FakeSkPixelRef(ctypes.Structure):
    _fields_ = [
        ("vtable_ptr", ctypes.c_void_p),
        ("refcount", ctypes.c_int32),
        ("_pad", ctypes.c_int32),
        ("fWidth", ctypes.c_int32),
        ("fHeight", ctypes.c_int32),
        ("fPixels", ctypes.c_void_p),
        ("fRowBytes", ctypes.c_size_t),
        ("_extra", ctypes.c_uint8 * 64),
    ]


_FAKE_VTABLE = (ctypes.c_void_p * 16)()
_K_BGRA_8888 = 6
_K_PREMUL = 2


def _make_bitmap(pixels: bytes, width: int, height: int) -> _SkBitmap:
    pixel_buffer = ctypes.create_string_buffer(pixels, len(pixels))
    pixel_address = ctypes.addressof(pixel_buffer)
    row_bytes = width * 4

    info = _SkImageInfo(
        fColorSpace=0,
        fColorType=_K_BGRA_8888,
        fAlphaType=_K_PREMUL,
        fWidth=width,
        fHeight=height,
    )
    pixmap = _SkPixmap(fPixels=pixel_address, fRowBytes=row_bytes, fInfo=info)
    pixel_ref = _FakeSkPixelRef(
        vtable_ptr=ctypes.addressof(_FAKE_VTABLE),
        refcount=1,
        fWidth=width,
        fHeight=height,
        fPixels=pixel_address,
        fRowBytes=row_bytes,
    )
    bitmap = _SkBitmap(fPixelRef=ctypes.addressof(pixel_ref), fPixmap=pixmap, fFlags=0)
    bitmap._prevent_gc = (pixel_buffer, pixel_ref)
    return bitmap


class ChromeScreenAiEngine:
    def __init__(self, component_dir: Path | None = None):
        component_dir = component_dir or find_screen_ai_dir()
        library_path = component_dir / LIB_NAME
        if not library_path.exists():
            raise FileNotFoundError(f"Chrome Screen AI library not found: {library_path}")

        global _model_dir
        _model_dir = component_dir
        _file_cache.clear()
        for variable in ("GLOG_minloglevel", "TF_CPP_MIN_LOG_LEVEL", "ABSL_MIN_LOG_LEVEL"):
            os.environ.setdefault(variable, "3")

        logger.info("Loading Chrome Screen AI from %s", library_path)
        with suppress_native_output():
            self._dll = ctypes.CDLL(str(library_path))
        self._bind()
        with suppress_native_output():
            self._dll.SetFileContentFunctions(_get_file_size, _get_file_content)
            self._dll.SetOCRLightMode(False)

            if not self._dll.InitOCRUsingCallback():
                raise RuntimeError("Failed to initialize Chrome Screen AI OCR pipeline.")

            self.max_image_dimension = int(self._dll.GetMaxImageDimension())
            time.sleep(0.5)
        logger.info("Chrome Screen AI initialized with max image dimension %d.", self.max_image_dimension)

    def _bind(self):
        self._dll.GetLibraryVersion.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
        self._dll.GetLibraryVersion.restype = None
        self._dll.SetFileContentFunctions.argtypes = [_GetFileSizeFn, _GetFileContentFn]
        self._dll.SetFileContentFunctions.restype = None
        self._dll.InitOCRUsingCallback.argtypes = []
        self._dll.InitOCRUsingCallback.restype = ctypes.c_bool
        self._dll.SetOCRLightMode.argtypes = [ctypes.c_bool]
        self._dll.SetOCRLightMode.restype = None
        self._dll.GetMaxImageDimension.argtypes = []
        self._dll.GetMaxImageDimension.restype = ctypes.c_uint32
        self._dll.PerformOCR.argtypes = [ctypes.POINTER(_SkBitmap), ctypes.POINTER(ctypes.c_uint32)]
        self._dll.PerformOCR.restype = ctypes.c_void_p
        self._dll.FreeLibraryAllocatedCharArray.argtypes = [ctypes.c_void_p]
        self._dll.FreeLibraryAllocatedCharArray.restype = None

    def scan(self, image: Image.Image) -> tuple[list[LineResult], tuple[int, int]]:
        prepared = self._prepare_image(image)
        width, height = prepared.size
        raw_result = self._perform_ocr(prepared.tobytes("raw", "BGRA"), width, height)
        if raw_result is None:
            return [], (width, height)
        return parse_visual_annotation(raw_result), (width, height)

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        image = image.convert("RGBA")
        max_dimension = self.max_image_dimension or 0
        if max_dimension and max(image.size) > max_dimension:
            scale = max_dimension / max(image.size)
            new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        return image

    def _perform_ocr(self, bgra_pixels: bytes, width: int, height: int) -> bytes | None:
        bitmap = _make_bitmap(bgra_pixels, width, height)
        output_length = ctypes.c_uint32(0)
        with suppress_native_output():
            result_ptr = self._dll.PerformOCR(ctypes.byref(bitmap), ctypes.byref(output_length))
        if not result_ptr:
            logger.warning("Chrome Screen AI returned no OCR result.")
            return None

        try:
            return ctypes.string_at(result_ptr, output_length.value)
        finally:
            self._dll.FreeLibraryAllocatedCharArray(result_ptr)
