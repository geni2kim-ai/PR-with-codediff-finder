#!/usr/bin/env python3
"""checker.py 회귀 테스트. 실행: python -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import checker

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "syntax_db.json")


class DBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = checker.load_db(DB)

    def test_load_has_candidates_cached(self):
        self.assertIn("cand_by_first", self.db)
        self.assertGreater(len(self.db["known_all_lower"]), 400)

    def test_typo_in_defined_name(self):
        # 정의된 이름의 오타도 검출한다(방침: README 참고)
        f, _ = checker.check_typos("def recieve_data():\n    pass\n", self.db, "a.py")
        self.assertTrue(any("recieve" in x["summary"] for x in f))

    def test_inflection_not_flagged(self):
        f, _ = checker.check_typos("defined = 1\nchanged = 2\nchecks = 3\n", self.db, "a.py")
        self.assertEqual([x for x in f if "유사어" in x["summary"]], [])

    def test_case_unique_only(self):
        f, _ = checker.check_typos("x = Override\ny = Toast\n", self.db, "a.java")
        self.assertEqual(f, [])
        f2, _ = checker.check_typos("x = getElementByID\n", self.db, "a.js")
        self.assertTrue(any("getElementById" in x["summary"] for x in f2))

    def test_whitelist(self):
        f, _ = checker.check_typos("colour = 1\nparser = 2\ntoast = 3\n", self.db, "a.py")
        self.assertEqual(f, [])

    def test_url_base64_skipped(self):
        f, _ = checker.check_typos("u = 'https://example.com/someLongPathHere'\n", self.db, "a.py")
        self.assertEqual([x for x in f if "example" in x.get("token", "")], [])

    def test_if_assign_nested(self):
        f, _ = checker.check_code_hygiene("if ((a = foo()) !== null) {\n", self.db, "a.js")
        self.assertEqual([x for x in f if "대입" in x["summary"]], [])
        f2, _ = checker.check_code_hygiene("if (fn(a) = 3) {\n", self.db, "a.js")
        self.assertTrue(any("대입" in x["summary"] for x in f2))
        f3, _ = checker.check_code_hygiene("if (a = foo()) {\n", self.db, "a.java")
        self.assertTrue(any("대입" in x["summary"] for x in f3))

    def test_if_assign_bare(self):
        f, _ = checker.check_code_hygiene("if biometricOn = true {\n", self.db, "a.swift")
        self.assertTrue(any("대입" in x["summary"] for x in f))

    def test_eq_in_string_comment_ignored(self):
        code = 'var s = "a == b"; // c == d\nif (a == b) {}\n'
        f, _ = checker.check_code_hygiene(code, self.db, "a.js")
        hits = [x for x in f if "완화된 동등" in x["summary"]]
        self.assertEqual(len(hits), 1)

    def test_ne_null_idiom_ignored(self):
        f, _ = checker.check_code_hygiene("if (x != null) {\n", self.db, "a.js")
        self.assertEqual([x for x in f if "완화된 동등" in x["summary"]], [])

    def test_ne_null_and_loose_eq_same_line(self):
        # Medium: "a != null && b == c"에서 b == c는 경고 유지, != null만 제외
        f, _ = checker.check_code_hygiene("if (a != null && b == c) {\n", self.db, "a.js")
        hits = [x for x in f if "완화된 동등" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("b == c", hits[0]["detail"])

    def test_todo_in_string_ignored(self):
        # Medium: msg = "TODO: ..." 같은 문자열은 미완성 주석이 아니다
        f, _ = checker.check_code_hygiene('msg = "TODO: refactor later"\n', self.db, "a.py")
        self.assertEqual([x for x in f if "미완성" in x["summary"]], [])

    def test_todo_in_comment_kept(self):
        f, _ = checker.check_code_hygiene("// TODO: fix this\n", self.db, "a.js")
        self.assertTrue(any("미완성" in x["summary"] for x in f))
        f2, _ = checker.check_code_hygiene("# TODO: fix this\n", self.db, "a.py")
        self.assertTrue(any("미완성" in x["summary"] for x in f2))

    def test_todo_identifier_not_flagged(self):
        # 식별자 TODO는 주석이 아니다
        for code, fn in (("TODO = 1\n", "a.py"),
                         ("const TODO = 1;\n", "a.js"),
                         ("int TODO = 1;\n", "a.java")):
            f, _ = checker.check_code_hygiene(code, self.db, fn)
            self.assertEqual([x for x in f if "미완성" in x["summary"]], [],
                             f"{fn}: {code!r}")

    def test_todo_apostrophe_comment_kept(self):
        # 주석 안 아포스트로피에 흔들리지 않아야 한다
        f, _ = checker.check_code_hygiene("// it's a hack, TODO: don't ship\n",
                                          self.db, "a.js")
        self.assertTrue(any("미완성" in x["summary"] for x in f))

    def test_todo_quoted_in_md_kept(self):
        # 비코드 확장자는 원문 그대로 본다
        f, _ = checker.check_code_hygiene('Remember the "TODO" list\n', self.db, "a.md")
        self.assertTrue(any("미완성" in x["summary"] for x in f))

    def test_todo_json_string_ignored(self):
        # Medium: json 문자열 안의 TODO는 미완성이 아니다
        f, _ = checker.check_code_hygiene('{"note": "TODO fix this"}\n', self.db, "a.json")
        self.assertEqual([x for x in f if "미완성" in x["summary"]], [])

    def test_todo_sql_comment_vs_string(self):
        # Medium: sql -- 주석 안은 검출, '...' 안은 제외, '' 이스케이프 처리
        f, _ = checker.check_code_hygiene("SELECT 'TODO: not a task';\n", self.db, "a.sql")
        self.assertEqual([x for x in f if "미완성" in x["summary"]], [])
        f2, _ = checker.check_code_hygiene("SELECT 1; -- TODO: real task\n", self.db, "a.sql")
        self.assertTrue(any("미완성" in x["summary"] for x in f2))
        f3, _ = checker.check_code_hygiene("SELECT 'it''s TODO here';\n", self.db, "a.sql")
        self.assertEqual([x for x in f3 if "미완성" in x["summary"]], [])
        f4, _ = checker.check_code_hygiene("/* TODO: block */\nSELECT 1;\n", self.db, "a.sql")
        self.assertTrue(any("미완성" in x["summary"] for x in f4))

    def test_template_interp_code_checked(self):
        # ${} 안은 실제 코드다
        f, _ = checker.check_code_hygiene("const s = `value=${a == b}`;\n",
                                          self.db, "a.js")
        self.assertTrue(any("완화된 동등" in x["summary"] for x in f))
        f2, _ = checker.check_code_hygiene("const t = `value=${alert(x)}`;\n",
                                           self.db, "a.js")
        self.assertTrue(any("alert" in x["summary"] for x in f2))

    def test_template_text_still_ignored(self):
        code = "var s = `start\nconsole.log('x')\nend`;\n"
        f, _ = checker.check_code_hygiene(code, self.db, "a.js")
        self.assertEqual([x for x in f if "console" in x["summary"]], [])

    def test_console_in_template_ignored(self):
        # Medium: 여러 줄 백틱 문자열 안의 console.log/alert는 코드가 아니다
        code = "var s = `start\nconsole.log('x')\nalert('y')\nend`;\n"
        f, _ = checker.check_code_hygiene(code, self.db, "a.js")
        self.assertEqual([x for x in f if "console" in x["summary"]], [])
        self.assertEqual([x for x in f if "alert" in x["summary"]], [])

    def test_indent_region(self):
        far = "\tx = 1\n" + "y = 2\n" * 50 + "    z = 3\n"
        f, _ = checker.check_code_hygiene(far, self.db, "a.py")
        self.assertEqual([x for x in f if "들여쓰기" in x["summary"]], [])
        near = "\tx = 1\n    y = 2\n"
        f2, _ = checker.check_code_hygiene(near, self.db, "a.py")
        self.assertTrue(any("들여쓰기" in x["summary"] for x in f2))

    def test_typo_limit_flag(self):
        old = checker.MAX_GROUPS_PER_FILE
        checker.MAX_GROUPS_PER_FILE = 3
        try:
            code = "x recieve\nx lenght\nx pritn\nx widht\nx teh\n"
            f, info = checker.check_typos(code, self.db, "a.js")
        finally:
            checker.MAX_GROUPS_PER_FILE = old
        self.assertTrue(info["truncated"])
        self.assertEqual(len(f), 3)

    def test_typo_grouping_counts(self):
        code = "".join(f"recieve_line{i} = {i}\n" for i in range(300))
        code += "lenght = 1\nwidht = 2\n"
        f, info = checker.check_typos(code, self.db, "a.py")
        self.assertFalse(info["truncated"])
        self.assertEqual(info["occurrences"], 302)
        rec = [x for x in f if "recieve" in x["summary"]]
        self.assertEqual(len(rec), 1)
        self.assertIn("총 300곳", rec[0]["summary"])
        self.assertIn("외 295곳", rec[0]["detail"])
        self.assertTrue(any("lenght" in x["summary"] for x in f))
        self.assertTrue(any("widht" in x["summary"] for x in f))

    def test_new_in_b(self):
        f, s = checker.compare("x = 1\n", "x = 1\npritn(x)\n",
                               "a.py", "b.py", self.db)
        new = [x for x in f if x.get("is_new")]
        self.assertTrue(new)
        self.assertEqual(s["new_in_b"], len(new))

    def test_new_key_stable_across_counts(self):
        # A·B에 같은 종류가 있으면 B의 동일 종류는 신규가 아니다(건수 달라도)
        f, s = checker.compare("recieve = 1\n", "recieve = 1\nrecieve = 2\n",
                               "a.py", "b.py", self.db)
        self.assertEqual([x for x in f if x.get("is_new")], [])

    def test_block_comment_ignored(self):
        code = "/*\nif (a = b) {}\n*/\nif (c = d) {}\n"
        f, _ = checker.check_code_hygiene(code, self.db, "a.java")
        hits = [x for x in f if "대입" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("c = d", hits[0]["summary"])

    def test_docstring_ignored(self):
        code = '"""\nif x = 3\n"""\nif y = 4\n'
        f, _ = checker.check_code_hygiene(code, self.db, "a.py")
        hits = [x for x in f if "대입" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("y = 4", hits[0]["summary"])

    def test_elif_assign(self):
        f, _ = checker.check_code_hygiene("elif x = 3:\n", self.db, "a.py")
        self.assertTrue(any("대입" in x["summary"] for x in f))

    def test_floor_div_kept(self):
        code = "v = x // 2\nif w = 3:\n"
        f, _ = checker.check_code_hygiene(code, self.db, "a.py")
        self.assertTrue(any("w = 3" in x["summary"] for x in f if "대입" in x["summary"]))

    def test_long_camel_not_base64(self):
        name = "calculateTotalAmountForRecieveItemsInThisLongMethodName"
        self.assertGreaterEqual(len(name), 40)
        f, _ = checker.check_typos(name + " = 1\n", self.db, "a.py")
        self.assertTrue(any("recieve" in x["summary"].lower() for x in f))

    def test_real_base64_skipped(self):
        b64 = "QUJDREVGR0hJSktMTU5PUFFSU1RUVVZXWFlaYWJjZGVmZ2hpams= extra"
        f, _ = checker.check_typos("data = " + b64 + "\n", self.db, "a.py")
        self.assertEqual(f, [])

    def test_bom_equal(self):
        f, s = checker.compare("\ufeffabc\n", "abc\n", "a.txt", "b.txt",
                               self.db, run_checks=False)
        self.assertEqual(s["hunks"], 0)

    def test_line_endings(self):
        f, s = checker.compare("a\r\nb\r\n", "a\nb\n", "a.txt", "b.txt",
                               self.db, run_checks=False)
        self.assertTrue(any("줄바꿈 형식" in x["summary"] for x in f))
        f2, _ = checker.compare("a\n", "a", "a.txt", "b.txt",
                                self.db, run_checks=False)
        self.assertTrue(any("끝 개행" in x["summary"] for x in f2))

    def test_inline_diff(self):
        f, _ = checker.compare("hello brave world\n", "hello small world\n",
                               "a.txt", "b.txt", self.db, run_checks=False)
        self.assertTrue(any("[-brave-]" in x["detail"] and "[+small+]" in x["detail"]
                            for x in f))

    def test_cancel(self):
        ev = threading.Event()
        ev.set()
        code = "x = 1\n" * 5000
        with self.assertRaises(checker.Cancelled):
            checker.check_typos(code, self.db, "a.py", cancel=ev)

    def test_cancel_single_long_line(self):
        # Medium: 수 MB 한 줄에서도 토큰 단위로 취소가 먹어야 한다
        code = "".join(f"w{i} " for i in range(300000))
        ev = threading.Event()
        t = threading.Timer(0.05, ev.set)
        t.start()
        try:
            with self.assertRaises(checker.Cancelled):
                checker.check_typos(code, self.db, "a.py", cancel=ev)
        finally:
            t.cancel()

    def test_perf_pool(self):
        import time
        code = "".join(f"alpha{i} = beta{i} + gamma{i}\n" for i in range(2000))
        t0 = time.perf_counter()
        checker.check_typos(code, self.db, "a.py")
        self.assertLess(time.perf_counter() - t0, 10)


class UserDBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = checker.load_db(DB)
        cls.tmp = tempfile.mkdtemp()

    def _write(self, name, data, encoding="utf-8"):
        p = os.path.join(self.tmp, name)
        if isinstance(data, bytes):
            with open(p, "wb") as fo:
                fo.write(data)
        else:
            with open(p, "w", encoding=encoding) as fo:
                fo.write(data)
        return p

    def test_bom_user_db(self):
        p = self._write("u1.json", '{"words": ["zzzcustomword"]}')
        with open(p, "rb") as fi:
            raw = fi.read()
        with open(p, "wb") as fo:
            fo.write(b"\xef\xbb\xbf" + raw)
        db = checker.load_db(DB, p)
        self.assertIn("zzzcustomword", db["known_all_lower"])
        self.assertEqual(db["warnings"], [])

    def test_cp949_user_db_keeps_base(self):
        p = self._write("u2.json", '{"words": ["한글단어"]}', encoding="cp949")
        db = checker.load_db(DB, p)
        self.assertGreater(len(db["known_all_lower"]), 400)
        self.assertTrue(any("사용자 DB" in w for w in db["warnings"]))

    def test_words_null(self):
        p = self._write("u3.json", '{"words": null}')
        db = checker.load_db(DB, p)
        self.assertGreater(len(db["known_all_lower"]), 400)

    def test_words_string_no_char_split(self):
        p = self._write("u4.json", '{"words": "abc"}')
        db = checker.load_db(DB, p)
        self.assertNotIn("a", db["known_all_lower"])
        self.assertNotIn("b", db["known_all_lower"])

    def test_words_with_list_inside(self):
        p = self._write("u5.json", '{"words": ["okword", ["nested"]]}')
        db = checker.load_db(DB, p)
        self.assertIn("okword", db["known_all_lower"])
        self.assertTrue(any("제외" in w for w in db["warnings"]))

    def test_base_bom_loads(self):
        p = self._write("base.json", '{"identifiers": ["Q1"], "words": [], "typo_map": {}, "patterns": []}')
        with open(p, "rb") as fi:
            raw = fi.read()
        with open(p, "wb") as fo:
            fo.write(b"\xef\xbb\xbf" + raw)
        db = checker.load_db(p)
        self.assertIn("Q1", db["known_exact"])

    def test_user_typo_applies(self):
        p = self._write("u6.json", '{"typo_map": {"tehName": "theName"}}')
        db = checker.load_db(DB, p)
        f, _ = checker.check_typos("tehName = 1\n", db, "a.py")
        self.assertTrue(any("theName" in x["summary"] for x in f))


class UserPatternTest(unittest.TestCase):
    """사용자 패턴 방어 검증(①). 어떤 깨진 패턴도 앱을 죽이지 않아야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.base = checker.load_db(DB)

    def _db_with(self, patterns):
        p = os.path.join(tempfile.mkdtemp(), "u.json")
        with open(p, "w", encoding="utf-8") as fo:
            json.dump({"patterns": patterns}, fo, ensure_ascii=False)
        return checker.load_db(DB, p)

    def test_not_if_non_string(self):
        # not_if가 숫자 → TypeError 대신 경고 후 규칙은 유지
        db = self._db_with([{"id": "p1", "title": "T", "message": "M",
                             "regex": r"\bconsole\.log\b", "not_if": 123,
                             "extensions": ["js"], "code_only": True}])
        self.assertTrue(any("not_if" in w for w in db["warnings"]))
        self.assertEqual(len(db["patterns"]), len(self.base["patterns"]) + 1)
        f, _ = checker.check_code_hygiene("console.log(1)\n", db, "a.js")
        self.assertTrue(any("T" in x["summary"] for x in f))

    def test_missing_title_message_excluded(self):
        db = self._db_with([{"id": "p1", "regex": r"\bfoo\b"},
                            {"id": "p2", "regex": r"\bbar\b", "title": "제목만"}])
        self.assertTrue(any("필수 키" in w for w in db["warnings"]))
        self.assertEqual(len(db["patterns"]), len(self.base["patterns"]))
        # 검사가 KeyError로 죽지 않는다
        checker.check_code_hygiene("foo bar\n", db, "a.js")

    def test_extensions_string(self):
        db = self._db_with([{"id": "p1", "title": "T", "message": "M",
                             "regex": r"\bbaz\b", "extensions": "py"}])
        f, _ = checker.check_code_hygiene("baz = 1\n", db, "a.py")
        self.assertTrue(any("T" in x["summary"] for x in f))

    def test_bad_regex_excluded(self):
        db = self._db_with([{"id": "p1", "title": "T", "message": "M",
                             "regex": "(["}])
        self.assertTrue(any("p1" in w for w in db["warnings"]))
        self.assertEqual(len(db["patterns"]), len(self.base["patterns"]))

    def test_non_dict_pattern_excluded(self):
        db = self._db_with([123, "문자열", None])
        self.assertEqual(len(db["patterns"]), len(self.base["patterns"]))

    def test_severity_allowlist(self):
        db = self._db_with([{"id": "p1", "title": "T", "message": "M",
                             "regex": r"\bquux\b", "severity": "경고"}])
        self.assertTrue(any("severity" in w for w in db["warnings"]))
        self.assertEqual(len(db["patterns"]), len(self.base["patterns"]) + 1)
        f, _ = checker.check_code_hygiene("quux = 1\n", db, "a.py")
        hit = [x for x in f if "T" in x["summary"]]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["category"], "특이사항")

    def test_severity_diff_category_rejected(self):
        # Medium: 사용자 규칙이 '차이점' 카테고리를 쓰면 실제 diff와 섞인다
        db = self._db_with([{"id": "p1", "title": "T", "message": "M",
                             "regex": r"\bquux\b", "severity": "차이점"}])
        self.assertTrue(any("severity" in w for w in db["warnings"]))
        f, _ = checker.check_code_hygiene("quux = 1\n", db, "a.py")
        hit = [x for x in f if "T" in x["summary"]]
        self.assertEqual(len(hit), 1)
        self.assertNotEqual(hit[0]["category"], "차이점")

    def test_evil_quantifier_excluded(self):
        # High: (a+)+$ 같은 중첩 수량자는 로드 단계에서 제외된다
        import time
        db = self._db_with([{"id": "evil", "title": "E", "message": "M",
                             "regex": "(a+)+$"}])
        self.assertTrue(any("중첩 수량자" in w for w in db["warnings"]))
        self.assertTrue(all(p.get("id") != "evil" for p in db["patterns"]))
        t0 = time.perf_counter()
        checker.check_code_hygiene("a" * 30 + "b\nx = 1\n", db, "a.py")
        self.assertLess(time.perf_counter() - t0, 5)

    def test_evil_quantifier_detector_units(self):
        evil = [r"(a+)+$", r"(a*)*", r"(\w+)+x", r"((ab)+cd)+", r"(a+){2,}"]
        for rx in evil:
            self.assertTrue(checker._evil_quantifier(rx), rx)
        ok = [r"(a|b)+", r"(ab)+", r"(?:foo|bar)+", r"[a+]+x", r"a+b",
              r"if\s*\([^()]*\)", r"(?<![=!<>])==(?!=)|!=(?!=)",
              r"console\.(log|debug|info)\s*\(", r"!=\s*null", r"(\s*foo)?"]
        for rx in ok:
            self.assertFalse(checker._evil_quantifier(rx), rx)

    def test_evil_not_if_dropped(self):
        db = self._db_with([{"id": "p1", "title": "T", "message": "M",
                             "regex": r"\bquux\b", "extensions": ["py"],
                             "not_if": r"(x+)+$"}])
        self.assertTrue(any("not_if" in w and "중첩" in w for w in db["warnings"]))
        f, _ = checker.check_code_hygiene("quux = 1\n", db, "a.py")
        self.assertTrue(any("T" in x["summary"] for x in f))

    @unittest.skipIf(not checker._HAS_REGEX, "regex 모듈 없음")
    def test_redos_alternation_timeout(self):
        # High: (a|a?)+$ 는 정적 필터를 통과하지만 실행 단계에서 멈추지 않아야 한다
        import time
        db = self._db_with([{"id": "alt", "title": "A", "message": "M",
                             "regex": "(a|a?)+$"}])
        # 합법 패턴이므로 로드되고(정적 필터 통과), 실행 단계에서 멈추지 않는다
        self.assertTrue(any(p.get("id") == "alt" for p in db["patterns"]))
        t0 = time.perf_counter()
        checker.check_code_hygiene("a" * 24 + "!\n", db, "a.txt")
        self.assertLess(time.perf_counter() - t0, 5)

    def test_lazy_iteration_caps_at_60(self):
        # Medium: 수천 매치가 있어도 60건에서 중단하고 나머지는 만들지 않는다
        db = self._db_with([{"id": "many", "title": "M", "message": "M",
                             "regex": r"(foo|bar)"}])
        text = "".join(f"foo bar {i}\n" for i in range(5000))
        f, info = checker.check_code_hygiene(text, db, "a.txt")
        hits = [x for x in f if x["summary"].startswith("[M]")]
        self.assertEqual(len(hits), 60)
        self.assertIn("many", info["capped"])

    def test_lazy_iteration_memory(self):
        # Medium: 512KB 입력에서 수십만 매치 객체를 미리 만들지 않는다
        import tracemalloc
        db = self._db_with([{"id": "many", "title": "M", "message": "M",
                             "regex": r"(?=x)"}])
        text = "x" * (512 * 1024) + "\n"
        tracemalloc.start()
        try:
            f, info = checker.check_code_hygiene(text, db, "a.txt")
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(len([x for x in f if x["summary"].startswith("[M]")]), 60)
        self.assertLess(peak, 30 * 1024 * 1024)

    def test_no_regex_fallback_notice(self):
        # Low: regex 모듈이 없으면 시간 제한 비활성화를 경고에 표시한다
        old = checker._HAS_REGEX
        checker._HAS_REGEX = False
        try:
            db = self._db_with([{"id": "p1", "title": "T", "message": "M",
                                 "regex": r"\bquux\b"}])
            self.assertTrue(any("시간 제한 비활성화" in w for w in db["warnings"]))
        finally:
            checker._HAS_REGEX = old
        if checker._HAS_REGEX:
            db = self._db_with([{"id": "p1", "title": "T", "message": "M",
                                 "regex": r"\bquux\b"}])
            self.assertFalse(any("시간 제한 비활성화" in w for w in db["warnings"]))

    def test_rx_timeout_plumbing(self):
        # timeout=0은 결정적으로 _RxTimeout을 일으킨다(regex 엔진일 때)
        rx = checker._compile_rx("abc")
        if checker._HAS_REGEX:
            with self.assertRaises(checker._RxTimeout):
                checker._collect_matches(rx, "abc", timeout=0)
            got = checker._collect_matches(rx, "abc", timeout=60)
            self.assertEqual([(m.start(), m.end()) for m in got], [(0, 3)])
        else:
            self.assertEqual(len(checker._collect_matches(rx, "abc")), 1)

    def test_user_typo_counted_in_stats(self):
        # Medium: 사용자 패턴이 낸 오타 의심도 목록과 통계에 함께 반영된다
        db = self._db_with([{"id": "uq", "title": "사내 약어", "message": "M",
                             "regex": r"\bquux\b", "severity": "오타 의심"}])
        f, s = checker.compare("quux = 1\n", "quux = 1\n",
                               "a.py", "b.py", db)
        hits = [x for x in f if x.get("category") == "오타 의심"]
        self.assertEqual(len(hits), 2)
        self.assertEqual(s["typos"], 2)
        self.assertEqual(s["typo_kinds"], 1)

    def test_malformed_fuzz_no_crash(self):
        # High: 어떤 깨진 사용자 규칙도 로드·검사를 죽이지 않아야 한다
        bad_patterns = [
            {"regex": "foo"},                       # id/title/message 누락
            {"id": 1, "regex": "foo", "title": "T", "message": "M"},
            {"id": "x", "regex": 123, "title": "T", "message": "M"},
            {"id": "x", "regex": "", "title": "T", "message": "M"},
            {"id": "x", "regex": "foo", "title": "", "message": "M"},
            {"id": "x", "regex": "foo", "title": "T", "message": None},
            {"id": "x", "regex": "foo", "title": "T", "message": "M",
             "extensions": 123},
            {"id": "x", "regex": "foo", "title": "T", "message": "M",
             "extensions": ["py", 123]},
            {"id": "x", "regex": "foo", "title": "T", "message": "M",
             "extensions": {"py": 1}},
            {"id": "x", "regex": "foo", "title": "T", "message": "M",
             "not_if": None},
            {"id": "x", "regex": "foo", "title": "T", "message": "M",
             "not_if": ["a"]},
            {"id": "x", "regex": "foo", "title": "T", "message": "M",
             "not_if": "(("},
            {"id": "x", "regex": "foo", "title": "T", "message": "M",
             "severity": 5},
            {"id": "x", "regex": "foo", "title": "T", "message": "M",
             "code_only": "yes"},
            {"id": "x", "regex": "foo", "title": "T", "message": "M",
             "scanner": ["if_assign"]},
            ["not", "a", "dict"],
            "just a string",
            42, None, True,
        ]
        for i, bad in enumerate(bad_patterns):
            with self.subTest(i=i):
                db = self._db_with([bad])
                # 로드된 규칙 수: base 이하, 검사는 예외 없이
                self.assertLessEqual(len(db["patterns"]), len(self.base["patterns"]) + 1)
                checker.check_code_hygiene(
                    "foo bar\nif (a == b) {}\nconsole.log(1)\n", db, "a.js")
                checker.check_code_hygiene(
                    "foo bar\nif x == 1:\n", db, "a.py")


