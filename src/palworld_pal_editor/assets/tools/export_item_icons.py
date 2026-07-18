from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import re
import struct

from PIL import Image


DDSD_CAPS = 0x1
DDSD_HEIGHT = 0x2
DDSD_WIDTH = 0x4
DDSD_PIXELFORMAT = 0x1000
DDSD_LINEARSIZE = 0x80000
DDSCAPS_TEXTURE = 0x1000
DDPF_ALPHAPIXELS = 0x1
DDPF_FOURCC = 0x4
DDPF_RGB = 0x40


def dds_header(pixel_format: str, width: int, height: int, data_size: int) -> bytes:
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    if pixel_format in {"PF_DXT1", "PF_DXT5"}:
        fourcc = b"DXT1" if pixel_format == "PF_DXT1" else b"DXT5"
        pixel_format_header = struct.pack(
            "<II4sIIIII", 32, DDPF_FOURCC, fourcc, 0, 0, 0, 0, 0
        )
    elif pixel_format == "PF_B8G8R8A8":
        pixel_format_header = struct.pack(
            "<IIIIIIII",
            32,
            DDPF_RGB | DDPF_ALPHAPIXELS,
            0,
            32,
            0x00FF0000,
            0x0000FF00,
            0x000000FF,
            0xFF000000,
        )
    else:
        raise ValueError(f"Unsupported pixel format: {pixel_format}")

    return b"DDS " + b"".join(
        [
            struct.pack("<IIIIIII", 124, flags, height, width, data_size, 0, 1),
            bytes(44),
            pixel_format_header,
            struct.pack("<IIIII", DDSCAPS_TEXTURE, 0, 0, 0, 0),
        ]
    )


def export_icon(source: Path, destination: Path) -> None:
    serialized_export = source.read_bytes()[:-4]
    match = re.search(rb"PF_[A-Z0-9_]+\x00", serialized_export[:256])
    if not match:
        raise ValueError(f"Pixel format not found: {source}")
    pixel_format = match.group(0)[:-1].decode("ascii")

    if pixel_format not in {"PF_DXT1", "PF_DXT5", "PF_B8G8R8A8"}:
        raise ValueError(f"Unsupported pixel format {pixel_format}: {source}")

    payload = None
    width = height = data_size = 0
    for offset in range(min(512, len(serialized_export) - 32)):
        bulk_flags, element_count, serialized_size = struct.unpack_from(
            "<III", serialized_export, offset
        )
        if bulk_flags != 0x48 or element_count != serialized_size:
            continue
        payload_start = offset + 20
        payload_end = payload_start + serialized_size
        if payload_end + 12 > len(serialized_export):
            continue
        candidate_width, candidate_height, depth = struct.unpack_from(
            "<III", serialized_export, payload_end
        )
        expected_size = (
            max(1, (candidate_width + 3) // 4)
            * max(1, (candidate_height + 3) // 4)
            * (8 if pixel_format == "PF_DXT1" else 16)
            if pixel_format in {"PF_DXT1", "PF_DXT5"}
            else candidate_width * candidate_height * 4
        )
        if depth == 1 and expected_size == serialized_size:
            width, height, data_size = (
                candidate_width,
                candidate_height,
                serialized_size,
            )
            payload = serialized_export[payload_start:payload_end]
            break
    if payload is None:
        raise ValueError(f"Verified top mip payload not found: {source}")
    dds = dds_header(pixel_format, width, height, data_size) + payload
    with Image.open(BytesIO(dds)) as image:
        if image.size != (width, height):
            raise ValueError(f"Unexpected decoded size {image.size}: {source}")
        image.convert("RGBA").save(destination, format="PNG", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export verified Build 24088745 item icon texture layouts."
    )
    parser.add_argument("texture_root", type=Path)
    parser.add_argument("item_data", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()

    item_data = json.loads(args.item_data.read_text(encoding="utf-8"))
    requested = sorted(
        {item["Icon"] for item in item_data.values() if item.get("Icon")}
    )
    args.output_root.mkdir(parents=True, exist_ok=True)

    exported = 0
    missing: list[str] = []
    for icon_name in requested:
        sources = list(args.texture_root.rglob(f"{icon_name}.uexp"))
        if len(sources) != 1:
            missing.append(icon_name)
            continue
        source = sources[0]
        export_icon(source, args.output_root / f"{icon_name}.png")
        exported += 1

    print(f"Exported {exported}/{len(requested)} item icons")
    if missing:
        print("Missing: " + ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
