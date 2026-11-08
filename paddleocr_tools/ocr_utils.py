from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

from i18n import get_language, t
from .progress import OCRProgress, PROGRESS_PREFIX

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_VENV = PROJECT_ROOT / ".venv"
OCR_PYTHON = PROJECT_VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
OCR_WORKER = Path(__file__).resolve().with_name("ocr_worker.py")
OCR_CACHE = PROJECT_ROOT / ".ocr-cache"
OCR_REQUIREMENTS = PROJECT_ROOT / "requirements-ocr.txt"
OCR_EXTENSIONS = {".docx", ".pptx", ".xlsx", ".pdf", ".bmp", ".gif", ".jpeg", ".jpg",
                  ".png", ".tif", ".tiff", ".webp"}
_REQUIRED_MODULES = ("paddleocr", "paddle", "PIL", "pymupdf", "markitdown",
                     "pdfminer", "pdfplumber", "mammoth", "lxml", "pptx", "pandas", "openpyxl")
# Same version as requirements-ocr.txt. PaddleOCR selects the GPU on its own once this build is present.
_PADDLE_GPU_REQUIREMENT = "paddlepaddle-gpu==3.3.1"
_PADDLE_GPU_INDEX = "https://www.paddlepaddle.org.cn/packages/stable/cu126/"
_PADDLE_GPU_MIN_DRIVER = 560  # First driver series with CUDA 12.6, which this build targets.
_setup_lock = threading.Lock()
_environment_ready = False
# no_torch must come first, see that module. Runs from PROJECT_ROOT, so the package is importable.
_IMPORT_CHECK = (
    "import sys\n"
    "import paddleocr_tools.no_torch\n"
    "try:\n"
    "    from paddleocr import PaddleOCR\n"
    "    import paddle, PIL, pymupdf\n"
    "    import markitdown, pdfminer.high_level, pdfplumber\n"
    "    import mammoth, lxml.etree, pptx, pandas, openpyxl\n"
    "except ModuleNotFoundError as error:\n"
    "    print(error, file=sys.stderr)\n"
    "    sys.exit(42)\n"
)


def _run_python(*arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(OCR_PYTHON), *arguments], cwd=PROJECT_ROOT, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _install(command: list[str], progress: Callable[[str], None] | None) -> None:
    # Stream pip output so downloads do not look like a frozen conversion.
    lines: deque[str] = deque(maxlen=30)
    with subprocess.Popen(
        command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        text=True, encoding="utf-8", errors="replace",
    ) as process:
        for line in process.stdout:
            if line := line.strip():
                lines.append(line)
                if progress:
                    progress(line)
        if process.wait() != 0:
            raise RuntimeError(t("err_ocr_install", error="\n".join(lines)))


def _cuda_gpu_available() -> bool:
    try:
        probe = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            capture_output=True, text=True, timeout=15,
        )
        return probe.returncode == 0 and int(probe.stdout.split(".")[0]) >= _PADDLE_GPU_MIN_DRIVER
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def _enable_gpu_ocr(progress: Callable[[str], None] | None) -> None:
    """Move the project's Paddle to its CUDA build, which reads a dense page ~70x faster than the CPU."""
    if not _cuda_gpu_available():
        return
    build = _run_python("-c", "import paddle; print(paddle.is_compiled_with_cuda())", env=ocr_environment())
    if build.stdout.split()[-1:] != ["False"]:
        return
    pip = [str(OCR_PYTHON), "-m", "pip", "--isolated", "--disable-pip-version-check", "--no-input"]
    # Both builds install the same "paddle" package, so one must be gone before the other arrives.
    remove = [*pip, "uninstall", "--yes", "paddlepaddle", "paddlepaddle-gpu"]
    if progress:
        progress(t("log_ocr_gpu_install"))
    with tempfile.TemporaryDirectory(prefix="makethemd-paddle-gpu-") as wheels:
        try:
            # Download first: a failure here leaves the working CPU build untouched.
            _install([*pip, "download", "--progress-bar", "off", "--dest", wheels,
                      "--index-url", "https://pypi.org/simple", "--extra-index-url", _PADDLE_GPU_INDEX,
                      _PADDLE_GPU_REQUIREMENT], progress)
        except RuntimeError as error:
            if progress:
                progress(t("log_ocr_gpu_skipped", error=error))
            return
        try:
            _install(remove, progress)
            _install([*pip, "install", "--progress-bar", "off", "--no-index", "--find-links", wheels,
                      _PADDLE_GPU_REQUIREMENT], progress)
            check = _run_python("-c", _IMPORT_CHECK, env=ocr_environment())
            if check.returncode:
                raise RuntimeError(check.stderr.strip() or check.stdout.strip())
        except RuntimeError as error:
            _install(remove, progress)
            _install([*pip, "install", "--progress-bar", "off", "-r", str(OCR_REQUIREMENTS)], progress)
            if progress:
                progress(t("log_ocr_gpu_skipped", error=error))
            return
    if progress:
        progress(t("log_ocr_gpu_ready"))