class StripTest(unittest.TestCase):
    """여러 줄 문자열·전처리 지시문 처리(⑤)."""

    def test_js_multiline_template_ignored(self):
        code = "var s = `line1\nif (a = b) {}\nvar x == y`;\nif (c = d) {}\n"
        f, _ = checker.check_code_hygiene(code, checker.load_db(DB), "a.js")
        hits = [x for x in f if "대입" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("c = d", hits[0]["summary"])

    def test_java_text_block_ignored(self):
        code = 'String s = """\nif (a = b)\n""";\nif (c = d) {}\n'
        f, _ = checker.check_code_hygiene(code, checker.load_db(DB), "a.java")
        hits = [x for x in f if "대입" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("c = d", hits[0]["summary"])

    def test_c_preprocessor_ignored(self):
        code = "#if (a = b)\n#define X 1\nif (c = d) {\n"
        f, _ = checker.check_code_hygiene(code, checker.load_db(DB), "a.c")
        hits = [x for x in f if "대입" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("c = d", hits[0]["summary"])

    def test_c_line_comment_still_works(self):
        code = "// if (a = b) {}\nif (c = d) {\n"
        f, _ = checker.check_code_hygiene(code, checker.load_db(DB), "a.c")
        self.assertEqual(len([x for x in f if "대입" in x["summary"]]), 1)

    def test_cpp_raw_string_ignored(self):
        # Medium: R"(...)" 안의 if (a = b)는 코드가 아니다
        code = 'std::string s = R"(if (a = b) {})";\nif (c = d) {}\n'
        f, _ = checker.check_code_hygiene(code, checker.load_db(DB), "a.cpp")
        hits = [x for x in f if "대입" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("c = d", hits[0]["summary"])

    def test_cpp_raw_string_multiline_ignored(self):
        code = 'auto s = R"xyz(\nif (a = b) {}\n)xyz";\nif (c = d) {}\n'
        f, _ = checker.check_code_hygiene(code, checker.load_db(DB), "a.cpp")
        hits = [x for x in f if "대입" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("c = d", hits[0]["summary"])

    def test_cs_verbatim_string_ignored(self):
        # Medium: @"..." 안의 if (a = b)는 코드가 아니다
        code = 'var s = @"if (a = b)";\nif (c = d) {}\n'
        f, _ = checker.check_code_hygiene(code, checker.load_db(DB), "a.cs")
        hits = [x for x in f if "대입" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("c = d", hits[0]["summary"])

    def test_cs_verbatim_multiline_escape_ignored(self):
        code = 'var s = @"l1\nsay ""hi""\nif (a = b)\n";\nif (c = d) {}\n'
        f, _ = checker.check_code_hygiene(code, checker.load_db(DB), "a.cs")
        hits = [x for x in f if "대입" in x["summary"]]
        self.assertEqual(len(hits), 1)
        self.assertIn("c = d", hits[0]["summary"])


class DiffTest(unittest.TestCase):
    def test_full_replace_boundary_merge(self):
        # High: 2000→2001행 경계. 전체 교체는 크기와 무관하게 1 hunk이어야 한다
        for n in (2001, 2100):
            a = [f"row{i}" for i in range(n)]
            b = [f"ROW{i}" for i in range(n)]
            f, s = checker.diff_texts(a, b, "a", "b")
            self.assertEqual(s["hunks"], 1, f"n={n}")
            self.assertEqual(s["changed_lines"], n, f"n={n}")
            self.assertFalse(s["approx"], f"n={n}")

    def test_pure_insert_delete_labels_kept(self):
        # 병합 후에도 순수 삽입/삭제 블록의 라벨은 유지된다
        a = ["same"] * 2100
        b = ["same"] * 1000 + ["NEW"] * 50 + ["same"] * 1100
        f, s = checker.diff_texts(a, b, "a", "b")
        self.assertEqual(s["hunks"], 1)
        self.assertIn("[추가]", f[0]["summary"])
        f2, _ = checker.diff_texts(b, a, "b", "a")
        self.assertIn("[삭제]", f2[0]["summary"])

    def test_exact_flag_same_result_small(self):
        a = ["x = 1", "y = 2", "z = 3"]
        b = ["x = 1", "y = 9", "z = 3"]
        f1, s1 = checker.diff_texts(a, b, "a", "b")
        f2, s2 = checker.diff_texts(a, b, "a", "b", exact=True)
        self.assertEqual(f1, f2)
        self.assertEqual(s1["approx"], s2["approx"])

    def test_no_autojunk_accuracy_large(self):
        # High: 16000행 중 1행 변경 → 1건으로 정확히 (autojunk 시절엔 8000행 오판)
        a = [f"line{i % 7}" for i in range(16000)]
        b = list(a)
        b[8000] = "changed"
        f, s = checker.diff_texts(a, b, "a", "b")
        self.assertFalse(s["approx"])
        self.assertEqual(s["hunks"], 1)
        self.assertEqual(s["changed_lines"], 1)

    def test_repetitive_perf_no_cliff(self):
        # High: 반복행 14999개도 수 초 내 (기존 26초 절벽)
        import time
        a = ["same"] * 14999
        b = list(a)
        b[7000] = "DIFF"
        t0 = time.perf_counter()
        f, s = checker.diff_texts(a, b, "a", "b")
        self.assertLess(time.perf_counter() - t0, 5)
        self.assertEqual(s["changed_lines"], 1)

    def test_scattered_edits_all_found(self):
        # 16k 중 7곳 편집 → 7블록 그대로
        a = [f"line{i:05d} value={i}" for i in range(16000)]
        b = list(a)
        for p in (100, 2500, 5000, 8000, 10000, 13000, 15500):
            b[p] = "EDITED"
        f, s = checker.diff_texts(a, b, "a", "b")
        self.assertEqual(s["hunks"], 7)
        self.assertEqual(s["changed_lines"], 7)

    def test_diff_cancel_preset(self):
        # High: 미리 설정된 취소는 즉시 raise
        ev = threading.Event()
        ev.set()
        with self.assertRaises(checker.Cancelled):
            checker.diff_texts(["a", "b"], ["a", "c"], "x", "y", cancel=ev)

    def test_block_move_exact(self):
        # High: 2500행 중 300행 블록 이동 → 과대 판정 없이 정확히
        a = [f"L{i:04d}" for i in range(2500)]
        b = a[:500] + a[800:1000] + a[500:800] + a[1000:]
        f, s = checker.diff_texts(a, b, "a", "b")
        self.assertFalse(s["approx"])
        self.assertEqual(s["equal_lines"], 2300)
        self.assertEqual(s["changed_lines"], 400)

    def test_approx_flag_on_extreme(self):
        # 극단적 drift + 공통행 없음 → 근사 표시(결정적)
        a = ["x"] * 3000
        b = ["y"] * 3000 + ["z"] * 1500
        f, s = checker.diff_texts(a, b, "a", "b")
        self.assertTrue(s["approx"])
        f2, s2 = checker.diff_texts(a, b, "a", "b")
        self.assertEqual(
            [(x["category"], x["summary"]) for x in f],
            [(x["category"], x["summary"]) for x in f2])

    def test_patience_code_move(self):
        # 고유 행이 풍부한 코드형 대이동 → patience 분할로 정확히
        # (B는 [0-999][3000-3999][1000-2999][4000+] → LCS 5000이 최적)
        a = [f"stmt_{i:05d}();" for i in range(6000)]
        b = a[:1000] + a[3000:4000] + a[1000:3000] + a[4000:]
        f, s = checker.diff_texts(a, b, "a", "b")
        self.assertFalse(s["approx"])
        self.assertEqual(s["equal_lines"], 5000)
        self.assertEqual(s["changed_lines"], 2000)

    def test_exact_honored(self):
        # exact=True는 상한을 완화한다
        self.assertGreater(checker._DIFF_FULL_D_CAP_EXACT,
                           checker._DIFF_FULL_D_CAP)
        a = [f"L{i}" for i in range(100)]
        b = [f"M{i}" for i in range(100)]
        f1, _ = checker.diff_texts(a, b, "a", "b")
        f2, _ = checker.diff_texts(a, b, "a", "b", exact=True)
        self.assertEqual(
            [(x["category"], x["summary"]) for x in f1],
            [(x["category"], x["summary"]) for x in f2])

    def test_diff_apply_invariant(self):
        # opcode를 A에 적용하면 B가 나와야 한다
        import random
        rnd = random.Random(42)
        for _ in range(30):
            alpha = [f"L{i}" for i in range(rnd.randint(1, 5))]
            a = [rnd.choice(alpha) for _ in range(rnd.randint(0, 30))]
            b = list(a)
            for _ in range(rnd.randint(0, 4)):
                if not b:
                    break
                p = rnd.randrange(len(b))
                op = rnd.choice(["chg", "ins", "del"])
                if op == "chg":
                    b[p] = "ZZZ"
                elif op == "ins":
                    b.insert(p, "III")
                else:
                    del b[p]
            out = []
            for tag, i1, i2, j1, j2 in checker._diff_opcodes(a, b)[0]:
                if tag == "equal":
                    self.assertEqual(a[i1:i2], b[j1:j2])
                    out += a[i1:i2]
                elif tag in ("insert", "replace"):
                    out += b[j1:j2]
            self.assertEqual(out, b)

    def test_typo_stats_two_counts(self):
        # 발생 횟수(typos)와 묶음 수(typo_kinds)가 따로 집계된다(③)
        code = "recieve = 1\nrecieve = 2\nlenght = 3\n"
        f, info = checker.check_typos(code, checker.load_db(DB), "a.py")
        self.assertEqual(info["occurrences"], 3)
        self.assertEqual(info["groups"], 2)
        self.assertEqual(len(f), 2)

    def test_empty_file_is_zero_lines(self):
        # Medium: 빈 파일은 0행이다. "" → "x"는 1행 수정이 아니라 1행 추가다
        db = checker.load_db(DB)
        f, s = checker.compare("", "x\n", "a.py", "b.py", db,
                               run_checks=False)
        self.assertEqual(s["a_total"], 0)
        self.assertEqual(s["b_total"], 1)
        self.assertEqual(s["hunks"], 1)
        self.assertEqual(s["changed_lines"], 1)
        self.assertIn("[추가]", f[0]["summary"])
        f2, s2 = checker.compare("", "", "a.py", "b.py", db)
        self.assertEqual(f2, [])
        self.assertEqual(s2["hunks"], 0)

    def test_typo_kinds_dedup_across_files(self):
        # Medium: 같은 오타가 A/B에 있어도 종류는 1종, 발생은 2곳이다
        db = checker.load_db(DB)
        f, s = checker.compare("recieve = 1\n", "recieve = 1\n",
                               "a.py", "b.py", db)
        self.assertEqual(s["typo_kinds"], 1)
        self.assertEqual(s["typos"], 2)


class SideBySideTest(unittest.TestCase):
    def test_pairing_and_numbers(self):
        a = "same1\nold1\nold2\nsame2\n"
        b = "same1\nnew1\nsame2\n"
        rows = checker.side_by_side(a, b)
        kinds = [r["kind"] for r in rows]
        self.assertEqual(kinds, ["equal", "replace", "delete", "equal"])
        self.assertEqual([(r["a_no"], r["b_no"]) for r in rows],
                         [(1, 1), (2, 2), (3, None), (4, 3)])
        self.assertEqual(rows[1]["a_text"], "old1")
        self.assertEqual(rows[1]["b_text"], "new1")
        self.assertIsNone(rows[2]["b_text"])

    def test_insert_pairing(self):
        rows = checker.side_by_side("a\n", "a\nb\n")
        self.assertEqual([r["kind"] for r in rows], ["equal", "insert"])
        self.assertIsNone(rows[1]["a_no"])
        self.assertEqual(rows[1]["b_no"], 2)

    def test_reconstructs_inputs(self):
        a_raw = "x = 1\ny = 2\nz = 3\n"
        b_raw = "x = 1\nY = 9\nz = 3\ntail\n"
        rows = checker.side_by_side(a_raw, b_raw)
        self.assertEqual([r["a_text"] for r in rows if r["a_text"] is not None],
                         a_raw.split("\n")[:-1] if a_raw.endswith("\n") else a_raw.split("\n"))
        self.assertEqual([r["b_text"] for r in rows if r["b_text"] is not None],
                         b_raw.split("\n")[:-1])

    def test_changed_count_matches_diff_texts(self):
        a_raw = "l1\nl2\nl3\nl4\nl5\n"
        b_raw = "l1\nL2\nL3\nl4\nl5\nextra\n"
        rows = checker.side_by_side(a_raw, b_raw)
        non_eq = sum(1 for r in rows if r["kind"] != "equal")
        _, s = checker.diff_texts(a_raw.split("\n")[:-1], b_raw.split("\n")[:-1],
                                  "a", "b")
        self.assertEqual(non_eq, s["changed_lines"])

    def test_ignore_ws_parity(self):
        a_raw = "x  =  1\ny=2\n"
        b_raw = "x = 1\ny=2\n"
        rows = checker.side_by_side(a_raw, b_raw, ignore_ws=True)
        self.assertTrue(all(r["kind"] == "equal" for r in rows))
        rows2 = checker.side_by_side(a_raw, b_raw, ignore_ws=False)
        self.assertTrue(any(r["kind"] != "equal" for r in rows2))

    def test_crlf_parity(self):
        rows = checker.side_by_side("a\r\nb\r\n", "a\nb\n")
        self.assertTrue(all(r["kind"] == "equal" for r in rows))

    def test_word_spans(self):
        sa, sb = checker.word_spans("hello brave world", "hello small world")
        self.assertEqual(len(sa), 1)
        self.assertEqual("hello brave world"[sa[0][0]:sa[0][1]], "brave")
        self.assertEqual(len(sb), 1)
        self.assertEqual("hello small world"[sb[0][0]:sb[0][1]], "small")

    def test_word_spans_identical(self):
        self.assertEqual(checker.word_spans("abc", "abc"), ([], []))

    def test_word_spans_cjk(self):
        sa, sb = checker.word_spans("금액 계산 모듈", "금액 정산 모듈")
        self.assertTrue(sa and sb)


class FileTest(unittest.TestCase):
    def test_binary_rejected(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as fo:
            fo.write(b"GIF89a\x00\x01\x02binary")
            name = fo.name
        try:
            with self.assertRaises(checker.BinaryFileError):
                checker.read_text_file(name)
        finally:
            os.unlink(name)

    def test_too_large(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as fo:
            fo.write(b"x" * 100)
            name = fo.name
        try:
            with self.assertRaises(checker.TooLargeError):
                checker.read_text_file(name, size_limit=10)
        finally:
            os.unlink(name)

    def test_bom_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as fo:
            fo.write("한글".encode("utf-8-sig"))
            name = fo.name
        try:
            text, meta = checker.read_text_file(name)
            self.assertEqual(text, "한글")
            self.assertEqual(meta["encoding"], "utf-8-sig")
        finally:
            os.unlink(name)

    def test_binary_without_nul_rejected(self):
        # Medium: NUL이 없어도 제어 문자 비율이 높으면 바이너리로 거부.
        # 디코딩 자체가 실패해도(UnicodeDecodeError) 읽기 실패로 중단되면 된다.
        # 손실 replace로 0건 비교가 되면 안 된다.
        raw = bytes([(i * 37 + 11) % 251 + 1 for i in range(4000)])
        self.assertNotIn(b"\x00", raw)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as fo:
            fo.write(raw)
            name = fo.name
        try:
            with self.assertRaises((checker.BinaryFileError, UnicodeDecodeError)):
                checker.read_text_file(name)
        finally:
            os.unlink(name)

    def test_valid_sources_accepted(self):
        # 정상 텍스트가 바이너리 휴리스틱에 걸리지 않아야 한다
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fn in ("checker.py", "app.py", "syntax_db.json", "README.md"):
            checker.read_text_file(os.path.join(base, fn))


class DecodeStrictTest(unittest.TestCase):
    """손실 replace 없이 레거시/부분 손상 텍스트의 바이트 차이를 보존한다."""

    def test_different_broken_bytes_remain_different(self):
        tmp = tempfile.mkdtemp()
        p1 = os.path.join(tmp, "a.bin")
        p2 = os.path.join(tmp, "b.bin")
        with open(p1, "wb") as fo:
            fo.write(b"hello\xffworld")
        with open(p2, "wb") as fo:
            fo.write(b"hello\xfeworld")
        try:
            t1, m1 = checker.read_text_file(p1)
            t2, m2 = checker.read_text_file(p2)
            self.assertNotEqual(t1, t2)
            self.assertIn(m1["encoding"], ("cp1252", "latin-1-fallback"))
            self.assertIn(m2["encoding"], ("cp1252", "latin-1-fallback"))
            _, stats = checker.diff_texts([t1], [t2], "a", "b")
            self.assertGreater(stats["changed_lines"], 0)
        finally:
            os.unlink(p1)
            os.unlink(p2)

    def test_bom_corrupted_uses_lossless_fallback(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as fo:
            fo.write(b"\xef\xbb\xbfhello\xffworld")
            name = fo.name
        try:
            text, meta = checker.read_text_file(name)
            self.assertEqual(meta["encoding"], "latin-1-fallback")
            self.assertIn("바이트 차이는 보존", meta["note"])
            self.assertEqual(text, "helloÿworld")
        finally:
            os.unlink(name)

    def test_cp1252_western_text_opens(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as fo:
            fo.write('café — “Müller”'.encode('cp1252'))
            name = fo.name
        try:
            text, meta = checker.read_text_file(name)
            self.assertEqual(text, 'café — “Müller”')
            self.assertEqual(meta["encoding"], "cp1252")
            self.assertTrue(meta["note"])
        finally:
            os.unlink(name)

    def test_shift_jis_japanese_prefers_japanese_decode(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as fo:
            fo.write('こんにちは'.encode('shift_jis'))
            name = fo.name
        try:
            text, meta = checker.read_text_file(name)
            self.assertEqual(text, 'こんにちは')
            self.assertEqual(meta["encoding"], "shift_jis")
            self.assertTrue(meta["note"])
        finally:
            os.unlink(name)

    def test_utf16_corrupted_raises(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as fo:
            fo.write(b"\xff\xfeH\x00i\x00\xff")
            name = fo.name
        try:
            with self.assertRaises((UnicodeDecodeError, checker.BinaryFileError)):
                checker.read_text_file(name)
        finally:
            os.unlink(name)

    def test_valid_cp949_still_ok(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as fo:
            fo.write("한글 테스트".encode("cp949"))
            name = fo.name
        try:
            text, meta = checker.read_text_file(name)
            self.assertEqual(text, "한글 테스트")
            self.assertEqual(meta["encoding"], "cp949")
        finally:
            os.unlink(name)


class ApiCompatTest(unittest.TestCase):
    """Medium: 1.4.2 이전 2값 API 유지 + GUI용 helper 분리."""

    @classmethod
    def setUpClass(cls):
        cls.db = checker.load_db(DB)

    def test_compare_returns_two(self):
        r = checker.compare("a\n", "b\n", "a", "b", self.db, run_checks=False)
        self.assertEqual(len(r), 2)
        f, s = r
        self.assertIn("hunks", s)

    def test_diff_returns_two(self):
        r = checker.diff_texts(["a"], ["b"], "a", "b")
        self.assertEqual(len(r), 2)

    def test_helpers_return_three_and_match(self):
        f, s = checker.compare("a\n", "b\n", "a", "b", self.db, run_checks=False)
        f2, s2, op = checker.compare_with_opcodes(
            "a\n", "b\n", "a", "b", self.db, run_checks=False)
        self.assertEqual(f, f2)
        self.assertEqual(s, s2)
        self.assertTrue(isinstance(op, list))
        g, h = checker.diff_texts(["a"], ["b"], "a", "b")
        g2, h2, op2 = checker.diff_texts_with_opcodes(["a"], ["b"], "a", "b")
        self.assertEqual(g, g2)
        self.assertEqual(h, h2)
        # 구별칭도 동일
        self.assertIs(checker._compare_with_opcodes, checker.compare_with_opcodes)

    def test_side_by_side_opcode_reuse(self):
        a_raw = "l1\nl2\nl3\n"
        b_raw = "l1\nL2\nl3\n"
        a_lines = a_raw.split("\n")[:-1]
        b_lines = b_raw.split("\n")[:-1]
        _, _, op = checker.diff_texts_with_opcodes(a_lines, b_lines, "a", "b")
        rows1 = checker.side_by_side(a_raw, b_raw)
        rows2 = checker.side_by_side(a_raw, b_raw, opcodes=op)
        self.assertEqual(rows1, rows2)

    def test_no_sbsrow_or_global(self):
        self.assertFalse(hasattr(checker, "_SBSRow"))
        self.assertFalse(hasattr(checker, "_SIDE_BY_SIDE_ROWS"))


class BandedValidationTest(unittest.TestCase):
    """Medium: banded 밴드 밖 블록 이동이 4배 부풀려지면 안 된다."""

    def test_block_move_1100_optimal(self):
        n = 20000
        a = [f"L{i:05d}" for i in range(n)]
        b = a[:5000] + a[6100:12000] + a[5000:6100] + a[12000:]
        f, s = checker.diff_texts(a, b, "a", "b")
        self.assertFalse(s["approx"])
        self.assertEqual(s["equal_lines"], 18900)
        self.assertEqual(s["changed_lines"], 2200)
        self.assertEqual(s["hunks"], 2)

    def test_block_move_2000_optimal(self):
        n = 20000
        a = [f"L{i:05d}" for i in range(n)]
        b = a[2000:12000] + a[:2000] + a[12000:]
        f, s = checker.diff_texts(a, b, "a", "b")
        self.assertFalse(s["approx"])
        self.assertEqual(s["changed_lines"], 4000)

    def test_full_replace_still_exact(self):
        for n in (2001, 2100):
            a = [f"row{i}" for i in range(n)]
            b = [f"ROW{i}" for i in range(n)]
            f, s = checker.diff_texts(a, b, "a", "b")
            self.assertEqual(s["hunks"], 1)
            self.assertFalse(s["approx"])

    def test_tried_patience_segment_keeps_banded_result(self):
        # patience로 이미 한 번 분할된 구간에서는 다시 보이는 앵커 때문에
        # 유효한 banded 결과를 버리고 coarse approx로 떨어지면 안 된다.
        old_myers = checker._myers_opcodes
        old_banded = checker._banded_myers_opcodes
        old_patience = checker._patience_split
        try:
            def too_complex(*args, **kwargs):
                raise checker._TooComplex()

            def one_large_replace(aa, bb, *args, **kwargs):
                return [("replace", 0, len(aa), 0, len(bb))]

            def same_gap(a, b, a0, a1, b0, b1):
                return [("gap", a0, a1, b0, b1)]

            checker._myers_opcodes = too_complex
            checker._banded_myers_opcodes = one_large_replace
            checker._patience_split = same_gap
            a = [f"a{i}" for i in range(2101)]
            b = [f"b{i}" for i in range(2102)]
            ops, approx = checker._diff_opcodes(a, b)
            self.assertFalse(approx)
            self.assertEqual(checker._merge_edits(ops),
                             [("replace", 0, len(a), 0, len(b))])
        finally:
            checker._myers_opcodes = old_myers
            checker._banded_myers_opcodes = old_banded
            checker._patience_split = old_patience


class JsRobustnessTest(unittest.TestCase):
    """Low: 극단적 중첩 템플릿에서도 검사가 중단되면 안 된다."""

    def test_deep_nesting_no_crash(self):
        def make_nested(depth):
            s = "x"
            for _ in range(depth):
                s = "`a${" + s + "}`"
            return "var s = " + s + ";"
        for d in (300, 800, 1500):
            code = make_nested(d)
            st = checker._js_states(code)
            self.assertEqual(len(st), len(code))
            # 위생 검사 전체도 죽지 않아야 한다
            db = checker.load_db(DB)
            checker.check_code_hygiene(code, db, "a.js")

    def test_blank_non_code_bytearray(self):
        text = "var x = 1; // hi\n"
        st = checker._js_states(text)
        self.assertIsInstance(st, bytearray)
        out = checker._blank_non_code(text, st)
        self.assertIn("var x", out)
        self.assertNotIn("hi", out.replace(" ", ""))

    def test_trigger_rx(self):
        rx = checker._trigger_rx("py")
        self.assertIsNotNone(rx)
        self.assertIsNotNone(rx.search("x = 'a'\n"))
        self.assertIsNone(rx.search("plain = 1\n"))
        rx2 = checker._trigger_rx("py")
        self.assertIs(rx, rx2)


class V146RegressionTest(unittest.TestCase):
    """v1.4.6: 대소문자 오탐 제거, 열 번호·위치 라벨 수정."""

    @classmethod
    def setUpClass(cls):
        cls.db = checker.load_db(DB)

    def _kinds(self, text, name):
        f, _ = checker.check_typos(text, self.db, name)
        return [x for x in f if x["gkey"][0] == "case"]

    def test_sentence_case_not_flagged(self):
        # 주석/문장 첫 글자 대문자는 오타가 아니다
        self.assertEqual(self._kinds("# The value is wrong. This is a note.\n", "a.py"), [])
        self.assertEqual(self._kinds("This is a plain sentence. Return it.\n", "a.txt"), [])

    def test_lowercase_of_capitalized_type_not_flagged(self):
        # Python의 object/optional처럼 다른 언어 타입명의 소문자 사용
        self.assertEqual(self._kinds("x = object()\ndef f(optional=None): pass\n", "a.py"), [])

    def test_all_caps_constant_not_flagged(self):
        self.assertEqual(self._kinds("NAME = 1\nVERSION = 2\nx = NULL\n", "a.py"), [])

    def test_mixed_case_still_flagged(self):
        k = self._kinds("x = getElementByID\n", "a.js")
        self.assertEqual(len(k), 1)
        self.assertIn("getElementById", k[0]["summary"])

    def test_is_mixed_case(self):
        for tok in ("getElementByID", "LIne", "FileDialog"):
            self.assertTrue(checker._is_mixed_case(tok), tok)
        for tok in ("object", "Object", "The", "NAME", "OS", "x"):
            self.assertFalse(checker._is_mixed_case(tok), tok)

    def test_column_preserved_after_url(self):
        url = "http://example.com/" + "a" * 40
        line = f'u = "{url}"; x = recieve\n'
        f, _ = checker.check_typos(line, self.db, "a.py")
        hit = [x for x in f if "recieve" in x["summary"]]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["column"], line.index("recieve") + 1)

    def test_column_preserved_after_base64(self):
        b64 = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVowMTIzNDU2Nzg5Ky8="
        line = f"d = '{b64}'; y = recieve\n"
        f, _ = checker.check_typos(line, self.db, "a.py")
        hit = [x for x in f if "recieve" in x["summary"]]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["column"], line.index("recieve") + 1)

    def test_location_label_line_then_column(self):
        f, _ = checker.check_typos("a = 1\nb = recieve\n", self.db, "a.py")
        hit = [x for x in f if "recieve" in x["summary"]][0]
        self.assertIn("a.py:2행 5열", hit["detail"])
        self.assertNotIn("2열", hit["detail"])


if __name__ == "__main__":
    unittest.main()


class HarnessTraceTest(unittest.TestCase):
    """Harness integration: algorithm provenance must expose calibration risk."""

    @staticmethod
    def _edit_cost(ops):
        return sum((i2 - i1) + (j2 - j1)
                   for tag, i1, i2, j1, j2 in ops if tag != "equal")

    def test_false_exact_fixture_is_marked_heuristic(self):
        # DIFF-FALSE-EXACT: full Myers exceeds default cap, banded succeeds with
        # a valid but non-optimal path. It must not be advertised as PROVEN_EXACT.
        a = ["A"] * 1000 + ["B"] * 1000 + ["A"] * 1000
        rotated = a[500:] + a[:500]
        b = [("C" if i % 2 == 0 and i < 2600 else x)
             for i, x in enumerate(rotated)]
        _, s, ops, trace = checker.diff_texts_with_trace(a, b, "a", "b")
        _, sx, opsx, tracex = checker.diff_texts_with_trace(a, b, "a", "b", exact=True)
        self.assertFalse(s["approx"])
        self.assertEqual(s["quality_class"], "HEURISTIC")
        self.assertIn("full_myers_exceeded", trace["algorithm_path"])
        self.assertIn("banded_myers", trace["algorithm_path"])
        self.assertGreater(self._edit_cost(ops), self._edit_cost(opsx))
        self.assertEqual(sx["quality_class"], "PROVEN_EXACT")
        self.assertIn("full_myers", tracex["algorithm_path"])

    def test_small_diff_is_deterministic(self):
        _, s, _, trace = checker.diff_texts_with_trace(["a"], ["b"], "a", "b")
        self.assertEqual(s["quality_class"], "DETERMINISTIC")
        self.assertEqual(trace["quality_class"], "DETERMINISTIC")
        self.assertIn("sequence_matcher", trace["algorithm_path"])
