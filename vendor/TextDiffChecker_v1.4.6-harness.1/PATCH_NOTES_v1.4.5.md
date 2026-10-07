# TextDiffChecker v1.4.5 patch notes

## Changes from v1.4.4

- Legacy/partially damaged text decoding no longer relies on lossy replacement characters.
  - UTF-8/UTF-16 remain first-class paths.
  - cp949 and Shift-JIS are distinguished with simple Korean/Japanese script hints when both decode successfully.
  - cp1252 is supported for Western legacy text.
  - latin-1 is the final byte-preserving fallback.
  - UTF-8 BOM files with invalid bytes use a byte-preserving latin-1 fallback after removing the BOM.
  - Damaged UTF-16 remains a hard read error because alignment cannot be recovered safely.
- When a segment has already been split by patience, a valid banded diff is retained instead of being discarded into the coarse fallback path.
- Removed two unused local test imports.
- Version raised to 1.4.5.

## Validation

- `python -m py_compile checker.py app.py`: PASS
- `python -m unittest discover -s tests -v`: 128/128 PASS
- Additional random diff reconstruction: 600/600 PASS
- Encoding spot checks: cp949 / Shift-JIS / cp1252: 3/3 PASS

## Not run in this environment

- Native Windows tkinter GUI interaction
- PyInstaller Windows executable build and execution
- Keyboard/mouse scroll synchronization on a real Windows display
