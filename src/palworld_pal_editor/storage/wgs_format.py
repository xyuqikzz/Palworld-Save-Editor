from __future__ import annotations

from dataclasses import dataclass, replace
import struct
import uuid


INDEX_VERSION = 14
CONTAINER_VERSION = 4
MAX_RECORDS = 100_000
MAX_TEXT_UNITS = 1_048_576
PAL_SAVE_MAGICS = (b"PlM", b"PlZ")


@dataclass(eq=False)
class WgsFormatError(ValueError):
    code: str
    message: str
    offset: int

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.message)


@dataclass(frozen=True)
class NormalizedPayload:
    data: bytes
    encoding: str


def normalize_palworld_payload(data: bytes) -> NormalizedPayload:
    """Expose a WGS payload as the Steam-style .sav bytes editors expect.

    Current Xbox Level payloads may contain one standard Palworld save after a
    12-byte CNK0 envelope. Unknown CNK variants are rejected instead of being
    interpreted or rewritten speculatively.
    """

    marker = data[8:11] if len(data) >= 11 else b""
    if marker != b"CNK":
        return NormalizedPayload(data=data, encoding="direct")
    if len(data) < 24:
        raise WgsFormatError(
            "TRUNCATED",
            "The Palworld CNK payload is truncated.",
            len(data),
        )
    if data[8:12] != b"CNK0":
        raise WgsFormatError(
            "UNSUPPORTED_CNK",
            "The Palworld CNK payload version is unsupported.",
            8,
        )
    chunk_count = struct.unpack("<I", data[4:8])[0]
    if chunk_count != 1:
        raise WgsFormatError(
            "UNSUPPORTED_CNK",
            "Only single-save Palworld CNK payloads are supported.",
            4,
        )
    nested = data[12:]
    if nested[8:11] not in PAL_SAVE_MAGICS or nested[11] not in (0x31, 0x32):
        raise WgsFormatError(
            "INVALID_CNK",
            "The Palworld CNK payload does not contain a supported save.",
            20,
        )
    return NormalizedPayload(data=nested, encoding="cnk0")


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read(self, size: int, field: str) -> bytes:
        if size < 0 or self.offset + size > len(self.data):
            raise WgsFormatError(
                "TRUNCATED",
                f"Truncated WGS data while reading {field}.",
                self.offset,
            )
        value = self.data[self.offset : self.offset + size]
        self.offset += size
        return value

    def u8(self, field: str) -> int:
        return self.read(1, field)[0]

    def u32(self, field: str) -> int:
        return struct.unpack("<I", self.read(4, field))[0]

    def u64(self, field: str) -> int:
        return struct.unpack("<Q", self.read(8, field))[0]

    def text(self, field: str) -> str:
        length = self.u32(f"{field}.length")
        if length > MAX_TEXT_UNITS:
            raise WgsFormatError(
                "INVALID_LENGTH",
                f"WGS text length is invalid for {field}.",
                self.offset - 4,
            )
        raw = self.read(length * 2, field)
        try:
            return raw.decode("utf-16-le", errors="strict")
        except UnicodeDecodeError as error:
            raise WgsFormatError(
                "INVALID_TEXT",
                f"WGS text is not valid UTF-16LE for {field}.",
                self.offset - len(raw),
            ) from error

    def remaining(self) -> bytes:
        return self.data[self.offset :]


