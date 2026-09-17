from code_deck.turzx import libusb


def test_env_override_wins(tmp_path):
    lib = tmp_path / "libusb-1.0.dylib"
    lib.write_bytes(b"")
    assert libusb.find_libusb(env={libusb.ENV_VAR: str(lib)}, candidates=()) == str(lib)


def test_env_override_missing_file_is_none(tmp_path):
    assert libusb.find_libusb(env={libusb.ENV_VAR: str(tmp_path / "nope")}, candidates=()) is None


def test_candidate_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(libusb.ctypes.util, "find_library", lambda _: None)
    lib = tmp_path / "libusb-1.0.so.0"
    lib.write_bytes(b"")
    assert libusb.find_libusb(env={}, candidates=(str(tmp_path / "x"), str(lib))) == str(lib)


def test_nothing_found(monkeypatch):
    monkeypatch.setattr(libusb.ctypes.util, "find_library", lambda _: None)
    assert libusb.find_libusb(env={}, candidates=()) is None
