from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--mod", type=Path, required=True)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--version-file", type=Path, required=True)
    args = parser.parse_args()

    version = args.version_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"Invalid PalEditorBridge version: {version!r}")

    expected_name = f"PalEditorBridge-UE4SS-Mod-{version}.zip"
    if args.mod.name != expected_name:
        raise SystemExit(
            f"Unexpected Mod package name: {args.mod.name!r}, expected {expected_name!r}"
        )

    dll_bytes = args.dll.read_bytes()
    if version.encode("ascii") not in dll_bytes:
        raise SystemExit("The compiled DLL does not contain the declared Mod version.")

    with zipfile.ZipFile(args.mod) as package:
        entries = package.namelist()
        dll_entries = [
            name
            for name in entries
            if name.endswith("/PalEditorBridge/dlls/main.dll")
        ]
        install_entries = [
            name for name in entries if name.endswith("/INSTALL.zh-CN.md")
        ]
        if len(dll_entries) != 1 or len(install_entries) != 1:
            raise SystemExit(
                "The Mod package does not contain exactly one DLL and install guide."
            )
        packaged_dll = package.read(dll_entries[0])
        install_guide = package.read(install_entries[0]).decode("utf-8")

    if packaged_dll != dll_bytes:
        raise SystemExit("The packaged main.dll does not match the compiled DLL.")
    if version not in install_guide:
        raise SystemExit("The install guide does not contain the declared Mod version.")

    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(args.exe))
    embedded_name = f"mod\\{expected_name}"
    if embedded_name not in archive.toc:
        raise SystemExit(f"The EXE does not contain {embedded_name}.")
    embedded_package = archive.extract(embedded_name)
    package_bytes = args.mod.read_bytes()
    if embedded_package != package_bytes:
        raise SystemExit("The EXE-embedded Mod package does not match the release ZIP.")

    print(
        json.dumps(
            {
                "bridgeVersion": version,
                "dllSha256": sha256(dll_bytes),
                "modSha256": sha256(package_bytes),
                "embeddedModSha256": sha256(embedded_package),
                "exeSha256": sha256(args.exe.read_bytes()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