def _encode_text(value: str) -> bytes:
    raw = value.encode("utf-16-le", errors="strict")
    return struct.pack("<I", len(raw) // 2) + raw


def _uuid_folder(raw: bytes, field: str, offset: int) -> str:
    if raw == b"\0" * 16:
        raise WgsFormatError("INVALID_UUID", f"Zero UUID is invalid for {field}.", offset)
    return uuid.UUID(bytes_le=raw).hex.upper()


@dataclass(frozen=True)
class WgsIndexEntry:
    name: str
    repeated_name: str
    cloud_id: str
    sequence: int
    flags: int
    container_id_bytes: bytes
    modified_filetime: int
    opaque_bytes: bytes
    size: int

    @property
    def container_folder(self) -> str:
        return _uuid_folder(self.container_id_bytes, "container UUID", 0)

    def with_payload(self, *, size: int, modified_filetime: int) -> "WgsIndexEntry":
        return replace(self, size=size, modified_filetime=modified_filetime)


@dataclass(frozen=True)
class WgsIndex:
    version: int
    flag1: int
    package_name: str
    modified_filetime: int
    flag2: int
    index_id: str
    opaque_bytes: bytes
    entries: tuple[WgsIndexEntry, ...]
    trailing_bytes: bytes = b""

    def replace_entry(self, position: int, entry: WgsIndexEntry) -> "WgsIndex":
        entries = list(self.entries)
        entries[position] = entry
        return replace(self, entries=tuple(entries))


@dataclass(frozen=True)
class WgsContainerFile:
    name: str
    name_bytes: bytes
    primary_id_bytes: bytes
    secondary_id_bytes: bytes

    @property
    def primary_folder(self) -> str | None:
        if self.primary_id_bytes == b"\0" * 16:
            return None
        return uuid.UUID(bytes_le=self.primary_id_bytes).hex.upper()

    @property
    def secondary_folder(self) -> str | None:
        if self.secondary_id_bytes == b"\0" * 16:
            return None
        return uuid.UUID(bytes_le=self.secondary_id_bytes).hex.upper()


@dataclass(frozen=True)
class WgsContainer:
    version: int
    files: tuple[WgsContainerFile, ...]
    trailing_bytes: bytes = b""


def select_payload_folder(
    file: WgsContainerFile, available_files: set[str]
) -> str:
    candidates = {
        value
        for value in (file.primary_folder, file.secondary_folder)
        if value is not None and value in available_files
    }
    if not candidates:
        raise WgsFormatError(
            "DANGLING_REFERENCE",
            "No referenced WGS payload exists.",
            0,
        )
    if len(candidates) != 1:
        raise WgsFormatError(
            "AMBIGUOUS_REFERENCE",
            "Multiple referenced WGS payloads exist.",
            0,
        )
    return next(iter(candidates))


def parse_index(data: bytes) -> WgsIndex:
    reader = _Reader(data)
    version = reader.u32("index.version")
    if version != INDEX_VERSION:
        raise WgsFormatError(
            "UNSUPPORTED_VERSION",
            f"Unsupported containers.index version: {version}.",
            0,
        )
    count = reader.u32("index.container_count")
    if count > MAX_RECORDS:
        raise WgsFormatError("INVALID_LENGTH", "Container count is invalid.", 4)
    flag1 = reader.u32("index.flag1")
    package_name = reader.text("index.package_name")
    modified_filetime = reader.u64("index.modified_filetime")
    flag2 = reader.u32("index.flag2")
    index_id = reader.text("index.id")
    opaque_bytes = reader.read(8, "index.opaque")
    entries: list[WgsIndexEntry] = []
    seen_container_ids: set[bytes] = set()
    for position in range(count):
        name = reader.text(f"entries[{position}].name")
        repeated_name = reader.text(f"entries[{position}].repeated_name")
        if repeated_name != name:
            raise WgsFormatError(
                "NAME_MISMATCH",
                "The repeated WGS container name does not match.",
                reader.offset,
            )
        cloud_id = reader.text(f"entries[{position}].cloud_id")
        sequence = reader.u8(f"entries[{position}].sequence")
        flags = reader.u32(f"entries[{position}].flags")
        uuid_offset = reader.offset
        container_id_bytes = reader.read(16, f"entries[{position}].container_uuid")
        _uuid_folder(container_id_bytes, "container UUID", uuid_offset)
        if container_id_bytes in seen_container_ids:
            raise WgsFormatError(
                "DUPLICATE_REFERENCE",
                "Duplicate WGS container UUID reference.",
                uuid_offset,
            )
        seen_container_ids.add(container_id_bytes)
        entry_mtime = reader.u64(f"entries[{position}].modified_filetime")
        entry_opaque = reader.read(8, f"entries[{position}].opaque")
        size = reader.u64(f"entries[{position}].size")
        entries.append(
            WgsIndexEntry(
                name=name,
                repeated_name=repeated_name,
                cloud_id=cloud_id,
                sequence=sequence,
                flags=flags,
                container_id_bytes=container_id_bytes,
                modified_filetime=entry_mtime,
                opaque_bytes=entry_opaque,
                size=size,
            )
        )
    return WgsIndex(
        version=version,
        flag1=flag1,
        package_name=package_name,
        modified_filetime=modified_filetime,
        flag2=flag2,
        index_id=index_id,
        opaque_bytes=opaque_bytes,
        entries=tuple(entries),
        trailing_bytes=reader.remaining(),
    )


def encode_index(index: WgsIndex) -> bytes:
    output = bytearray()
    output += struct.pack("<III", index.version, len(index.entries), index.flag1)
    output += _encode_text(index.package_name)
    output += struct.pack("<QI", index.modified_filetime, index.flag2)
    output += _encode_text(index.index_id)
    if len(index.opaque_bytes) != 8:
        raise WgsFormatError(
            "INVALID_LENGTH", "Index opaque field must be 8 bytes.", len(output)
        )
    output += index.opaque_bytes
    for entry in index.entries:
        output += _encode_text(entry.name)
        output += _encode_text(entry.repeated_name)
        output += _encode_text(entry.cloud_id)
        output += struct.pack("<BI", entry.sequence, entry.flags)
        if len(entry.container_id_bytes) != 16:
            raise WgsFormatError("INVALID_UUID", "Container UUID must be 16 bytes.", len(output))
        output += entry.container_id_bytes
        output += struct.pack("<Q", entry.modified_filetime)
        if len(entry.opaque_bytes) != 8:
            raise WgsFormatError(
                "INVALID_LENGTH", "Entry opaque field must be 8 bytes.", len(output)
            )
        output += entry.opaque_bytes
        output += struct.pack("<Q", entry.size)
    output += index.trailing_bytes
    return bytes(output)


def parse_container(data: bytes) -> WgsContainer:
    reader = _Reader(data)
    version = reader.u32("container.version")
    if version != CONTAINER_VERSION:
        raise WgsFormatError(
            "UNSUPPORTED_VERSION",
            f"Unsupported container.N version: {version}.",
            0,
        )
    count = reader.u32("container.file_count")
    if count > MAX_RECORDS:
        raise WgsFormatError("INVALID_LENGTH", "Container file count is invalid.", 4)
    files: list[WgsContainerFile] = []
    for position in range(count):
        raw_name = reader.read(128, f"files[{position}].name")
        try:
            name = raw_name.decode("utf-16-le", errors="strict").rstrip("\0")
        except UnicodeDecodeError as error:
            raise WgsFormatError(
                "INVALID_TEXT",
                "Container file name is not valid UTF-16LE.",
                reader.offset - 128,
            ) from error
        primary = reader.read(16, f"files[{position}].primary_uuid")
        secondary = reader.read(16, f"files[{position}].secondary_uuid")
        if primary == b"\0" * 16 and secondary == b"\0" * 16:
            raise WgsFormatError(
                "INVALID_UUID",
                "Container payload references cannot both be zero.",
                reader.offset - 32,
            )
        files.append(
            WgsContainerFile(
                name=name,
                name_bytes=raw_name,
                primary_id_bytes=primary,
                secondary_id_bytes=secondary,
            )
        )
    return WgsContainer(version=version, files=tuple(files), trailing_bytes=reader.remaining())


def encode_container(container: WgsContainer) -> bytes:
    output = bytearray(struct.pack("<II", container.version, len(container.files)))
    for file in container.files:
        if len(file.name_bytes) != 128:
            raise WgsFormatError("INVALID_LENGTH", "Container file name must be 128 bytes.", len(output))
        if len(file.primary_id_bytes) != 16 or len(file.secondary_id_bytes) != 16:
            raise WgsFormatError("INVALID_UUID", "Payload UUID must be 16 bytes.", len(output))
        output += file.name_bytes
        output += file.primary_id_bytes
        output += file.secondary_id_bytes
    output += container.trailing_bytes
    return bytes(output)
