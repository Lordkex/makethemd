"""A felület szövegei magyarul és angolul.

A `t(kulcs, **paraméterek)` az aktuális nyelven adja vissza a szöveget; ha egy kulcs
csak angolul létezik, az angol változat jelenik meg. A `tn` darabszámtól függően
választ (angolban „1 link” / „3 links”, a magyarban nincs külön alak).
"""
from __future__ import annotations

import locale

LANGUAGES = ("hu", "en")
DEFAULT_LANGUAGE = "en"

STRINGS: dict[str, dict[str, str]] = {
    "hu": {
        # fájlválasztók
        "dlg_pick_files": "Fájl kiválasztása",
        "dlg_output_folder": "Kimeneti mappa kiválasztása",
        "dlg_link_list": "Linklista kiválasztása",
        "ft_all_supported": "Minden támogatott",
        "ft_ebook": "E-könyv",
        "ft_text_file": "Szövegfájl",
        "ft_all_files": "Minden fájl",

        # fejléc
        "header_title": "Konvertálható",
        "header_subtitle": "fájlok és linkek",
        "formats_title": "Konvertálható fájltípusok",
        "fmt_documents": "Dokumentumok",
        "fmt_spreadsheets": "Táblázatok",
        "fmt_web": "Webfájlok és szöveg",
        "fmt_ebooks": "E-könyvek",
        "fmt_notebooks": "Notebook és adatok",
        "fmt_images": "Képek",
        "fmt_audio": "Hangfájlok",
        "fmt_outlook": "Outlook-üzenetek",
        "fmt_archives": "Archívumok",
        "tip_tiktok": "TikTok · videók",
        "tip_youtube": "YouTube · videók és feliratok",
        "tip_facebook": "Facebook · videók és Reels · fb.watch",
        "tip_instagram": "Instagram · videók és Reels",
        "tip_x": "X / Twitter · videók",
        "lang_switch_tip": "A felület nyelve",
        "lang_switch_busy": "A nyelv a konvertálás befejezése után váltható.",

        # források
        "sec_files": "Fájlok",
        "btn_pick_files": "Fájlok kiválasztása",
        "btn_clear_files": "Fájlok törlése",
        "sec_links": "Linkek",
        "links_loaded": "{n} link betöltve",
        "btn_load_links": "Linklista (.txt) betöltése",
        "btn_clear_links": "Linkek törlése",
        "btn_retry": "Újrapróbálás",
        "btn_retry_n": "Újrapróbálás ({n})",
        "retry_tip": "A kimeneti mappa korábban sikertelen linkjeinek visszatöltése ({name})",
        "links_hint": "Egy vagy több videólink, soronként egy, pl.\n"
                      "https://www.youtube.com/watch?v=…\nhttps://www.tiktok.com/@…/video/…",

        # kimenet és beállítások
        "sec_output": "Kimenet és beállítások",
        "btn_output_folder": "Kimenet mappa",
        "ocr_label": "OCR képekből helyileg",
        "audio_language": "Nyelv (audio)",
        "auto_detect": "Automatikus",
        "whisper_model": "Whisper modell",
        "model_tiny_gpu": "leggyorsabb, gyengébb",
        "model_base_gpu": "gyors",
        "model_small_gpu": "közepes",
        "model_medium_gpu": "lassabb, pontosabb",
        "model_turbo_gpu": "ajánlott",
        "model_large_gpu": "legjobb, leglassabb",
        "model_tiny_cpu": "nagyon gyors",
        "model_base_cpu": "gyors",
        "model_small_cpu": "lassabb, pontosabb",
        "model_turbo_cpu": "pontos, CPU-n lassú",
        "device_no_whisper": "CPU (whisper nincs telepítve)",
        "eta_recalc": "ETA újraszámítása",
        "eta_unknown": "(ismeretlen hossz)",
        "eta_total": "Összesen: {eta}",
        "dur_sec": "~{n} mp",
        "dur_min": "~{n} perc",
        "dur_hm": "~{h} óra {m} perc",

        # konvertálás és napló
        "btn_convert": "Konvertálás",
        "sec_log": "Napló",
        "copy_tip": "Másolás vágólapra",
        "copied": "kimásolva vágólapra",
        "method_captions": "[felirat]",
        "method_whisper": "[whisper]",
        "log_retry_loaded": "↻  {n} sikertelen link visszatöltve a linklistába ({name}) – indítsd a Konvertálást.",
        "log_outdated": "↻  A hiba elavult letöltőre utal – a következő indításkor "
                        "(start_makethemd.bat) automatikusan frissítem a yt-dlp-t.",
        "log_ocr_failed": "PaddleOCR nem indítható: {error}",
        "log_ocr_setup": "Lásd a README „Local image OCR” szakaszát.",
        "log_yt_pause": "szünet a YouTube-kérések között ({n} mp)...",
        "log_yt_blocked": "⏸  A YouTube letiltotta a felirat-kéréseket – a lista további YouTube-linkjeit "
                          "most nem kérem le, hogy ne hosszabbodjon a tiltás. Elhalasztva, később "
                          "az „Újrapróbálás” gombbal folytathatod.",
        "log_skipped_exists": "(kihagyva, a kimeneti fájl már létezik)",
        "log_audio_eta": "becsült: {eta}",
        "log_starting": "indul...",
        "log_ocr_images": "  OCR: {n} képből került szöveg a kimenetbe.",
        "log_ocr_none": "  OCR: nem található kiolvasható szöveget tartalmazó kép.",
        "log_duplicates": "⏭  {n} ismétlődő link a listában – mindegyiket csak egyszer dolgozom fel.",
        "log_already_done": "(már megvan, kihagyva)",
        "reason_deferred": "elhalasztva: a YouTube ebben a futásban letiltotta a felirat-kéréseket",
        "log_deferred": "(YouTube-tiltás miatt elhalasztva)",
        "log_nothing_selected": "Nincs kiválasztott fájl vagy URL.",
        "log_summary": "Kész: {ok} sikeres, {errors} hiba{deferred}{skipped}  →  {folder}",
        "log_summary_deferred": ", {n} elhalasztva",
        "log_summary_skipped": ", {n} kihagyva",
        "log_errors_warning": "⚠  {n} elem nem készült el (lásd a fenti ✗ sorokat) – "
                              "ezekhez nem jött létre valós átirat.",
        "log_failed_saved": "↻  A sikertelen-listán összesen {n} link van (a korábbi futásokból is): {path}\n"
                            "   Később az „Újrapróbálás” gombbal visszatöltheted őket.",

        # Whisper-ajánlat a futás végén
        "wb_downloading": "hang letöltése...",
        "wb_done": "Whisper-átírás kész: {ok} sikeres, {errors} hiba",
        "wd_title": "Átírás Whisperrel?",
        "wd_intro": "{n} videóhoz nem készült átirat. "
                    "Jelöld ki, melyeket írja át a Whisper (hang letöltése + helyi átírás):",
        "wd_eta": "átírás {eta}",
        "wd_unknown": "ismeretlen hossz",
        "wd_long": "Az 1 óránál hosszabb videók alapból nincsenek kijelölve.",
        "wd_cancel": "Mégse",
        "wd_start": "Átírás",
        "wd_skipped": "Whisper-átírás kihagyva.",
        "wd_none_selected": "Nem volt kijelölt videó, a Whisper-átírás elmaradt.",

        # hibák és folyamatjelzések a letöltőkből
        "err_no_info": "nem sikerült átiratot lekérni, és a videó adatai sem érhetők el. "
                       "Lehet, hogy a videó privát, törölt vagy korhatáros, esetleg a "
                       "YouTube átmenetileg blokkolja a kéréseket erről a hálózatról.",
        "err_no_captions": "a videónak NINCS FELIRATA a YouTube-on (se kézi, se automatikus), "
                           "ezért nem készült átirat. Whisper-átírással viszont elkészíthető.",
        "err_captions_blocked": "a videónak van felirata, de a YouTube felirat-API nem adta ki – "
                                "valószínűleg túl sok kérés miatt átmenetileg blokkolta az IP-címedet. "
                                "Válts hálózatot vagy várj néhány órát; a Whisper-átírás így is működik.",
        "env_create": "Első indítás: a projektkörnyezet (.venv) létrehozása…",
        "env_create_failed": "A .venv környezet nem hozható létre.",
        "env_bad_python": "A Python {version} nem használható a projektkörnyezethez: telepítsd a Python 3.12-t.",
        "env_torch_gpu": "NVIDIA GPU észlelve: a PyTorch GPU-s (CUDA) változatának egyszeri letöltése, kb. 3 GB…",
        "env_torch_cpu": "Nincs használható NVIDIA GPU: a PyTorch CPU-s változatának telepítése…",
        "env_torch_fallback": "A GPU-s PyTorch nem tudja használni ezt a kártyát, marad a CPU-s változat.",
        "env_deps": "A program csomagjainak ellenőrzése és telepítése…",
        "env_pip_failed": "a pip parancs nem sikerült: {command}",
        "env_failed": "A környezet beállítása nem sikerült, a következő indításkor újrapróbálom: {error}",
        "env_ready": "A projektkörnyezet kész ({device}).",
        "err_transcript_lib_missing": "a felirat lekéréséhez szükséges youtube-transcript-api csomag hiányzik ebből a "
                                      "Python-környezetből, ezért nem készült átirat. A következő indításkor a program "
                                      "automatikusan telepíti; addig a Whisper-átírás használható.",
        "err_no_media": "A letöltő nem adott médiafájlt.",
        "err_media_missing": "A letöltött médiafájl nem található vagy üres.",
        "err_no_transcript": "A hangletöltés után nem készült átirat; a kimenet nem lett elmentve.",
        "prog_captions": "Felirat keresése...",
        "prog_no_captions": "Nincs felirat, hang letöltése...",
        "prog_fb_to_mp3": "Facebook-hangsáv átalakítása MP3-má...",
        "prog_fdown_fallback": "A közvetlen letöltés nem sikerült; ingyenes FDOWN tartalékletöltő indul...",
        "fdown_searching": "FDOWN: Facebook-hangsáv keresése...",
        "fdown_downloading": "FDOWN: hang letöltése...",
        "fdown_downloading_proxy": "FDOWN: hang letöltése proxyn keresztül...",
        "fdown_converting": "FDOWN: hangsáv átalakítása MP3-má...",
        "err_ffmpeg_missing": "Az MP3 előállításához ffmpeg szükséges; nem található a PATH-on.",
        "err_mp3_failed": "Nem sikerült MP3-hangot kinyerni: {details}",
        "err_fdown_facebook_only": "A FDOWN tartalékletöltő csak Facebook-linket fogad el.",
        "err_fdown_bad_response": "A FDOWN hibás választ adott a hangsáv lekérésére.",
        "err_fdown_failed": "A FDOWN nem tudta lekérni a videót: {message}",
        "err_fdown_no_content": "nincs letölthető tartalom",
        "err_fdown_no_formats": "A FDOWN válaszából hiányoznak a letöltési formátumok.",
        "err_fdown_no_audio": "A FDOWN nem adott letölthető hangsávot; a videó lehet privát vagy törölt.",
        "err_fdown_text": "A letöltő médiafájl helyett szöveges választ adott.",
        "err_fdown_all_failed": "A Facebook-hang letöltése a FDOWN szolgáltatóval sem sikerült: {error}",

        # OCR
        "err_ocr_env": "A projekt .venv környezete hiányos: {path}. Javítsd vagy hozd létre újra a projektkörnyezetet.",
        "err_ocr_install": "Az OCR-függőségek telepítése nem sikerült. Ellenőrizd az internetkapcsolatot és "
                           "a projekt Python-verziójának kompatibilitását. A következő OCR-kérés újrapróbálja.\n{error}",
        "err_ocr_import": "Az OCR-csomagok nem tölthetők be a projekt .venv környezetében:\n{error}",
        "log_ocr_create_env": "OCR: a projekt .venv környezetének létrehozása…",
        "log_ocr_check": "OCR: a projektkörnyezet függőségeinek ellenőrzése…",
        "log_ocr_prepare": "OCR és dokumentumolvasás előkészítése. A konvertálás megvárja a telepítés befejezését…",
        "log_ocr_install": "OCR: hiányzó függőségek telepítése a .venv környezetbe ({packages}). Ez több percig tarthat…",
        "log_ocr_gpu_install": "OCR: NVIDIA GPU észlelve. A GPU-s futtatókörnyezet egyszeri letöltése (kb. 3 GB), "
                               "ez több percig tarthat…",
        "log_ocr_gpu_ready": "OCR: a felismerés mostantól a GPU-n fut.",
        "log_ocr_gpu_skipped": "OCR: a GPU-s futtatókörnyezet nem telepíthető, ezért a felismerés CPU-n fut "
                               "(sűrű oldalanként kb. egy perc): {error}",
        "log_ocr_ready": "OCR: a projektkörnyezet használatra kész.",
        "log_ocr_models": "OCR-felismerés indul. Első használatkor a szükséges modellek letöltése több percig tarthat…",
        "err_ocr_worker_missing": "Az OCR worker nem található: {path}",
        "err_ocr_worker_failed": "Az OCR worker hibával leállt.",
        "ocr_heading": "OCR-rel kinyert szöveg képekből",
        "ocr_image": "Kép {n}",
        "ocr_progress_starting": "Feldolgozás indítása…",
        "ocr_progress_reading": "Dokumentum szövegének kiolvasása…",
        "ocr_progress_finding": "Képek keresése a dokumentumban…",
        "ocr_progress_scan": "Képek keresése: {done}/{total} oldal",
        "ocr_progress_found": "{total} kép vár feldolgozásra.",
        "ocr_progress_models": "OCR-modellek betöltése; első alkalommal letöltés is szükséges lehet…",
        "ocr_progress_images": "OCR: {done}/{total} kép kész · {name}",
        "ocr_progress_done": "OCR-feldolgozás kész.",
        "ocr_progress_failed": "Az OCR-feldolgozás megszakadt; a részletek a naplóban láthatók.",
        "ocr_progress_elapsed": "{message} · Eltelt idő: {time}",
        "pdf_page_heading": "PDF-oldal {page}",
        "pdf_progress_page": "{page}/{total}. oldal · {action}",
        "pdf_progress_reading": "szöveg ellenőrzése",
        "pdf_progress_ocr": "teljes oldal OCR-felismerése",
        "pdf_progress_images": "az oldal ábráinak OCR-felismerése",
        "pdf_progress_cached": "OCR betöltve a gyorsítótárból",
        "pdf_progress_text": "szöveg kiolvasva",
        "err_pdf_page_ocr": "A(z) {page}. PDF-oldalról nem sikerült használható szöveget felismerni.",
        "err_pdf_page_failed": "A(z) {page}. PDF-oldal feldolgozása nem sikerült: {error}",
        "log_ocr_pages": "  PDF: {n} oldal szövege teljesoldalas OCR-rel került a kimenetbe.",
        "log_pdf_text_ok": "  PDF: az oldalak szövege közvetlenül kiolvasható volt; teljesoldalas OCR nem kellett.",

        # kimeneti fájlok
        "failed_header": "# MakeThemd – sikertelen linkek\n"
                         "# Az app „Újrapróbálás” gombja innen tölti vissza őket a linklistába;\n"
                         "# ami később elkészül, automatikusan lekerül innen.\n",
        "exists_title": "Kimeneti fájl már létezik",
        "exists_body": "A(z) {name} fájl már létezik.\n\n"
                       "Igen: felülírás\nNem: mentés új néven\nMégse: kihagyás",

        # frissítő (konzol)
        "upd_skipped": "Frissítés-ellenőrzés kihagyva (nincs internet vagy nem érhető el a PyPI).",
        "upd_updating": "Letöltő-csomagok frissítése: {names} ...",
        "upd_done": "Kész: {versions}",
        "upd_broken": "A frissített csomag nem működik, visszaállítom az előző verziót: {versions}",
        "upd_restored": "Visszaállítva, az előző verzióval indul az app.",
        "upd_restore_failed": "A visszaállítás sem sikerült. Kézzel: py -3 -m pip install -U \"yt-dlp[default]\"",
    },
    "en": {
        "dlg_pick_files": "Select files",
        "dlg_output_folder": "Select output folder",
        "dlg_link_list": "Select link list",
        "ft_all_supported": "All supported",
        "ft_ebook": "E-book",
        "ft_text_file": "Text file",
        "ft_all_files": "All files",

        "header_title": "Converts",
        "header_subtitle": "files and links",
        "formats_title": "Supported file types",
        "fmt_documents": "Documents",
        "fmt_spreadsheets": "Spreadsheets",
        "fmt_web": "Web files and text",
        "fmt_ebooks": "E-books",
        "fmt_notebooks": "Notebooks and data",
        "fmt_images": "Images",
        "fmt_audio": "Audio files",
        "fmt_outlook": "Outlook messages",
        "fmt_archives": "Archives",
        "tip_tiktok": "TikTok · videos",
        "tip_youtube": "YouTube · videos and captions",
        "tip_facebook": "Facebook · videos and Reels · fb.watch",
        "tip_instagram": "Instagram · videos and Reels",
        "tip_x": "X / Twitter · videos",
        "lang_switch_tip": "Interface language",
        "lang_switch_busy": "The language can be changed once the conversion has finished.",

        "sec_files": "Files",
        "btn_pick_files": "Select files",
        "btn_clear_files": "Clear files",
        "sec_links": "Links",
        "links_loaded_one": "{n} link loaded",
        "links_loaded": "{n} links loaded",
        "btn_load_links": "Load link list (.txt)",
        "btn_clear_links": "Clear links",
        "btn_retry": "Retry failed",
        "btn_retry_n": "Retry failed ({n})",
        "retry_tip": "Reload the links that failed earlier in the output folder ({name})",
        "links_hint": "One or more video links, one per line, e.g.\n"
                      "https://www.youtube.com/watch?v=…\nhttps://www.tiktok.com/@…/video/…",

        "sec_output": "Output and settings",
        "btn_output_folder": "Output folder",
        "ocr_label": "Local OCR for images",
        "audio_language": "Audio language",
        "auto_detect": "Auto-detect",
        "whisper_model": "Whisper model",
        "model_tiny_gpu": "fastest, less precise",
        "model_base_gpu": "fast",
        "model_small_gpu": "balanced",
        "model_medium_gpu": "slower, more precise",
        "model_turbo_gpu": "recommended",
        "model_large_gpu": "slowest, best quality",
        "model_tiny_cpu": "very fast",
        "model_base_cpu": "fast",
        "model_small_cpu": "slower, more precise",
        "model_turbo_cpu": "precise, slow on CPU",
        "device_no_whisper": "CPU (Whisper not installed)",
        "eta_recalc": "Recalculate ETA",
        "eta_unknown": "(unknown length)",
        "eta_total": "Total: {eta}",
        "dur_sec": "~{n} s",
        "dur_min": "~{n} min",
        "dur_hm": "~{h} h {m} min",

        "btn_convert": "Convert",
        "sec_log": "Log",
        "copy_tip": "Copy to clipboard",
        "copied": "copied to clipboard",
        "method_captions": "[captions]",
        "method_whisper": "[whisper]",
        "log_retry_loaded": "↻  {n} failed links reloaded into the link list ({name}) – press Convert.",
        "log_retry_loaded_one": "↻  1 failed link reloaded into the link list ({name}) – press Convert.",
        "log_outdated": "↻  The error suggests an outdated downloader – yt-dlp will be updated "
                        "automatically on the next start (start_makethemd.bat).",
        "log_ocr_failed": "PaddleOCR could not start: {error}",
        "log_ocr_setup": "See the “Local image OCR” section of the README.",
        "log_yt_pause": "pausing between YouTube requests ({n} s)...",
        "log_yt_blocked": "⏸  YouTube blocked caption requests – the remaining YouTube links in the list "
                          "are not requested now so the block does not get longer. They are deferred; "
                          "continue later with the “Retry failed” button.",
        "log_skipped_exists": "(skipped, output file already exists)",
        "log_audio_eta": "est. {eta}",
        "log_starting": "starting...",
        "log_ocr_images_one": "  OCR: text from 1 image added to the output.",
        "log_ocr_images": "  OCR: text from {n} images added to the output.",
        "log_ocr_none": "  OCR: no image with readable text was found.",
        "log_duplicates_one": "⏭  1 duplicate link in the list – each link is processed only once.",
        "log_duplicates": "⏭  {n} duplicate links in the list – each link is processed only once.",
        "log_already_done": "(already done, skipped)",
        "reason_deferred": "deferred: YouTube blocked caption requests during this run",
        "log_deferred": "(deferred because of a YouTube block)",
        "log_nothing_selected": "No files or URLs selected.",
        "log_summary": "Done: {ok} succeeded, {errors} failed{deferred}{skipped}  →  {folder}",
        "log_summary_deferred": ", {n} deferred",
        "log_summary_skipped": ", {n} skipped",
        "log_errors_warning_one": "⚠  1 item was not completed (see the ✗ line above) – "
                                  "no real transcript was created for it.",
        "log_errors_warning": "⚠  {n} items were not completed (see the ✗ lines above) – "
                              "no real transcript was created for them.",
        "log_failed_saved_one": "↻  1 failed link saved to: {path}\n"
                                "   Reload it later with the “Retry failed” button.",
        "log_failed_saved": "↻  The failed list now holds {n} links (including earlier runs): {path}\n"
                            "   Reload them later with the “Retry failed” button.",

        "wb_downloading": "downloading audio...",
        "wb_done": "Whisper transcription finished: {ok} succeeded, {errors} failed",
        "wd_title": "Transcribe with Whisper?",
        "wd_intro_one": "1 video has no transcript. "
                        "Select it to transcribe with Whisper (audio download + local transcription):",
        "wd_intro": "{n} videos have no transcript. "
                    "Select the ones to transcribe with Whisper (audio download + local transcription):",
        "wd_eta": "transcribe {eta}",
        "wd_unknown": "unknown length",
        "wd_long": "Videos longer than 1 hour are not selected by default.",
        "wd_cancel": "Cancel",
        "wd_start": "Transcribe",
        "wd_skipped": "Whisper transcription skipped.",
        "wd_none_selected": "No video was selected, Whisper transcription skipped.",

        "err_no_info": "could not fetch a transcript, and the video details are unavailable too. "
                       "The video may be private, deleted or age-restricted, or YouTube may be "
                       "temporarily blocking requests from this network.",
        "err_no_captions": "the video has NO CAPTIONS on YouTube (neither manual nor automatic), "
                           "so no transcript was created. It can still be transcribed with Whisper.",
        "err_captions_blocked": "the video has captions, but the YouTube caption API did not serve them – "
                                "your IP address is probably blocked temporarily after too many requests. "
                                "Switch networks or wait a few hours; Whisper transcription still works.",
        "env_create": "First start: creating the project environment (.venv)…",
        "env_create_failed": "Could not create the .venv environment.",
        "env_bad_python": "Python {version} cannot be used for the project environment: install Python 3.12.",
        "env_torch_gpu": "NVIDIA GPU detected: downloading the GPU (CUDA) build of PyTorch once, about 3 GB…",
        "env_torch_cpu": "No usable NVIDIA GPU: installing the CPU build of PyTorch…",
        "env_torch_fallback": "The GPU build of PyTorch cannot use this card, keeping the CPU build.",
        "env_deps": "Checking and installing the app's packages…",
        "env_pip_failed": "the pip command failed: {command}",
        "env_failed": "Environment setup failed, it will be retried at the next start: {error}",
        "env_ready": "The project environment is ready ({device}).",
        "err_transcript_lib_missing": "the youtube-transcript-api package needed for captions is missing from this "
                                      "Python environment, so no transcript was created. The app installs it "
                                      "automatically at the next start; Whisper transcription works until then.",
        "err_no_media": "The downloader returned no media file.",
        "err_media_missing": "The downloaded media file is missing or empty.",
        "err_no_transcript": "No transcript was created from the downloaded audio; nothing was saved.",
        "prog_captions": "Looking for captions...",
        "prog_no_captions": "No captions, downloading audio...",
        "prog_fb_to_mp3": "Converting the Facebook audio to MP3...",
        "prog_fdown_fallback": "Direct download failed; starting the free FDOWN fallback...",
        "fdown_searching": "FDOWN: looking for the Facebook audio track...",
        "fdown_downloading": "FDOWN: downloading audio...",
        "fdown_downloading_proxy": "FDOWN: downloading audio via proxy...",
        "fdown_converting": "FDOWN: converting the audio track to MP3...",
        "err_ffmpeg_missing": "ffmpeg is required to create the MP3, but it was not found on the PATH.",
        "err_mp3_failed": "Could not extract MP3 audio: {details}",
        "err_fdown_facebook_only": "The FDOWN fallback only accepts Facebook links.",
        "err_fdown_bad_response": "FDOWN returned an invalid response for the audio request.",
        "err_fdown_failed": "FDOWN could not fetch the video: {message}",
        "err_fdown_no_content": "no downloadable content",
        "err_fdown_no_formats": "The FDOWN response contains no download formats.",
        "err_fdown_no_audio": "FDOWN returned no downloadable audio; the video may be private or deleted.",
        "err_fdown_text": "The downloader returned a text response instead of a media file.",
        "err_fdown_all_failed": "Downloading the Facebook audio via FDOWN failed as well: {error}",

        "err_ocr_env": "The project .venv is incomplete: {path}. Repair or recreate the project environment.",
        "err_ocr_install": "Could not install the OCR dependencies. Check your internet connection and "
                           "project Python version compatibility. The next OCR request will retry.\n{error}",
        "err_ocr_import": "Could not import the OCR packages in the project .venv:\n{error}",
        "log_ocr_create_env": "OCR: creating the project .venv environment…",
        "log_ocr_check": "OCR: checking dependencies in the project environment…",
        "log_ocr_prepare": "Preparing OCR and document readers. Conversion will wait for setup to finish…",
        "log_ocr_install": "OCR: installing missing dependencies into .venv ({packages}). This may take several minutes…",
        "log_ocr_gpu_install": "OCR: NVIDIA GPU detected. Downloading the GPU runtime once (about 3 GB); "
                               "this may take several minutes…",
        "log_ocr_gpu_ready": "OCR: recognition now runs on the GPU.",
        "log_ocr_gpu_skipped": "OCR: the GPU runtime could not be installed, so recognition runs on the CPU "
                               "(about a minute per dense page): {error}",
        "log_ocr_ready": "OCR: the project environment is ready.",
        "log_ocr_models": "Starting OCR. On first use, downloading the required models may take several minutes…",
        "err_ocr_worker_missing": "The OCR worker was not found: {path}",
        "err_ocr_worker_failed": "The OCR worker stopped with an error.",
        "ocr_heading": "Text extracted from images (OCR)",
        "ocr_image": "Image {n}",
        "ocr_progress_starting": "Starting processing…",
        "ocr_progress_reading": "Reading document text…",
        "ocr_progress_finding": "Finding images in the document…",
        "ocr_progress_scan": "Finding images: page {done}/{total}",
        "ocr_progress_found": "{total} images ready for processing.",
        "ocr_progress_models": "Loading OCR models; the first run may also need a download…",
        "ocr_progress_images": "OCR: {done}/{total} images complete · {name}",
        "ocr_progress_done": "OCR processing complete.",
        "ocr_progress_failed": "OCR processing stopped; see the log for details.",
        "ocr_progress_elapsed": "{message} · Elapsed: {time}",
        "pdf_page_heading": "PDF page {page}",
        "pdf_progress_page": "Page {page}/{total} · {action}",
        "pdf_progress_reading": "checking text",
        "pdf_progress_ocr": "recognizing the whole page",
        "pdf_progress_images": "recognizing images on the page",
        "pdf_progress_cached": "OCR loaded from cache",
        "pdf_progress_text": "text extracted",
        "err_pdf_page_ocr": "Could not recognize usable text on PDF page {page}.",
        "err_pdf_page_failed": "Could not process PDF page {page}: {error}",
        "log_ocr_pages": "  PDF: text from {n} pages was recovered with whole-page OCR.",
        "log_ocr_pages_one": "  PDF: text from 1 page was recovered with whole-page OCR.",
        "log_pdf_text_ok": "  PDF: page text was readable directly; whole-page OCR was not needed.",

        "failed_header": "# MakeThemd – failed links\n"
                         "# The app's “Retry failed” button reloads them into the link list;\n"
                         "# links that succeed later are removed from here automatically.\n",
        "exists_title": "Output file already exists",
        "exists_body": "{name} already exists.\n\n"
                       "Yes: overwrite\nNo: save under a new name\nCancel: skip",

        "upd_skipped": "Update check skipped (no internet connection or PyPI is unreachable).",
        "upd_updating": "Updating downloader packages: {names} ...",
        "upd_done": "Done: {versions}",
        "upd_broken": "The updated package does not work, restoring the previous version: {versions}",
        "upd_restored": "Restored; the app starts with the previous version.",
        "upd_restore_failed": "Restoring failed too. Run manually: py -3 -m pip install -U \"yt-dlp[default]\"",
    },
}

_current = DEFAULT_LANGUAGE


def detect_language() -> str:
    """A rendszer nyelve alapján: magyar Windowson magyar, máshol angol."""
    try:
        name = (locale.getlocale()[0] or "").lower()
    except ValueError:
        name = ""
    return "hu" if name.startswith(("hu", "hungarian")) else DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    global _current
    _current = code if code in LANGUAGES else DEFAULT_LANGUAGE


def get_language() -> str:
    return _current


def t(key: str, **params) -> str:
    text = STRINGS[_current].get(key) or STRINGS[DEFAULT_LANGUAGE][key]
    return text.format(**params) if params else text


def tn(key: str, n: int, **params) -> str:
    """Darabszámos szöveg: n == 1 esetén a `<kulcs>_one` alak, ha van ilyen."""
    if n == 1 and (key + "_one") in STRINGS[_current]:
        key += "_one"
    return t(key, n=n, **params)
