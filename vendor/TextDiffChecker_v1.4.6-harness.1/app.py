#!/usr/bin/env python3
"""두 텍스트 파일 대조 + 오타/문법 검출 GUI (Windows)."""
import csv
import html
import json
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND_OK = True
except ImportError:
    _DND_OK = False

import checker

APP_VERSION = "1.4.6"
APP_TITLE = f"TextDiffChecker {APP_VERSION} - 파일 대조 + 오타 검출"
CONFIG_NAME = "TextDiffChecker.config.json"
USER_DB_NAME = "user_db.json"
FILTERS = ["전체", "차이점", "오타 의심", "문법 주의", "특이사항", "B 신규"]
_SBS_AUTO_COLLAPSE = 20000  # 이 행 수를 넘으면 '변경된 행만 보기' 자동 적용
_SBS_WORD_LIMIT = 1000  # 이 길이 이하의 수정 행에만 단어 강조
_SBS_CONTEXT = 2  # '변경된 행만 보기'에서 앞뒤로 보여줄 동일 행 수
_SBS_WORD_ROW_CAP = 2000  # 변경 행이 이 수를 넘으면 단어 강조 생략(UI 정지 방지)


def sbs_display_plan(rows: list[dict], hide: bool,
                     context: int = _SBS_CONTEXT) -> list[tuple]:
    """나란히 보기 표시 계획(순수 함수, tkinter 불필요).

    반환: ("row", index) 또는 ("skip", count) 순서 리스트.
    - hide=False면 모든 행을 순서대로 표시한다.
    - hide=True면 변경 행 앞뒤 context만 남기고 나머지는 skip으로 묶는다.
    - 모든 행이 동일해도 첫 행은 보이게 하고, 마지막에 남은 skip도
      반드시 하나의 ("skip", n)으로 출력한다(trailing 생략 누락 방지).
    """
    if not rows:
        return []
    if not hide:
        return [("row", i) for i in range(len(rows))]
    vis = [False] * len(rows)
    for i, r in enumerate(rows):
        if r.get("kind") != "equal":
            lo = max(0, i - context)
            hi = min(len(rows), i + context + 1)
            for j in range(lo, hi):
                vis[j] = True
    if not any(vis):
        vis[0] = True
    plan: list[tuple] = []
    skip = 0
    for i, v in enumerate(vis):
        if not v:
            skip += 1
            continue
        if skip:
            plan.append(("skip", skip))
            skip = 0
        plan.append(("row", i))
    if skip:
        plan.append(("skip", skip))
    return plan


def sbs_change_stops(rows: list[dict], plan: list[tuple]) -> list[int]:
    """'이전/다음 차이' 이동 지점(표시 행 번호, 1-based). 순수 함수.

    연속된 변경 행은 하나의 블록(hunk)으로 보고 첫 행만 지점으로 삼는다.
    equal 행이나 생략 행이 사이에 끼면 새 블록이다. 이렇게 해야 요약란의
    '차이점 N건'과 이동 횟수가 일치한다.
    """
    stops: list[int] = []
    prev_changed = False
    disp = 0
    for kind, val in plan:
        disp += 1
        if kind == "skip":
            prev_changed = False
            continue
        changed = rows[val].get("kind") != "equal"
        if changed and not prev_changed:
            stops.append(disp)
        prev_changed = changed
    return stops


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def config_path() -> str:
    """쓰기 가능한 설정 파일 경로. 파일을 만들며 탐색하지 않는다."""
    primary = os.path.join(_app_dir(), CONFIG_NAME)
    if os.path.exists(primary):
        if os.access(primary, os.W_OK):
            return primary
    elif os.access(_app_dir(), os.W_OK):
        return primary
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, CONFIG_NAME)


