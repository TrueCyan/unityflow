"""Tests for DLL inspector - .NET metadata parsing and Unity fileID computation."""

from unityflow.dll_inspector import (
    _md4,
    _md4_pure,
    compute_unity_file_id,
)


class TestMD4:
    def test_rfc1320_empty(self):
        assert _md4_pure(b"").hex() == "31d6cfe0d16ae931b73c59d7e0c089c0"

    def test_rfc1320_a(self):
        assert _md4_pure(b"a").hex() == "bde52cb31de33e46245e05fbdbd6fb24"

    def test_rfc1320_abc(self):
        assert _md4_pure(b"abc").hex() == "a448017aaf21d8525fc10ae87aa6729d"

    def test_rfc1320_message_digest(self):
        assert _md4_pure(b"message digest").hex() == "d9130a8164549fe818874806e1c7014b"

    def test_rfc1320_alphabet(self):
        assert _md4_pure(b"abcdefghijklmnopqrstuvwxyz").hex() == "d79e1c308aa5bbcdeea8ed63df412da9"

    def test_wrapper_matches_pure(self):
        for data in [b"", b"test", b"hello world"]:
            assert _md4(data) == _md4_pure(data)


class TestUnityFileID:
    def test_deterministic(self):
        a = compute_unity_file_id("Namespace", "ClassName")
        b = compute_unity_file_id("Namespace", "ClassName")
        assert a == b

    def test_different_namespace_different_id(self):
        a = compute_unity_file_id("NS1", "Class")
        b = compute_unity_file_id("NS2", "Class")
        assert a != b

    def test_different_class_different_id(self):
        a = compute_unity_file_id("NS", "ClassA")
        b = compute_unity_file_id("NS", "ClassB")
        assert a != b

    def test_empty_namespace(self):
        fid = compute_unity_file_id("", "MyClass")
        assert isinstance(fid, int)

    def test_returns_signed_int32(self):
        fid = compute_unity_file_id("DG.Tweening", "DOTweenAnimation")
        assert -(2**31) <= fid <= 2**31 - 1
