import string
import unittest

import i18n


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_every_key_exists_in_both_languages(self):
        # a `_one` alak csak angolban kell (a magyarban nincs külön egyes szám)
        hu = set(i18n.STRINGS["hu"])
        en = {key for key in i18n.STRINGS["en"] if not key.endswith("_one")}
        self.assertEqual(hu ^ en, set())

    def test_placeholders_match_between_languages(self):
        en = i18n.STRINGS["en"]
        for key, text in i18n.STRINGS["hu"].items():
            with self.subTest(key=key):
                self.assertEqual(placeholders(text), placeholders(en[key]))
                if key + "_one" in en:
                    self.assertLessEqual(placeholders(en[key + "_one"]), placeholders(en[key]))

    def test_plural_form_only_in_english(self):
        i18n.set_language("en")
        self.assertEqual(i18n.tn("links_loaded", 1), "1 link loaded")
        self.assertEqual(i18n.tn("links_loaded", 3), "3 links loaded")
        i18n.set_language("hu")
        self.assertEqual(i18n.tn("links_loaded", 1), "1 link betöltve")

    def test_unknown_language_falls_back_to_default(self):
        i18n.set_language("xx")
        self.assertEqual(i18n.get_language(), i18n.DEFAULT_LANGUAGE)


if __name__ == "__main__":
    unittest.main()
