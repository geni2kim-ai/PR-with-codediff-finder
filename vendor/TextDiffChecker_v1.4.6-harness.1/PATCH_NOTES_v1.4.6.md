# TextDiffChecker v1.4.6 patch notes

## Changes from v1.4.5

- **Case check false positives removed.**
  - The case check now only looks at mixed-case tokens such as `getElementByID`.
    All-lowercase (`object`), initial-capital (`The`, `Object`) and all-caps (`NAME`, `NULL`)
    tokens are conventions, not typo signals, and are no longer reported.
  - Before: 120 CPython stdlib files (about 94k lines) produced 1,810 case groups out of
    1,912 flagged groups, none of them real typos. After: 3 case groups.
- **Previous/next difference moves by hunk, not by row.** A 20-row change used to need 20
  clicks; now it is one stop, matching the "차이점 N건" count.
- **Saved report header after cancel/error.** The status bar text ("취소됨") was written into
  the report header next to the previous results. The header now uses the last completed
  summary (`_result_summary`). An error now shows "검사 오류" instead of "취소됨".
- **Typo locations.**
  - URLs and base64 are masked with same-length blanks, so columns after them are correct
    (was 14 instead of 70 in the reproduction).
  - Label fixed from `a.py:1열 14` to `a.py:1행 14열`.
- Version raised to 1.4.6 (`app.py`, `version_info.txt`).

## Validation

- `python -m py_compile checker.py app.py`: PASS
- `python -m unittest discover -s tests` under Xvfb: 145/145 PASS (128 existing + 17 new)
- Without a display: 142 run, GUI integration class skipped, 0 failures
- New tests were run against the v1.4.5 code: 16 of 17 fail there as expected
  (the remaining one guards that mixed-case tokens are still flagged)
- Diff engine fuzz (about 13,500 random cases across all branches): no invalid opcode tilings

## Known / not changed

- Encoding detection is heuristic: Shift-JIS without kana is read as cp949, GBK as cp949,
  Big5 as cp1252; UTF-32 with BOM is not recognised. A note is shown, text may be garbled.
- Segments of up to 2000 lines use `difflib.SequenceMatcher`: valid but not always a
  minimal diff.
- Files with very many distinct tokens spend most of the time in fuzzy matching.
- `<<DropEnter>>`/`<<DropLeave>>` handlers return nothing; tkinterdnd2 examples return
  `event.action`. Needs a check on Windows.

## Not run in this environment

- Native Windows tkinter GUI interaction and drag and drop
- PyInstaller Windows executable build and execution
