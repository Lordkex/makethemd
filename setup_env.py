"""A projekt .venv környezetének kialakítása és karbantartása indításkor.

A start_makethemd.bat futtatja az app előtt. Első induláskor (új gépen) létrehozza a
.venv-et, és a hardverhez illő motorokat telepíti: használható NVIDIA GPU esetén a CUDA-s
PyTorch és PaddlePaddle kerül fel, különben a CPU-s. Később csak akkor dolgozik, ha a
csomaglista vagy a GPU megléte változott; minden más indítás azonnal továbblép.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from i18n import t
from output_utils import apply_saved_language
from paddleocr_tools import ocr_utils

PROJECT_ROOT = ocr_utils.PROJECT_ROOT
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
MARKITDOWN = PROJECT_ROOT / "packages" / "markitdown"
STAMP_NAME = "makethemd-env.json"
# A PaddlePaddle-hez ezekre a Python-verziókra van Windows-wheel.
SUPPORTED_PYTHONS = ((3, 10), (3, 11), (3, 12), (3, 13))
TORCH_INDEX = "https://download.pytorch.org/whl/{build}"
_TORCH_PROBE = "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')"
_APP_PROBE = "import flet, markitdown"


class SetupError(RuntimeError):
    pass


def stamp_path() -> Path:
    return ocr_utils.PROJECT_VENV / STAMP_NAME


def venv_works() -> bool:
    if not ocr_utils.OCR_PYTHON.is_file():
        return False
    try:
        return ocr_utils._run_python("-c", "").returncode == 0
    except OSError:  # pl. másik gépről átmásolt .venv, amelynek az alap-Pythonja nincs meg
        return False


def ensure_venv() -> None:
    if venv_works():
        return
    if sys.version_info[:2] not in SUPPORTED_PYTHONS:
        raise SetupError(t("env_bad_python", version=sys.version.split()[0]))
    print(t("env_create"))
    # A globális csomagok nem látszódhatnak: egy ottani CPU-s torch elfedné a GPU-s telepítést.
    command = [sys.executable, "-m", "venv", "--clear", str(ocr_utils.PROJECT_VENV)]
    if subprocess.run(command, cwd=PROJECT_ROOT).returncode != 0:
        raise SetupError(t("env_create_failed"))


def pip(*arguments: str) -> None:
    """A kimenet a konzolra megy, hogy a több GB-os letöltés ne tűnjön lefagyásnak."""
    command = [str(ocr_utils.OCR_PYTHON), "-m", "pip", "--isolated", "--disable-pip-version-check",
               "--no-input", *arguments]
    if subprocess.run(command, cwd=PROJECT_ROOT).returncode != 0:
        raise SetupError(t("env_pip_failed", command=" ".join(arguments)))


def torch_device() -> str | None:
    """'cuda' vagy 'cpu' a .venv-ben betöltődő torch szerint; None, ha nem tölthető be."""
    probe = ocr_utils._run_python("-c", _TORCH_PROBE)
    words = probe.stdout.split()
    return words[-1] if probe.returncode == 0 and words else None


def install_torch(build: str, replace: bool) -> None:
    # Csak a --force-reinstall cseréli le a más buildet (a globálisat pedig a .venv-ben fedi el).
    extra = ["--no-deps"] if replace else []
    pip("install", "--force-reinstall", *extra, "torch", "--index-url", TORCH_INDEX.format(build=build))


def ensure_torch(gpu: bool) -> None:
    current = torch_device()
    if current == "cuda" or (current == "cpu" and not gpu):
        return
    print(t("env_torch_gpu" if gpu else "env_torch_cpu"))
    install_torch("cu128" if gpu else "cpu", replace=current is not None)
    if gpu and torch_device() != "cuda":
        print(t("env_torch_fallback"))
        install_torch("cpu", replace=True)


def fingerprint() -> str:
    digest = hashlib.sha256()
    for path in (REQUIREMENTS, ocr_utils.OCR_REQUIREMENTS, MARKITDOWN / "pyproject.toml"):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def read_stamp() -> dict | None:
    try:
        return json.loads(stamp_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def app_can_start() -> bool:
    try:
        return ocr_utils._run_python("-c", _APP_PROBE).returncode == 0
    except OSError:
        return False


def main() -> int:
    """0, ha az app elindítható; a részleges hibát a következő indítás újrapróbálja."""
    apply_saved_language()
    try:
        ensure_venv()
    except SetupError as error:
        print(t("env_failed", error=error))
        return 1

    gpu = ocr_utils._cuda_gpu_available()
    wanted = {"packages": fingerprint(), "gpu": gpu}
    if read_stamp() == wanted:
        return 0

    try:
        ensure_torch(gpu)
        print(t("env_deps"))
        pip("install", "-r", str(REQUIREMENTS))
        pip("install", "-e", f"{MARKITDOWN}[all]")
        ocr_utils.ensure_ocr_environment(print)
    except RuntimeError as error:  # a SetupError és az OCR-telepítés hibája is ilyen
        print(t("env_failed", error=error))
        return 0 if app_can_start() else 1

    stamp_path().write_text(json.dumps(wanted), encoding="utf-8")
    print(t("env_ready", device=torch_device() or "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
