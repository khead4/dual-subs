from __future__ import annotations

import argparse
from typing import Iterable


COMMON_LANGUAGE_CODES = {"ja", "en", "zh", "ko"}
APP_LANGUAGE_CODES = {"ja", "en", "zh", "ko", "es", "fr", "de", "it", "pt", "ar", "hi"}


def build_required_pairs(language_codes: Iterable[str]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for code in language_codes:
        if code == "en":
            continue
        pairs.add((code, "en"))
        pairs.add(("en", code))
    return pairs


def install_argos_language_models(profile: str) -> None:
    import argostranslate.package

    language_codes = COMMON_LANGUAGE_CODES if profile == "common" else APP_LANGUAGE_CODES
    required_pairs = build_required_pairs(language_codes)

    print(f"Updating Argos package index for the '{profile}' profile...")
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()
    available_lookup = {(package.from_code, package.to_code): package for package in available_packages}

    missing_pairs = [pair for pair in sorted(required_pairs) if pair not in available_lookup]
    if missing_pairs:
        missing_list = ", ".join([f"{source}->{target}" for source, target in missing_pairs])
        print(f"Warning: some offline translation packages were not found in the Argos index: {missing_list}")

    for source_code, target_code in sorted(required_pairs):
        package = available_lookup.get((source_code, target_code))
        if not package:
            continue
        print(f"Installing Argos package {source_code}->{target_code}...")
        download_path = package.download()
        argostranslate.package.install_from_path(download_path)


def warm_up_whisper_model(model_name: str) -> None:
    from faster_whisper import WhisperModel

    print(f"Downloading or opening the local Whisper model '{model_name}'...")
    WhisperModel(model_name, device="cpu", compute_type="int8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install local translation packages and warm up the local Whisper model.")
    parser.add_argument("--profile", choices=["common", "all"], default="all")
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--skip-translation", action="store_true")
    parser.add_argument("--skip-whisper", action="store_true")
    args = parser.parse_args()

    if not args.skip_translation:
        install_argos_language_models(args.profile)

    if not args.skip_whisper:
        warm_up_whisper_model(args.whisper_model)

    print("Local AI model setup complete.")


if __name__ == "__main__":
    main()
