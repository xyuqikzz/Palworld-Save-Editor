from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NATIVE_ROOT = PROJECT_ROOT / "native" / "pal_editor_bridge"
PREBUILT_ROOT = NATIVE_ROOT / "prebuilt"
DLL_PATH = PREBUILT_ROOT / "PalEditorBridge.dll"
MANIFEST_PATH = PREBUILT_ROOT / "manifest.json"


def source_files() -> list[Path]:
    candidates = [
        NATIVE_ROOT / "CMakeLists.txt",
        NATIVE_ROOT / "VERSION",
        NATIVE_ROOT / "ue4ss" / "CMakeLists.txt",
    ]
    for directory, patterns in (
        (NATIVE_ROOT / "include", ("*.hpp", "*.h")),
        (NATIVE_ROOT / "src", ("*.cpp", "*.cxx", "*.cc")),
        (NATIVE_ROOT / "ue4ss" / "include", ("*.hpp", "*.h")),
        (NATIVE_ROOT / "ue4ss" / "src", ("*.cpp", "*.cxx", "*.cc")),
    ):
        for pattern in patterns:
            candidates.extend(directory.rglob(pattern))
    files = sorted({path.resolve() for path in candidates})
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing bridge build input: {missing[0]}")
    return files


def source_sha256() -> str:
    digest = hashlib.sha256()
    for path in source_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(ue4ss_revision: str) -> dict[str, object]:
    if not DLL_PATH.is_file():
        raise SystemExit(f"Missing verified bridge DLL: {DLL_PATH}")
    version = (NATIVE_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    dll_bytes = DLL_PATH.read_bytes()
    if version.encode("ascii") not in dll_bytes:
        raise SystemExit(f"Bridge DLL does not contain declared version {version}.")
    return {
        "formatVersion": 1,
        "bridgeVersion": version,
        "ue4ssRevision": ue4ss_revision,
        "sourceSha256": source_sha256(),
        "dllSha256": file_sha256(DLL_PATH),
        "dllSize": len(dll_bytes),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--ue4ss-revision")
    parser.add_argument("--expected-ue4ss-revision")
    args = parser.parse_args()

    if args.write:
        if not args.ue4ss_revision:
            raise SystemExit("--ue4ss-revision is required with --write.")
        PREBUILT_ROOT.mkdir(parents=True, exist_ok=True)
        expected = manifest(args.ue4ss_revision)
        MANIFEST_PATH.write_text(
            json.dumps(expected, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        if not MANIFEST_PATH.is_file():
            raise SystemExit(f"Missing prebuilt manifest: {MANIFEST_PATH}")
        recorded = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        revision = args.expected_ue4ss_revision or recorded.get("ue4ssRevision")
        expected = manifest(str(revision))
        if recorded != expected:
            raise SystemExit(
                "Verified PalEditorBridge prebuilt is stale or was modified. "
                "Rebuild it with -RefreshVerifiedPrebuilt."
            )

    print(json.dumps(expected, indent=2))


if __name__ == "__main__":
    main()
