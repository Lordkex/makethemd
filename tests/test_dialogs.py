import ast
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from i18n import t


PROJECT = Path(app.__file__).resolve().parent
MODULES = ["app.py", "output_utils.py", "updater.py", "facebook_audio.py", "paddleocr_tools/ocr_utils.py"]


class DialogTests(unittest.TestCase):
    """A _pick külön szálon fut: a benne dobott kivétel nem jut el a hívóhoz, csak a konzolra ír."""

    def test_file_dialog_returns_selection_with_translated_title(self):
        with patch.object(app.tk, "Tk"), \
             patch.object(app.filedialog, "askopenfilenames", return_value=("a.pdf", "b.docx")) as ask:
            self.assertEqual(app.open_file_dialog(), [Path("a.pdf"), Path("b.docx")])
        self.assertEqual(ask.call_args.kwargs["title"], t("dlg_pick_files"))

    def test_folder_dialog_returns_selection_with_translated_title(self):
        with patch.object(app.tk, "Tk"), \
             patch.object(app.filedialog, "askdirectory", return_value="kimenet") as ask:
            self.assertEqual(app.open_folder_dialog(), Path("kimenet"))
        self.assertEqual(ask.call_args.kwargs["title"], t("dlg_output_folder"))

    def test_txt_dialog_returns_selection_with_translated_title(self):
        with patch.object(app.tk, "Tk"), \
             patch.object(app.filedialog, "askopenfilename", return_value="linkek.txt") as ask:
            self.assertEqual(app.open_txt_dialog(), Path("linkek.txt"))
        self.assertEqual(ask.call_args.kwargs["title"], t("dlg_link_list"))


class TranslatorShadowingTests(unittest.TestCase):
    def test_translator_names_are_never_reassigned(self):
        """Egy helyi `t = ...` a teljes függvényben (és a belső függvényekben) elfedi a t()-t."""
        names = {"t", "tn"}
        hits = []
        for module in MODULES:
            tree = ast.parse((PROJECT / module).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                stored = isinstance(node, ast.Name) and node.id in names and isinstance(node.ctx, ast.Store)
                param = isinstance(node, ast.arg) and node.arg in names
                if stored or param:
                    hits.append(f"{module}:{node.lineno}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
