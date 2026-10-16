#!/usr/bin/env python3
"""
AI Context Dumper (dump.py) - Version 2.0 (Dual GUI/CLI Engine)

Preserves canonical manifest evaluation, safety invariants, and text extraction.
Exposes inspector interfaces and transactional file exporting for PySide6.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime
import enum
import fnmatch
import json
import math
import os
import re
import shutil
import sys
import time
import tempfile
import threading
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, Any

# ============================================================================
# 1. CONSTANTS & SYSTEM GLOBALS
# ============================================================================

# ============================================================================
# VERSION & BUILD METADATA
# ============================================================================

__version__: str = "0.1.1"
__build__: str = "2026.10.16.1"

SCHEMA_VERSION: int = 1
DEFAULT_MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5 MiB hard safety ceiling
DEFAULT_SETTINGS_FILENAME: str = "settings.json"
EXAMPLE_CSV_FILENAME: str = "example.csv"
GUI_STATE_FILENAME: str = "gui_state.json"
MAX_HISTORY_ENTRIES: int = 6

WINDOWS_RESERVED_NAMES: Set[str] = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

DEFAULT_SKIPPED_DIRECTORIES: List[str] = [
    ".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", ".cache"
]

EXAMPLE_CSV_CONTENT: str = """# AI Context Dumper - Manifest Specification & Syntax Guide
# Lines beginning with '#' and blank lines are ignored.
#
# Rule Precedence:
#   1. Most specific matching rule wins.
#   2. Equal specificity -> INCLUDE wins over EXCLUDE.
#   3. Explicit CSV inclusion overrides ordinary global selection settings.
#   4. Explicit CSV inclusion does NOT bypass hard safety constraints (5 MB limit, symlinks).
#
ACTION,TARGET,PATTERN
INCLUDE,PATH,./src
EXCLUDE,PATH,./src/generated
INCLUDE,PATH,./src/generated/bootstrap.py
EXCLUDE,FILENAME,*_test.py
EXCLUDE,FILENAME,temp_*
EXCLUDE,EXTENSION,.log
EXCLUDE,EXTENSION,.bak
"""

# ============================================================================
# 2. CONFIGURATION & HISTORY MODELS
# ============================================================================

@dataclass
class HistoryEntry:
    name: str
    manifest_filenames: List[str]
    last_used: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "manifest_filenames": sorted(list(set(self.manifest_filenames)), key=lambda s: (s.casefold(), s)),
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        if not isinstance(data, dict):
            raise ValueError("History entry must be a JSON object.")
        name = data.get("name", "").strip()
        if not name:
            raise ValueError("History entry missing string property 'name'.")
        fn_list = data.get("manifest_filenames", [])
        if not isinstance(fn_list, list) or not all(isinstance(fn, str) for fn in fn_list):
            raise ValueError("History entry 'manifest_filenames' must be a list of strings.")
        clean_filenames = [fn.strip() for fn in fn_list if fn.strip()]
        last_used = float(data.get("last_used", time.time()))
        return cls(name=name, manifest_filenames=sorted(list(set(clean_filenames)), key=lambda s: (s.casefold(), s)), last_used=last_used)

@dataclass
class Settings:
    schema_version: int = SCHEMA_VERSION
    output_directory: str = "output"
    max_file_size: int = DEFAULT_MAX_FILE_SIZE
    include_extensions: List[str] = field(default_factory=list)
    include_filenames: List[str] = field(default_factory=list)
    exclude_extensions: List[str] = field(default_factory=list)
    exclude_filenames: List[str] = field(default_factory=list)
    allow_extensionless: bool = False
    skipped_directories: List[str] = field(default_factory=lambda: list(DEFAULT_SKIPPED_DIRECTORIES))
    binary_detection: bool = True
    verbose: bool = False
    approximate_token_count: bool = False
    multi_select_history: List[HistoryEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "output_directory": self.output_directory,
            "max_file_size": self.max_file_size,
            "include_extensions": self.include_extensions,
            "include_filenames": self.include_filenames,
            "exclude_extensions": self.exclude_extensions,
            "exclude_filenames": self.exclude_filenames,
            "allow_extensionless": self.allow_extensionless,
            "skipped_directories": self.skipped_directories,
            "binary_detection": self.binary_detection,
            "verbose": self.verbose,
            "approximate_token_count": self.approximate_token_count,
            "multi_select_history": [h.to_dict() for h in self.multi_select_history],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        if not isinstance(data, dict):
            raise ValueError("Root configuration must be a JSON object.")
        schema = data.get("schema_version")
        if schema != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema_version: {schema}. Expected {SCHEMA_VERSION}.")

        max_file_size = data.get("max_file_size", DEFAULT_MAX_FILE_SIZE)
        if not isinstance(max_file_size, int) or max_file_size <= 0:
            raise ValueError("max_file_size must be a positive integer.")
        if max_file_size > DEFAULT_MAX_FILE_SIZE:
            raise ValueError(f"max_file_size cannot exceed the hard safety limit of {DEFAULT_MAX_FILE_SIZE:,} bytes (5 MiB).")

        history_raw = data.get("multi_select_history", [])
        if len(history_raw) > MAX_HISTORY_ENTRIES:
            raise ValueError(f"multi_select_history exceeds limit of {MAX_HISTORY_ENTRIES}.")
        history = [HistoryEntry.from_dict(h) for h in history_raw]
        history.sort(key=lambda x: x.last_used, reverse=True)

        return cls(
            schema_version=schema,
            output_directory=str(data.get("output_directory", "output")).strip() or "output",
            max_file_size=max_file_size,
            include_extensions=[ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in data.get("include_extensions", [])],
            include_filenames=list(data.get("include_filenames", [])),
            exclude_extensions=[ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in data.get("exclude_extensions", [])],
            exclude_filenames=list(data.get("exclude_filenames", [])),
            allow_extensionless=bool(data.get("allow_extensionless", False)),
            skipped_directories=list(data.get("skipped_directories", DEFAULT_SKIPPED_DIRECTORIES)),
            binary_detection=bool(data.get("binary_detection", True)),
            verbose=bool(data.get("verbose", False)),
            approximate_token_count=bool(data.get("approximate_token_count", False)),
            multi_select_history=history,
        )

class ConfigManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.resolve()
        self.settings_path = self.base_dir / DEFAULT_SETTINGS_FILENAME
        self.example_csv_path = self.base_dir / EXAMPLE_CSV_FILENAME

    def save_settings(self, settings: Settings) -> None:
        temp_file = self.base_dir / f"{DEFAULT_SETTINGS_FILENAME}.{os.getpid()}.{time.time_ns()}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(settings.to_dict(), f, indent=4)
            temp_file.replace(self.settings_path)
        finally:
            if temp_file.exists():
                with contextlib.suppress(OSError):
                    temp_file.unlink()

    def create_example_csv_if_missing(self) -> bool:
        if not self.example_csv_path.exists():
            try:
                with open(self.example_csv_path, "w", encoding="utf-8") as f:
                    f.write(EXAMPLE_CSV_CONTENT)
                return True
            except OSError:
                return False
        return False

    def backup_corrupt_settings(self) -> Path:
        idx = 1
        while True:
            backup = self.base_dir / f"settings-old({idx}).json"
            if not backup.exists():
                break
            idx += 1
        self.settings_path.rename(backup)
        return backup

    def bootstrap_settings(self, interactive: bool = True) -> Settings:
        if not self.settings_path.exists():
            if interactive:
                print(f"[!] Configuration '{DEFAULT_SETTINGS_FILENAME}' not found.")
                resp = input("Create default configuration now? [Y/n]: ").strip().lower()
                if resp not in ("", "y", "yes"):
                    sys.exit(0)
            self.save_settings(Settings())
            self.create_example_csv_if_missing()

        while True:
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                settings = Settings.from_dict(data)
                self.create_example_csv_if_missing()
                return settings
            except Exception as e:
                backup = self.backup_corrupt_settings()
                if interactive:
                    print(f"[!] Invalid configuration: {e}. Preserved as '{backup.name}'.")
                self.save_settings(Settings())
                self.create_example_csv_if_missing()
                if not interactive:
                    return Settings()

# ============================================================================
# 3. PATH RESOLUTION, EXPANSION, AND PATH IDENTITY
# ============================================================================

class PathResolver:
    @staticmethod
    def expand_path_string(raw_path: str, base_dir: Path) -> Path:
        p_str = raw_path.strip()
        win_var = re.compile(r"%([^%]+)%")
        p_str = win_var.sub(lambda m: os.environ.get(m.group(1), m.group(0)), p_str)
        p_str = os.path.expandvars(p_str)
        p_str = os.path.expanduser(p_str)
        p = Path(p_str)
        if not p.is_absolute():
            p = base_dir / p
        return Path(os.path.normpath(str(p)))

    @staticmethod
    def normalized_absolute_path(path: Path) -> Path:
        return Path(os.path.normcase(os.path.normpath(str(path.absolute()))))

    @staticmethod
    def path_identity(path: Path) -> str:
        return os.path.normcase(os.path.normpath(str(path.absolute())))

    @staticmethod
    def is_directory_symlink_or_junction(path: Path) -> bool:
        try:
            if path.is_symlink() and path.is_dir():
                return True
            if hasattr(os.path, "isjunction") and os.path.isjunction(path):
                return True
            return False
        except (OSError, PermissionError):
            return True

# ============================================================================
# 4. MANIFEST DISCOVERY & SPREADSHEET IDENTIFIERS
# ============================================================================

def index_to_spreadsheet_id(index: int) -> str:
    result = []
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result.append(chr(65 + remainder))
    return "".join(reversed(result))

@dataclass
class ManifestInfo:
    ident: str
    filename: str
    path: Path

class ManifestDiscovery:
    @staticmethod
    def discover(base_dir: Path) -> List[ManifestInfo]:
        csv_files = []
        try:
            for entry in os.scandir(base_dir):
                if entry.is_file() and entry.name.lower().endswith(".csv"):
                    if entry.name.lower() == EXAMPLE_CSV_FILENAME.lower():
                        continue
                    csv_files.append(entry.name)
        except OSError:
            return []
        csv_files.sort(key=lambda s: (s.casefold(), s))
        return [ManifestInfo(index_to_spreadsheet_id(i), fn, base_dir / fn) for i, fn in enumerate(csv_files)]

# ============================================================================
# 5. CSV PARSER & PURE RULE ENGINE
# ============================================================================

class Action:
    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"

class Target:
    PATH = "PATH"
    FILENAME = "FILENAME"
    EXTENSION = "EXTENSION"

@dataclass
class Rule:
    action: str
    target: str
    raw_pattern: str
    normalized_path: Optional[Path] = None
    line_number: int = 0
    source_manifest: str = ""

    def specificity(self) -> int:
        if self.target == Target.PATH and self.normalized_path is not None:
            try:
                return 500 + len(self.normalized_path.parts)
            except Exception:
                return 500
        if self.target == Target.FILENAME:
            wc = self.raw_pattern.count("*") + self.raw_pattern.count("?")
            return max(150, 200 - wc) if wc > 0 else 300
        if self.target == Target.EXTENSION:
            return 100
        return 0

    def compact_repr(self) -> str:
        return f"{self.action} {self.target} {self.raw_pattern}"

class CSVManifestParser:
    @staticmethod
    def parse_manifest(manifest_path: Path, base_dir: Path) -> Tuple[List[Rule], List[str], int]:
        rules: List[Rule] = []
        errors: List[str] = []
        malformed = 0
        if not manifest_path.exists():
            return rules, [f"Manifest file does not exist: {manifest_path}"], 1

        try:
            with open(manifest_path, "r", encoding="utf-8-sig", errors="strict", newline="") as f:
                reader = csv.reader(f)
                for line_no, row in enumerate(reader, start=1):
                    cells = [c.strip() for c in row]
                    if not cells or all(len(c) == 0 for c in cells):
                        continue
                    if cells[0].startswith("#"):
                        continue
                    if len(cells) == 3 and cells[0].upper() == "ACTION" and cells[1].upper() == "TARGET" and cells[2].upper() == "PATTERN":
                        continue

                    if len(cells) == 3:
                        action, target, pattern = cells[0].upper(), cells[1].upper(), cells[2]
                        if action not in (Action.INCLUDE, Action.EXCLUDE):
                            errors.append(f"Line {line_no}: Invalid ACTION '{action}'")
                            malformed += 1
                            continue
                        if target not in (Target.PATH, Target.FILENAME, Target.EXTENSION):
                            errors.append(f"Line {line_no}: Invalid TARGET '{target}'")
                            malformed += 1
                            continue
                        norm_p = PathResolver.expand_path_string(pattern, base_dir) if target == Target.PATH else None
                        if target == Target.EXTENSION:
                            pattern = f".{pattern.lstrip('.').lower()}"
                        rules.append(Rule(action, target, pattern, norm_p, line_no, manifest_path.name))
                    elif len(cells) == 1:
                        raw = cells[0]
                        rules.append(Rule(Action.INCLUDE, Target.PATH, raw, PathResolver.expand_path_string(raw, base_dir), line_no, manifest_path.name))
                    else:
                        errors.append(f"Line {line_no}: Expected 1 or 3 columns, got {len(cells)}")
                        malformed += 1
        except Exception as e:
            errors.append(f"Error parsing manifest {manifest_path.name}: {e}")
            malformed += 1
        return rules, errors, malformed

@dataclass
class MatchResult:
    eligible: bool
    reason: str
    winning_rule: Optional[Rule] = None
    overrides_global_selection: bool = False

class RuleEngine:
    @staticmethod
    def is_subpath(child: Path, parent: Path) -> bool:
        try:
            c = os.path.normcase(os.path.abspath(str(child)))
            p = os.path.normcase(os.path.abspath(str(parent)))
            return os.path.commonpath([c, p]) == p
        except (ValueError, OSError):
            return False

    @staticmethod
    def evaluate_file(file_path: Path, manifest_rules: List[Rule], settings: Settings, output_dir: Path) -> MatchResult:
        if RuleEngine.is_subpath(file_path, output_dir):
            return MatchResult(False, "Protected: File is inside output directory.")

        filename = file_path.name
        ext = file_path.suffix.lower()
        matching_rules: List[Rule] = []

        for rule in manifest_rules:
            if rule.target == Target.PATH and rule.normalized_path is not None:
                if RuleEngine.is_subpath(file_path, rule.normalized_path):
                    matching_rules.append(rule)
            elif rule.target == Target.FILENAME and fnmatch.fnmatchcase(filename, rule.raw_pattern):
                matching_rules.append(rule)
            elif rule.target == Target.EXTENSION and ext == rule.raw_pattern.lower():
                matching_rules.append(rule)

        if matching_rules:
            matching_rules.sort(key=lambda r: (r.specificity(), 1 if r.action == Action.INCLUDE else 0), reverse=True)
            winner = matching_rules[0]
            if winner.action == Action.INCLUDE:
                return MatchResult(True, f"Matched manifest rule [{winner.compact_repr()}] (specificity {winner.specificity()})", winner, True)
            return MatchResult(False, f"Excluded by manifest rule [{winner.compact_repr()}] (specificity {winner.specificity()})", winner, False)

        if not ext and not settings.allow_extensionless:
            return MatchResult(False, "Extensionless file excluded by global settings.")
        if ext in settings.exclude_extensions:
            return MatchResult(False, f"Extension '{ext}' matched global exclude_extensions.")
        for pat in settings.exclude_filenames:
            if fnmatch.fnmatchcase(filename, pat):
                return MatchResult(False, f"Filename '{filename}' matched global exclude_filenames pattern '{pat}'.")
        if settings.include_extensions and ext not in settings.include_extensions:
            return MatchResult(False, f"Extension '{ext}' not in global include_extensions whitelist.")
        if settings.include_filenames and not any(fnmatch.fnmatchcase(filename, pat) for pat in settings.include_filenames):
            return MatchResult(False, f"Filename '{filename}' not in global include_filenames whitelist.")

        return MatchResult(True, "Allowed by default global settings.")

    @classmethod
    def explain_file(cls, file_path: Path, manifest_rules: List[Rule], settings: Settings, output_dir: Path) -> Dict[str, Any]:
        """Provides full structural explanation for GUI Rule Inspector."""
        result = cls.evaluate_file(file_path, manifest_rules, settings, output_dir)
        filename = file_path.name
        ext = file_path.suffix.lower()

        matched = []
        for r in manifest_rules:
            if (r.target == Target.PATH and r.normalized_path and cls.is_subpath(file_path, r.normalized_path)) or \
               (r.target == Target.FILENAME and fnmatch.fnmatchcase(filename, r.raw_pattern)) or \
               (r.target == Target.EXTENSION and ext == r.raw_pattern.lower()):
                matched.append(r)

        matched.sort(key=lambda r: (r.specificity(), 1 if r.action == Action.INCLUDE else 0), reverse=True)

        safety_blocker = None
        if file_path.is_file():
            try:
                stat_res = file_path.stat()
                if stat_res.st_size > settings.max_file_size:
                    safety_blocker = f"File exceeds max size ({stat_res.st_size / (1024*1024):.2f} MB > {settings.max_file_size / (1024*1024):.2f} MB)"
            except OSError as e:
                safety_blocker = f"Filesystem access error: {e}"
        elif file_path.exists() and PathResolver.is_directory_symlink_or_junction(file_path):
            safety_blocker = "Directory symlink or junction cannot be followed"

        return {
            "canonical_path": str(PathResolver.normalized_absolute_path(file_path)),
            "effective_eligible": result.eligible and (safety_blocker is None),
            "reason": result.reason,
            "winning_rule": result.winning_rule.compact_repr() if result.winning_rule else None,
            "matching_rules": [m.compact_repr() for m in matched],
            "overrides_global": result.overrides_global_selection,
            "safety_blocker": safety_blocker
        }

# ============================================================================
# 6. FILESYSTEM SCANNING & DISCOVERY
# ============================================================================

@dataclass
class DiscoveredFile:
    source_path: Path
    canonical_id: str
    manifest_name: str
    match_result: MatchResult

@dataclass
class ScanResult:
    discovered_files: List[DiscoveredFile]
    missing_paths: List[str]
    warnings: List[str]
    symlink_skips: int = 0

class FilesystemScanner:
    @staticmethod
    def scan_manifest(
        manifest_info: ManifestInfo,
        rules: List[Rule],
        settings: Settings,
        output_dir: Path,
        counter_cb: Optional[Callable[[int], None]] = None,
        check_cancelled: Optional[Callable[[], bool]] = None,
    ) -> ScanResult:
        discovered: List[DiscoveredFile] = []
        missing_paths: List[str] = []
        warnings: List[str] = []
        symlink_skips = 0

        include_path_roots = [r for r in rules if r.target == Target.PATH and r.action == Action.INCLUDE and r.normalized_path]
        if not include_path_roots:
            warnings.append(f"[{manifest_info.filename}] No INCLUDE PATH roots found.")
            return ScanResult(discovered, missing_paths, warnings, symlink_skips)

        skipped_names = {name.casefold() for name in settings.skipped_directories}
        count = 0

        for p_rule in include_path_roots:
            if check_cancelled and check_cancelled():
                break
            root = p_rule.normalized_path
            assert root is not None
            if not root.exists():
                missing_paths.append(f"[{manifest_info.filename}] Path missing: '{p_rule.raw_pattern}' ({root})")
                continue

            if root.is_file():
                if root.is_symlink():
                    symlink_skips += 1
                    continue
                res = RuleEngine.evaluate_file(root, rules, settings, output_dir)
                discovered.append(DiscoveredFile(root, PathResolver.path_identity(root), manifest_info.filename, res))
                count += 1
                if counter_cb:
                    counter_cb(count)
                continue

            for dirpath, dirnames, filenames in os.walk(str(root), topdown=True, followlinks=False):
                if check_cancelled and check_cancelled():
                    break
                current_dir = Path(dirpath)
                pruned = []
                for d in dirnames:
                    d_p = current_dir / d
                    if PathResolver.is_directory_symlink_or_junction(d_p):
                        symlink_skips += 1
                        continue
                    if RuleEngine.is_subpath(d_p, output_dir):
                        continue
                    if d.casefold() in skipped_names:
                        override = any(r.action == Action.INCLUDE and r.target == Target.PATH and r.normalized_path and RuleEngine.is_subpath(r.normalized_path, d_p) for r in rules)
                        if not override:
                            continue
                    pruned.append(d)
                dirnames[:] = pruned

                for fn in filenames:
                    if check_cancelled and check_cancelled():
                        break
                    f_p = current_dir / fn
                    if f_p.is_symlink():
                        symlink_skips += 1
                        continue
                    if RuleEngine.is_subpath(f_p, output_dir):
                        continue
                    res = RuleEngine.evaluate_file(f_p, rules, settings, output_dir)
                    discovered.append(DiscoveredFile(f_p, PathResolver.path_identity(f_p), manifest_info.filename, res))
                    count += 1
                    if counter_cb:
                        counter_cb(count)

        return ScanResult(discovered, missing_paths, warnings, symlink_skips)

# ============================================================================
# 7. CONSERVATIVE ENCODING & CONTENT SAFETY
# ============================================================================

class EncodingDetector:
    @staticmethod
    def is_binary_buffer(data: bytes) -> bool:
        if not data:
            return False
        if b"\x00" in data:
            return True
        controls = sum(1 for b in data if (0 <= b < 32 or b == 127) and b not in (9, 10, 12, 13))
        return (controls / len(data)) > 0.10

    @classmethod
    def read_and_decode(cls, file_path: Path, max_file_size: int, binary_detection: bool, explicit_include: bool = False) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        try:
            stat_res = file_path.stat()
        except OSError as e:
            return None, None, f"Cannot access file: {e}"

        if stat_res.st_size > max_file_size:
            return None, None, f"Oversized file ({stat_res.st_size/(1024*1024):.2f} MB > {max_file_size/(1024*1024):.2f} MB)"
        if stat_res.st_size == 0:
            return "", "EMPTY", None

        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except OSError as e:
            return None, None, f"Read error: {e}"

        if len(raw) > max_file_size:
            return None, None, f"File grew during read ({len(raw)/(1024*1024):.2f} MB > {max_file_size/(1024*1024):.2f} MB)"

        # ------------------------------------------------------------
        # Explicit BOM Detection (Must precede binary check because
        # UTF-16 BOM files legitimately contain \x00 bytes)
        # ------------------------------------------------------------
        if raw.startswith(b"\xef\xbb\xbf"):
            with contextlib.suppress(UnicodeDecodeError):
                return raw[3:].decode("utf-8"), "UTF-8-BOM", None
        if raw.startswith(b"\xff\xfe"):
            with contextlib.suppress(UnicodeDecodeError):
                return raw.decode("utf-16-le"), "UTF-16-LE", None
        if raw.startswith(b"\xfe\xff"):
            with contextlib.suppress(UnicodeDecodeError):
                return raw.decode("utf-16-be"), "UTF-16-BE", None

        # ------------------------------------------------------------
        # Binary Heuristic Detection
        # ------------------------------------------------------------
        if binary_detection and cls.is_binary_buffer(raw[:8192]):
            if not explicit_include:
                return None, None, "Binary file detected"

        # ------------------------------------------------------------
        # Standard UTF-8
        # ------------------------------------------------------------
        try:
            return raw.decode("utf-8"), "UTF-8", None
        except UnicodeDecodeError:
            pass

        # ------------------------------------------------------------
        # Conservative CP1252 Fallback
        # ------------------------------------------------------------
        try:
            cand = raw.decode("cp1252")
            sample = cand[: min(len(cand), 4096)]
            unprintable = sum(1 for ch in sample if ord(ch) < 32 and ch not in "\r\n\t")
            if sample and (unprintable / len(sample)) < 0.02:
                return cand, "Windows-1252", None
        except UnicodeDecodeError:
            pass

        return None, None, "Explicitly included file could not be safely decoded as text" if explicit_include else "Undecodable text encoding"

# ============================================================================
# 8. OUTPUT WRITER & TRANSACTIONAL DUMP-TO-FILES
# ============================================================================

def sanitize_filename_part(name: str) -> str:
    s = re.sub(r'[\\/*?:"<>|\t\n\r]+', "_", name).strip("._").rstrip(" .")
    if not s:
        return "dump"
    if s.upper() in WINDOWS_RESERVED_NAMES:
        return f"_{s}"
    return s

class StreamState(enum.Enum):
    OPEN = "OPEN"
    FINALIZED = "FINALIZED"
    PRESERVED = "PRESERVED"
    ABORTED = "ABORTED"

class IncrementalStreamWriter:
    def __init__(self, final_path: Path):
        self.final_path = final_path
        self.temp_path = final_path.parent / f".{final_path.name}.{os.getpid()}.{time.time_ns()}.tmp"
        self._file_handle = None
        self.state = StreamState.OPEN
        self.total_bytes_written: int = 0
        self.total_chars_written: int = 0

    def __enter__(self):
        self.final_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_handle = open(self.temp_path, "w", encoding="utf-8", newline="\n")
        self.state = StreamState.OPEN
        return self

    def _write_str(self, text: str) -> None:
        self._file_handle.write(text)
        self.total_bytes_written += len(text.encode("utf-8"))
        self.total_chars_written += len(text)

    def write_header(self, manifest_names: List[str], timestamp_str: str, manifest_rules_map: Dict[str, List[Rule]], is_all: bool) -> None:
        self._write_str(f"MANIFESTS: {'ALL' if is_all else ', '.join(manifest_names)}\nGENERATED: {timestamp_str}\n\n")
        for m_name in manifest_names:
            rules = manifest_rules_map.get(m_name, [])
            self._write_str(f"RULES {m_name}:\n")
            if rules:
                for r in rules:
                    self._write_str(f"{r.compact_repr()}\n")
            else:
                self._write_str("# (No active rules)\n")
            self._write_str("\n")

    def append_file(self, display_path: Path, encoding_name: str, content: str) -> None:
        self._write_str(f"FILE: {display_path}, encoding={encoding_name}\n{content}")
        if not content.endswith("\n"):
            self._write_str("\n")
        self._write_str("\n")

    def finalize(self) -> Path:
        if self._file_handle:
            self._file_handle.flush()
            with contextlib.suppress(OSError):
                os.fsync(self._file_handle.fileno())
            self._file_handle.close()
            self._file_handle = None

        if self.final_path.exists():
            raise FileExistsError(f"Output exists: {self.final_path}")
        self.temp_path.replace(self.final_path)
        self.state = StreamState.FINALIZED
        return self.final_path

    def preserve_partial(self) -> Optional[Path]:
        if self._file_handle:
            with contextlib.suppress(OSError):
                self._write_str("\n\nSTATUS: PARTIAL OUTPUT - DUMP INTERRUPTED OR FAILED\n")
                self._file_handle.close()
            self._file_handle = None

        if not self.temp_path.exists():
            return None

        base = self.final_path.stem
        cand = self.final_path.parent / f"{base}.partial"
        ctr = 1
        while cand.exists():
            cand = self.final_path.parent / f"{base}_{ctr:02d}.partial"
            ctr += 1
        with contextlib.suppress(OSError):
            self.temp_path.replace(cand)
            self.state = StreamState.PRESERVED
            return cand
        return self.temp_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file_handle:
            with contextlib.suppress(OSError):
                self._file_handle.close()
            self._file_handle = None
        return False

class DumpToFilesEngine:
    """Transactional Dump to Files implementation satisfying RoadToGUI Section 8.2 & 18.2."""

    def __init__(self, settings: Settings, output_base_dir: Path):
        self.settings = settings
        self.output_base_dir = output_base_dir

    def export_files(
        self,
        eligible_files: List[DiscoveredFile],
        base_name: str,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        check_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Tuple[Path, Dict[str, Any]]:
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        now_str = datetime.datetime.now().strftime("%m_%d_%H_%M")
        sanitized = sanitize_filename_part(base_name)
        target_dir_name = f"{sanitized}_{now_str}"
        final_dir = self.output_base_dir / target_dir_name

        ctr = 1
        while final_dir.exists():
            final_dir = self.output_base_dir / f"{target_dir_name}_{ctr:02d}"
            ctr += 1

        staging_dir = self.output_base_dir / f".staging_{target_dir_name}_{os.getpid()}_{time.time_ns()}"
        staging_dir.mkdir(parents=True, exist_ok=False)

        exported, skipped, failed = [], [], []

        try:
            # Common root detection for preserving relative structure
            parent_paths = [df.source_path.parent for df in eligible_files if df.match_result.eligible]
            try:
                common_base = Path(os.path.commonpath([str(p) for p in parent_paths])) if parent_paths else Path(".")
            except ValueError:
                common_base = None

            total = len(eligible_files)
            for idx, df in enumerate(eligible_files, start=1):
                if check_cancelled and check_cancelled():
                    raise KeyboardInterrupt("Export cancelled by user.")

                sp = df.source_path
                try:
                    if common_base and RuleEngine.is_subpath(sp, common_base):
                        rel_path = sp.relative_to(common_base)
                    else:
                        rel_path = Path(sp.drive.replace(":", "") if sp.drive else "") / sp.relative_to(sp.anchor)
                except Exception:
                    rel_path = Path(sp.name)

                dest_file = (staging_dir / rel_path).resolve()

                # Safety: Destination escape prevention
                if not RuleEngine.is_subpath(dest_file, staging_dir):
                    failed.append({"path": str(sp), "error": "Destination path escape detected"})
                    continue

                explicit_inc = (df.match_result.winning_rule is not None and df.match_result.winning_rule.action == Action.INCLUDE)
                content, enc, err = EncodingDetector.read_and_decode(sp, self.settings.max_file_size, self.settings.binary_detection, explicit_inc)

                if err:
                    skipped.append({"path": str(sp), "reason": err})
                    continue

                assert content is not None
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_text(content, encoding="utf-8")
                exported.append({"source": str(sp), "exported": str(rel_path), "encoding": enc})

                if progress_cb:
                    progress_cb(idx, total)

            report = {
                "timestamp": now_str,
                "exported_count": len(exported),
                "skipped_count": len(skipped),
                "failed_count": len(failed),
                "exported_files": exported,
                "skipped_files": skipped,
                "failed_files": failed
            }

            (staging_dir / "export_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            staging_dir.rename(final_dir)
            return final_dir, report

        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

# ============================================================================
# 9. CONSOLE PROGRESS & DIAGNOSTICS DISPLAY
# ============================================================================

class UIProgress:
    @staticmethod
    def show_discovery(count: int) -> None:
        sys.stdout.write(f"\rScanning... {count:,} filesystem entries examined")
        sys.stdout.flush()

    @staticmethod
    def render_bar(current: int, total: int, prefix: str = "Processing...", bar_length: int = 25) -> None:
        pct = 100.0 if total <= 0 else (current / total) * 100.0
        filled = bar_length if total <= 0 else int(bar_length * current // total)
        bar = "█" * filled + "░" * (bar_length - filled)
        sys.stdout.write(f"\r{prefix:<14} [{bar}] {pct:5.1f}% ({current}/{total})")
        sys.stdout.flush()

    @staticmethod
    def finish() -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()

@dataclass
class DiagnosticStats:
    selected_manifests: List[str] = field(default_factory=list)
    csv_rules_parsed: int = 0
    malformed_csv_rows: int = 0
    missing_paths: int = 0
    entries_discovered: int = 0
    unique_files_included: int = 0
    unique_files_excluded: int = 0
    duplicate_paths: int = 0
    symlink_skips: int = 0
    oversized_skips: int = 0
    binary_skips: int = 0
    encoding_skips: int = 0
    unreadable_skips: int = 0
    files_dumped: int = 0
    total_source_bytes: int = 0
    output_file_bytes: int = 0
    output_path: Optional[Path] = None
    output_status: str = "COMPLETED"
    elapsed_time: float = 0.0
    approx_tokens: int = 0
    notices_and_warnings: List[str] = field(default_factory=list)

# ============================================================================
# 10. ENGINE EXECUTION & ORCHESTRATION
# ============================================================================

class DumperEngine:
    def __init__(self, base_dir: Path, config_mgr: ConfigManager, settings: Settings):
        self.base_dir = base_dir.resolve()
        self.config_mgr = config_mgr
        self.settings = settings

    def get_output_dir(self) -> Path:
        out_p = Path(self.settings.output_directory)
        if not out_p.is_absolute():
            out_p = self.base_dir / out_p
        return PathResolver.normalized_absolute_path(out_p)

    def generate_output_filename(self, base_name: str, output_dir: Path, timestamp_str: str) -> Path:
        sanitized = sanitize_filename_part(base_name)
        cand = output_dir / f"{sanitized}_{timestamp_str}.txt"
        ctr = 1
        while cand.exists():
            cand = output_dir / f"{sanitized}_{timestamp_str}_{ctr:02d}.txt"
            ctr += 1
        return cand

    def run_dump(self, selected_manifests: List[ManifestInfo], custom_name: Optional[str] = None, is_all: bool = False,
                 check_cancelled: Optional[Callable[[], bool]] = None,
                 progress_cb: Optional[Callable[[int, int], None]] = None) -> DiagnosticStats:
        start_time = time.time()
        output_dir = self.get_output_dir()
        stats = DiagnosticStats(selected_manifests=[m.filename for m in selected_manifests])
        now_str = datetime.datetime.now().strftime("%m_%d_%H_%M")

        manifest_rules_map: Dict[str, List[Rule]] = {}
        for m in selected_manifests:
            rules, errors, malformed = CSVManifestParser.parse_manifest(m.path, self.base_dir)
            manifest_rules_map[m.filename] = rules
            stats.csv_rules_parsed += len(rules)
            stats.malformed_csv_rows += malformed
            for err in errors:
                stats.notices_and_warnings.append(f"[{m.filename}] {err}")

        discovered_by_manifest: Dict[str, List[DiscoveredFile]] = {}
        total_discovered = 0

        def discovery_counter(c: int):
            nonlocal total_discovered
            total_discovered = c
            UIProgress.show_discovery(c)

        for m in selected_manifests:
            if check_cancelled and check_cancelled():
                stats.output_status = "CANCELLED"
                return stats
            res = FilesystemScanner.scan_manifest(m, manifest_rules_map[m.filename], self.settings, output_dir, counter_cb=discovery_counter, check_cancelled=check_cancelled)
            discovered_by_manifest[m.filename] = res.discovered_files
            stats.missing_paths += len(res.missing_paths)
            stats.symlink_skips += res.symlink_skips
            stats.notices_and_warnings.extend(res.missing_paths + res.warnings)

        UIProgress.finish()
        stats.entries_discovered = total_discovered

        # Union & Deduplication
        id_to_source: Dict[str, Path] = {}
        id_to_inc: Dict[str, List[str]] = {}
        id_to_match: Dict[str, Dict[str, MatchResult]] = {}

        for m in selected_manifests:
            for disc in discovered_by_manifest[m.filename]:
                cid = disc.canonical_id
                if cid not in id_to_source:
                    id_to_source[cid] = disc.source_path
                    id_to_inc[cid] = []
                    id_to_match[cid] = {}
                id_to_match[cid][m.filename] = disc.match_result
                if disc.match_result.eligible and m.filename not in id_to_inc[cid]:
                    id_to_inc[cid].append(m.filename)

        unique_ids = list(id_to_source.keys())
        stats.duplicate_paths = max(0, stats.entries_discovered - len(unique_ids))
        eligible_ids = [cid for cid in unique_ids if id_to_inc[cid]]
        stats.unique_files_included = len(eligible_ids)
        stats.unique_files_excluded = len(unique_ids) - len(eligible_ids)

        selected_sorted = sorted(selected_manifests, key=lambda m: (m.filename.casefold(), m.filename))
        manifest_files: Dict[str, List[Tuple[Path, MatchResult]]] = {m.filename: [] for m in selected_sorted}

        for cid in eligible_ids:
            attr = sorted(id_to_inc[cid], key=lambda s: (s.casefold(), s))[0]
            manifest_files[attr].append((id_to_source[cid], id_to_match[cid][attr]))

        for m_name in manifest_files:
            manifest_files[m_name].sort(key=lambda it: (str(it[0]).casefold(), str(it[0])))

        total_files = sum(len(lst) for lst in manifest_files.values())
        base_output_name = "all" if is_all else (custom_name.strip() if custom_name and custom_name.strip() else ("_".join(sanitize_filename_part(Path(m.filename).stem) for m in selected_sorted) or "selection"))
        final_output_path = self.generate_output_filename(base_output_name, output_dir, now_str)

        streamer = IncrementalStreamWriter(final_output_path)
        processed = 0

        try:
            with streamer:
                streamer.write_header([m.filename for m in selected_sorted], now_str, manifest_rules_map, is_all)
                for m in selected_sorted:
                    for sp, match in manifest_files[m.filename]:
                        if check_cancelled and check_cancelled():
                            raise KeyboardInterrupt("Operation cancelled by user.")
                        explicit_inc = (match.winning_rule is not None and match.winning_rule.action == Action.INCLUDE)
                        content, enc, err = EncodingDetector.read_and_decode(sp, self.settings.max_file_size, self.settings.binary_detection, explicit_inc)
                        processed += 1
                        UIProgress.render_bar(processed, total_files)
                        if progress_cb:
                            progress_cb(processed, total_files)

                        if err:
                            if "Oversized" in err:
                                stats.oversized_skips += 1
                            elif "Binary" in err:
                                stats.binary_skips += 1
                            elif "Undecodable" in err:
                                stats.encoding_skips += 1
                            else:
                                stats.unreadable_skips += 1
                            stats.notices_and_warnings.append(f"{sp}: {err}")
                            continue

                        assert content is not None and enc is not None
                        streamer.append_file(sp, enc, content)
                        stats.files_dumped += 1
                        with contextlib.suppress(OSError):
                            stats.total_source_bytes += sp.stat().st_size

                UIProgress.finish()
                stats.output_path = streamer.finalize()
                stats.output_file_bytes = streamer.total_bytes_written
                stats.output_status = "SUCCESS"
        except (KeyboardInterrupt, Exception) as e:
            UIProgress.finish()
            partial = streamer.preserve_partial()
            stats.output_status = f"INTERRUPTED (PARTIAL): {e}"
            stats.output_path = partial

        stats.elapsed_time = time.time() - start_time
        return stats

# ============================================================================
# 11. CLI INTERFACE
# ============================================================================

class MainMenu:
    @classmethod
    def run(cls, base_dir: Path) -> None:
        cfg = ConfigManager(base_dir)
        settings = cfg.bootstrap_settings(interactive=True)
        engine = DumperEngine(base_dir, cfg, settings)
        manifests = ManifestDiscovery.discover(base_dir)

        print("\n" + "=" * 55)
        print("              AI CONTEXT DUMPER v2.0 (CLI)")
        print("=" * 55)
        print(" 1. ALL")
        print(" 2. MULTI-SELECT")
        for m in manifests:
            print(f" {m.ident}. {m.filename}")
        print(" 0. EXIT\n" + "=" * 55)

        choice = input("Enter selection: ").strip().upper()
        if choice == "0":
            return
        if choice == "1" and manifests:
            stats = engine.run_dump(manifests, is_all=True)
            print(f"\nCompleted! Dump written to: {stats.output_path}")
        elif manifests:
            selected = [m for m in manifests if m.ident == choice]
            if selected:
                stats = engine.run_dump(selected)
                print(f"\nCompleted! Dump written to: {stats.output_path}")

# ============================================================================
# 12. ENTRY POINT
# ============================================================================

def main() -> None:
    base_dir = Path(__file__).resolve().parent
    # CLI fallback if --cli is passed or if PySide6 is unavailable
    if "--cli" in sys.argv:
        MainMenu.run(base_dir)
        return

    try:
        from gui import launch_gui
        launch_gui(base_dir)
    except ImportError:
        # Fallback to CLI if GUI dependencies are not installed
        print("[!] PySide6 GUI package not loaded. Starting CLI mode (run launch script to use GUI)...")
        MainMenu.run(base_dir)

if __name__ == "__main__":
    main()