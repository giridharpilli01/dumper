from pathlib import Path
from dump import IncrementalStreamWriter, DumpToFilesEngine, DiscoveredFile, MatchResult, Settings

def test_incremental_txt_stream_and_partial_on_error(tmp_path: Path):
    final_txt = tmp_path / "output.txt"
    streamer = IncrementalStreamWriter(final_txt)
    with streamer:
        streamer.write_header(["manifest.csv"], "10_16_12_00", {}, is_all=False)
        streamer.append_file(tmp_path / "test.py", "UTF-8", "print('hello')")
        # Simulating interrupt/exception by preserving partial
        partial = streamer.preserve_partial()

    assert partial is not None
    assert partial.exists()
    assert partial.suffix == ".partial"
    assert not final_txt.exists()

def test_dump_to_files_transactional_staging(tmp_path: Path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    f1 = source_root / "app.py"
    f1.write_text("print(1)", encoding="utf-8")

    out_dir = tmp_path / "export"
    disc = [
        DiscoveredFile(f1, str(f1), "m.csv", MatchResult(True, "Included"))
    ]

    exporter = DumpToFilesEngine(Settings(), out_dir)
    final_dir, report = exporter.export_files(disc, base_name="test_export")

    assert final_dir.exists()
    assert (final_dir / "app.py").exists()
    assert (final_dir / "app.py").read_text(encoding="utf-8") == "print(1)"
    assert (final_dir / "export_report.json").exists()