def ensure_ocr_environment(progress: Callable[[str], None] | None = None) -> None:
    """Prepare the project's venv on demand; never install into the global Python."""
    global _environment_ready
    with _setup_lock:
        if _environment_ready and OCR_PYTHON.is_file():
            return
        if not OCR_WORKER.is_file():
            raise RuntimeError(t("err_ocr_worker_missing", path=OCR_WORKER))
        if not OCR_PYTHON.is_file():
            if PROJECT_VENV.exists():
                raise RuntimeError(t("err_ocr_env", path=OCR_PYTHON))
            if progress:
                progress(t("log_ocr_create_env"))
            # Preserve access to an app installed in the system Python on older setups.
            _install([sys.executable, "-m", "venv", "--system-site-packages", str(PROJECT_VENV)], progress)
        check_ocr_environment()
        if progress:
            progress(t("log_ocr_check"))
        probe = _run_python("-c", "import importlib.util, json; "
                            f"print(json.dumps([m for m in {_REQUIRED_MODULES!r} "
                            "if importlib.util.find_spec(m) is None]))")
        if probe.returncode:
            raise RuntimeError(t("err_ocr_install", error=probe.stderr.strip() or probe.stdout.strip()))
        missing = json.loads(probe.stdout)
        check = None
        if not missing:
            check = _run_python("-c", _IMPORT_CHECK, env=ocr_environment())
            if check.returncode == 42:
                missing = [check.stderr.strip()]
        if missing:
            if progress:
                progress(t("log_ocr_install", packages=", ".join(missing)))
            if _run_python("-m", "pip", "--version").returncode:
                _install([str(OCR_PYTHON), "-m", "ensurepip", "--upgrade"], progress)
            _install([str(OCR_PYTHON), "-m", "pip", "--isolated", "install",
                      "--disable-pip-version-check", "--no-input", "--progress-bar", "off",
                      "-r", str(OCR_REQUIREMENTS)], progress)
            # Check actual imports too: DLL and transitive dependency errors need a useful message.
            check = _run_python("-c", _IMPORT_CHECK, env=ocr_environment())
        if check.returncode:
            raise RuntimeError(t("err_ocr_import", error=check.stderr.strip() or check.stdout.strip()))
        _enable_gpu_ocr(progress)
        _environment_ready = True
        if progress:
            progress(t("log_ocr_ready"))


def check_ocr_environment() -> None:
    if not OCR_PYTHON.is_file():
        raise RuntimeError(t("err_ocr_env", path=OCR_PYTHON))
    if not OCR_WORKER.is_file():
        raise RuntimeError(t("err_ocr_worker_missing", path=OCR_WORKER))


def ocr_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "HF_HOME": str(OCR_CACHE / "huggingface"),
            "PADDLE_PDX_CACHE_HOME": str(OCR_CACHE / "paddlex"),
            "PYTHONIOENCODING": "utf-8",
            "MAKETHEMD_UI_LANGUAGE": get_language(),
        }
    )
    OCR_CACHE.mkdir(exist_ok=True)
    return environment


