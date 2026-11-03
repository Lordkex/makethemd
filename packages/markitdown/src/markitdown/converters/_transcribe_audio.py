import os
import re
import sys
import tempfile
from typing import BinaryIO, Callable
from .._exceptions import MissingDependencyException

_dependency_exc_info = None
try:
    import whisper
    import torch

    # Ampere (RTX 30xx+) optimalizáció
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True

except ImportError:
    _dependency_exc_info = sys.exc_info()

_model_cache: dict = {}

# tqdm sor formátuma: "10%|█░░| 1838/18868 [01:40<11:43, 242.07frames/s]"
_TQDM_RE = re.compile(
    r"(\d+)%.*?(\d+)/(\d+)\s*\[(\d+:\d+)<([\d:]+),\s*([\d.]+)\s*(?:frames)?/?(?:s|it/s)"
)


class _StderrInterceptor:
    """Stderr proxy: átengedi az eredeti kimenetet és parse-olja a tqdm sorokat."""

    def __init__(self, on_line: Callable[[str], None], original):
        self._on_line = on_line
        self._original = original
        self._buf = ""

    def write(self, text: str):
        self._original.write(text)
        self._buf += text
        while True:
            ir = self._buf.find("\r")
            in_ = self._buf.find("\n")
            if ir == -1 and in_ == -1:
                break
            idx = min(x for x in (ir, in_) if x >= 0)
            line = self._buf[:idx]
            self._buf = self._buf[idx + 1 :]
            self._on_line(line)

    def flush(self):
        self._original.flush()

    def __getattr__(self, name):
        return getattr(self._original, name)


def _get_model(model_size: str, device: str):
    key = (model_size, device)
    if key not in _model_cache:
        _model_cache[key] = whisper.load_model(model_size, device=device)
    return _model_cache[key]


def transcribe_audio(
    file_stream: BinaryIO,
    *,
    audio_format: str = "wav",
    language: str | None = None,
    model_size: str = "base",
    progress_fn: Callable[[str], None] | None = None,
) -> str:
    if _dependency_exc_info is not None:
        raise MissingDependencyException(
            "Audio transcription requires openai-whisper and torch. "
            "Install with: pip install openai-whisper torch"
        ) from _dependency_exc_info[1].with_traceback(_dependency_exc_info[2])  # type: ignore[union-attr]

    import time as _time

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dev_label = f"CUDA • {torch.cuda.get_device_name(0)}" if device == "cuda" else "CPU"
    print(f"[whisper] device={dev_label}  model={model_size}", flush=True)

    model = _get_model(model_size, device)
    print("[whisper] model loaded, transcribing...", flush=True)

    audio_bytes = file_stream.read()
    suffix = f".{audio_format}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    def _parse_line(line: str):
        line = line.strip()
        if not line or progress_fn is None:
            return
        m = _TQDM_RE.search(line)
        if m:
            pct, cur, total, elapsed, remaining, fps = m.groups()
            progress_fn(
                f"   ⟳  {pct}%  {cur}/{total}  [{elapsed} < {remaining}  {float(fps):.0f} fr/s]"
            )

    orig_stderr = sys.stderr
    if progress_fn:
        sys.stderr = _StderrInterceptor(_parse_line, orig_stderr)

    t0 = _time.monotonic()
    try:
        result = model.transcribe(
            tmp_path,
            language=language or None,
            fp16=(device == "cuda"),
            verbose=False,
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
            temperature=0,
        )
        transcript = (result.get("text") or "").strip()
        elapsed = _time.monotonic() - t0
        lang_det = result.get("language", "?")
        segs = len(result.get("segments", []))
        words = len(transcript.split())
        print(
            f"[whisper] done  {elapsed:.1f}s  language={lang_det}  {segs} segments  {words} words",
            flush=True,
        )
    finally:
        sys.stderr = orig_stderr
        os.unlink(tmp_path)

    return "[No speech detected]" if not transcript else transcript
