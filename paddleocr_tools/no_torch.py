"""Import this first in every process that loads Paddle.

Torch and Paddle ship different CUDA DLLs under the same names, so one process can only load
one of them (WinError 127). The app process owns Torch (Whisper); OCR processes only need Paddle,
but PaddleOCR and MarkItDown import Torch when it is installed. This makes Torch look not
installed: ``sys.modules["torch"] = None`` would crash SciPy, and a finder that raises would crash
ModelScope's ``importlib.util.find_spec("torch")``.
"""
import sys
from importlib.machinery import PathFinder


class _PathFinderWithoutTorch(PathFinder):
    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        if fullname.partition(".")[0] == "torch":
            return None
        return super().find_spec(fullname, path, target)


if PathFinder in sys.meta_path:
    sys.meta_path[sys.meta_path.index(PathFinder)] = _PathFinderWithoutTorch
