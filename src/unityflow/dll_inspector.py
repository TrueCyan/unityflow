"""DLL Inspector for Unity .NET assemblies.

Parses .NET DLL PE/CLI metadata to extract type definitions (class names
and namespaces) and compute Unity fileIDs for script references.

Unity stores DLL-based MonoBehaviour references as:
    m_Script: {fileID: <hash>, guid: <dll_meta_guid>, type: 3}

Where fileID = MD4("s\\0\\0\\0" + namespace + className) as little-endian int32.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DllTypeInfo:
    namespace: str
    name: str
    flags: int

    @property
    def full_name(self) -> str:
        if self.namespace:
            return f"{self.namespace}.{self.name}"
        return self.name

    @property
    def is_public(self) -> bool:
        return (self.flags & 0x7) == 0x1


def compute_unity_file_id(namespace: str, class_name: str) -> int:
    text = f"s\x00\x00\x00{namespace}{class_name}"
    digest = _md4(text.encode("utf-8"))
    return struct.unpack("<i", digest[:4])[0]


def inspect_dll(dll_path: Path) -> list[DllTypeInfo]:
    try:
        data = dll_path.read_bytes()
        return _parse_dotnet_types(data)
    except Exception:
        return []


def find_class_in_dll(dll_path: Path, class_name: str) -> tuple[str, int] | None:
    """Find a class by name in a DLL.

    Returns (namespace, unity_file_id) or None.
    """
    for t in inspect_dll(dll_path):
        if t.name == class_name:
            return t.namespace, compute_unity_file_id(t.namespace, t.name)
    return None


def find_class_by_file_id(dll_path: Path, file_id: int) -> str | None:
    """Find a class name by its Unity fileID in a DLL.

    Returns the class name, or None if no match.
    """
    for t in inspect_dll(dll_path):
        if compute_unity_file_id(t.namespace, t.name) == file_id:
            return t.name
    return None


_dll_cache: dict[Path, list[DllTypeInfo]] = {}


def inspect_dll_cached(dll_path: Path) -> list[DllTypeInfo]:
    resolved = dll_path.resolve()
    if resolved not in _dll_cache:
        _dll_cache[resolved] = inspect_dll(dll_path)
    return _dll_cache[resolved]


def find_class_in_dlls(
    dll_paths: list[tuple[Path, str]],
    class_name: str,
) -> tuple[str, int, str] | None:
    """Search multiple DLLs for a class by name.

    Args:
        dll_paths: List of (dll_path, guid) tuples
        class_name: Class name to find

    Returns (guid, file_id, namespace) or None.
    """
    for dll_path, guid in dll_paths:
        for t in inspect_dll_cached(dll_path):
            if t.name == class_name:
                file_id = compute_unity_file_id(t.namespace, t.name)
                return guid, file_id, t.namespace
    return None


def resolve_dll_class_name(
    dll_path: Path,
    file_id: int,
) -> str | None:
    """Resolve a fileID to a class name within a DLL.

    Args:
        dll_path: Path to the .dll file
        file_id: Unity fileID (MD4 hash)

    Returns class name or None.
    """
    for t in inspect_dll_cached(dll_path):
        if compute_unity_file_id(t.namespace, t.name) == file_id:
            return t.name
    return None


# --- .NET PE/CLI metadata parser ---


def _parse_dotnet_types(data: bytes) -> list[DllTypeInfo]:
    if len(data) < 128:
        return []

    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew + 4 > len(data) or data[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        return []

    coff = e_lfanew + 4
    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_header_size = struct.unpack_from("<H", data, coff + 16)[0]

    opt = coff + 20
    if opt + 2 > len(data):
        return []
    magic = struct.unpack_from("<H", data, opt)[0]

    if magic == 0x10B:
        data_dir_base = opt + 96
    elif magic == 0x20B:
        data_dir_base = opt + 112
    else:
        return []

    cli_dd = data_dir_base + 14 * 8
    if cli_dd + 8 > len(data):
        return []
    cli_rva = struct.unpack_from("<I", data, cli_dd)[0]
    if cli_rva == 0:
        return []

    sections = []
    for i in range(num_sections):
        so = opt + opt_header_size + i * 40
        if so + 40 > len(data):
            break
        va = struct.unpack_from("<I", data, so + 12)[0]
        vs = struct.unpack_from("<I", data, so + 8)[0]
        ro = struct.unpack_from("<I", data, so + 20)[0]
        rs = struct.unpack_from("<I", data, so + 16)[0]
        sections.append((va, vs, ro, rs))

    def rva_to_offset(rva: int) -> int | None:
        for va, vs, ro, rs in sections:
            if va <= rva < va + max(vs, rs):
                return rva - va + ro
        return None

    cli_off = rva_to_offset(cli_rva)
    if cli_off is None or cli_off + 16 > len(data):
        return []
    meta_rva = struct.unpack_from("<I", data, cli_off + 8)[0]

    meta_off = rva_to_offset(meta_rva)
    if meta_off is None or meta_off + 16 > len(data):
        return []
    if struct.unpack_from("<I", data, meta_off)[0] != 0x424A5342:
        return []

    ver_len = struct.unpack_from("<I", data, meta_off + 12)[0]
    sh_base = meta_off + 16 + ((ver_len + 3) & ~3)
    if sh_base + 4 > len(data):
        return []
    num_streams = struct.unpack_from("<H", data, sh_base + 2)[0]

    streams: dict[str, tuple[int, int]] = {}
    pos = sh_base + 4
    for _ in range(num_streams):
        if pos + 8 > len(data):
            return []
        s_off, s_size = struct.unpack_from("<II", data, pos)
        pos += 8
        name_start = pos
        while pos < len(data) and data[pos] != 0:
            pos += 1
        name = data[name_start:pos].decode("ascii", errors="replace")
        pos = ((pos + 1) + 3) & ~3
        streams[name] = (meta_off + s_off, s_size)

    str_off = streams.get("#Strings", (0, 0))[0]
    if str_off == 0:
        return []

    def read_str(idx: int) -> str:
        start = str_off + idx
        if start >= len(data):
            return ""
        end = data.index(b"\x00", start)
        return data[start:end].decode("utf-8", errors="replace")

    tbl_key = "#~" if "#~" in streams else "#-" if "#-" in streams else None
    if tbl_key is None:
        return []
    tbl_off = streams[tbl_key][0]
    if tbl_off + 24 > len(data):
        return []

    pos = tbl_off + 6
    heap_sizes = data[pos]
    pos += 2
    valid = struct.unpack_from("<Q", data, pos)[0]
    pos += 8
    pos += 8  # sorted

    rows: dict[int, int] = {}
    for i in range(64):
        if valid & (1 << i):
            if pos + 4 > len(data):
                return []
            rows[i] = struct.unpack_from("<I", data, pos)[0]
            pos += 4

    str_sz = 4 if heap_sizes & 0x01 else 2
    guid_sz = 4 if heap_sizes & 0x02 else 2

    def tbl_idx_sz(t: int) -> int:
        return 4 if rows.get(t, 0) > 0xFFFF else 2

    def coded_idx_sz(tag_bits: int, tables: list[int]) -> int:
        mx = max((rows.get(t, 0) for t in tables), default=0)
        return 4 if mx >= (1 << (16 - tag_bits)) else 2

    res_scope_sz = coded_idx_sz(2, [0x00, 0x01, 0x1A, 0x23])
    tdr_sz = coded_idx_sz(2, [0x02, 0x01, 0x1B])

    row_sizes: dict[int, int] = {
        0x00: 2 + str_sz + 3 * guid_sz,
        0x01: res_scope_sz + 2 * str_sz,
        0x02: 4 + 2 * str_sz + tdr_sz + tbl_idx_sz(0x04) + tbl_idx_sz(0x06),
    }

    typedef_offset = pos
    for t in range(0x02):
        if valid & (1 << t):
            typedef_offset += rows[t] * row_sizes[t]

    if not (valid & (1 << 0x02)):
        return []

    num_typedefs = rows[0x02]
    typedef_row_size = row_sizes[0x02]
    fmt = "<I" if str_sz == 4 else "<H"
    result: list[DllTypeInfo] = []

    for i in range(num_typedefs):
        row_off = typedef_offset + i * typedef_row_size
        if row_off + typedef_row_size > len(data):
            break
        flags = struct.unpack_from("<I", data, row_off)[0]
        name_idx = struct.unpack_from(fmt, data, row_off + 4)[0]
        ns_idx = struct.unpack_from(fmt, data, row_off + 4 + str_sz)[0]

        name = read_str(name_idx)
        namespace = read_str(ns_idx)

        if name == "<Module>":
            continue

        result.append(DllTypeInfo(namespace=namespace, name=name, flags=flags))

    return result


# --- MD4 hash (RFC 1320) ---


def _md4(data: bytes) -> bytes:
    try:
        import hashlib

        return hashlib.new("md4", data, usedforsecurity=False).digest()
    except (ValueError, TypeError):
        return _md4_pure(data)


def _md4_pure(data: bytes) -> bytes:
    def _rol(n: int, b: int) -> int:
        return ((n << b) | (n >> (32 - b))) & 0xFFFFFFFF

    def _f(x: int, y: int, z: int) -> int:
        return (x & y) | ((~x) & z)

    def _g(x: int, y: int, z: int) -> int:
        return (x & y) | (x & z) | (y & z)

    def _h(x: int, y: int, z: int) -> int:
        return x ^ y ^ z

    msg = bytearray(data)
    orig_len = len(data)
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += struct.pack("<Q", orig_len * 8)

    a0, b0, c0, d0 = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476

    for i in range(0, len(msg), 64):
        words = struct.unpack_from("<16I", msg, i)
        a, b, c, d = a0, b0, c0, d0

        for k in range(16):
            a = _rol((a + _f(b, c, d) + words[k]) & 0xFFFFFFFF, (3, 7, 11, 19)[k % 4])
            a, b, c, d = d, a, b, c

        for j in range(16):
            k = (j % 4) * 4 + j // 4
            a = _rol((a + _g(b, c, d) + words[k] + 0x5A827999) & 0xFFFFFFFF, (3, 5, 9, 13)[j % 4])
            a, b, c, d = d, a, b, c

        r3_order = (0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15)
        for j in range(16):
            a = _rol((a + _h(b, c, d) + words[r3_order[j]] + 0x6ED9EBA1) & 0xFFFFFFFF, (3, 9, 11, 15)[j % 4])
            a, b, c, d = d, a, b, c

        a0 = (a0 + a) & 0xFFFFFFFF
        b0 = (b0 + b) & 0xFFFFFFFF
        c0 = (c0 + c) & 0xFFFFFFFF
        d0 = (d0 + d) & 0xFFFFFFFF

    return struct.pack("<4I", a0, b0, c0, d0)
