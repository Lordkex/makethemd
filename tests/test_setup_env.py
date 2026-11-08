import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import setup_env
from paddleocr_tools import ocr_utils


def installs(pip):
    return [call.args for call in pip.call_args_list]


class TorchChoiceTests(unittest.TestCase):
    def run_ensure(self, gpu, devices):
        with patch.object(setup_env, "torch_device", side_effect=devices), \
             patch.object(setup_env, "pip") as pip, patch("builtins.print"):
            setup_env.ensure_torch(gpu)
        return installs(pip)

    def test_gpu_machine_replaces_a_visible_cpu_torch(self):
        calls = self.run_ensure(True, ["cpu", "cuda"])
        self.assertEqual(len(calls), 1)
        self.assertIn("--force-reinstall", calls[0])
        self.assertIn("--no-deps", calls[0])
        self.assertIn(setup_env.TORCH_INDEX.format(build="cu128"), calls[0])

    def test_gpu_machine_without_torch_installs_cuda_with_dependencies(self):
        calls = self.run_ensure(True, [None, "cuda"])
        self.assertNotIn("--no-deps", calls[0])
        self.assertIn(setup_env.TORCH_INDEX.format(build="cu128"), calls[0])

    def test_no_gpu_installs_the_cpu_build(self):
        calls = self.run_ensure(False, [None])
        self.assertEqual(len(calls), 1)
        self.assertIn(setup_env.TORCH_INDEX.format(build="cpu"), calls[0])

    def test_gpu_build_that_cannot_use_the_card_falls_back_to_cpu(self):
        calls = self.run_ensure(True, ["cpu", "cpu"])
        self.assertEqual([call[-1] for call in calls],
                         [setup_env.TORCH_INDEX.format(build=b) for b in ("cu128", "cpu")])

    def test_matching_torch_is_left_alone(self):
        self.assertEqual(self.run_ensure(True, ["cuda"]), [])
        self.assertEqual(self.run_ensure(False, ["cpu"]), [])
        self.assertEqual(self.run_ensure(False, ["cuda"]), [])


class MainFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.venv = Path(temporary.name) / ".venv"
        self.venv.mkdir()
        for target, name, value in [
            (ocr_utils, "PROJECT_VENV", self.venv),
            (setup_env, "fingerprint", lambda: "hash"),
            (setup_env, "ensure_venv", lambda: None),
            (setup_env, "apply_saved_language", lambda: None),
        ]:
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, gpu=True, ensure=None, can_start=True):
        with patch.object(ocr_utils, "_cuda_gpu_available", return_value=gpu), \
             patch.object(setup_env, "ensure_torch", side_effect=ensure) as torch, \
             patch.object(setup_env, "pip") as pip, \
             patch.object(ocr_utils, "ensure_ocr_environment") as ocr, \
             patch.object(setup_env, "torch_device", return_value="cuda"), \
             patch.object(setup_env, "app_can_start", return_value=can_start), \
             patch("builtins.print"):
            code = setup_env.main()
        return code, torch, pip, ocr

    def test_first_run_sets_up_everything_and_records_it(self):
        code, torch, pip, ocr = self.run_main()
        self.assertEqual(code, 0)
        torch.assert_called_once_with(True)
        self.assertEqual(pip.call_count, 2)
        ocr.assert_called_once()
        self.assertEqual(setup_env.read_stamp(), {"packages": "hash", "gpu": True})

    def test_unchanged_environment_starts_immediately(self):
        setup_env.stamp_path().write_text(json.dumps({"packages": "hash", "gpu": True}))
        _, torch, pip, ocr = self.run_main()
        torch.assert_not_called()
        pip.assert_not_called()
        ocr.assert_not_called()

    def test_new_gpu_triggers_setup_again(self):
        setup_env.stamp_path().write_text(json.dumps({"packages": "hash", "gpu": False}))
        _, torch, _, _ = self.run_main(gpu=True)
        torch.assert_called_once_with(True)

    def test_offline_failure_is_retried_and_a_working_app_still_starts(self):
        code, _, _, _ = self.run_main(ensure=setup_env.SetupError("offline"))
        self.assertEqual(code, 0)
        self.assertIsNone(setup_env.read_stamp())

    def test_failed_first_install_stops_the_start(self):
        code, _, _, _ = self.run_main(ensure=setup_env.SetupError("offline"), can_start=False)
        self.assertEqual(code, 1)


class VenvCreationTests(unittest.TestCase):
    def test_new_venv_does_not_see_global_packages(self):
        with patch.object(setup_env, "venv_works", return_value=False), \
             patch.object(setup_env.sys, "version_info", (3, 12, 10)), \
             patch.object(setup_env.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch("builtins.print"):
            setup_env.ensure_venv()
        command = run.call_args.args[0]
        self.assertIn("venv", command)
        self.assertNotIn("--system-site-packages", command)

    def test_python_without_paddle_wheels_is_refused(self):
        with patch.object(setup_env, "venv_works", return_value=False), \
             patch.object(setup_env.sys, "version_info", (3, 14, 2)), \
             patch.object(setup_env.subprocess, "run") as run:
            with self.assertRaises(setup_env.SetupError):
                setup_env.ensure_venv()
        run.assert_not_called()

    def test_working_venv_is_not_touched(self):
        with patch.object(setup_env, "venv_works", return_value=True), \
             patch.object(setup_env.subprocess, "run") as run:
            setup_env.ensure_venv()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
