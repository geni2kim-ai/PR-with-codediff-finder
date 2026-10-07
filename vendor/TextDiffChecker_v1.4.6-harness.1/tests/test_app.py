#!/usr/bin/env python3
"""app.py의 순수 함수 테스트(디스플레이 불필요). 실행: python -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import app
except ImportError:  # tkinter가 없는 환경에서는 GUI 테스트를 건너뛴다
    app = None


@unittest.skipIf(app is None, "tkinter 없음")
class ConfigPathTest(unittest.TestCase):
    def test_no_side_effect_file(self):
        # D: config_path()가 탐색용 0바이트 설정 파일을 만들지 않아야 한다
        primary = os.path.join(app._app_dir(), app.CONFIG_NAME)
        existed = os.path.exists(primary)
        size_before = os.path.getsize(primary) if existed else None
        app.config_path()
        if not existed:
            self.assertFalse(os.path.exists(primary))
        else:
            self.assertEqual(os.path.getsize(primary), size_before)

    def test_path_is_str_and_absolute(self):
        p = app.config_path()
        self.assertIsInstance(p, str)
        self.assertTrue(os.path.isabs(p))

    def test_resource_path_db(self):
        # DB 리소스 경로가 존재해야 한다(패키징 확인용)
        self.assertTrue(os.path.exists(app.resource_path("syntax_db.json")))

    def test_csv_cell_injection(self):
        self.assertEqual(app._csv_cell("=cmd"), "'=cmd")
        self.assertEqual(app._csv_cell("+1+1"), "'+1+1")
        self.assertEqual(app._csv_cell("-2"), "'-2")
        self.assertEqual(app._csv_cell("@x"), "'@x")
        self.assertEqual(app._csv_cell("보통 요약"), "보통 요약")
        self.assertEqual(app._csv_cell(5), "5")

    def test_csv_cell_leading_whitespace(self):
        # Low: 앞 공백/탭으로 우회하는 수식도 막는다
        self.assertEqual(app._csv_cell(" =cmd"), "' =cmd")
        self.assertEqual(app._csv_cell("\t+1+1"), "'\t+1+1")
        self.assertEqual(app._csv_cell("  @x"), "'  @x")
        self.assertEqual(app._csv_cell("  보통 요약"), "  보통 요약")

    def test_fallback_path_shared(self):
        # Medium: 저장 폴백과 로드 후보가 같은 경로를 써야 유실이 없다
        fb = app._fallback_config_path()
        self.assertTrue(os.path.isabs(fb))
        cands = app._config_candidates()
        self.assertIn(fb, cands)
        self.assertIn(app.config_path(), cands)
        # 소스에 하드코딩된 별도 APPDATA 경로가 남아 있으면 안 된다
        import inspect
        src = inspect.getsource(app.App._save_config)
        self.assertIn("_fallback_config_path", src)
        src2 = inspect.getsource(app.App._load_config)
        self.assertIn("_config_candidates", src2)

    def test_spec_bundles_regex(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base, "TextDiffChecker.spec"),
                  encoding="utf-8") as fo:
            spec = fo.read()
        self.assertIn("regex", spec)


@unittest.skipIf(app is None, "tkinter 없음")
class SbsPlanTest(unittest.TestCase):
    """Medium: 변경된 행만 보기 trailing 생략 표시."""

    def _rows(self, kinds):
        rows = []
        for i, k in enumerate(kinds):
            rows.append({"a_no": i + 1, "b_no": i + 1,
                         "a_text": "x", "b_text": "x", "kind": k})
        return rows

    def test_all_equal_trailing_skip(self):
        rows = self._rows(["equal"] * 20001)
        plan = app.sbs_display_plan(rows, True)
        # 첫 행 + 마지막 20000행 생략
        self.assertEqual(plan[0], ("row", 0))
        self.assertEqual(plan[-1], ("skip", 20000))
        self.assertEqual(len(plan), 2)

    def test_middle_change_trailing_skip(self):
        rows = self._rows(["equal"] * 100 + ["replace"] + ["equal"] * 100)
        plan = app.sbs_display_plan(rows, True, context=2)
        # 마지막 동일 구간도 skip으로 닫혀야 한다
        kinds = [p[0] for p in plan]
        self.assertIn("skip", kinds)
        self.assertEqual(plan[-1][0], "skip")
        # 앞쪽 skip도 있다
        self.assertEqual(plan[0][0], "skip")

    def test_no_hide_no_skip(self):
        rows = self._rows(["equal", "replace", "equal"])
        plan = app.sbs_display_plan(rows, False)
        self.assertEqual(plan, [("row", 0), ("row", 1), ("row", 2)])

    def test_empty(self):
        self.assertEqual(app.sbs_display_plan([], True), [])


@unittest.skipIf(app is None, "tkinter 없음")
class ChangeStopsTest(unittest.TestCase):
    """v1.4.6: 이전/다음 차이는 행이 아니라 블록(hunk) 단위로 이동한다."""

    def _rows(self, kinds):
        return [{"kind": k} for k in kinds]

    def _stops(self, kinds, hide=False):
        rows = self._rows(kinds)
        return app.sbs_change_stops(rows, app.sbs_display_plan(rows, hide))

    def test_consecutive_changes_are_one_stop(self):
        kinds = ["equal"] * 3 + ["replace"] * 20 + ["equal"] * 3
        self.assertEqual(self._stops(kinds), [4])

    def test_separate_blocks_are_separate_stops(self):
        kinds = ["equal", "replace", "replace", "equal", "insert", "equal", "delete"]
        self.assertEqual(self._stops(kinds), [2, 5, 7])

    def test_leading_change(self):
        self.assertEqual(self._stops(["delete", "delete", "equal"]), [1])

    def test_no_changes(self):
        self.assertEqual(self._stops(["equal"] * 5), [])

    def test_hide_same_uses_display_numbers(self):
        # 생략 행도 표시 행 1줄을 차지한다. 접힌 상태에서도 번호가 맞아야 한다.
        kinds = ["equal"] * 50 + ["replace", "replace"] + ["equal"] * 50
        rows = self._rows(kinds)
        plan = app.sbs_display_plan(rows, True, context=2)
        stops = app.sbs_change_stops(rows, plan)
        self.assertEqual(len(stops), 1)
        # plan: skip, row, row, row(변경 시작)...
        self.assertEqual(plan[stops[0] - 1], ("row", 50))

    def test_stops_match_hunk_count(self):
        import checker
        a = "\n".join(f"l{i}" for i in range(60)) + "\n"
        bl = [f"l{i}" for i in range(60)]
        for i in list(range(10, 25)) + list(range(40, 45)):
            bl[i] = f"X{i}"
        b = "\n".join(bl) + "\n"
        db = checker.load_db(app.resource_path("syntax_db.json"))
        findings, stats, ops = checker.compare_with_opcodes(
            a, b, "a.txt", "b.txt", db, run_checks=False)
        rows = checker.side_by_side(a, b, opcodes=ops)
        plan = app.sbs_display_plan(rows, False)
        self.assertEqual(len(app.sbs_change_stops(rows, plan)), stats["hunks"])


def _make_app():
    """디스플레이가 없으면 None. GUI 통합 테스트는 이 경우 건너뛴다."""
    if app is None:
        return None
    try:
        return app.App()
    except Exception:  # tk.TclError(디스플레이 없음) 등
        return None


@unittest.skipIf(app is None, "tkinter 없음")
class SaveHeaderAfterCancelTest(unittest.TestCase):
    """v1.4.6: 취소·오류 후에도 저장 파일 헤더는 마지막 완료 결과 요약이다."""

    @classmethod
    def setUpClass(cls):
        cls.gui = _make_app()
        if cls.gui is None:
            raise unittest.SkipTest("디스플레이 없음")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "gui", None) is not None:
            cls.gui.destroy()

    def _run_finished(self):
        import checker
        g = self.gui
        a, b = "a\nb\nc\n", "a\nB\nc\n"
        findings, stats, ops = checker.compare_with_opcodes(
            a, b, "a.txt", "b.txt", g.db, run_checks=False)
        rows = checker.side_by_side(a, b, opcodes=ops)
        g._finish(findings, stats, rows)

    def _read(self, writer, suffix):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            writer(path)
            with open(path, encoding="utf-8") as fo:
                return fo.read()
        finally:
            os.remove(path)

    def test_txt_header_survives_cancel(self):
        self._run_finished()
        done_summary = self.gui._result_summary
        self.assertIn("차이점 1건", done_summary)
        self.gui._finish_cancel()
        self.assertEqual(self.gui.var_summary.get(), "취소됨")  # 상태 표시는 취소
        text = self._read(self.gui._save_txt, ".txt")
        self.assertTrue(text.startswith(done_summary))
        self.assertNotIn("취소됨", text.splitlines()[0])

    def test_html_header_survives_error(self):
        self._run_finished()
        done_summary = self.gui._result_summary
        self.gui._finish_cancel("검사 오류")
        self.assertEqual(self.gui.var_summary.get(), "검사 오류")
        text = self._read(self.gui._save_html, ".html")
        self.assertIn(done_summary.split(" | ")[0], text)
        self.assertNotIn("검사 오류", text)

    def test_next_diff_moves_by_block(self):
        import checker
        g = self.gui
        a = "\n".join(f"line{i}" for i in range(60)) + "\n"
        bl = [f"line{i}" for i in range(60)]
        for i in range(10, 30):
            bl[i] = f"CHANGED{i}"
        b = "\n".join(bl) + "\n"
        findings, stats, ops = checker.compare_with_opcodes(
            a, b, "a.txt", "b.txt", g.db, run_checks=False)
        g._finish(findings, stats, checker.side_by_side(a, b, opcodes=ops))
        g.nb.select(0)
        self.assertEqual(stats["hunks"], 1)
        self.assertEqual(len(g._sbs_change_idx), 1)
        g._move_diff(1)
        first = g._sbs_cursor
        g._move_diff(1)  # 블록이 하나뿐이므로 같은 지점으로 순환
        self.assertEqual(g._sbs_cursor, first)


if __name__ == "__main__":
    unittest.main()
