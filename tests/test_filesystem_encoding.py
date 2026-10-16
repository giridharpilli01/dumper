import pytest
from pathlib import Path
from dump import EncodingDetector, PathResolver, DEFAULT_MAX_FILE_SIZE

def test_symlink_safety_rejection(tmp_path: Path):
    target = tmp_path / "real_dir"
    target.mkdir()
    link = tmp_path / "link_dir"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform/privilege")

    assert PathResolver.is_directory_symlink_or_junction(link) is True
    assert PathResolver.is_directory_symlink_or_junction(target) is False

def test_encoding_bom_and_utf8(tmp_path: Path):
    f_utf8 = tmp_path / "utf8.txt"
    f_utf8.write_text("Hello World", encoding="utf-8")
    content, enc, err = EncodingDetector.read_and_decode(f_utf8, DEFAULT_MAX_FILE_SIZE, binary_detection=True)
    assert err is None
    assert content == "Hello World"
    assert enc == "UTF-8"

    f_bom = tmp_path / "bom.txt"
    f_bom.write_bytes(b"\xef\xbb\xbfBOM Content")
    content, enc, err = EncodingDetector.read_and_decode(f_bom, DEFAULT_MAX_FILE_SIZE, binary_detection=True)
    assert err is None
    assert content == "BOM Content"
    assert enc == "UTF-8-BOM"

def test_binary_heuristic_and_explicit_override(tmp_path: Path):
    f_bin = tmp_path / "data.bin"
    f_bin.write_bytes(b"hello\x00world\x00binary")

    # Regular evaluation skips binary
    content, enc, err = EncodingDetector.read_and_decode(f_bin, DEFAULT_MAX_FILE_SIZE, binary_detection=True, explicit_include=False)
    assert err == "Binary file detected"

    # Explicit include tries decoding
    content, enc, err = EncodingDetector.read_and_decode(f_bin, DEFAULT_MAX_FILE_SIZE, binary_detection=True, explicit_include=True)
    assert content is not None or "could not be safely decoded" in err

def test_oversized_file_limit(tmp_path: Path):
    f_large = tmp_path / "large.txt"
    f_large.write_bytes(b"x" * 1024)
    # Set limit below file size
    _, _, err = EncodingDetector.read_and_decode(f_large, max_file_size=512, binary_detection=True)
    assert "Oversized file" in err