def _stream_worker(
    command: list[str], progress: Callable[[str], None] | None = None,
    status: Callable[[OCRProgress], None] | None = None,
) -> subprocess.CompletedProcess:
    """Drain child output continuously and keep the UI alive during long silent stages."""
    started = time.monotonic()
    lines: queue.Queue[str | None] = queue.Queue()
    diagnostics: deque[str] = deque(maxlen=60)
    current = {"stage": "starting"}
    total_images = 0
    completed_images = 0

    def report(changed: bool = False) -> None:
        stage = current.get("stage", "starting")
        fraction = None
        if stage == "pdf_page":
            mode = current["mode"]
            action = t({"reading": "pdf_progress_reading", "ocr": "pdf_progress_ocr",
                        "images": "pdf_progress_images",
                        "cached": "pdf_progress_cached", "text": "pdf_progress_text"}[mode])
            message = t("pdf_progress_page", page=current["page"], total=current["total"], action=action)
            fraction = current["completed"] / current["total"] if current["total"] else None
        elif stage == "scan":
            done, total = current["completed"], current["total"]
            message = t("ocr_progress_scan", done=done, total=total)
            fraction = done / total if total else None
        elif stage in {"image_start", "image_done"}:
            message = t("ocr_progress_images", done=completed_images, total=total_images,
                        name=current.get("name", ""))
            fraction = completed_images / total_images if total_images else None
        elif stage == "images_found":
            message = t("ocr_progress_found", total=total_images)
        else:
            message = t({"starting": "ocr_progress_starting", "reading": "ocr_progress_reading",
                         "finding": "ocr_progress_finding", "models": "ocr_progress_models",
                         "done": "ocr_progress_done"}.get(stage, "ocr_progress_starting"))
            if stage == "done":
                fraction = 1.0
        if status:
            status(OCRProgress(message, time.monotonic() - started, fraction))
        elif progress and changed:
            progress(message)

    with subprocess.Popen(
        command, cwd=PROJECT_ROOT, env=ocr_environment(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    ) as process:
        def read_output():
            try:
                for line in process.stdout:
                    lines.put(line)
            finally:
                lines.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            report(changed=True)
            last_report = time.monotonic()
            while True:
                try:
                    line = lines.get(timeout=0.2)
                except queue.Empty:
                    line = ""
                if line is None:
                    break
                if line.startswith(PROGRESS_PREFIX):
                    try:
                        event = json.loads(line[len(PROGRESS_PREFIX):])
                        if event.get("stage") == "images_found":
                            total_images = int(event["total"])
                        elif event.get("stage") == "image_done":
                            completed_images = int(event["completed"])
                        current = event
                    except (ValueError, TypeError, KeyError, AttributeError):
                        diagnostics.append(line.strip())
                    else:
                        report(changed=True)
                        last_report = time.monotonic()
                elif line.strip():
                    diagnostics.append(line.strip())
                if time.monotonic() - last_report >= 1:
                    report()
                    last_report = time.monotonic()
            returncode = process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()
            reader.join(timeout=2)
    return subprocess.CompletedProcess(command, returncode, "", "\n".join(diagnostics))


def _run_ocr_payload(arguments: list[str], progress: Callable[[str], None] | None = None,
                     status: Callable[[OCRProgress], None] | None = None) -> dict:
    ensure_ocr_environment(progress)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temporary:
        result_path = Path(temporary.name)
    try:
        process = _stream_worker([str(OCR_PYTHON), "-u", str(OCR_WORKER), *arguments,
                                  "--output", str(result_path)], progress, status)
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as ex:
            details = process.stderr.strip() or process.stdout.strip()
            raise RuntimeError(details or t("err_ocr_worker_failed")) from ex
        if error := payload.get("error"):
            raise RuntimeError(str(error))
        if process.returncode != 0:
            details = process.stderr.strip() or process.stdout.strip()
            raise RuntimeError(details or t("err_ocr_worker_failed"))
        return payload
    finally:
        result_path.unlink(missing_ok=True)


def _image_texts(payload: dict) -> list[dict[str, str]]:
    return [
        {"name": str(item["name"]), "text": str(item["text"])}
        for item in payload.get("images", []) if item.get("text")
    ]


def run_ocr_worker(arguments: list[str], progress: Callable[[str], None] | None = None) -> list[dict[str, str]]:
    return _image_texts(_run_ocr_payload(arguments, progress))


def convert_file_with_ocr(source_path: Path, progress: Callable[[str], None] | None = None,
                          status: Callable[[OCRProgress], None] | None = None) -> tuple[str, int]:
    """Read the document and OCR its images in a fresh, fully prepared project Python."""
    payload = _run_ocr_payload(["--source", str(source_path.resolve()), "--convert"], progress, status)
    if not isinstance(payload.get("markdown"), str):
        raise RuntimeError(t("err_ocr_worker_failed"))
    if "ocr_pages" in payload:
        return payload["markdown"], int(payload["ocr_pages"])
    return _append_image_texts(payload["markdown"], _image_texts(payload))


def extract_image_texts(source_path: Path, progress: Callable[[str], None] | None = None) -> list[dict[str, str]]:
    if source_path.suffix.lower() not in OCR_EXTENSIONS:
        return []
    return run_ocr_worker(["--source", str(source_path.resolve())], progress)


def append_image_ocr(
    markdown: str,
    source_path: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[str, int]:
    if progress:
        progress(f"OCR worker: {source_path.name}")

    images = extract_image_texts(source_path, progress)
    return _append_image_texts(markdown, images)


def _append_image_texts(markdown: str, images: list[dict[str, str]]) -> tuple[str, int]:
    if not images:
        return markdown, 0

    sections = [
        f"### {t('ocr_image', n=index)}\n\n{image['text']}"
        for index, image in enumerate(images, start=1)
    ]
    ocr_markdown = f"## {t('ocr_heading')}\n\n" + "\n\n".join(sections)
    return markdown.rstrip() + "\n\n" + ocr_markdown + "\n", len(sections)
