import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import app
import updater


NOW = datetime(2026, 10, 25, 12, 0)


class ScheduleTests(unittest.TestCase):
    def test_weekly_check_and_forced_update(self):
        recent = (NOW - timedelta(days=2)).isoformat()
        old = (NOW - timedelta(days=8)).isoformat()
        self.assertFalse(updater.is_due({"last_update_check": recent}, NOW))
        self.assertTrue(updater.is_due({"last_update_check": old}, NOW))
        self.assertTrue(updater.is_due({}, NOW))
        self.assertTrue(updater.is_due({"last_update_check": recent, "force_update": True}, NOW))


class UpdateFlowTests(unittest.TestCase):
    def run_main(self, installed, latest, works, pip_ok=True):
        saved = {}
        with patch.object(updater, "load_settings", return_value={}), \
             patch.object(updater, "save_settings", side_effect=lambda **kw: saved.update(kw)), \
             patch.object(updater, "installed_version", side_effect=lambda n: installed[n]), \
             patch.object(updater, "latest_version", side_effect=latest), \
             patch.object(updater, "works", side_effect=works), \
             patch.object(updater, "pip_install", return_value=pip_ok) as pip, \
             patch("builtins.print"):
            updater.main()
        return pip, saved

    def test_up_to_date_does_not_touch_packages(self):
        installed = {"yt-dlp": "1", "yt-dlp-ejs": "1", "youtube-transcript-api": "1"}
        pip, saved = self.run_main(installed, lambda n: "1", works=[True])
        pip.assert_not_called()
        self.assertFalse(saved["force_update"])

    def test_broken_update_restores_previous_versions(self):
        installed = {"yt-dlp": "2026.6.9", "yt-dlp-ejs": "0.3", "youtube-transcript-api": "1.2.4"}
        pip, _ = self.run_main(installed, lambda n: "9", works=[False, True])
        self.assertEqual(pip.call_count, 2)
        self.assertIn("yt-dlp[default]", pip.call_args_list[0].args)
        self.assertEqual(set(pip.call_args_list[1].args),
                         {"yt-dlp==2026.6.9", "yt-dlp-ejs==0.3", "youtube-transcript-api==1.2.4"})

    def test_offline_skips_without_recording_the_check(self):
        installed = {"yt-dlp": "1", "yt-dlp-ejs": "1", "youtube-transcript-api": "1"}

        def offline(_name):
            raise OSError("nincs internet")

        pip, saved = self.run_main(installed, offline, works=[True])
        pip.assert_not_called()
        self.assertEqual(saved, {})


class OutdatedFlagTests(unittest.TestCase):
    def test_403_requests_update_once_but_ip_block_does_not(self):
        settings = {}
        with patch.object(app, "load_settings", side_effect=lambda: dict(settings)), \
             patch.object(app, "save_settings", side_effect=lambda **kw: settings.update(kw)):
            self.assertFalse(app.flag_update_if_outdated(RuntimeError("felirat-API blokk")))
            err = RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
            self.assertTrue(app.flag_update_if_outdated(err))
            self.assertFalse(app.flag_update_if_outdated(err))  # már kérve: nem jelez újra
        self.assertTrue(settings["force_update"])


if __name__ == "__main__":
    unittest.main()
