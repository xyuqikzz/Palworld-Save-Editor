try:
    import ooz
except ModuleNotFoundError as exc:
    if exc.name != "ooz":
        raise
    import palooz as ooz
else:
    if not all(
        callable(getattr(ooz, operation, None))
        for operation in ("compress", "decompress")
    ):
        import palooz as ooz

from palworld_save_tools.compressor import (
    Compressor,
    SaveType
)

class OodleCompressor:
    Kraken    = 8
    Mermaid   = 9
    Selkie    = 11
    Hydra     = 12  # hydra doesn't exist in libooz
    Leviathan = 13

class OodleLevel:
    SuperFast = 1
    VeryFast  = 2
    Fast      = 3
    Normal    = 4
    Optimal1  = 5
    Optimal2  = 6
    Optimal3  = 7
    Optimal4  = 8
    Optimal5  = 9

    HyperFast1 = -1
    HyperFast2 = -2
    HyperFast3 = -3
    HyperFast4 = -4


class OozLib(Compressor):
    def __init__(self):
        """
        OozLib is an open source library for compression and decompression using Oodle.
        """
        self.SAFE_SPACE_PADDING = 128

    def compress(self, data: bytes, save_type: int) -> bytes:
        print("\nStarting compression process with libooz...")

        uncompressed_len = len(data)
        if uncompressed_len == 0:
            raise ValueError("Input data for compression must not be empty.")

        if save_type != SaveType.PLM:
            raise ValueError(
                f"Unhandled compression type: 0x{save_type:02X}, only 0x31 (PLM) is supported"
            )

        print("Compressing data...")

        compressed_data = ooz.compress(
            OodleCompressor.Kraken,
            OodleLevel.Normal,
            data,
            uncompressed_len
        )

        if not compressed_data:
            raise RuntimeError(f"Ooz_Compress failed or returned empty result (code: {compressed_data})")

        compressed_len = len(compressed_data)
        magic_bytes = self._get_magic(save_type)

        print(f"Compression successful, compressed size: {compressed_len:,} bytes")

        print(f"File information (Compress):")
        print(f"  Magic bytes: {magic_bytes.decode('ascii', errors='ignore')}")
        print(f"  Save type: 0x{save_type:02X}")
        print(f"  Compressed size: {compressed_len:,} bytes")
        print(f"  Uncompressed size: {uncompressed_len:,} bytes")

        sav_data = self.build_sav(
            compressed_data,
            uncompressed_len,
            compressed_len,
            magic_bytes,
            save_type
        )

        return sav_data

    def decompress(self, data: bytes) -> bytes:
        print("\nStarting decompression process with libooz...")

        if not data:
            raise ValueError("SAV data cannot be empty")

        format_result = self.check_sav_format(data)
        if format_result == 0:
            raise ValueError(
                "Detected PLZ format (Zlib), this tool only supports PLM format (Oodle)"
            )
        elif format_result == -1:
            raise ValueError("Unknown SAV file format")

        uncompressed_len, compressed_len, magic, save_type, data_offset = (
            self._parse_sav_header(data)
        )

        print(f"File information (Decompress):")
        print(f"  Magic bytes: {magic.decode('ascii', errors='ignore')}")
        print(f"  Save type: 0x{save_type:02X}")
        print(f"  Compressed size: {compressed_len:,} bytes")
        print(f"  Uncompressed size: {uncompressed_len:,} bytes")
        print(f"  Data offset: {data_offset} bytes")
        print("Detected PLM format (Oodle), starting decompression...")

        compressed_data = data[data_offset : data_offset + compressed_len]
        decompressed = ooz.decompress(compressed_data, uncompressed_len)

        if len(decompressed) != uncompressed_len:
            raise ValueError(
                f"Decompressed data length {len(decompressed)} does not match expected uncompressed length {uncompressed_len}"
            )

        print(f"Decompression successful, decompressed size: {len(decompressed):,} bytes")

        return decompressed, save_type
