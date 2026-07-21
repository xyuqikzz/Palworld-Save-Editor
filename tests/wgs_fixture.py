from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import struct
import uuid

from palworld_pal_editor.storage.wgs_format import (
    WgsIndex,
    WgsIndexEntry,
    encode_index,
)


def make_user_directory(
    root: Path,
    user_name: str,
    worlds: dict[str, dict[str, bytes]],
    *,
    level_container_suffix: str = "Level",
) -> Path:
    user = root / user_name
    user.mkdir(parents=True)
    entries: list[WgsIndexEntry] = []
    for world_id, logical_files in worlds.items():
        for logical_path, payload in logical_files.items():
            if logical_path == "Level.sav":
                suffix = level_container_suffix
            elif logical_path in {"LevelMeta.sav", "LocalData.sav", "WorldOption.sav"}:
                suffix = Path(logical_path).stem
            elif logical_path.startswith("Players/"):
                suffix = f"Players-{Path(logical_path).stem}"
            else:
                suffix = logical_path.replace("/", "-").removesuffix(".sav")
            container_id = uuid.uuid5(uuid.NAMESPACE_URL, f"container:{user_name}:{world_id}:{suffix}")
            payload_id = uuid.uuid5(uuid.NAMESPACE_URL, f"payload:{user_name}:{world_id}:{suffix}")
            container_dir = user / container_id.hex.upper()
            container_dir.mkdir()
            fixed_name = "Data".encode("utf-16-le").ljust(128, b"\0")
            (container_dir / "container.1").write_bytes(
                struct.pack("<II", 4, 1)
                + fixed_name
                + (b"\0" * 16)
                + payload_id.bytes_le
            )
            (container_dir / payload_id.hex.upper()).write_bytes(payload)
            # Real WGS counted strings include a trailing UTF-16 NUL.
            name = f"{world_id}-{suffix}\0"
            entries.append(
                WgsIndexEntry(
                    name=name,
                    repeated_name=name,
                    cloud_id="cloud-id-preserved\0",
                    sequence=1,
                    flags=1,
                    container_id_bytes=container_id.bytes_le,
                    modified_filetime=133800000000000000,
                    opaque_bytes=struct.pack("<Q", 0x1234),
                    size=len(payload),
                )
            )
    index = WgsIndex(
        version=14,
        flag1=0,
        package_name="PocketpairInc.Palworld_ad4psfrxyesvt!AppPalworldShipping\0",
        modified_filetime=133800000000000000,
        flag2=0,
        index_id="synthetic-index\0",
        opaque_bytes=struct.pack("<Q", 0x5678),
        entries=tuple(entries),
    )
    (user / "containers.index").write_bytes(encode_index(index))
    return user