def _fallback_config_path() -> str:
    """쓰기 실패 시 저장되는 APPDATA 경로. 저장과 로드가 공유한다."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, CONFIG_NAME)


def _config_candidates() -> list[str]:
    """로드 시 시도할 경로들. 앱 폴더 우선, 없으면 폴백도 읽는다.

    _save_config는 쓰기 실패 시 폴백에 저장하므로, _load_config가
    config_path()만 읽으면 다음 실행에서 설정이 유실된다.
    같은 결정 함수를 써서 양쪽을 맞춘다.
    """
    primary = config_path()
    fallback = _fallback_config_path()
    if fallback == primary:
        return [primary]
    return [primary, fallback]


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _csv_cell(v) -> str:
    """CSV formula injection 방지: =,+,-,@,|,%로 시작하면 '를 앞에 붙인다.
    앞의 공백/탭으로 우회하는 경우까지 막는다."""
    s = str(v)
    if s.lstrip()[:1] in ("=", "+", "-", "@", "|", "%"):
        return "'" + s
    return s


class App(TkinterDnD.Tk if _DND_OK else tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x680")
        self.cfg = self._load_config()
        base_db = resource_path("syntax_db.json")
        user_db = os.path.join(_app_dir(), USER_DB_NAME)
        try:
            self.db = checker.load_db(base_db, user_db if os.path.exists(user_db) else None)
        except Exception as e:  # ValueError뿐 아니라 예상 밖 오류에도 앱은 떠 있어야 한다
            messagebox.showerror("DB 오류", str(e))
            self.db = {"known_exact": set(), "known_lower": {},
                       "known_all_lower": set(), "typo": {}, "patterns": [],
                       "cand_by_first": {}, "warnings": [str(e)], "notices": []}
        self.file_a = ""
        self.file_b = ""
        self.all_findings: list[dict] = []
        self.stats: dict = {}
        # 마지막으로 완료된 검사의 요약. 상태 표시줄(var_summary)은 취소·오류·진행
        # 문구로 덮어써지므로 저장 파일 헤더는 이 값을 쓴다.
        self._result_summary: str = ""
        self.sbs_rows: list[dict] = []
        self.sbs_names: tuple[str, str] = ("원본", "수정본")
        self._sbs_change_idx: list[int] = []
        self._sbs_cursor = -1
        self._sbs_syncing = False
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.msg_queue: queue.Queue = queue.Queue()
        self.read_notes: list[str] = []
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        msgs = []
        if self.db.get("warnings"):
            msgs.append("DB 경고: " + " / ".join(self.db["warnings"][:3]))
        if self.db.get("notices"):
            msgs.append(" / ".join(self.db["notices"]))
        if msgs:
            self.var_summary.set(" | ".join(msgs))

    def _load_config(self) -> dict:
        # 저장 폴백(APPDATA)과 같은 후보 목록을 읽는다. 앱 폴더에 쓸 수
        # 없는데 os.access가 True를 돌려주는 환경(Program Files)에서도
        # 다음 실행에 설정이 유실되지 않는다.
        for path in _config_candidates():
            try:
                with open(path, encoding="utf-8") as fo:
                    data = json.load(fo)
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError):
                continue
        return {}

    def _save_config(self) -> None:
        data = {"lastdir": self.cfg.get("lastdir", ""),
                "ignore_ws": self.var_ws.get(),
                "run_checks": self.var_checks.get()}
        try:
            with open(config_path(), "w", encoding="utf-8") as fo:
                json.dump(data, fo, ensure_ascii=False, indent=1)
        except OSError:
            try:
                # Program Files 등 쓰기 불가 위치면 APPDATA에 저장 (조용한 유실 방지)
                with open(_fallback_config_path(), "w",
                          encoding="utf-8") as fo:
                    json.dump(data, fo, ensure_ascii=False, indent=1)
            except OSError:
                pass

    def _on_close(self) -> None:
        """종료 시 설정을 저장한다(D)."""
        self._save_config()
        self.destroy()

    def _build(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        hint = "여기에 파일을 드래그하세요" if _DND_OK else "드래그 불가(tkinterdnd2 미설치)"
        self.var_a = tk.StringVar(value=f"(원본 파일을 선택하거나 {hint})")
        self.var_b = tk.StringVar(value=f"(수정본 파일을 선택하거나 {hint})")
        self.btn_pick_a = ttk.Button(top, text="원본 열기", command=lambda: self._pick("a"))
        self.btn_pick_a.grid(row=0, column=0, padx=4)
        self.lbl_a = ttk.Label(top, textvariable=self.var_a, width=76, anchor="w")
        self.lbl_a.grid(row=0, column=1, sticky="w")
        self.btn_pick_b = ttk.Button(top, text="수정본 열기", command=lambda: self._pick("b"))
        self.btn_pick_b.grid(row=1, column=0, padx=4, pady=4)
        self.lbl_b = ttk.Label(top, textvariable=self.var_b, width=76, anchor="w")
        self.lbl_b.grid(row=1, column=1, sticky="w")
        if _DND_OK:
            for lbl, which in ((self.lbl_a, "a"), (self.lbl_b, "b")):
                lbl.drop_target_register(DND_FILES)
                lbl.dnd_bind("<<Drop>>", lambda e, w=which: self._drop(w, e))
                lbl.dnd_bind("<<DropEnter>>", lambda e, L=lbl: L.configure(relief="sunken"))
                lbl.dnd_bind("<<DropLeave>>", lambda e, L=lbl: L.configure(relief="flat"))

        opts = ttk.Frame(self, padding=(10, 0))
        opts.pack(fill="x")
        self.var_ws = tk.BooleanVar(value=bool(self.cfg.get("ignore_ws", False)))
        self.var_checks = tk.BooleanVar(value=bool(self.cfg.get("run_checks", True)))
        self.chk_ws = ttk.Checkbutton(opts, text="공백 차이 무시", variable=self.var_ws,
                                      command=self._save_config)
        self.chk_ws.pack(side="left", padx=4)
        self.chk_checks = ttk.Checkbutton(opts, text="오타/문법 검사 포함", variable=self.var_checks,
                                          command=self._save_config)
        self.chk_checks.pack(side="left", padx=4)
        self.btn_run = ttk.Button(opts, text="비교하기", command=self._run)
        self.btn_run.pack(side="left", padx=12)
        self.btn_cancel = ttk.Button(opts, text="취소", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left")
        self.btn_save = ttk.Button(opts, text="결과 저장", command=self._save)
        self.btn_save.pack(side="left", padx=4)
        ttk.Label(opts, text="필터:").pack(side="left", padx=(12, 2))
        self.var_filter = tk.StringVar(value="전체")
        self.cmb_filter = ttk.Combobox(opts, textvariable=self.var_filter, values=FILTERS,
                                       width=10, state="readonly")
        self.cmb_filter.pack(side="left")
        self.cmb_filter.bind("<<ComboboxSelected>>", lambda e: self._render())
        ttk.Button(opts, text="◀ 이전 차이", command=lambda: self._move_diff(-1)).pack(side="left", padx=(12, 2))
        ttk.Button(opts, text="다음 차이 ▶", command=lambda: self._move_diff(1)).pack(side="left")

        prog = ttk.Frame(self, padding=(10, 4))
        prog.pack(fill="x")
        self.bar = ttk.Progressbar(prog, mode="determinate", maximum=100)
        self.bar.pack(fill="x")
        self.var_summary = tk.StringVar(value="대기 중")
        ttk.Label(self, textvariable=self.var_summary, padding=(10, 2)).pack(fill="x")

        body = ttk.Frame(self, padding=(10, 0))
        body.pack(fill="both", expand=True)
        self.nb = ttk.Notebook(body)
        self.nb.pack(fill="both", expand=True)
        tab_sbs = ttk.Frame(self.nb)
        tab_list = ttk.Frame(self.nb)
        self.nb.add(tab_sbs, text="나란히 보기")
        self.nb.add(tab_list, text="검사 결과 목록")

        # --- 나란히 보기 탭: 왼쪽 원본 / 오른쪽 수정본, 함께 스크롤 ---
        sbs_bar = ttk.Frame(tab_sbs)
        sbs_bar.pack(fill="x", pady=(6, 2))
        self.var_hide_same = tk.BooleanVar(value=False)
        ttk.Checkbutton(sbs_bar, text="변경된 행만 보기", variable=self.var_hide_same,
                        command=self._render_sbs).pack(side="left", padx=4)
        ttk.Label(sbs_bar, text="■ 삭제", foreground="#cf222e").pack(side="left", padx=(12, 2))
        ttk.Label(sbs_bar, text="■ 추가", foreground="#1a7f37").pack(side="left", padx=2)
        ttk.Label(sbs_bar, text="■ 수정(단어 강조)",
                  foreground="#9a6700").pack(side="left", padx=2)

        grid = ttk.Frame(tab_sbs)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(1, weight=1)
        self.lbl_sbs_a = ttk.Label(grid, text="원본", anchor="center",
                                   font=("", 10, "bold"))
        self.lbl_sbs_a.grid(row=0, column=0, sticky="ew", pady=2)
        self.lbl_sbs_b = ttk.Label(grid, text="수정본", anchor="center",
                                   font=("", 10, "bold"))
        self.lbl_sbs_b.grid(row=0, column=1, sticky="ew", pady=2)
        self.txt_a = tk.Text(grid, wrap="none", font=("Consolas", 10),
                             state="disabled")
        self.txt_a.grid(row=1, column=0, sticky="nsew")
        self.txt_b = tk.Text(grid, wrap="none", font=("Consolas", 10),
                             state="disabled")
        self.txt_b.grid(row=1, column=1, sticky="nsew")
        self.vsb_sbs = ttk.Scrollbar(grid, orient="vertical",
                                     command=self._sbs_yview_all)
        self.vsb_sbs.grid(row=1, column=2, sticky="ns")
        hsb_a = ttk.Scrollbar(grid, orient="horizontal", command=self.txt_a.xview)
        hsb_a.grid(row=2, column=0, sticky="ew")
        hsb_b = ttk.Scrollbar(grid, orient="horizontal", command=self.txt_b.xview)
        hsb_b.grid(row=2, column=1, sticky="ew")
        for t in (self.txt_a, self.txt_b):
            src = "a" if t is self.txt_a else "b"
            t.configure(yscrollcommand=(lambda f, l, s=src: self._sbs_sync_from(s, f, l)),
                        xscrollcommand=(hsb_a.set if t is self.txt_a else hsb_b.set))
            t.bind("<MouseWheel>", self._sbs_wheel)
            # 키보드 스크롤(화살표/PageUp·Down/Home/End)도 동기화한다.
            # yscrollcommand 경유로도 동기화되지만, 키 이벤트 직후 상대 창을
            # 즉시 맞춰 반응성을 확보한다.
            t.bind("<KeyRelease>", self._sbs_key_sync)
        self.txt_a.tag_configure("del", background="#ffebe9")
        self.txt_a.tag_configure("wdel", background="#ffcecb")
        self.txt_a.tag_configure("ln", foreground="#6e7781")
        self.txt_a.tag_configure("skip", foreground="#6e7781")
        self.txt_b.tag_configure("add", background="#e6ffec")
        self.txt_b.tag_configure("wadd", background="#bef5cb")
        self.txt_b.tag_configure("ln", foreground="#6e7781")
        self.txt_b.tag_configure("skip", foreground="#6e7781")

        # --- 검사 결과 목록 탭: 기존 트리 + 상세 버튼 ---
        frame = ttk.Frame(tab_list, padding=(0, 6, 0, 0))
        frame.pack(fill="both", expand=True)
        cols = ("no", "cat", "file", "line", "summary")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=20)
        for c, h, w in [("no", "No", 50), ("cat", "구분", 100), ("file", "파일/위치", 200),
                        ("line", "라인", 60), ("summary", "요약", 520)]:
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w" if c == "summary" else "center")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure("차이점", foreground="#0b5394")
        self.tree.tag_configure("오타 의심", foreground="#b45f06")
        self.tree.tag_configure("문법 주의", foreground="#cc0000")
        self.tree.tag_configure("특이사항", foreground="#38761d")
        self.tree.tag_configure("신규", background="#fff2cc")
        self.tree.bind("<Double-1>", lambda e: self._popup())
        ttk.Button(tab_list, text="선택 항목 상세 보기",
                   command=self._popup).pack(pady=6)
        self.after(120, self._poll)

    def _busy(self) -> bool:
        return bool(self.worker and self.worker.is_alive())

    def _set_inputs_enabled(self, on: bool) -> None:
        state = "normal" if on else "disabled"
        for w in (self.btn_pick_a, self.btn_pick_b, self.chk_ws,
                  self.chk_checks, self.btn_save):
            w.configure(state=state)

    def _pick(self, which: str) -> None:
        if self._busy():
            messagebox.showwarning("검사 중", "검사가 끝난 뒤 파일을 바꾸세요.")
            return
        name = "원본" if which == "a" else "수정본"
        path = filedialog.askopenfilename(
            title=f"{name} 파일 선택", initialdir=self.cfg.get("lastdir", ""),
            filetypes=[("텍스트/코드", "*.txt *.py *.js *.ts *.java *.kt *.swift *.cs *.cpp *.c *.h *.json *.xml *.md *.log *.csv"), ("모든 파일", "*.*")])
        if not path:
            return
        self.cfg["lastdir"] = os.path.dirname(path)
        self._set_file(which, path)

    def _set_file(self, which: str, path: str) -> None:
        if which == "a":
            self.file_a = path
            self.var_a.set(path)
        else:
            self.file_b = path
            self.var_b.set(path)
        self._save_config()

    def _parse_drop(self, data: str) -> str:
        try:
            parts = list(self.tk.splitlist(data))
        except Exception:
            parts = []
        for p in parts:
            if os.path.exists(p):
                return p
        s = data.strip()
        if s.startswith("{") and s.endswith("}"):
            s = s[1:-1]
        return s

    def _drop(self, which: str, event) -> None:
        if self._busy():
            messagebox.showwarning("검사 중", "검사가 끝난 뒤 파일을 바꾸세요.")
            return
        path = self._parse_drop(event.data)
        if not path:
            return
        if not os.path.exists(path):
            messagebox.showwarning("드롭", f"파일을 찾을 수 없습니다:\n{path}")
            return
        if os.path.isdir(path):
            messagebox.showwarning("드롭", "폴더가 아닌 파일을 드래그하세요.")
            return
        self.cfg["lastdir"] = os.path.dirname(path)
        self._set_file(which, path)

    def _run(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.file_a or not self.file_b:
            messagebox.showwarning("입력 부족", "원본과 수정본 파일을 모두 선택하세요.")
            return
        try:
            a_raw, meta_a = checker.read_text_file(self.file_a)
            b_raw, meta_b = checker.read_text_file(self.file_b)
        except (checker.BinaryFileError, checker.TooLargeError, OSError,
                UnicodeDecodeError, ValueError) as e:
            messagebox.showerror("읽기 오류", str(e))
            return
        self.read_notes = []
        for label, meta in (("원본", meta_a), ("수정본", meta_b)):
            if meta.get("note"):
                self.read_notes.append(f"{label}: {meta['note']}")
        if self.read_notes:
            self.var_summary.set(" | ".join(self.read_notes))  # 팝업 대신 상태 표시(E)
        na = os.path.basename(self.file_a)
        nb = os.path.basename(self.file_b)
        self.sbs_names = (na, nb)
        self.cancel_event.clear()
        self.btn_run.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self._set_inputs_enabled(False)
        self.bar.configure(mode="indeterminate")
        self.bar.start(10)
        args = (a_raw, b_raw, na, nb, self.var_ws.get(), self.var_checks.get())
        self.worker = threading.Thread(target=self._work, args=args, daemon=True)
        self.worker.start()

    def _work(self, a_raw, b_raw, na, nb, ignore_ws, run_checks) -> None:
        try:
            # opcode 재사용으로 diff 1회만 계산한다(중복 계산 방지 유지).
            findings, stats, diff_opcodes = checker.compare_with_opcodes(
                a_raw, b_raw, na, nb, self.db, ignore_ws=ignore_ws,
                run_checks=run_checks,
                progress=lambda ph, d, t: self.msg_queue.put(("progress", ph, d, t)),
                cancel=self.cancel_event)
            sbs_rows = checker.side_by_side(
                a_raw, b_raw, ignore_ws=ignore_ws, cancel=self.cancel_event,
                opcodes=diff_opcodes)
            self.msg_queue.put(("done", findings, stats, sbs_rows))
        except checker.Cancelled:
            self.msg_queue.put(("cancelled",))
        except Exception:
            self.msg_queue.put(("error", traceback.format_exc(limit=5)))

    def _poll(self) -> None:
        try:
            while True:
                kind, *rest = self.msg_queue.get_nowait()
                if kind == "progress":
                    ph, d, t = rest
                    if ph in ("typo-a", "typo-b") and t:
                        self.bar.stop()
                        self.bar.configure(mode="determinate")
                        base = 0 if ph == "typo-a" else 50
                        self.bar["value"] = base + 50 * d / max(t, 1)
                        self.var_summary.set(f"검사 중... ({ph} {d}/{t}행)")
                elif kind == "done":
                    self._finish(*rest)
                elif kind == "cancelled":
                    self._finish_cancel()
                elif kind == "error":
                    self._finish_cancel("검사 오류")
                    messagebox.showerror("검사 오류", f"검사 중 오류가 발생했습니다:\n{rest[0]}")
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _finish(self, findings: list[dict], stats: dict,
                sbs_rows: list[dict] | None = None) -> None:
        self.all_findings = findings
        self.stats = stats
        self.sbs_rows = sbs_rows or []
        self._sbs_cursor = -1
        if len(self.sbs_rows) > _SBS_AUTO_COLLAPSE:
            self.var_hide_same.set(True)
        na, nb = self.sbs_names
        self.lbl_sbs_a.configure(text=f"원본 — {na}")
        self.lbl_sbs_b.configure(text=f"수정본 — {nb}")
        self.btn_run.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self._set_inputs_enabled(True)
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self.bar["value"] = 100
        self._render()
        self._render_sbs()
        extra = ""
        if self.read_notes:
            extra += " | " + " / ".join(self.read_notes)
        if stats.get("typo_truncated"):
            extra += (f" | 오타 상한({checker.MAX_GROUPS_PER_FILE}종/파일) 도달: "
                      f"뒤쪽 종류 미검사")
        if stats.get("pattern_caps"):
            extra += f" | 규칙 상한 도달: {', '.join(stats['pattern_caps'])}"
        if stats.get("approx"):
            extra += " | 대규모 변경 일부 근사 표시"
        self._result_summary = (
            f"원본 {stats['a_total']}행 / 수정본 {stats['b_total']}행 | "
            f"차이점 {stats['hunks']}건(변경 약 {stats['changed_lines']}행) | "
            f"오타 {stats.get('typo_kinds', 0)}종(총 {stats['typos']}곳) | "
            f"문법·특이 {stats['hygiene']}건 | "
            f"B 신규 {stats.get('new_in_b', 0)}건 | 전체 {len(findings)}건{extra}")
        self.var_summary.set(self._result_summary)

    def _finish_cancel(self, msg: str = "취소됨") -> None:
        self.btn_run.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self._set_inputs_enabled(True)
        self.bar.stop()
        self.bar["value"] = 0
        self.var_summary.set(msg)

    def _cancel(self) -> None:
        self.cancel_event.set()

    def _visible(self) -> list[dict]:
        f = self.var_filter.get()
        if f == "전체":
            return self.all_findings
        if f == "B 신규":
            return [x for x in self.all_findings if x.get("is_new")]
        return [x for x in self.all_findings if x["category"] == f]

    def _render(self) -> None:
        for r in self.tree.get_children():
            self.tree.delete(r)
        for x in self._visible():
            tags = [x["category"]] + (["신규"] if x.get("is_new") else [])
            mark = "🆕 " if x.get("is_new") else ""
            self.tree.insert("", "end", iid=str(x["no"]),
                             values=(x["no"], x["category"], x["file"], x["line"],
                                     mark + x["summary"]), tags=tuple(tags))

    def _sbs_yview_all(self, *args) -> None:
        self.txt_a.yview(*args)
        self.txt_b.yview(*args)

    def _sbs_yset(self, first: str, last: str) -> None:
        self.vsb_sbs.set(first, last)

    def _sbs_sync_from(self, src: str, first: str, last: str) -> None:
        """한쪽 창의 스크롤을 스크롤바+상대 창에 반영한다.

        마우스휠·스크롤바뿐 아니라 화살표/PageDown 등 키보드 스크롤도
        yscrollcommand를 타므로 함께 동기화된다. 재진입 가드로 무한 루프 방지.
        """
        self.vsb_sbs.set(first, last)
        if self._sbs_syncing:
            return
        self._sbs_syncing = True
        try:
            other = self.txt_b if src == "a" else self.txt_a
            try:
                other.yview_moveto(float(first))
            except (ValueError, tk.TclError):
                pass
        finally:
            self._sbs_syncing = False

    def _sbs_key_sync(self, event=None) -> None:
        """키보드 스크롤 직후 양쪽을 강제 동기화한다(포커스된 쪽 기준)."""
        if self._sbs_syncing:
            return
        w = event.widget if event is not None and hasattr(event, "widget") else None
        try:
            if w is self.txt_b:
                first, _ = self.txt_b.yview()
                self._sbs_syncing = True
                try:
                    self.txt_a.yview_moveto(first)
                finally:
                    self._sbs_syncing = False
            elif w is self.txt_a or w is None:
                first, _ = self.txt_a.yview()
                self._sbs_syncing = True
                try:
                    self.txt_b.yview_moveto(first)
                finally:
                    self._sbs_syncing = False
        except (ValueError, tk.TclError):
            self._sbs_syncing = False

    def _sbs_wheel(self, event) -> str:
        steps = -1 if event.delta > 0 else 1
        self.txt_a.yview_scroll(steps, "units")
        self.txt_b.yview_scroll(steps, "units")
        return "break"

    def _render_sbs(self) -> None:
        for t in (self.txt_a, self.txt_b):
            t.configure(state="normal")
            t.delete("1.0", "end")
        self._sbs_change_idx = []
        self._sbs_cursor = -1
        rows = self.sbs_rows
        if not rows:
            msg = "(비교 결과가 없습니다. 비교하기를 실행하세요.)"
            self.txt_a.insert("1.0", msg)
            self.txt_b.insert("1.0", msg)
            for t in (self.txt_a, self.txt_b):
                t.configure(state="disabled")
            return
        max_no = max([r["a_no"] or 0 for r in rows] + [r["b_no"] or 0 for r in rows])
        w = max(len(str(max_no)), 4)
        hide = self.var_hide_same.get()
        plan = sbs_display_plan(rows, hide, _SBS_CONTEXT)
        self._sbs_change_idx = sbs_change_stops(rows, plan)
        disp = 0  # 양쪽 창의 표시 행 번호(1-based, 생략행 포함 동일)
        # 대규모 교체에서 단어 강조가 수만 건의 Tk 호출을 만들어 UI를 멈추게
        # 하므로 변경 행이 많으면 단어 강조를 생략한다(행 배경은 유지).
        n_change = sum(1 for r in rows if r["kind"] != "equal")
        word_on = n_change <= _SBS_WORD_ROW_CAP
        for kind, val in plan:
            if kind == "skip":
                disp += 1
                mark = f"⋯ {val}행 생략 ⋯"
                self.txt_a.insert("end", mark + "\n", "skip")
                self.txt_b.insert("end", mark + "\n", "skip")
                continue
            r = rows[val]
            disp += 1
            a_pre = f"{r['a_no']:>{w}} | " if r["a_no"] else " " * (w + 3)
            b_pre = f"{r['b_no']:>{w}} | " if r["b_no"] else " " * (w + 3)
            a_txt = a_pre + (r["a_text"] if r["a_text"] is not None else "")
            b_txt = b_pre + (r["b_text"] if r["b_text"] is not None else "")
            a_tag = "del" if r["kind"] in ("delete", "replace") else None
            b_tag = "add" if r["kind"] in ("insert", "replace") else None
            a_ln = f"{disp}.0"
            self.txt_a.insert("end", a_txt + "\n")
            self.txt_a.tag_add("ln", a_ln, f"{a_ln} + {len(a_pre)} chars")
            if a_tag:
                self.txt_a.tag_add(a_tag, f"{a_ln} + {len(a_pre)} chars", f"{disp}.end")
            b_ln = f"{disp}.0"
            self.txt_b.insert("end", b_txt + "\n")
            self.txt_b.tag_add("ln", b_ln, f"{b_ln} + {len(b_pre)} chars")
            if b_tag:
                self.txt_b.tag_add(b_tag, f"{b_ln} + {len(b_pre)} chars", f"{disp}.end")
            if (word_on and r["kind"] == "replace" and r["a_text"] is not None
                    and r["b_text"] is not None
                    and len(r["a_text"]) < _SBS_WORD_LIMIT
                    and len(r["b_text"]) < _SBS_WORD_LIMIT):
                try:
                    spans_a, spans_b = checker.word_spans(r["a_text"], r["b_text"])
                except Exception:
                    spans_a, spans_b = [], []
                for s, e in spans_a:
                    self.txt_a.tag_add("wdel", f"{disp}.{len(a_pre) + s}",
                                       f"{disp}.{len(a_pre) + e}")
                for s, e in spans_b:
                    self.txt_b.tag_add("wadd", f"{disp}.{len(b_pre) + s}",
                                       f"{disp}.{len(b_pre) + e}")
        for t in (self.txt_a, self.txt_b):
            t.configure(state="disabled")

    def _move_diff(self, step: int) -> None:
        try:
            sbs_active = self.nb.index(self.nb.select()) == 0
        except Exception:
            sbs_active = False
        if sbs_active and self._sbs_change_idx:
            if step > 0:
                nxt = min([d for d in self._sbs_change_idx if d > self._sbs_cursor],
                          default=self._sbs_change_idx[0])
            else:
                cand = [d for d in self._sbs_change_idx if d < self._sbs_cursor]
                nxt = max(cand) if cand else self._sbs_change_idx[-1]
            self._sbs_cursor = nxt
            for t in (self.txt_a, self.txt_b):
                t.see(f"{nxt}.0")
            return
        ids = [int(c) for c in self.tree.get_children()]
        diffs = [i for i in ids
                 if self.all_findings[i - 1]["category"] == "차이점"]
        if not diffs:
            return
        sel = self.tree.selection()
        if not sel:
            # 선택이 없으면 끝/처음으로 바로 이동(G: 마지막 차이 건너뛰기 수정)
            nxt = diffs[-1] if step < 0 else diffs[0]
        elif step > 0:
            cur = int(sel[0])
            nxt = min([d for d in diffs if d > cur], default=diffs[0])
        else:
            cur = int(sel[0])
            nxt = max([d for d in diffs if d < cur], default=diffs[-1])
        self.tree.selection_set(str(nxt))
        self.tree.see(str(nxt))

    def _current(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.all_findings[int(sel[0]) - 1]

    def _popup(self) -> None:
        f = self._current()
        if not f:
            return
        win = tk.Toplevel(self)
        win.title(f"상세 - No.{f['no']} [{f['category']}]")
        win.geometry("720x500")
        ttk.Label(win, text=f"[{f['category']}] {f['file']} : 라인 {f['line']}",
                  padding=8, font=("", 10, "bold")).pack(fill="x")
        frame = ttk.Frame(win, padding=(8, 0))
        frame.pack(fill="both", expand=True)
        txt = tk.Text(frame, wrap="none", font=("Consolas", 10))
        txt.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        vsb.pack(side="right", fill="y")
        hsb = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
        hsb.pack(fill="x", padx=8)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        txt.insert("1.0", f["summary"] + "\n\n" + f["detail"])
        txt.configure(state="disabled")
        ttk.Button(win, text="닫기", command=win.destroy).pack(pady=6)
        win.transient(self)
        win.grab_set()

    def _save(self) -> None:
        # Low: 0건이어도 "문제 없음" 보고서를 저장할 수 있다.
        # 필터가 걸리면 필터된 결과만 저장되며, 헤더에 필터 상태를 표기한다.
        if not self.stats:
            messagebox.showinfo("저장", "저장할 결과가 없습니다. 먼저 대조하세요.")
            return
        path = filedialog.asksaveasfilename(
            title="결과 저장", defaultextension=".txt",
            filetypes=[("텍스트", "*.txt"), ("CSV", "*.csv"), ("HTML", "*.html")])
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                self._save_csv(path)
            elif path.lower().endswith((".html", ".htm")):
                self._save_html(path)
            else:
                self._save_txt(path)
        except OSError as e:
            messagebox.showerror("저장 오류", str(e))
            return
        messagebox.showinfo("저장", f"저장했습니다:\n{path}")

    def _filter_label(self) -> str:
        vis = len(self._visible())
        return (f"필터: {self.var_filter.get()} "
                f"({vis}/{len(self.all_findings)}건)")

    def _save_txt(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fo:
            fo.write(self._result_summary + "\n" + self._filter_label() + "\n"
                     + "=" * 60 + "\n")
            vis = self._visible()
            if not vis:
                fo.write("\n검출된 항목이 없습니다.\n")
                return
            for f in vis:
                fo.write(f"\n[No.{f['no']}][{f['category']}] {f['file']} : 라인 {f['line']}\n"
                         f"{f['summary']}\n{f['detail']}\n")

    def _save_csv(self, path: str) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as fo:
            w = csv.writer(fo)
            w.writerow([self._filter_label()])  # 필터 상태를 헤더에 표기(H)
            w.writerow(["No", "구분", "파일", "라인", "B신규", "요약"])
            for f in self._visible():
                w.writerow([f["no"], _csv_cell(f["category"]), _csv_cell(f["file"]),
                            f["line"], "Y" if f.get("is_new") else "",
                            _csv_cell(f["summary"])])
            if not self._visible():
                w.writerow(["-", "-", "-", "-", "-", "검출된 항목이 없습니다."])

    def _save_html(self, path: str) -> None:
        colors = {"차이점": "#0b5394", "오타 의심": "#b45f06",
                  "문법 주의": "#cc0000", "특이사항": "#38761d"}
        rows = []
        for f in self._visible():
            new = " 🆕" if f.get("is_new") else ""
            cls = " class='new'" if f.get("is_new") else ""
            rows.append(
                f"<tr{cls}><td>{f['no']}</td>"
                f"<td style='color:{colors.get(f['category'], '#000')}'>{html.escape(f['category'])}{new}</td>"
                f"<td>{html.escape(str(f['file']))}</td><td>{f['line']}</td>"
                f"<td>{html.escape(f['summary'])}<pre>{html.escape(f['detail'])}</pre></td></tr>")
        if not rows:
            rows.append("<tr><td colspan='5'>검출된 항목이 없습니다.</td></tr>")
        doc = ("<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
               "<title>TextDiffChecker 결과</title>"
               "<style>"
               "body{font-family:'Malgun Gothic',sans-serif;font-size:13px;}"
               "table{border-collapse:collapse;width:100%;}"
               "th,td{border:1px solid #bbb;padding:4px 6px;vertical-align:top;}"
               "th{background:#f0f0f0;position:sticky;top:0;}"
               "tr.new{background:#fff2cc;}"  # 앱 화면과 같은 노란 강조(H)
               "pre{white-space:pre-wrap;margin:4px 0 0;color:#444;}"
               "</style></head><body>"
               f"<p>{html.escape(self._result_summary)}</p>"
               f"<p><b>{html.escape(self._filter_label())}</b></p>"
               "<table>"
               "<tr><th>No</th><th>구분</th><th>파일</th><th>라인</th><th>내용</th></tr>"
               + "".join(rows) + "</table></body></html>")
        with open(path, "w", encoding="utf-8") as fo:
            fo.write(doc)


if __name__ == "__main__":
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
    App().mainloop()
