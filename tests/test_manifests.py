from pathlib import Path
from dump import ManifestDiscovery, index_to_spreadsheet_id, CSVManifestParser, Action, Target

def test_spreadsheet_ids():
    assert index_to_spreadsheet_id(0) == "A"
    assert index_to_spreadsheet_id(25) == "Z"
    assert index_to_spreadsheet_id(26) == "AA"
    assert index_to_spreadsheet_id(51) == "AZ"
    assert index_to_spreadsheet_id(52) == "BA"

def test_manifest_discovery_ignores_example(tmp_path: Path):
    (tmp_path / "example.csv").write_text("# example", encoding="utf-8")
    (tmp_path / "app.csv").write_text("src", encoding="utf-8")
    (tmp_path / "backend.csv").write_text("src/api", encoding="utf-8")

    manifests = ManifestDiscovery.discover(tmp_path)
    assert len(manifests) == 2
    assert manifests[0].ident == "A"
    assert manifests[0].filename == "app.csv"
    assert manifests[1].ident == "B"
    assert manifests[1].filename == "backend.csv"

def test_csv_parser_simple_and_advanced(tmp_path: Path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "# Comment row\n"
        "./src\n"
        "ACTION,TARGET,PATTERN\n"
        "EXCLUDE,PATH,./src/generated\n"
        "EXCLUDE,FILENAME,*_test.py\n"
        "EXCLUDE,EXTENSION,.log\n",
        encoding="utf-8"
    )
    rules, errors, malformed = CSVManifestParser.parse_manifest(csv_file, tmp_path)
    assert malformed == 0
    assert len(errors) == 0
    assert len(rules) == 4
    assert rules[0].action == Action.INCLUDE and rules[0].target == Target.PATH
    assert rules[1].action == Action.EXCLUDE and rules[1].target == Target.PATH
    assert rules[2].action == Action.EXCLUDE and rules[2].target == Target.FILENAME
    assert rules[3].action == Action.EXCLUDE and rules[3].target == Target.EXTENSION