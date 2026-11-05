import json
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from paddleocr_tools import ocr_utils as ocr


def result(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class OCRSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.venv = root / ".venv"
        self.python = self.venv / "Scripts" / "python.exe"
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        worker = root / "ocr_worker.py"
        worker.touch()
        for name, value in {
            "PROJECT_ROOT": root, "PROJECT_VENV": self.venv,
            "OCR_PYTHON": self.python, "OCR_WORKER": worker,
            "OCR_CACHE": root / ".ocr-cache", "_environment_ready": False,
        }.items():
            patcher = patch.object(ocr, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(ocr, "_cuda_gpu_available", return_value=False)
        self.gpu_available = patcher.start()
        self.addCleanup(patcher.stop)

    def test_cpu_paddle_moves_to_gpu_build_only_after_the_download_succeeded(self):
        self.gpu_available.return_value = True
        messages = []
        with patch.object(ocr, "_run_python", side_effect=[result("noise\nFalse\n"), result()]), \
             patch.object(ocr, "_install") as install:
            ocr._enable_gpu_ocr(messages.append)
        commands = [call.args[0] for call in install.call_args_list]
        self.assertEqual([command[6] for command in commands], ["download", "uninstall", "install"])
        self.assertIn(ocr._PADDLE_GPU_INDEX, commands[0])
        self.assertEqual(commands[1][-2:], ["paddlepaddle", "paddlepaddle-gpu"])
        self.assertIn("--no-index", commands[2])
        self.assertEqual(commands[2][-1], ocr._PADDLE_GPU_REQUIREMENT)
        self.assertEqual(messages, [ocr.t("log_ocr_gpu_install"), ocr.t("log_ocr_gpu_ready")])

    def test_failed_gpu_download_keeps_the_cpu_build_and_setup_continues(self):
        self.gpu_available.return_value = True
        messages = []
        with patch.object(ocr, "_run_python", return_value=result("False\n")), \
             patch.object(ocr, "_install", side_effect=RuntimeError("offline")) as install:
            ocr._enable_gpu_ocr(messages.append)
        install.assert_called_once()
        self.assertEqual(install.call_args.args[0][6], "download")
        self.assertIn("offline", messages[-1])

    def test_gpu_build_that_cannot_be_imported_is_replaced_by_the_cpu_build(self):
        self.gpu_available.return_value = True
        messages = []
        with patch.object(ocr, "_run_python", side_effect=[result("False\n"), result(returncode=1, stderr="DLL load failed")]), \
             patch.object(ocr, "_install") as install:
            ocr._enable_gpu_ocr(messages.append)
        commands = [call.args[0] for call in install.call_args_list]
        self.assertEqual([command[6] for command in commands], ["download", "uninstall", "install", "uninstall", "install"])
        self.assertEqual(commands[-1][-2:], ["-r", str(ocr.OCR_REQUIREMENTS)])
        self.assertIn("DLL load failed", messages[-1])

    def test_gpu_build_or_broken_paddle_is_not_swapped_again(self):
        self.gpu_available.return_value = True
        for probe in (result("True\n"), result(returncode=1, stderr="DLL load failed")):
            with patch.object(ocr, "_run_python", return_value=probe), patch.object(ocr, "_install") as install:
                ocr._enable_gpu_ocr(None)
            install.assert_not_called()

    def test_no_usable_gpu_never_inspects_or_changes_paddle(self):
        with patch.object(ocr, "_run_python") as run, patch.object(ocr, "_install") as install:
            ocr._enable_gpu_ocr(None)
        run.assert_not_called()
        install.assert_not_called()

    def test_environment_setup_includes_the_gpu_step(self):
        with patch.object(ocr, "_run_python", side_effect=[result("[]"), result()]), \
             patch.object(ocr, "_enable_gpu_ocr") as enable:
            ocr.ensure_ocr_environment()
        enable.assert_called_once()

    def test_existing_environment_does_not_install_and_is_checked_once(self):
        with patch.object(ocr, "_run_python", side_effect=[result("[]"), result()]) as run, \
             patch.object(ocr, "_install") as install:
            ocr.ensure_ocr_environment()
            ocr.ensure_ocr_environment()
        install.assert_not_called()
        self.assertEqual(run.call_count, 2)

    def test_missing_packages_install_in_project_python(self):
        messages = []
        with patch.object(ocr, "_run_python", side_effect=[result('["paddle"]'), result(), result()]), \
             patch.object(ocr, "_install") as install:
            ocr.ensure_ocr_environment(messages.append)
        command = install.call_args.args[0]
        self.assertEqual(command[:5], [str(self.python), "-m", "pip", "--isolated", "install"])
        self.assertEqual(command[-2:], ["-r", str(ocr.OCR_REQUIREMENTS)])
        self.assertTrue(messages)
        self.assertTrue(ocr._environment_ready)

    def test_missing_pip_is_bootstrapped(self):
        with patch.object(ocr, "_run_python", side_effect=[result('["paddle"]'), result(returncode=1), result()]), \
             patch.object(ocr, "_install") as install:
            ocr.ensure_ocr_environment()
        self.assertEqual(install.call_args_list[0].args[0],
                         [str(self.python), "-m", "ensurepip", "--upgrade"])
        self.assertEqual(install.call_count, 2)

    def test_missing_pdf_readers_trigger_setup_even_when_paddle_is_present(self):
        with patch.object(ocr, "_run_python", side_effect=[result('["pdfminer", "pdfplumber"]'), result(), result()]), \
             patch.object(ocr, "_install") as install:
            ocr.ensure_ocr_environment()
        install.assert_called_once()
        self.assertTrue(ocr._environment_ready)

    def test_failed_install_retries_on_next_request(self):
        with patch.object(ocr, "_run_python", side_effect=[result('["paddle"]'), result(),
                                                         result('["paddle"]'), result(), result()]), \
             patch.object(ocr, "_install", side_effect=[RuntimeError("offline"), None]) as install:
            with self.assertRaisesRegex(RuntimeError, "offline"):
                ocr.ensure_ocr_environment()
            self.assertFalse(ocr._environment_ready)
            ocr.ensure_ocr_environment()
        self.assertEqual(install.call_count, 2)

    def test_installer_streams_output_and_reports_pip_failure(self):
        process = MagicMock()
        process.__enter__.return_value = process
        process.stdout = io.StringIO("Downloading packages\nERROR: connection refused\n")
        process.wait.return_value = 1
        messages = []
        with patch.object(ocr.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "ERROR: connection refused"):
                ocr._install([str(self.python), "-m", "pip"], messages.append)
        self.assertEqual(messages, ["Downloading packages", "ERROR: connection refused"])

    def test_missing_transitive_dependency_also_installs(self):
        with patch.object(ocr, "_run_python", side_effect=[result("[]"),
                result(returncode=42, stderr="No module named dependency"), result(), result()]), \
             patch.object(ocr, "_install") as install:
            ocr.ensure_ocr_environment()
        install.assert_called_once()

    def test_broken_dll_is_reported_without_reinstall_loop(self):
        with patch.object(ocr, "_run_python", side_effect=[result("[]"),
                result(returncode=1, stderr="DLL load failed")]), patch.object(ocr, "_install") as install:
            with self.assertRaisesRegex(RuntimeError, "DLL load failed"):
                ocr.ensure_ocr_environment()
        install.assert_not_called()
        self.assertFalse(ocr._environment_ready)

    def test_absent_venv_is_created_but_incomplete_venv_is_not_overwritten(self):
        self.python.unlink()
        with patch.object(ocr, "_install") as install:
            with self.assertRaises(RuntimeError):
                ocr.ensure_ocr_environment()
        install.assert_not_called()
        self.python.parent.rmdir()
        self.venv.rmdir()

        def create(command, progress):
            self.assertEqual(command[1:], ["-m", "venv", "--system-site-packages", str(self.venv)])
            self.python.parent.mkdir(parents=True)
            self.python.touch()

        with patch.object(ocr, "_install", side_effect=create), \
             patch.object(ocr, "_run_python", side_effect=[result("[]"), result()]):
            ocr.ensure_ocr_environment()
        self.assertTrue(self.python.is_file())

    def test_unsupported_file_does_not_prepare_ocr(self):
        with patch.object(ocr, "ensure_ocr_environment") as setup:
            self.assertEqual(ocr.append_image_ocr("markdown", Path("audio.mp3")), ("markdown", 0))
        setup.assert_not_called()

    def test_worker_startup_error_preserves_stderr_and_cleans_result_file(self):
        output_paths = []

        def fail(command, *args, **kwargs):
            output_paths.append(Path(command[command.index("--output") + 1]))
            return result(returncode=1, stderr="ImportError: missing runtime")

        with patch.object(ocr, "ensure_ocr_environment"), patch.object(ocr, "_stream_worker", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "ImportError: missing runtime"):
                ocr.run_ocr_worker(["--self-test"])
        self.assertFalse(output_paths[0].exists())

    def test_worker_result_is_appended_to_markdown(self):
        def recognize(command, *args, **kwargs):
            output = Path(command[command.index("--output") + 1])
            output.write_text(json.dumps({"images": [{"name": "image.png", "text": "OCR 123"}]}))
            return result()

        with patch.object(ocr, "ensure_ocr_environment"), patch.object(ocr, "_stream_worker", side_effect=recognize):
            markdown, count = ocr.append_image_ocr("original", Path("image.png"))
        self.assertEqual(count, 1)
        self.assertTrue(markdown.startswith("original\n\n"))
        self.assertIn("OCR 123", markdown)

    def test_document_conversion_waits_for_setup_and_uses_fresh_worker(self):
        events = []

        def recognize(command, *args, **kwargs):
            events.append("worker")
            self.assertIn("--convert", command)
            output = Path(command[command.index("--output") + 1])
            output.write_text(json.dumps({"markdown": "PDF text", "images": [{"name": "scan", "text": "OCR 123"}]}))
            return result()

        with patch.object(ocr, "ensure_ocr_environment", side_effect=lambda progress: events.append("setup")), \
             patch.object(ocr, "_stream_worker", side_effect=recognize):
            markdown, count = ocr.convert_file_with_ocr(Path("document.pdf"))
        self.assertEqual(events, ["setup", "worker"])
        self.assertTrue(markdown.startswith("PDF text\n\n"))
        self.assertIn("OCR 123", markdown)
        self.assertEqual(count, 1)

    def test_document_setup_failure_does_not_start_conversion(self):
        with patch.object(ocr, "ensure_ocr_environment", side_effect=RuntimeError("offline")), \
             patch.object(ocr, "_stream_worker") as worker:
            with self.assertRaisesRegex(RuntimeError, "offline"):
                ocr.convert_file_with_ocr(Path("document.pdf"))
        worker.assert_not_called()

    def test_pdf_pages_are_not_appended_again_as_image_ocr(self):
        payload = {"markdown": "page one\npage two OCR", "ocr_pages": 1,
                   "images": [{"name": "duplicate", "text": "page two OCR"}]}
        with patch.object(ocr, "_run_ocr_payload", return_value=payload):
            markdown, count = ocr.convert_file_with_ocr(Path("book.pdf"))
        self.assertEqual(count, 1)
        self.assertEqual(markdown.count("page two OCR"), 1)


class CudaDetectionTests(unittest.TestCase):
    def test_only_a_driver_new_enough_for_the_paddle_build_counts(self):
        cases = [(result("610.88\n"), True), (result("560.76\n"), True), (result("471.41\n"), False),
                 (result("", returncode=9), False), (result("unexpected\n"), False)]
        for probe, expected in cases:
            with patch.object(ocr.subprocess, "run", return_value=probe):
                self.assertEqual(ocr._cuda_gpu_available(), expected, probe.stdout)

    def test_missing_or_hanging_nvidia_smi_means_no_gpu(self):
        for failure in (FileNotFoundError(), subprocess.TimeoutExpired("nvidia-smi", 15)):
            with patch.object(ocr.subprocess, "run", side_effect=failure):
                self.assertFalse(ocr._cuda_gpu_available())


if __name__ == "__main__":
    unittest.main()
