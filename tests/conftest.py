# tests/conftest.py
import sys
from pathlib import Path

# Ensure the project root directory is at the front of sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))