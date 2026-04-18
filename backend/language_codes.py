# language_codes.py
# Mapping tables between human-readable language names, Whisper ISO codes,
# and NLLB-200 BCP-47 codes used by facebook/nllb-200-distilled-600M.

LANGUAGE_TO_NLLB: dict[str, str] = {
    "English":                "eng_Latn",
    "Chinese (Simplified)":   "zho_Hans",
    "Chinese (Traditional)":  "zho_Hant",
    "Japanese":               "jpn_Jpan",
    "Korean":                 "kor_Hang",
    "Spanish":                "spa_Latn",
    "French":                 "fra_Latn",
    "German":                 "deu_Latn",
    "Portuguese (Portugal)":  "por_Latn",
    "Portuguese (Brazil)":    "por_Latn",
    "Swedish":                "swe_Latn",
    "Finnish":                "fin_Latn",
    "Danish":                 "dan_Latn",
    "Arabic":                 "arb_Arab",
    "Russian":                "rus_Cyrl",
    "Hindi":                  "hin_Deva",
    "Mongolian":              "khk_Cyrl",
}

# Whisper returns ISO 639-1 two-letter codes; map them to NLLB codes so we
# can use the detected source language directly with the translation model.
WHISPER_TO_NLLB: dict[str, str] = {
    "en": "eng_Latn",
    "zh": "zho_Hans",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "es": "spa_Latn",
    "pt": "por_Latn",
    "it": "ita_Latn",
    "ar": "arb_Arab",
    "ru": "rus_Cyrl",
    "hi": "hin_Deva",
    "nl": "nld_Latn",
    "pl": "pol_Latn",
    "tr": "tur_Latn",
    "vi": "vie_Latn",
    "th": "tha_Thai",
    "id": "ind_Latn",
}

SUPPORTED_LANGUAGES: list[str] = sorted(LANGUAGE_TO_NLLB.keys())
