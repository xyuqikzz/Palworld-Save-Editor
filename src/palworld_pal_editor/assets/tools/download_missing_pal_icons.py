from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image


CDN_ROOT = "https://cdn.paldb.cc/image/Pal/Texture/PalIcon/Normal"


def download_icon(internal_name: str, output: Path) -> tuple[str, str | None]:
    filename = urllib.parse.quote(
        f"T_{internal_name}_icon_normal.webp", safe="_-"
    )
    request = urllib.request.Request(
        f"{CDN_ROOT}/{filename}",
        headers={
            "User-Agent": "Mozilla/5.0 (Palworld-Save-Editor asset updater)",
            "Referer": "https://paldb.cc/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            source = response.read()
        with Image.open(io.BytesIO(source)) as image:
            image.convert("RGBA").save(output, "PNG", optimize=True)
        return internal_name, None
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as error:
        return internal_name, str(error)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pal_data", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--localized-table", type=Path, required=True)
    args = parser.parse_args()

    pal_data = json.loads(args.pal_data.read_text(encoding="utf-8"))
    localized_asset = json.loads(args.localized_table.read_text(encoding="utf-8"))
    official_ids = {
        row["Name"][len("PAL_NAME_") :]
        for row in localized_asset["Exports"][0]["Table"]["Data"]
        if row["Name"].startswith("PAL_NAME_")
    }
    args.output.mkdir(parents=True, exist_ok=True)
    downloaded: list[str] = []
    missing: list[str] = []

    jobs = {
        internal_name: args.output / f"{internal_name}.png"
        for internal_name in sorted(official_ids & set(pal_data))
        if not (args.output / f"{internal_name}.png").exists()
    }
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(download_icon, internal_name, output): internal_name
            for internal_name, output in jobs.items()
        }
        for future in as_completed(futures):
            internal_name, error = future.result()
            if error is None:
                downloaded.append(internal_name)
                print(f"Downloaded {internal_name}")
            else:
                missing.append(internal_name)
                print(f"Missing {internal_name}: {error}")

    print(f"Downloaded: {len(downloaded)}")
    print(f"Still missing: {len(missing)}")
    if missing:
        print("Missing: " + ", ".join(missing))


if __name__ == "__main__":
    main()
