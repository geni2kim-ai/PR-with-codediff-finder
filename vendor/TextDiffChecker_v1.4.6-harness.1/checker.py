#!/usr/bin/env python3
"""두 텍스트 대조(diff) + 코드 오타/문법 검출 로직. GUI 의존성 없음."""
from __future__ import annotations

import bisect
import difflib
import json
import re
import time
from array import array
from pathlib import Path

SIZE_LIMIT = 10 * 1024 * 1024
MAX_GROUPS_PER_FILE = 200   # 파일당 오타 묶음(종류) 상한
MAX_LOCS_PER_GROUP = 5      # 묶음당 표시 위치 수
MAX_FINDINGS_PER_KIND = 60
_REGEX_TIMEOUT = 1.0  # 정규식 단일 finditer 상한(초). 사용자 패턴 ReDoS 방지용.

# Harness integration metadata. This does not change the desktop product version.
HARNESS_API_VERSION = "1.4.6-harness.2"
_DIFF_QUALITY_ORDER = {"PROVEN_EXACT": 0, "DETERMINISTIC": 1, "HEURISTIC": 2, "APPROXIMATE": 3}

def _trace_event(trace, event: str, quality: str | None = None, **data) -> None:
    """Append a machine-readable diff-path event for external evidence collection."""
    if trace is None:
        return
    row = {"event": event}
    if quality is not None:
        row["quality"] = quality
    row.update(data)
    trace.append(row)

def _quality_from_trace(trace: list[dict], approx: bool) -> str:
    if approx:
        return "APPROXIMATE"
    worst = "PROVEN_EXACT"
    for row in trace:
        q = row.get("quality")
        if q in _DIFF_QUALITY_ORDER and _DIFF_QUALITY_ORDER[q] > _DIFF_QUALITY_ORDER[worst]:
            worst = q
    return worst

try:
    import regex as _regex_mod  # timeout 지원. 없으면 stdlib re로 동작(정적 필터만).
    _HAS_REGEX = True
except ImportError:
    _regex_mod = None
    _HAS_REGEX = False


def _compile_rx(pattern: str, flags=0):
    """regex 모듈이 있으면 timeout 지원 컴파일, 없으면 stdlib re."""
    if _HAS_REGEX:
        return _regex_mod.compile(pattern, flags)
    return re.compile(pattern, flags)


class _RxTimeout(Exception):
    """정규식 실행 시간 초과. 호출자는 해당 패턴을 건너뛰고 capped에 기록한다."""
    pass


def _rx_errors() -> tuple:
    """컴파일 실패 예외들. regex 모듈 유무에 따라 달라진다."""
    if _HAS_REGEX:
        return (re.error, _regex_mod.error, TypeError)
    return (re.error, TypeError)


def _collect_matches(rx, target: str, pos: int = 0, endpos=None,
                     timeout: float = _REGEX_TIMEOUT) -> list:
    """finditer 전체 수집. regex 엔진이면 timeout 적용, 초과 시 _RxTimeout.
    stdlib re 폴백에서는 timeout 없이 그대로 수집한다."""
    try:
        if _HAS_REGEX:
            if endpos is None:
                return list(rx.finditer(target, timeout=timeout))
            return list(rx.finditer(target, pos, endpos, timeout=timeout))
        if endpos is None:
            return list(rx.finditer(target))
        return list(rx.finditer(target, pos, endpos))
    except TimeoutError:
        raise _RxTimeout()


def _iter_matches(rx, target: str, timeout: float = _REGEX_TIMEOUT):
    """finditer 지연 순회 + 전체 시간 상한. 60건 상한에서 break하면 나머지는
    만들지 않아 메모리를 쓰지 않는다. 초과 시 _RxTimeout.

    regex 모듈의 timeout 의미론과 무관하게 전체를 bound하기 위해 자체
    deadline도 함께 확인한다(최악 timeout + α).
    """
    if _HAS_REGEX:
        t0 = time.monotonic()
        try:
            it = rx.finditer(target, timeout=timeout)
            while True:
                if time.monotonic() - t0 > timeout:
                    raise _RxTimeout()
                try:
                    m = next(it)
                except StopIteration:
                    return
                yield m
        except TimeoutError:
            raise _RxTimeout()
    else:
        yield from rx.finditer(target)

# diff 내부 상수. 시간 기반 중단은 쓰지 않는다(같은 입력은 항상 같은 결과).
# - 작은 구간: SequenceMatcher 정밀 비교
# - 중간: Myers 전체 탐색 (편집 거리 상한까지)
# - 대각선附近 큰 편집: banded Myers (Ukkonen 밴드)
# - 그 이상: patience 분할 → 그래도 안 되면 근사 표시(approx=True)
_DIFF_SMALL_LIMIT = 2000
_DIFF_FULL_D_CAP = 2000      # 기본 모드 Myers 편집 거리 상한
_DIFF_FULL_D_CAP_EXACT = 3000  # exact=True일 때 상한(느릴 수 있음)
_DIFF_BAND_W = 64            # banded 탐색의 대각선 허용 폭
_DIFF_BAND_D_CAP = 20000
_DIFF_BAND_D_CAP_EXACT = 40000
_DIFF_POSITIONAL_MAX_FRAC = 0.10  # 길이가 같고 이 비율 이하로 다르면 위치 기준 비교
_BANDED_LARGE_REPLACE = 200  # banded 결과 검증 임계. 이 크기 이상 replace가 있으면
# patience로 교차 검증한다(블록 이동 시 밴드 밖 최적 경로를 놓치는 문제 방지).
_NEG_INF = -(1 << 30)  # array('l')용 하한. 유효 x(0 이상)보다 항상 작다.

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SUBWORD_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")
URL_RE = re.compile(r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.]+")
B64_RE = re.compile(r"\b(?=[A-Za-z0-9+/]*\d)(?=[A-Za-z0-9+/]*[+/=])[A-Za-z0-9+/]{40,}={0,2}\b")
STRING_RE = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`")
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
_CPP_RAW_OPEN = re.compile(r'R"([A-Za-z0-9_]{0,16})\(')  # C++ raw string 여는 부분

C_LIKE_EXT = {"c", "h", "cpp", "hpp", "cc", "java", "kt", "kts", "cs",
              "js", "ts", "jsx", "tsx", "mjs", "cjs", "swift", "php", "go", "rs", "scala"}
HASH_COMMENT_EXT = {"py", "sh", "bash", "rb", "pl", "r", "toml", "yaml", "yml", "ini", "cfg"}
# """ 텍스트 블록/멀티라인 문자열을 사용하는 언어
TEXT_BLOCK_EXT = {"java", "kt", "kts", "cs", "swift", "scala", "py", "groovy"}
# 백틱 템플릿 리터럴이 줄을 넘는 언어(JS 템플릿, 셸, 루비 등)
BACKTICK_MULTI_EXT = {"js", "ts", "jsx", "tsx", "mjs", "cjs", "sh", "bash", "rb", "php"}
# ${} 보간을 코드로 해석하는 언어 (JS 템플릿 리터럴)
JS_EXT = {"js", "ts", "jsx", "tsx", "mjs", "cjs"}
# 줄 처음 # 전처리 지시문을 쓰는 언어 (JS 사설 필드 #name과 구분하기 위해 분리).
# php의 # 주석도 여기서 주석으로 둔다.
PREPROC_EXT = {"c", "h", "cpp", "hpp", "cc", "cs", "php"}
# -- 로 줄 주석을 쓰는 언어
DASH_COMMENT_EXT = {"sql"}
# 코드 개념이 있는 확장자. 그 외(txt/md/log/csv/...)는 TODO 등을 원문 그대로 본다.
# json은 주석이 없고 "..." 문자열만 있어 따옴표만 가린다.
CODE_EXTS = C_LIKE_EXT | HASH_COMMENT_EXT | TEXT_BLOCK_EXT | BACKTICK_MULTI_EXT | {"json", "sql"}
# 상태값: 0 코드, 1 문자열, 2 주석
ST_CODE, ST_STR, ST_COM = 0, 1, 2

_INFLECT_SUFFIX = ("ing", "ed", "es", "er", "est", "ly", "s", "d")


class Cancelled(Exception):
    pass


class BinaryFileError(Exception):
    pass


class TooLargeError(Exception):
    pass


class _TooComplex(Exception):
    """Myers 탐색이 예산(시간/편집거리)을 초과. 호출자가 대체 휴리스틱으로 처리."""
    pass


def split_subwords(token: str) -> list[str]:
    return [s for s in SUBWORD_RE.findall(token) if s]


def _is_mixed_case(tok: str) -> bool:
    """camelCase/PascalCase처럼 대소문자가 섞인 토큰이면 True.

    전부 소문자(object), 첫 글자만 대문자(The, Object), 전부 대문자(NAME, NULL)는
    문장 첫 글자·상수 표기·언어별 관례 차이라 오타 신호가 아니므로 제외한다.
    getElementByID 같은 내부 대문자 불일치만 대소문자 검사 대상이다.
    """
    return (tok != tok.lower() and tok != tok.upper()
            and tok != tok.capitalize())


def _is_inflection(a: str, b: str) -> bool:
    """어미 변화(복수·s, 과거·d/ed, ing 등) 관계면 True. 탈락 오타('creat'→'create')는 제외."""
    if a.startswith(b):
        return a[len(b):] in _INFLECT_SUFFIX
    if b.startswith(a):
        return b[len(a):] in _INFLECT_SUFFIX
    return False


def _looks_binary_text(text: str) -> bool:
    """NUL 없는 바이너리 판별. 제어 문자(\\t\\n\\r\\x1b 제외)·DEL·대체문자 비율로 판단.

    텍스트/로그(ANSI 색상 \\x1b 포함 가능)는 통과하고, cp949로 우연히
    디코딩된 랜덤 바이너리(약 10%가 제어 문자)는 거부된다.
    """
    s = text[:8192]
    if not s:
        return False
    bad = 0
    for ch in s:
        if ch in "\t\n\r\x1b":
            continue
        o = ord(ch)
        if o < 32 or o == 127 or ch == "\ufffd":
            bad += 1
    return bad >= 50 and bad / len(s) > 0.05


def _legacy_text_guess(raw: bytes) -> tuple[str, str, str]:
    """UTF-8이 아닌 레거시 텍스트를 손실 없이 가능한 범위에서 읽는다.

    cp949와 Shift-JIS가 모두 성공할 수 있어 간단한 문자군 힌트를 사용한다.
    - Shift-JIS 결과에 히라가나/전각 가타카나가 있으면 일본어 쪽을 우선
    - 그렇지 않고 cp949 결과에 한글이 있으면 cp949 우선
    - 둘 다 애매하면 기존 호환성을 위해 cp949 우선
    이후 cp1252, 마지막은 바이트 1:1 latin-1 폴백이다.
    반환: (text, encoding, note)
    """
    candidates: dict[str, str] = {}
    for enc in ("cp949", "shift_jis"):
        try:
            candidates[enc] = raw.decode(enc)
        except UnicodeDecodeError:
            pass

    cp = candidates.get("cp949")
    sj = candidates.get("shift_jis")
    if cp is not None and sj is not None:
        sj_japanese = sum(1 for ch in sj if "\u3040" <= ch <= "\u30ff")
        cp_hangul = sum(1 for ch in cp if "\uac00" <= ch <= "\ud7a3")
        if sj_japanese > 0:
            return sj, "shift_jis", (
                "UTF-8이 아니어서 Shift-JIS로 추정해 읽었습니다. "
                "레거시 인코딩 자동 판별은 확정적이지 않아 표시를 확인하세요."
            )
        if cp_hangul > 0:
            return cp, "cp949", (
                "UTF-8이 아니어서 cp949로 추정해 읽었습니다. "
                "다른 레거시 인코딩 파일은 표시가 다를 수 있습니다."
            )
        return cp, "cp949", (
            "UTF-8이 아니어서 cp949로 우선 해석했습니다. "
            "레거시 인코딩 자동 판별은 확정적이지 않아 표시를 확인하세요."
        )
    if cp is not None:
        return cp, "cp949", (
            "UTF-8이 아니어서 cp949로 해석했습니다. "
            "다른 레거시 인코딩 파일은 표시가 다를 수 있습니다."
        )
    if sj is not None:
        return sj, "shift_jis", (
            "UTF-8이 아니어서 Shift-JIS로 해석했습니다. "
            "레거시 인코딩 자동 판별은 확정적이지 않아 표시를 확인하세요."
        )
    try:
        text = raw.decode("cp1252")
        return text, "cp1252", (
            "인코딩을 확정할 수 없어 서유럽(cp1252) 텍스트로 해석했습니다. "
            "표시 문자가 원문 인코딩과 다를 수 있습니다."
        )
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
        return text, "latin-1-fallback", (
            "인코딩을 확정할 수 없어 손실 없는 latin-1 폴백으로 읽었습니다. "
            "표시 문자가 원문 인코딩과 다를 수 있으나 바이트 차이는 보존됩니다."
        )


def decode_text_bytes(raw: bytes) -> tuple[str, dict]:
    """Harness-facing byte decoder equivalent to read_text_file without filesystem I/O."""
    size = len(raw)
    meta: dict = {"size": size, "encoding": "", "note": ""}
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        meta["encoding"] = "utf-16"
        meta["note"] = "UTF-16 file"
        text = raw.decode("utf-16")
        if _looks_binary_text(text):
            raise BinaryFileError("binary-looking decoded text")
        return text, meta
    if b"\x00" in raw:
        raise BinaryFileError("NUL byte detected")
    if raw[:3] == b"\xef\xbb\xbf":
        try:
            text = raw.decode("utf-8-sig")
            meta["encoding"] = "utf-8-sig"
        except UnicodeDecodeError:
            text = raw[3:].decode("latin-1")
            meta["encoding"] = "latin-1-fallback"
            meta["note"] = "invalid UTF-8 after BOM; lossless latin-1 fallback"
        if _looks_binary_text(text):
            raise BinaryFileError("binary-looking decoded text")
        return text, meta
    try:
        text = raw.decode("utf-8")
        meta["encoding"] = "utf-8"
    except UnicodeDecodeError:
        text, enc, note = _legacy_text_guess(raw)
        meta["encoding"], meta["note"] = enc, note
    if _looks_binary_text(text):
        raise BinaryFileError("binary-looking decoded text")
    return text, meta


def read_text_file(path: str | Path, size_limit: int = SIZE_LIMIT) -> tuple[str, dict]:
    """파일을 읽어 (정규화된 텍스트, 메타정보)를 돌려준다.

    UTF-8(BOM 포함) → UTF-16 → cp949/Shift-JIS 추정 → cp1252/latin-1 순으로 시도한다.
    바이너리(NUL 포함, UTF-16 BOM 없음)나 크기 초과는 예외를 던진다.
    NUL이 없는 바이너리는 디코딩 뒤 제어 문자 비율로 가려낸다.

    UTF-8/cp949로 해석할 수 없는 레거시 텍스트는 마지막에 바이트를 1:1로
    보존하는 latin-1 계열 폴백으로 연다. errors="replace"는 사용하지 않으므로
    서로 다른 손상 바이트가 동일한 U+FFFD로 합쳐져 차이 0건이 되는 일은 없다.
    폴백을 쓴 경우 meta["note"]에 표시 정확도 주의를 남긴다.
    """
    p = Path(path)
    size = p.stat().st_size
    if size > size_limit:
        raise TooLargeError(f"파일이 너무 큽니다({size:,}B, 상한 {size_limit:,}B).")
    raw = p.read_bytes()
    meta: dict = {"size": size, "encoding": "", "note": ""}
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        meta["encoding"] = "utf-16"
        meta["note"] = "UTF-16 파일입니다. UTF-8이 아니므로 줄 번호만 참고하세요."
        try:
            text = raw.decode("utf-16")
        except UnicodeDecodeError as e:
            raise UnicodeDecodeError(
                e.encoding, e.object, e.start, e.end,
                f"UTF-16 디코딩 실패(손상된 파일 가능): {e.reason}") from e
        if _looks_binary_text(text):
            raise BinaryFileError("텍스트 파일이 아닙니다(바이너리로 보입니다).")
        return text, meta
    if b"\x00" in raw[:8192] or (len(raw) > 8192 and b"\x00" in raw):
        raise BinaryFileError("텍스트 파일이 아닙니다(바이너리로 보입니다).")
    if raw[:3] == b"\xef\xbb\xbf":
        meta["encoding"] = "utf-8-sig"
        meta["note"] = "UTF-8 BOM을 제거했습니다."
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            # BOM은 제거하되 나머지 바이트는 latin-1로 1:1 보존한다.
            # replace를 쓰지 않아 서로 다른 손상 바이트가 같은 문자로 합쳐지지 않는다.
            text = raw[3:].decode("latin-1")
            meta["encoding"] = "latin-1-fallback"
            meta["note"] = (
                "UTF-8 BOM이 있지만 일부 바이트를 UTF-8로 해석할 수 없어 "
                "손실 없는 latin-1 폴백으로 읽었습니다. 표시 문자가 원문 인코딩과 "
                "다를 수 있으나 바이트 차이는 보존됩니다."
            )
        if _looks_binary_text(text):
            raise BinaryFileError("텍스트 파일이 아닙니다(바이너리로 보입니다).")
        return text, meta
    try:
        text = raw.decode("utf-8")
        meta = {**meta, "encoding": "utf-8"}
    except UnicodeDecodeError:
        text, enc, note = _legacy_text_guess(raw)
        meta = {**meta, "encoding": enc, "note": note}
    if _looks_binary_text(text):
        raise BinaryFileError("텍스트 파일이 아닙니다(바이너리로 보입니다).")
    return text, meta


def normalize_text(text: str) -> str:
    text = text.lstrip("\ufeff")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _line_offsets(lines: list[str]) -> list[int]:
    offs = []
    pos = 0
    for s in lines:
        offs.append(pos)
        pos += len(s) + 1
    return offs


def _evil_quantifier(rx: str) -> bool:
    """중첩 수량자 탐지. (a+)+$ 같은 패턴은 매칭 중 기하급수 backtracking을 일으켜
    취소조차 듣지 않고 앱을 멈추게 하므로 로드 단계에서 걸러낸다.

    규칙: 수량자(+, *, {m,n})가 붙은 그룹 (...) 안에 같은 층위의 수량자가 또
    있으면 위험. (a|b)+ 처럼 내부에 수량자가 없는 교대는 선형이라 허용한다.
    문자 클래스([...])와 이스케이프(\\X) 안의 기호는 리터럴로 취급한다.
    """
    s = re.sub(r"\\.", "\x00", rx)  # 이스케이프 제거(의미 없는 자리표시자)
    # 문자 클래스 제거
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == "[":
            j = i + 1
            if j < n and s[j] == "^":
                j += 1
            if j < n and s[j] == "]":
                j += 1
            while j < n and s[j] != "]":
                j += 1
            i = j + 1
        else:
            out.append(s[i])
            i += 1
    s = "".join(out)
    s = re.sub(r"\(\?#.*?\)", "", s)  # (?#...) 주석 제거
    stack: list[bool] = []  # 각 그룹이 수량자를 직접 포함하는지
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "(":
            stack.append(False)
            i += 1
        elif c == ")":
            has_q = stack.pop() if stack else False
            j = i + 1
            if j < len(s) and s[j] in "+*":
                outer, j = True, j + 1
            elif j < len(s) and s[j] == "{" and re.match(r"^\{\d", s[j:]):
                outer = True
            else:
                outer = False
            if outer and has_q:
                return True
            if has_q and stack:
                stack[-1] = True  # 안쪽 수량자를 바깥 그룹에도 전파
            i += 1
        elif c in "+*":
            if stack:
                stack[-1] = True
            i += 1
        elif c == "{" and re.match(r"^\{\d", s[i:]):
            if stack:
                stack[-1] = True
            k = s.find("}", i)
            i = k + 1 if k != -1 else i + 1
        else:
            i += 1
    return False


def _compile_pattern(p: dict, warnings: list[str]) -> dict | None:
    """필수 키·타입 검증 후 정규식 컴파일. 문제가 있으면 경고를 남기고 None."""
    pid = p.get("id", "?")
    bad = [k for k in ("id", "regex", "title", "message")
           if not isinstance(p.get(k), str) or not p.get(k)]
    if bad:
        warnings.append(f"패턴 '{pid}': 필수 키 {', '.join(bad)} 누락/형식 이상 → 제외")
        return None
    p = dict(p)
    ext = p.get("extensions")
    if isinstance(ext, str):
        p["extensions"] = [ext]  # "py" → ["py"] (글자 단위 비교 방지)
    elif ext is not None:
        if not isinstance(ext, list) or not all(isinstance(e, str) for e in ext):
            warnings.append(f"패턴 '{pid}': extensions 형식 이상 → 제외")
            return None
    if "not_if" in p and not isinstance(p["not_if"], str):
        warnings.append(f"패턴 '{pid}': not_if 형식 이상 → not_if만 무시")
        p.pop("not_if")
    if isinstance(p.get("not_if"), str) and _evil_quantifier(p["not_if"]):
        warnings.append(f"패턴 '{pid}': not_if에 중첩 수량자(backtracking 위험) → not_if만 무시")
        p.pop("not_if")
    if "severity" in p and not isinstance(p["severity"], str):
        warnings.append(f"패턴 '{pid}': severity 형식 이상 → '특이사항'으로 대체")
        p.pop("severity")
    # 허용 severity: 문법 주의 / 특이사항 / 오타 의심.
    # '차이점'은 실제 A/B diff 전용이라 사용자 규칙에 허용하지 않는다(필터·이동이 섞임).
    if isinstance(p.get("severity"), str) and p["severity"] not in (
            "문법 주의", "특이사항", "오타 의심"):
        warnings.append(f"패턴 '{pid}': severity '{p['severity']}' 미지원 → '특이사항'으로 대체")
        p.pop("severity")
    if _evil_quantifier(p["regex"]):
        warnings.append(f"패턴 '{pid}': 중첩 수량자(무한 backtracking 위험) → 제외")
        return None
    if "scanner" in p and not isinstance(p["scanner"], str):
        p.pop("scanner")
    if "code_only" in p and not isinstance(p["code_only"], bool):
        p.pop("code_only")
    try:
        rx = _compile_rx(p["regex"], re.MULTILINE)
    except _rx_errors() as e:
        warnings.append(f"패턴 '{pid}' 제외: {e}")
        return None
    if "not_if" in p:
        try:
            not_if = _compile_rx(p["not_if"])
        except _rx_errors() as e:
            warnings.append(f"패턴 '{pid}'의 not_if 제외: {e}")
            not_if = None
    else:
        not_if = None
    return {**p, "compiled": rx, "not_if_compiled": not_if}


def _as_str_list(v, name: str, warnings: list[str]) -> list[str]:
    """문자열 리스트로 강제. 이상하면 경고를 남기고 빈 리스트를 돌려준다."""
    if v is None:
        return []
    if isinstance(v, str):
        warnings.append(f"DB '{name}'이(가) 문자열이라 무시합니다.")
        return []
    if not isinstance(v, list):
        warnings.append(f"DB '{name}' 형식이 이상해 무시합니다.")
        return []
    out = []
    for i, x in enumerate(v):
        if isinstance(x, str):
            out.append(x)
        else:
            warnings.append(f"DB '{name}'[{i}]이(가) 문자열이 아니라 제외합니다.")
    return out


def _as_typo_map(v, name: str, warnings: list[str]) -> dict[str, str]:
    if v is None:
        return {}
    if not isinstance(v, dict):
        warnings.append(f"DB '{name}' 형식이 이상해 무시합니다.")
        return {}
    out = {}
    for k, val in v.items():
        if isinstance(k, str) and isinstance(val, str):
            out[k.lower()] = val
        else:
            warnings.append(f"DB '{name}' 항목({str(k)[:20]})이 문자열이 아니라 제외합니다.")
    return out


def load_db(path: str | Path, extra_path: str | Path | None = None) -> dict:
    """DB 로드 + 스키마 검증 + (있으면) 사용자 DB 병합. 후보 목록을 미리 계산해 둔다.

    기본 DB가 깨지면 ValueError. 사용자 DB 문제는 warnings에 남기고 기본 DB는 유지한다.
    정보성 메시지는 notices에 따로 담는다.
    """
    warnings: list[str] = []
    notices: list[str] = []
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"DB를 열 수 없습니다: {e}")
    if not isinstance(raw, dict):
        raise ValueError("DB 최상위는 객체여야 합니다.")
    identifiers = _as_str_list(raw.get("identifiers"), "identifiers", warnings)
    words = _as_str_list(raw.get("words"), "words", warnings)
    typo_map = _as_typo_map(raw.get("typo_map"), "typo_map", warnings)
    raw_patterns = raw.get("patterns")
    if raw_patterns is None:
        raw_patterns = []
    elif not isinstance(raw_patterns, list):
        warnings.append("DB 'patterns' 형식이 이상해 무시합니다.")
        raw_patterns = []
    if extra_path and Path(extra_path).exists():
        try:
            extra = json.loads(Path(extra_path).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            warnings.append(f"사용자 DB 읽기 실패(기본 DB 유지): {e}")
            extra = None
        if isinstance(extra, dict):
            n_id = _as_str_list(extra.get("identifiers"), "사용자DB identifiers", warnings)
            n_w = _as_str_list(extra.get("words"), "사용자DB words", warnings)
            n_t = _as_typo_map(extra.get("typo_map"), "사용자DB typo_map", warnings)
            n_p = extra.get("patterns")
            if n_p is None:
                n_p = []
            elif not isinstance(n_p, list):
                warnings.append("사용자DB 'patterns' 형식이 이상해 무시합니다.")
                n_p = []
            identifiers += [w for w in n_id if w not in identifiers]
            words += [w for w in n_w if w not in words]
            typo_map.update(n_t)
            raw_patterns = raw_patterns + n_p
            notices.append(f"사용자 DB 병합: 식별자 {len(n_id)}, 단어 {len(n_w)}, "
                           f"오타 {len(n_t)}, 규칙 {len(n_p)}")
        elif extra is not None:
            warnings.append("사용자 DB 무시(최상위가 객체 아님, 기본 DB 유지)")
    if extra_path and Path(extra_path).exists() and not _HAS_REGEX:
        warnings.append("regex 모듈 없음: 사용자 정규식 시간 제한 비활성화 "
                        "(pip install regex 권장)")
    known_exact: set[str] = set(identifiers) | set(words)
    variants: dict[str, set[str]] = {}
    for w in known_exact:
        variants.setdefault(w.lower(), set()).add(w)
    known_lower = {low: next(iter(v)) for low, v in variants.items() if len(v) == 1}
    known_all_lower = set(variants)
    typo = dict(typo_map)
    patterns = []
    for p in raw_patterns:
        if not isinstance(p, dict) or not isinstance(p.get("regex"), str):
            warnings.append(f"형식 이상 패턴 제외: {str(p)[:60]}")
            continue
        c = _compile_pattern(p, warnings)
        if c:
            patterns.append(c)
    cand_by_first: dict[str, list[str]] = {}
    for w in known_all_lower:
        cand_by_first.setdefault(w[:1], []).append(w)
    return {"known_exact": known_exact, "known_lower": known_lower,
            "known_all_lower": known_all_lower, "typo": typo,
            "patterns": patterns, "cand_by_first": cand_by_first,
            "warnings": warnings, "notices": notices}


_TRIGGER_CACHE: dict[str, tuple[str, ...]] = {}
_TRIGGER_RX_CACHE: dict[str, re.Pattern | None] = {}


def _line_triggers(ext: str) -> tuple[str, ...]:
    """해당 확장자에서 상태 변화를 일으킬 수 있는 부분 문자열들(C-speed 사전 검사)."""
    key = ext
    t = _TRIGGER_CACHE.get(key)
    if t is None:
        parts = ["'", '"', "`"]
        if ext in C_LIKE_EXT or ext in DASH_COMMENT_EXT:
            parts.append("/*")
        if ext == "py":
            parts += ["'''", '"""']
        elif ext in TEXT_BLOCK_EXT:
            parts.append('"""')
        if ext in C_LIKE_EXT:
            parts.append("//")
        if ext in HASH_COMMENT_EXT or ext in PREPROC_EXT:
            parts.append("#")
        if ext in DASH_COMMENT_EXT:
            parts.append("--")
        t = tuple(parts)
        _TRIGGER_CACHE[key] = t
    return t


def _trigger_rx(ext: str) -> re.Pattern | None:
    """트리거 부분 문자열들을 한 번에 검사하는 정규식(C-speed).

    종전 any(s in line for s in triggers)는 줄마다 파이썬 제너레이터를
    수천만 번 돌려 대용량 .py에서 병목이었다. 미리 컴파일한 단일
    정규식으로 C 수준에서 한 번에 검사한다.
    """
    rx = _TRIGGER_RX_CACHE.get(ext)
    if rx is None and ext not in _TRIGGER_RX_CACHE:
        triggers = _line_triggers(ext)
        if not triggers:
            _TRIGGER_RX_CACHE[ext] = None
            return None
        # 긴 트리거를 먼저 두어 (''' 보다 '가 먼저 매치돼도 search라 무관하지만
        # 가독성을 위해 정렬). re.escape로 리터럴 처리.
        pat = "|".join(re.escape(s) for s in sorted(triggers, key=len, reverse=True))
        try:
            rx = re.compile(pat)
        except re.error:
            rx = None
        _TRIGGER_RX_CACHE[ext] = rx
    return rx


def _line_states(lines: list[str], ext: str) -> list[list[int]]:
    """각 행의 문자별 상태(0 코드, 1 문자열, 2 주석)를 구한다. JS 계열 제외.

    규칙은 기존 _strip_lines와 동일: 블록 주석·여러 줄 문자열은 줄을 넘어 추적,
    // 주석은 C 계열에서만, # 주석은 HASH 계열에서만, # 전처리 지시문은
    PREPROC_EXT에서만, 닫히지 않은 따옴표는 문자열로 보지 않는다.
    주석 안의 아포스트로피는 문자열 시작으로 짝짓지 않는다(주석을 먼저 판정).
    """
    c_like = ext in C_LIKE_EXT
    hash_c = ext in HASH_COMMENT_EXT
    preproc = ext in PREPROC_EXT
    dash_c = ext in DASH_COMMENT_EXT  # sql의 -- 줄 주석 (/* */도 함께 처리)
    sql_esc = (ext == "sql")  # '' 를 따옴표 이스케이프로 취급
    triples: tuple[str, ...] = ("'''", '"""') if ext == "py" else \
        ('"""',) if ext in TEXT_BLOCK_EXT else ()
    backtick_multi = ext in BACKTICK_MULTI_EXT
    cpp_raw = ext in {"c", "h", "cpp", "hpp", "cc"}  # R"delim(...)delim"
    cs_verb = (ext == "cs")  # @"..." / $@"..." / @$"..." ("" 이스케이프)
    trig_rx = _trigger_rx(ext)
    out: list[list[int]] = []
    multi: str | None = None  # "*/"이면 주석 계속, '@"'이면 verbatim 계속, 그 외면 문자열 계속
    for line in lines:
        n = len(line)
        st = [ST_CODE] * n
        i = 0
        if multi is None and (trig_rx is None or trig_rx.search(line) is None):
            # 트리거 문자 자체가 없으면 전 행 코드 확정(C-speed, 단일 정규식)
            out.append(st)
            continue
        if multi == '@"':
            # C# verbatim 계속: "" 쌍을 건너뛰고 홑따옴표에서 닫는다
            j = 0
            closed = -1
            while True:
                j = line.find('"', j)
                if j < 0:
                    break
                if line[j + 1:j + 2] == '"':
                    j += 2
                    continue
                closed = j
                break
            if closed < 0:
                out.append([ST_STR] * n)
                continue
            end = closed + 1
            for k in range(end):
                st[k] = ST_STR
            i = end
            multi = None
        elif multi is not None:
            j = line.find(multi)
            if j < 0:
                out.append([ST_STR if multi != "*/" else ST_COM] * n)
                continue
            end = j + len(multi)
            fill = ST_COM if multi == "*/" else ST_STR
            for k in range(end):
                st[k] = fill
            i = end
            multi = None
        while i < n:
            if (c_like or dash_c) and line.startswith("/*", i):
                j = line.find("*/", i + 2)
                if j < 0:
                    for k in range(i, n):
                        st[k] = ST_COM
                    multi = "*/"
                    break
                for k in range(i, j + 2):
                    st[k] = ST_COM
                i = j + 2
            elif any(line.startswith(t, i) for t in triples):
                t = next(t for t in triples if line.startswith(t, i))
                j = line.find(t, i + 3)
                if j < 0:
                    for k in range(i, n):
                        st[k] = ST_STR
                    multi = t
                    break
                for k in range(i, j + 3):
                    st[k] = ST_STR
                i = j + 3
            elif c_like and line.startswith("//", i):
                for k in range(i, n):
                    st[k] = ST_COM
                break
            elif dash_c and line.startswith("--", i):
                for k in range(i, n):
                    st[k] = ST_COM
                break
            elif hash_c and line[i] == "#":
                for k in range(i, n):
                    st[k] = ST_COM
                break
            elif preproc and line[i] == "#" and not line[:i].strip():
                for k in range(i, n):
                    st[k] = ST_COM
                break
            elif cpp_raw and line.startswith('R"', i):
                m = _CPP_RAW_OPEN.match(line, i)
                if m is None:
                    i += 1  # R은 일반 문자. 뒤의 "는 다음 루프에서 문자열로 처리
                    continue
                closer = ")" + m.group(1) + '"'
                j = line.find(closer, m.end())
                if j < 0:
                    for k in range(i, n):
                        st[k] = ST_STR
                    multi = closer  # )delim" 그대로 찾으면 정확히 닫힌다
                    break
                for k in range(i, j + len(closer)):
                    st[k] = ST_STR
                i = j + len(closer)
            elif cs_verb and (line.startswith('@"', i) or line.startswith('$@"', i)
                              or line.startswith('@$"', i)):
                # C# verbatim 문자열 전체를 문자열로 둔다. $ 보간 안의 코드까지
                # 뭉뚱그리므로 거짓 양성은 없지만 일부 진짜 코드는 놓친다.
                j = line.find('"', i) + 1  # 여는 따옴표 다음부터 탐색
                closed = -1
                while True:
                    j = line.find('"', j)
                    if j < 0:
                        break
                    if line[j + 1:j + 2] == '"':
                        j += 2
                        continue
                    closed = j
                    break
                if closed < 0:
                    for k in range(i, n):
                        st[k] = ST_STR
                    multi = '@"'
                    break
                for k in range(i, closed + 1):
                    st[k] = ST_STR
                i = closed + 1
            elif line[i] in "'\"`":
                q = line[i]
                j = i + 1
                closed = False
                while j < n:
                    if line[j] == "\\":
                        j += 2
                        continue
                    if sql_esc and q == "'" and line[j] == "'" and j + 1 < n and line[j + 1] == "'":
                        j += 2  # sql의 '' 이스케이프
                        continue
                    if line[j] == q:
                        closed = True
                        break
                    j += 1
                if not closed:
                    if q == "`" and backtick_multi:
                        for k in range(i, n):
                            st[k] = ST_STR
                        multi = "`"
                        break
                    i += 1  # 닫히지 않은 따옴표는 문자열로 보지 않는다
                    continue
                for k in range(i, j + 1):
                    st[k] = ST_STR
                i = j + 1
            else:
                i += 1
        out.append(st)
    return out


def _js_states(text: str) -> bytearray:
    """JS 계열 전체 텍스트의 문자별 상태. 템플릿 ${} 내부는 코드로 재귀 처리한다.

    - //, /* */ → 주석. '..', ".." → 문자열(줄 안 닫히면 코드 취급).
    - 백틱 템플릿: 텍스트는 문자열, ${} 안은 코드(중첩 템플릿·문자열·주석 포함).
    - 정규식 리터럴(/.../)은 구분하지 않는다(알려진 제한, README 참고).
    반환값은 bytearray로 메모리 효율을 높인다.
    극단적 중첩 템플릿(수백 단계)은 RecursionError로 검사가 중단되지 않게
    보수적으로 코드로 취급하고 반환한다.
    """
    n = len(text)
    st = bytearray([ST_CODE]) * n
    if ("/" not in text and "'" not in text and '"' not in text
            and "`" not in text):
        # 트리거 문자 자체가 없으면(# ! 제외) 전 구간 코드 확정(C-speed)
        if text.startswith("#!"):
            j = text.find("\n", 0)
            if j < 0:
                j = n
            for k in range(0, j):
                st[k] = ST_COM
        return st
    try:
        return _js_states_inner(text, st)
    except RecursionError:
        # 중첩이 너무 깊으면 지금까지 계산된 상태를 유지하고 나머지는
        # 코드로 두어 검사를 계속한다(거짓 양성 가능, 중단보다는 안전).
        return st


def _js_states_inner(text: str, st: bytearray) -> bytearray:
    """_js_states 본체. 재귀 깊이 초과 시 호출자가 보수적으로 복구한다."""
    n = len(text)
    i = 0
    if text.startswith("#!"):
        j = text.find("\n", 0)
        if j < 0:
            j = n
        for k in range(0, j):
            st[k] = ST_COM
        i = j
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            if j < 0:
                j = n
            for k in range(i, j):
                st[k] = ST_COM
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                st[k] = ST_COM
            i = j
        elif c in "'\"":
            j = i + 1
            closed = False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == c:
                    closed = True
                    break
                j += 1
            if closed:
                for k in range(i, j + 1):
                    st[k] = ST_STR
                i = j + 1
            else:
                i += 1
        elif c == "`":
            i = _js_template(text, i, n, st)
        else:
            i += 1
    return st


def _js_template(text: str, i: int, n: int, st) -> int:
    """text[i] == '`'인 템플릿 리터럴을 처리하고 리터럴 다음 인덱스를 돌려준다."""
    st[i] = ST_STR
    j = i + 1
    seg = j
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":
            for k in range(seg, j + 1):
                st[k] = ST_STR
            return j + 1
        if c == "$" and j + 1 < n and text[j + 1] == "{":
            for k in range(seg, j):
                st[k] = ST_STR
            j = _js_interp(text, j + 2, n, st)
            seg = j
            continue
        j += 1
    for k in range(seg, n):
        st[k] = ST_STR
    return n


def _js_interp(text: str, i: int, n: int, st) -> int:
    """'${' 다음부터 대응되는 '}' 다음 인덱스를 돌려준다. 내부는 코드로 둔다."""
    depth = 1
    while i < n:
        c = text[i]
        if c == "`":
            i = _js_template(text, i, n, st)
            continue
        if c in "'\"":
            j = i + 1
            closed = False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == c:
                    closed = True
                    break
                j += 1
            if closed:
                for k in range(i, j + 1):
                    st[k] = ST_STR
                i = j + 1
            else:
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            if j < 0:
                j = n
            for k in range(i, j):
                st[k] = ST_COM
            i = j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                st[k] = ST_COM
            i = j
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _strip_lines(lines: list[str], ext: str) -> list[str]:
    """문자열·주석을 공백으로 덮어 코드만 남긴다. 길이와 줄 수를 유지해 좌표를 보존한다.

    JS 계열은 템플릿 보간까지 아는 전체 스캐너를 쓰고, 그 외는 행 단위 상태로
    코드가 아닌 부분을 지운다.
    """
    if ext in JS_EXT:
        return _blank_non_code("\n".join(lines), _js_states("\n".join(lines))).split("\n")
    states = _line_states(lines, ext)
    return ["".join(ch if s == ST_CODE else " " for ch, s in zip(line, st))
            for line, st in zip(lines, states)]


def _blank_non_code(text: str, states) -> str:
    """states는 list[int] 또는 bytearray 가능. bytearray는 그대로 순회한다.

    종전처럼 list(states)로 복제하면 bytearray+list가 동시에 존재해
    피크 메모리가 오히려 증가하므로 복사하지 않는다.
    """
    return "".join(ch if s == ST_CODE else " " for ch, s in zip(text, states))


def _scan_code_lines(text: str, ext: str) -> str:
    if ext in JS_EXT:
        return _blank_non_code(text, _js_states(text))
    return "\n".join(_strip_lines(text.split("\n"), ext))


def _todo_hits(lines: list[str], ext: str) -> list[int]:
    """TODO/FIXME가 있는 행 번호(1-based) 목록.

    코드 확장자: 주석 구간 안에서만 찾는다. 식별자(TODO = 1)나 문자열 안의
    언급(msg = "TODO: ...")은 제외하고, 주석 안 아포스트로피(// it's ...)
    에도 흔들리지 않는다. 비코드 확장자(txt/md/...)는 원문 전체에서 찾는다.
    """
    hits: list[int] = []
    if ext in JS_EXT:
        states = _js_states("\n".join(lines))
        pos = 0
        for i, line in enumerate(lines, 1):
            for m in TODO_RE.finditer(line):
                a = pos + m.start()
                if states[a] == ST_COM:
                    hits.append(i)
                    break
            pos += len(line) + 1
        return hits
    if ext not in CODE_EXTS:
        return [i for i, line in enumerate(lines, 1) if TODO_RE.search(line)]
    for i, (line, st) in enumerate(zip(lines, _line_states(lines, ext)), 1):
        for m in TODO_RE.finditer(line):
            if st[m.start()] == ST_COM:
                hits.append(i)
                break
    return hits


def _if_assign_offsets(code: str) -> list[int]:
    """if (...) 구간의 대입(=) 위치를 찾는다. 중첩 괄호를 셈.

    - 깊이 0의 bare '=' → 플래그
    - ') =' 형태(호출 결과에 대입) → 플래그
    - 호출 인자의 keyword '=' (foo(x=1)) → 제외
    """
    hits: list[int] = []
    for m in re.finditer(r"\bif\b", code):
        j = m.end()
        while j < len(code) and code[j] in " \t":
            j += 1
        if j >= len(code) or code[j] != "(":
            continue
        depth = 0
        k = j
        span_start = j + 1
        span_end = -1
        while k < len(code):
            c = code[k]
            if c == "(" or c == "[":
                depth += 1
            elif c == ")" or c == "]":
                depth -= 1
                if depth == 0:
                    span_end = k
                    break
            k += 1
        if span_end < 0:
            continue
        inner = code[span_start:span_end]
        d = 0
        for t, ch in enumerate(inner):
            if ch == "(" or ch == "[":
                d += 1
            elif ch == ")" or ch == "]":
                d -= 1
            elif ch == "=":
                prev = inner[t - 1] if t > 0 else ""
                nxt = inner[t + 1] if t + 1 < len(inner) else ""
                if prev in "=!<>":
                    continue
                if nxt == "=" or nxt == ">":
                    continue
                if d == 0:
                    hits.append(span_start + t)
                elif re.search(r"\)\s*$", inner[:t]):
                    hits.append(span_start + t)
    return hits


def _blank_match(m) -> str:
    return " " * (m.end() - m.start())


def check_typos(text: str, db: dict, filename: str,
                progress=None, cancel=None) -> tuple[list[dict], dict]:
    """오타 검출. 같은 종류는 한 건으로 묶어 위치를 함께 보여준다.

    그룹 키: ('case', 토큰, 표준) / ('typo', 부분, 정정) / ('fuzzy', 부분, 제안).
    occurrences=전체 발생 횟수, groups=묶음 수.
    """
    known_exact = db["known_exact"]
    known_lower = db["known_lower"]
    known_all_lower = db["known_all_lower"]
    typo = db["typo"]
    cand_by_first = db["cand_by_first"]
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    memo: dict[str, str | None] = {}
    truncated = False
    occurrences = 0
    lines = text.split("\n")
    total = len(lines)

    def add(gkey: tuple, lineno: int, col: int, summary: str, detail_head: str):
        nonlocal truncated
        g = groups.get(gkey)
        if g is None:
            if len(groups) >= MAX_GROUPS_PER_FILE:
                truncated = True
                return False
            groups[gkey] = {"count": 0, "locs": [], "first_line": lineno,
                            "summary": summary, "detail_head": detail_head}
            order.append(gkey)
            g = groups[gkey]
        g["count"] += 1
        if len(g["locs"]) < MAX_LOCS_PER_GROUP:
            g["locs"].append((lineno, col))
        return True

    for lineno, raw_line in enumerate(lines, 1):
        if lineno % 500 == 0:
            if cancel is not None and cancel.is_set():
                raise Cancelled("사용자 취소")
            if progress is not None:
                progress("typo", lineno, total)
        if truncated:
            break
        # URL·base64는 같은 길이의 공백으로 가려 뒤따르는 토큰의 열 번호를 보존한다.
        line = URL_RE.sub(_blank_match, raw_line)
        line = B64_RE.sub(_blank_match, line)
        for n_tok, m in enumerate(IDENT_RE.finditer(line)):
            if n_tok % 1024 == 0 and cancel is not None and cancel.is_set():
                # 한 줄이 수 MB여도 토큰 단위로 취소를 확인한다
                raise Cancelled("사용자 취소")
            tok = m.group(0)
            col = m.start() + 1
            if tok in known_exact:
                continue
            low = tok.lower()
            if low in known_lower and tok not in known_exact and _is_mixed_case(tok):
                canon = known_lower[low]
                occurrences += 1
                if not add(("case", tok, canon), lineno, col,
                           f"'{tok}' -> 대소문자 확인 (표준: {canon})",
                           f"식별자 '{tok}'의 대소문자가 표준 '{canon}'와 다릅니다."):
                    truncated = True
                    break
            if low in known_all_lower or low in typo.values():
                continue
            if low in typo:
                # 전체 토큰이 오타표에 있으면 부분단어보다 우선한다
                # (예: 사용자 DB의 "tehName" → "theName")
                occurrences += 1
                if not add(("typo", low, typo[low]), lineno, col,
                           f"'{tok}' -> '{typo[low]}' 오타 의심",
                           f"'{tok}'은(는) '{typo[low]}'의 오타일 가능성이 큽니다."):
                    truncated = True
                    break
                continue
            for sub in split_subwords(tok):
                slow = sub.lower()
                if len(slow) < 2:
                    continue
                if slow in typo:
                    occurrences += 1
                    if not add(("typo", slow, typo[slow]), lineno, col,
                               f"'{tok}' (부분 '{sub}') -> '{typo[slow]}' 오타 의심",
                               f"식별자 안의 '{sub}'은(는) '{typo[slow]}'의 오타일 가능성이 큽니다."):
                        truncated = True
                        break
                    break
                if len(slow) >= 4 and slow not in known_all_lower:
                    if slow in memo:
                        sug_disp = memo[slow]
                    else:
                        pool = [c for c in cand_by_first.get(slow[:1], [])
                                if abs(len(c) - len(slow)) <= 2]
                        sug = difflib.get_close_matches(slow, pool, n=1, cutoff=0.9) if pool else []
                        if sug and sug[0] != slow and not _is_inflection(slow, sug[0]):
                            s0 = sug[0]
                            sug_disp = s0 if s0 in known_exact else known_lower.get(s0, s0)
                        else:
                            sug_disp = None
                        memo[slow] = sug_disp
                    if sug_disp:
                        occurrences += 1
                        if not add(("fuzzy", slow, sug_disp), lineno, col,
                                   f"'{tok}' (부분 '{sub}') -> '{sug_disp}' 유사어 존재",
                                   f"식별자 안의 '{sub}'과(와) 유사한 표준 '{sug_disp}'이(가) 있습니다. "
                                   f"오타인지, 의도한 새 이름인지 확인하세요."):
                            truncated = True
                            break
                        break
            if truncated:
                break
    out: list[dict] = []
    for gkey in sorted(order, key=lambda k: groups[k]["first_line"]):
        g = groups[gkey]
        n = g["count"]
        summary = g["summary"] + (f" (총 {n}곳)" if n > 1 else "")
        locs = "\n".join(f"  - {filename}:{ln}행 {c}열" for ln, c in g["locs"])
        if n > len(g["locs"]):
            locs += f"\n  ... 외 {n - len(g['locs'])}곳"
        out.append({"category": "오타 의심", "file": filename,
                    "line": g["first_line"], "column": g["locs"][0][1],
                    "token": "", "gkey": gkey,
                    "summary": summary,
                    "detail": f"{g['detail_head']}\n발생 위치:\n{locs}"})
    if progress is not None:
        progress("typo", total, total)
    return out, {"truncated": truncated, "scanned_lines": total,
                 "occurrences": occurrences, "groups": len(groups)}


def check_code_hygiene(text: str, db: dict, filename: str,
                       progress=None, cancel=None) -> tuple[list[dict], dict]:
    out: list[dict] = []
    capped: list[str] = []
    # NOTE: 정의된 이름 수집 루틴(collect_defined)은 제거됨.
    # 정의된 이름도 부분단어 기준으로 검사한다(정의 시점 오타 검출). README 참고.
    lines = text.split("\n")
    offsets = _line_offsets(lines)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    # 상태는 한 번만 계산해 코드 검사와 TODO 검사가 공유한다.
    # 종전에는 _scan_code_lines(내부 _line_states/_js_states 1회) +
    # _todo_hits(내부 _line_states/_js_states 1회)로 같은 텍스트를 두 번
    # 스캔해 대용량 .py가 2배 느려졌다.
    js_states = None
    line_states: list[list[int]] | None = None
    if ext in JS_EXT:
        js_states = _js_states(text)
        code_text = _blank_non_code(text, js_states)
    elif ext in CODE_EXTS:
        line_states = _line_states(lines, ext)
        code_text = "\n".join(
            "".join(ch if s == ST_CODE else " " for ch, s in zip(line, st))
            for line, st in zip(lines, line_states))
    else:
        code_text = _scan_code_lines(text, ext)

    def lineno_at(pos: int) -> int:
        return bisect.bisect_right(offsets, pos)

    for p in db["patterns"]:
        if cancel is not None and cancel.is_set():
            raise Cancelled("사용자 취소")
        allowed = p.get("extensions")
        if allowed and ext not in [e.lower() for e in allowed if isinstance(e, str)]:
            continue
        target = code_text if p.get("code_only") else text
        not_if = p.get("not_if_compiled")
        hits = 0
        if p.get("scanner") == "if_assign":
            for pos in _if_assign_offsets(code_text):
                ln = lineno_at(pos)
                out.append({"category": p.get("severity", "특이사항"), "file": filename,
                            "line": ln, "column": 0, "token": "",
                            "summary": f"[{p['title']}] {lines[ln - 1].strip()[:70]}",
                            "detail": f"{filename}:{ln}\n규칙: {p['title']}\n{p['message']}\n"
                                      f"발견: {lines[ln - 1].strip()[:200]}"})
                hits += 1
                if hits >= MAX_FINDINGS_PER_KIND:
                    capped.append(p.get("id", "?"))
                    break
            continue
        try:
            for m in _iter_matches(p["compiled"], target):
                ln = lineno_at(m.start())
                if not_if:
                    # 매치와 겹치는 not_if만 제외한다.
                    # (예: "a != null && b == c"에서 != null은 제외, b == c는 유지)
                    skip = False
                    lo = max(0, m.start() - 40)
                    hi = min(len(target), m.end() + 40)
                    try:
                        near = _collect_matches(not_if, target, lo, hi)
                    except _RxTimeout:
                        near = []  # 시간 초과면 제외하지 않고 보고한다
                    for nm in near:
                        if nm.start() < m.end() and m.start() < nm.end():
                            skip = True
                            break
                    if skip:
                        continue
                src = lines[ln - 1].strip()
                hit = m.group(0).strip()
                extra = f"\n매치: {hit[:100]}" if hit and hit not in src else ""
                out.append({"category": p.get("severity", "특이사항"), "file": filename,
                            "line": ln, "column": 0, "token": "",
                            "summary": f"[{p['title']}] {src[:70]}",
                            "detail": f"{filename}:{ln}\n규칙: {p['title']}\n{p['message']}\n"
                                      f"발견: {src[:200]}{extra}"})
                hits += 1
                if hits >= MAX_FINDINGS_PER_KIND:
                    capped.append(p.get("id", "?"))
                    break
        except _RxTimeout:
            # 실행 시간 초과(ReDoS급 패턴): 나머지를 만들지 않고 상한 도달로 기록
            capped.append(f"{p.get('id', '?')}(시간초과)")
        if cancel is not None and cancel.is_set():
            raise Cancelled("사용자 취소")
    tabbed = [i + 1 for i, l in enumerate(lines) if l.startswith("\t")]
    spaced = [i + 1 for i, l in enumerate(lines) if l.startswith("    ")]
    if tabbed and spaced:
        ti, si = 0, 0
        region = None
        while ti < len(tabbed) and si < len(spaced):
            if abs(tabbed[ti] - spaced[si]) <= 10:
                region = (min(tabbed[ti], spaced[si]), max(tabbed[ti], spaced[si]))
                break
            if tabbed[ti] < spaced[si]:
                ti += 1
            else:
                si += 1
        if region is not None:
            out.append({"category": "문법 주의", "file": filename, "line": region[0],
                        "column": 1, "token": "",
                        "summary": f"들여쓰기 혼용(인접 {region[0]}~{region[1]}행): 탭 {len(tabbed)}행 / 스페이스 {len(spaced)}행",
                        "detail": f"{filename} {region[0]}~{region[1]}행 근처에서 탭과 스페이스 들여쓰기가 섞여 있습니다.\n"
                                  f"탭 시작 행 예: {tabbed[:5]}\n스페이스 시작 행 예: {spaced[:5]}\n"
                                  f"같은 블록 안의 혼용은 Python 등에서 문법 오류의 원인이 됩니다."})
    todo_n = 0
    # 주석 안의 TODO만 본다(식별자·문자열 제외). 비코드 확장자는 원문 전체.
    # 위에서 계산한 상태를 재사용한다(이중 스캔 방지).
    if js_states is not None:
        todo_list: list[int] = []
        pos = 0
        for idx, line in enumerate(lines, 1):
            for m in TODO_RE.finditer(line):
                if js_states[pos + m.start()] == ST_COM:
                    todo_list.append(idx)
                    break
            pos += len(line) + 1
    elif line_states is not None:
        todo_list = []
        for idx, (line, st) in enumerate(zip(lines, line_states), 1):
            for m in TODO_RE.finditer(line):
                if st[m.start()] == ST_COM:
                    todo_list.append(idx)
                    break
    else:
        todo_list = _todo_hits(lines, ext)
    for i in todo_list:
        l = lines[i - 1]
        out.append({"category": "특이사항", "file": filename, "line": i,
                    "column": 0, "token": "",
                    "summary": f"미완성 표시: {l.strip()[:70]}",
                    "detail": f"{filename}:{i}\n{l.strip()[:300]}\n미완성 표시 주석이 남아 있습니다."})
        todo_n += 1
        if todo_n >= 20:
            capped.append("todo")
            break
    long_n = 0
    for i, l in enumerate(lines, 1):
        if len(l) > 200:
            out.append({"category": "특이사항", "file": filename, "line": i,
                        "column": 201, "token": "",
                        "summary": f"장문 행 ({len(l)}자)",
                        "detail": f"{filename}:{i}\n행 길이가 {len(l)}자입니다. 가독성을 위해 분할을 검토하세요."})
            long_n += 1
            if long_n >= 20:
                capped.append("long-line")
                break
    if progress is not None:
        progress("hygiene", 1, 1)
    return out, {"capped": capped}


def _mark_words(a: str, b: str, side: str) -> str:
    wa, wb = a.split(), b.split()
    parts: list[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, wa, wb).get_opcodes():
        if tag == "equal":
            parts += wa[i1:i2] if side == "-" else wb[j1:j2]
        elif side == "-":
            if i1 != i2:
                parts.append("[-" + " ".join(wa[i1:i2]) + "-]")
        else:
            if j1 != j2:
                parts.append("[+" + " ".join(wb[j1:j2]) + "+]")
    return " ".join(parts)


def _inline_block(a_seg: list[str], b_seg: list[str]) -> list[str]:
    out: list[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a_seg, b_seg).get_opcodes():
        if tag == "equal":
            out += ["  " + s for s in a_seg[i1:i2][:5]]
        else:
            for k in range(max(i2 - i1, j2 - j1)):
                a_l = a_seg[i1 + k] if i1 + k < i2 else ""
                b_l = b_seg[j1 + k] if j1 + k < j2 else ""
                out.append("- " + _mark_words(a_l, b_l, "-"))
                out.append("+ " + _mark_words(a_l, b_l, "+"))
    return out


def _new_row(n: int, fill: int = _NEG_INF) -> array:
    return array("l", [fill]) * n


def _myers_opcodes(a: list, b: list, cancel=None, d_cap: int = _DIFF_FULL_D_CAP) -> list[tuple]:
    """Myers O(ND) diff. 정수 ID 리스트 전용. 결과를 difflib opcode 형식으로 돌려준다.

    탐색 기록은 array('l')에 모아 메모리 사용을 고정한다(D=2000 → 최대 약 32MB).
    편집 거리가 상한을 넘으면 _TooComplex를 던진다(시간이 아닌 거리 기준이라
    같은 입력은 항상 같은 결과를 낸다). 취소는 매 64 D마다 확인한다.
    """
    n, m = len(a), len(b)
    if n == 0:
        return [("insert", 0, 0, 0, m)] if m else []
    if m == 0:
        return [("delete", 0, n, 0, 0)]
    off = n + m + 1
    v = _new_row(2 * off + 1)
    v[1 + off] = 0  # V[1] = 0
    trace: list[array] = []
    for d in range(n + m + 1):
        if (d & 63) == 0 and cancel is not None and cancel.is_set():
            raise Cancelled("사용자 취소")
        cur = _new_row(2 * d + 3, 0)
        co = d + 1  # cur의 k=0 위치
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v[k - 1 + off] < v[k + 1 + off]):
                x = v[k + 1 + off]
            else:
                x = v[k - 1 + off] + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            cur[k + co] = x
            if x >= n and y >= m:
                trace.append(cur)
                return _myers_backtrack(trace, n, m)
        trace.append(cur)
        v, off = cur, co  # 다음 반복의 V로 교체 (오프셋도 함께)
        if d >= d_cap:
            raise _TooComplex()
    raise _TooComplex()  # 도달 불가 (안전망)


def _myers_backtrack(trace: list[array], n: int, m: int) -> list[tuple]:
    """탐색 기록을 거슬러 올라가 opcode 목록으로 변환한다."""
    segs: list[tuple] = []  # (kind, ax, ay, bx, by) 역순
    x, y = n, m
    base = [d + 1 for d in range(len(trace))]  # trace[d]의 k=0 오프셋
    for d in range(len(trace) - 1, 0, -1):
        prev = trace[d - 1]
        po = base[d - 1]
        k = x - y
        if k == -d or (k != d and prev[k - 1 + po] < prev[k + 1 + po]):
            pk = k + 1  # 아래로 (삽입)
        else:
            pk = k - 1  # 오른쪽으로 (삭제)
        px = prev[pk + po]
        py = px - pk
        if pk == k + 1:
            sx, sy = px, py + 1
            edit = ("insert", px, sx, py, sy)
        else:
            sx, sy = px + 1, py
            edit = ("delete", px, sx, py, sy)
        if (x, y) != (sx, sy):
            segs.append(("equal", sx, x, sy, y))
        segs.append(edit)
        x, y = px, py
    if (x, y) != (0, 0):
        segs.append(("equal", 0, x, 0, y))
    segs.reverse()
    # 길이 0 구간 제거
    ops = [s for s in segs if s[1] != s[2] or s[3] != s[4]]
    # 인접한 delete+insert는 difflib의 replace와 같은 형태로 병합
    merged: list[tuple] = []
    for kind, a0, a1, b0, b1 in ops:
        if (merged and merged[-1][0] in ("delete", "insert")
                and kind in ("delete", "insert") and kind != merged[-1][0]
                and merged[-1][2] == a0 and merged[-1][4] == b0):
            merged[-1] = ("replace", merged[-1][1], a1, merged[-1][3], b1)
        else:
            merged.append((kind, a0, a1, b0, b1))
    return merged


def _banded_myers_opcodes(a: list, b: list, cancel=None,
                          width: int = _DIFF_BAND_W,
                          d_cap: int = _DIFF_BAND_D_CAP) -> list[tuple]:
    """Ukkonen 밴드 Myers. 최적 경로가 허용 밴드 안에 있을 때만 성공한다.

    밴드는 시작 대각선(k=0)과 끝 대각선(k=n-m)을 모두 품는
    [min(0,kend)-width, max(0,kend)+width] 구간이다. 흩어진 수정이 많은
    반복행 파일(삽입·삭제로 인한 drift가 작음)을 정확히 처리한다.
    밴드를 벗어나거나 너무 넓으면 _TooComplex. trace도 array라 메모리 고정.
    """
    n, m = len(a), len(b)
    if n == 0:
        return [("insert", 0, 0, 0, m)] if m else []
    if m == 0:
        return [("delete", 0, n, 0, 0)]
    kend = n - m
    blo = min(0, kend) - width
    bhi = max(0, kend) + width
    if bhi - blo + 1 > 1024:
        raise _TooComplex()  # drift가 너무 크면 밴드 탐색을 포기 (결정적)
    size = bhi - blo + 1
    v = _new_row(size)
    if blo <= 1 <= bhi:
        v[1 - blo] = 0  # V[1] = 0
    trace: list[array] = []
    for d in range(d_cap + 1):
        if (d & 63) == 0 and cancel is not None and cancel.is_set():
            raise Cancelled("사용자 취소")
        cur = _new_row(size)
        klo = max(-d, blo)
        khi = min(d, bhi)
        if ((klo & 1) != (d & 1)):
            klo += 1
        if ((khi & 1) != (d & 1)):
            khi -= 1
        if klo > khi:
            raise _TooComplex()
        for k in range(klo, khi + 1, 2):
            left = v[k - 1 - blo] if k - 1 >= blo else _NEG_INF
            right = v[k + 1 - blo] if k + 1 <= bhi else _NEG_INF
            if k == -d or (k != d and left < right):
                x = right
            else:
                x = left + 1 if left != _NEG_INF else _NEG_INF
            y = x - k
            if x >= 0:
                while x < n and y < m and a[x] == b[y]:
                    x += 1
                    y += 1
            cur[k - blo] = x
            if x >= n and y >= m:
                trace.append(cur)
                return _banded_backtrack(trace, n, m, blo, bhi)
        trace.append(cur)
        v = cur
    raise _TooComplex()


def _banded_backtrack(trace: list[array], n: int, m: int,
                      blo: int, bhi: int) -> list[tuple]:
    def _get(row: array, k: int) -> int:
        if k < blo or k > bhi:
            raise _TooComplex()
        v = row[k - blo]
        if v == _NEG_INF:
            raise _TooComplex()
        return v

    segs: list[tuple] = []
    x, y = n, m
    for d in range(len(trace) - 1, 0, -1):
        prev = trace[d - 1]
        k = x - y
        if k < blo or k > bhi:
            raise _TooComplex()
        left = prev[k - 1 - blo] if k - 1 >= blo else _NEG_INF
        right = prev[k + 1 - blo] if k + 1 <= bhi else _NEG_INF
        if k == -d or (k != d and left < right):
            pk = k + 1
        else:
            pk = k - 1
        px = _get(prev, pk)
        py = px - pk
        if pk == k + 1:
            sx, sy = px, py + 1
            edit = ("insert", px, sx, py, sy)
        else:
            sx, sy = px + 1, py
            edit = ("delete", px, sx, py, sy)
        if (x, y) != (sx, sy):
            if sx < 0 or sy < 0:
                raise _TooComplex()
            segs.append(("equal", sx, x, sy, y))
        segs.append(edit)
        x, y = px, py
    if (x, y) != (0, 0):
        segs.append(("equal", 0, x, 0, y))
    segs.reverse()
    ops = [s for s in segs if s[1] != s[2] or s[3] != s[4]]
    merged: list[tuple] = []
    for kind, a0, a1, b0, b1 in ops:
        if (merged and merged[-1][0] in ("delete", "insert")
                and kind in ("delete", "insert") and kind != merged[-1][0]
                and merged[-1][2] == a0 and merged[-1][4] == b0):
            merged[-1] = ("replace", merged[-1][1], a1, merged[-1][3], b1)
        else:
            merged.append((kind, a0, a1, b0, b1))
    return merged


def _patience_split(a: list, b: list, a0: int, a1: int,
                    b0: int, b1: int) -> list[tuple] | None:
    """양쪽에 정확히 한 번씩 나오는 공통 행을 앵커로 구간을 나눈다.

    LIS로 순서가 일치하는 최대 앵커 집합을 고른다. 앵커가 하나도 없으면 None.
    결정적(같은 입력 → 같은 분할)이다.
    """
    cb: dict = {}
    for j in range(b0, b1):
        line = b[j]
        c = cb.get(line)
        if c is None:
            cb[line] = j
        else:
            cb[line] = -1
    ca: dict = {}
    for i in range(a0, a1):
        line = a[i]
        c = ca.get(line)
        if c is None:
            ca[line] = i
        else:
            ca[line] = -1
    seq: list[tuple[int, int]] = []  # (ai, bi), A 순서
    for i in range(a0, a1):
        line = a[i]
        if ca.get(line, -1) < 0:
            continue
        j = cb.get(line, -1)
        if j < 0:
            continue
        seq.append((i, j))
    if not seq:
        return None
    # LIS (bi 기준, bisect_left라 동점이어도 결정적)
    tails: list[int] = []
    prev_idx = [-1] * len(seq)
    tail_idx: list[int] = []
    for s, (ai, bi) in enumerate(seq):
        p = bisect.bisect_left(tails, bi)
        if p == len(tails):
            tails.append(bi)
            tail_idx.append(s)
        else:
            tails[p] = bi
            tail_idx[p] = s
        prev_idx[s] = tail_idx[p - 1] if p > 0 else -1
    anchors: list[tuple[int, int]] = []
    s = tail_idx[-1]
    while s >= 0:
        anchors.append(seq[s])
        s = prev_idx[s]
    anchors.reverse()
    out: list[tuple] = []
    pa, pb = a0, b0
    for ai, bi in anchors:
        if ai > pa or bi > pb:
            out.append(("gap", pa, ai, pb, bi))
        out.append(("eq", ai, ai + 1, bi, bi + 1))
        pa, pb = ai + 1, bi + 1
    if pa < a1 or pb < b1:
        out.append(("gap", pa, a1, pb, b1))
    return out


def _positional_opcodes(a: list, b: list, a0: int, b0: int, n: int) -> list[tuple]:
    """길이가 같은 구간을 위치 기준으로 비교한다. O(n), 반복행에 강하다."""
    ops: list[tuple] = []
    i = 0
    while i < n:
        if a[a0 + i] == b[b0 + i]:
            j = i + 1
            while j < n and a[a0 + j] == b[b0 + j]:
                j += 1
            ops.append(("equal", a0 + i, a0 + j, b0 + i, b0 + j))
        else:
            j = i + 1
            while j < n and a[a0 + j] != b[b0 + j]:
                j += 1
            ops.append(("replace", a0 + i, a0 + j, b0 + i, b0 + j))
        i = j
    return ops


def _diff_opcodes(a: list, b: list, cancel=None,
                  exact: bool = False, trace: list[dict] | None = None) -> tuple[list[tuple], bool]:
    """정밀 diff. 시간 기반 중단은 쓰지 않으므로 같은 입력은 항상 같은 결과다.

    1. 공통 앞/뒤 자르기
    2. 작은 구간: SequenceMatcher 정밀 비교(autojunk=False)
    3. 길이 같고 10% 이하로 다르면 위치 기준 비교
    4. Myers 전체 탐색 (기본 상한 2000, exact면 3000)
    5. banded Myers (대각선 근처 큰 편집용). 단 병합 후 큰 replace(200행 이상)가
       있으면 patience로 교차 검증해 앵커가 있으면 재분할한다(밴드 밖 최적
       경로의 비최적 성공 방지). 앵커가 없으면 banded를 그대로 둔다.
    6. patience 분할 후 구간별 재처리
    7. 그래도 안 되면 근사 표시(approx=True): 같은 길이는 위치 비교,
       다른 길이는 단일 replace 블록
    모든 긴 루프에서 취소를 확인한다. approx는 (opcodes, True)로 함께 돌려준다.
    """
    full_cap = _DIFF_FULL_D_CAP_EXACT if exact else _DIFF_FULL_D_CAP
    band_cap = _DIFF_BAND_D_CAP_EXACT if exact else _DIFF_BAND_D_CAP
    _trace_event(trace, "diff_start", exact_requested=bool(exact),
                 full_myers_d_cap=full_cap, banded_myers_d_cap=band_cap,
                 band_width=_DIFF_BAND_W, small_limit=_DIFF_SMALL_LIMIT)
    approx = False
    ops: list[tuple] = []
    # tried: 이미 patience를 적용한 구간(무한 재귀 방지용 표시)
    stack = [(0, len(a), 0, len(b), False)]
    tick = 0
    while stack:
        sa0, a1, sb0, b1, tried = stack.pop()
        a0, b0 = sa0, sb0
        oa1, ob1 = a1, b1  # 꼬리 equal 계산용 원본 끝
        # 공통 앞부분
        while a0 < a1 and b0 < b1 and a[a0] == b[b0]:
            a0 += 1
            b0 += 1
            tick += 1
            if (tick & 1023) == 0 and cancel is not None and cancel.is_set():
                raise Cancelled("사용자 취소")
        if a0 > sa0:
            ops.append(("equal", sa0, a0, sb0, b0))
        # 공통 뒷부분 (앞과 겹치지 않게)
        while a1 > a0 and b1 > b0 and a[a1 - 1] == b[b1 - 1]:
            a1 -= 1
            b1 -= 1
            tick += 1
            if (tick & 1023) == 0 and cancel is not None and cancel.is_set():
                raise Cancelled("사용자 취소")
        if oa1 > a1:
            ops.append(("equal", a1, oa1, b1, ob1))
        n, m = a1 - a0, b1 - b0
        if n == 0 and m == 0:
            continue
        if n == 0:
            _trace_event(trace, "pure_insert", "PROVEN_EXACT", a_len=n, b_len=m)
            ops.append(("insert", a0, a0, b0, b1))
            continue
        if m == 0:
            _trace_event(trace, "pure_delete", "PROVEN_EXACT", a_len=n, b_len=m)
            ops.append(("delete", a0, a1, b0, b0))
            continue
        if max(n, m) <= _DIFF_SMALL_LIMIT:
            _trace_event(trace, "sequence_matcher", "DETERMINISTIC", a_len=n, b_len=m, autojunk=False)
            if cancel is not None and cancel.is_set():
                raise Cancelled("사용자 취소")
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                    None, a[a0:a1], b[b0:b1], autojunk=False).get_opcodes():
                ops.append((tag, a0 + i1, a0 + i2, b0 + j1, b0 + j2))
            continue
        if n == m:
            ham = _ham_frac(a, a0, b, b0, n, cancel)
            if ham <= _DIFF_POSITIONAL_MAX_FRAC:
                _trace_event(trace, "positional_low_hamming", "DETERMINISTIC", a_len=n, b_len=m, hamming_fraction=ham)
                ops.extend(_positional_opcodes(a, b, a0, b0, n))
                continue
        done = False
        # 1) Myers 전체 탐색: 성공하면 최적이라 그대로 채택한다.
        try:
            found = _myers_opcodes(a[a0:a1], b[b0:b1], cancel, full_cap)
            _trace_event(trace, "full_myers", "PROVEN_EXACT", a_len=n, b_len=m, d_cap=full_cap)
            for tag, i1, i2, j1, j2 in found:
                ops.append((tag, a0 + i1, a0 + i2, b0 + j1, b0 + j2))
            done = True
        except _TooComplex:
            _trace_event(trace, "full_myers_exceeded", a_len=n, b_len=m, d_cap=full_cap)
        if not done:
            # 2) banded Myers: 밴드 안 최선이라 큰 replace가 있으면
            # patience로 교차 검증한다. 앵커가 있으면 banded를 버리고
            # patience 경로로 재분할한다. 앵커가 없으면(완전 교체 등)
            # banded를 그대로 채택한다(근사로 표시하지 않음).
            # 주의: banded 원시 출력은 1행 replace 수천 개로 쪼개져 있대는
            # 경우가 많아 _merge_edits 후 크기로 판단한다.
            try:
                found = _banded_myers_opcodes(a[a0:a1], b[b0:b1], cancel,
                                              _DIFF_BAND_W, band_cap)
                _trace_event(trace, "banded_myers", "HEURISTIC", a_len=n, b_len=m,
                             width=_DIFF_BAND_W, d_cap=band_cap)
                merged_found = _merge_edits(found)
                large = any(tag == "replace" and max(i2 - i1, j2 - j1) >= _BANDED_LARGE_REPLACE
                            for tag, i1, i2, j1, j2 in merged_found)
                if large:
                    segs = _patience_split(a, b, a0, a1, b0, b1)
                    anchor_count = sum(1 for x in (segs or []) if x[0] == "eq")
                    _trace_event(trace, "patience_crosscheck", "HEURISTIC", a_len=n, b_len=m,
                                 anchor_count=anchor_count, already_split=bool(tried))
                    if segs and not tried:
                        # 첫 patience 적용 전에는 앵커를 우선해 banded 비최적 가능성을 줄인다.
                        # done=False로 두어 아래 patience 분기로 넘어간다.
                        pass
                    else:
                        # 이미 patience로 잘라 들어온 하위 구간(tried=True)에서는
                        # banded 결과를 버리고 coarse 근사로 떨어지지 않는다. 재귀적으로
                        # patience를 다시 적용하면 같은 구간을 반복할 수 있으므로 여기서 채택한다.
                        for tag, i1, i2, j1, j2 in found:
                            ops.append((tag, a0 + i1, a0 + i2, b0 + j1, b0 + j2))
                        done = True
                else:
                    for tag, i1, i2, j1, j2 in found:
                        ops.append((tag, a0 + i1, a0 + i2, b0 + j1, b0 + j2))
                    done = True
            except _TooComplex:
                _trace_event(trace, "banded_myers_exceeded", a_len=n, b_len=m,
                             width=_DIFF_BAND_W, d_cap=band_cap)
        if done:
            continue
        if not tried:
            segs = _patience_split(a, b, a0, a1, b0, b1)
            if segs:
                _trace_event(trace, "patience_split", "HEURISTIC", a_len=n, b_len=m,
                             anchor_count=sum(1 for x in segs if x[0] == "eq"))
                for kind, x0, x1, y0, y1 in segs:
                    if kind == "eq":
                        ops.append(("equal", x0, x1, y0, y1))
                    else:
                        stack.append((x0, x1, y0, y1, True))
                continue
        # 최후 수단: 근사 표시. 진짜 대량 변경이라 coarse하지만 정직하게 표시한다.
        approx = True
        if n == m:
            _trace_event(trace, "coarse_positional", "APPROXIMATE", a_len=n, b_len=m)
            ops.extend(_positional_opcodes(a, b, a0, b0, n))
        else:
            _trace_event(trace, "coarse_replace", "APPROXIMATE", a_len=n, b_len=m)
            ops.append(("replace", a0, a1, b0, b1))
    ops.sort(key=lambda t: (t[1], t[3]))
    return _merge_edits(ops), approx


def _merge_edits(ops: list[tuple]) -> list[tuple]:
    """인접한 비-equal opcode를 하나의 블록으로 합친다.

    Myers/banded 탐색은 완전 교체 블록을 수천 개의 1행 편집으로 내놓을 수 있어
    (2001행 전체 교체 → 2064 hunk) hunk 수·changed_lines 통계를 망가뜨린다.
    equal 없이 좌표가 이어지는 편집들은 하나의 교체로 보는 것이 정확하다.
    순수 삽입/삭제만으로 이뤄진 블록은 라벨을 유지한다.
    """
    merged: list[tuple] = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            merged.append((tag, i1, i2, j1, j2))
            continue
        if (merged and merged[-1][0] != "equal"
                and merged[-1][2] == i1 and merged[-1][4] == j1):
            _, pi1, _, pj1, _ = merged[-1]
            if pi1 == i2:
                ntag = "insert"
            elif pj1 == j2:
                ntag = "delete"
            else:
                ntag = "replace"
            merged[-1] = (ntag, pi1, i2, pj1, j2)
        else:
            merged.append((tag, i1, i2, j1, j2))
    return merged


def _ham_frac(a: list, a0: int, b: list, b0: int, n: int, cancel=None) -> float:
    """같은 길이 구간의 차이 비율. 긴 루프라 취소를 확인한다."""
    if n == 0:
        return 0.0
    diff = 0
    for i in range(n):
        if a[a0 + i] != b[b0 + i]:
            diff += 1
        if (i & 2047) == 0 and cancel is not None and cancel.is_set():
            raise Cancelled("사용자 취소")
    return diff / n


def _split_text_lines(raw: str) -> list[str]:
    """원시 텍스트를 정규화(CRLF→LF, BOM 제거) 후 행 리스트로 나눈다.
    빈 파일은 0행이다(1행 빈 문자열이 아님)."""
    t = normalize_text(raw)
    if t == "":
        return []
    has_trail = t.endswith("\n")
    lines = t.split("\n")
    if has_trail and lines and lines[-1] == "":
        lines.pop()
    return lines


def _line_ids(a_lines: list[str], b_lines: list[str],
              ignore_ws: bool = False) -> tuple[list[int], list[int]]:
    """비교용 키(공백 정규화 옵션 반영)를 정수 ID로 치환한다. 동일 결과, 더 빠름."""
    if ignore_ws:
        norm = lambda s: re.sub(r"\s+", " ", s).strip()
        a_key = [norm(s) for s in a_lines]
        b_key = [norm(s) for s in b_lines]
    else:
        a_key, b_key = a_lines, b_lines
    ids: dict[str, int] = {}

    def _id(s: str) -> int:
        v = ids.get(s)
        if v is None:
            v = len(ids)
            ids[s] = v
        return v

    return [_id(s) for s in a_key], [_id(s) for s in b_key]


_WORD_SPLIT_RE = re.compile(r"\w+|\W+")


def word_spans(a: str, b: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """두 행의 단어 단위 차이 구간을 문자 오프셋으로 돌려준다.

    ([(시작, 끝), ...] in a, [(시작, 끝), ...] in b). 공백뿐인 구간은 제외한다.
    """
    ta = [(m.start(), m.end()) for m in _WORD_SPLIT_RE.finditer(a)]
    tb = [(m.start(), m.end()) for m in _WORD_SPLIT_RE.finditer(b)]
    sa = [a[s:e] for s, e in ta]
    sb = [b[s:e] for s, e in tb]
    spans_a: list[tuple[int, int]] = []
    spans_b: list[tuple[int, int]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, sa, sb).get_opcodes():
        if tag == "equal":
            continue
        for s, e in ta[i1:i2]:
            if a[s:e].strip():
                spans_a.append((s, e))
        for s, e in tb[j1:j2]:
            if b[s:e].strip():
                spans_b.append((s, e))
    return spans_a, spans_b


def side_by_side(a_raw: str, b_raw: str, ignore_ws: bool = False,
                 cancel=None, exact: bool = False,
                 opcodes: list[tuple] | None = None) -> list[dict]:
    """나란히 보기용 행 모델. 각 행은 아래 키를 갖는다.

    - a_no/b_no: 행 번호(1-based, 반대쪽에 없으면 None)
    - a_text/b_text: 행 내용(없는 쪽은 None)
    - kind: equal/delete/insert/replace

    opcodes가 주어지면 diff 계산을 재사용한다(중복 계산 방지).
    메모리: dict를 직접 만들어 반환한다. 중간 _SBSRow 목록을 두고
    to_dict로 복제하면 두 자료구조가 동시에 존재해 피크가 증가하므로
    (50만 행 138MiB → 176MiB 회귀) 사용하지 않는다.
    """
    a_lines = _split_text_lines(a_raw)
    b_lines = _split_text_lines(b_raw)
    if cancel is not None and cancel.is_set():
        raise Cancelled("사용자 취소")

    if opcodes is None:
        a_id, b_id = _line_ids(a_lines, b_lines, ignore_ws)
        opcodes, _ = _diff_opcodes(a_id, b_id, cancel, exact)
    rows: list[dict] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append({"a_no": i1 + k + 1, "b_no": j1 + k + 1,
                             "a_text": a_lines[i1 + k], "b_text": b_lines[j1 + k],
                             "kind": "equal"})
        elif tag == "delete":
            for k in range(i2 - i1):
                rows.append({"a_no": i1 + k + 1, "b_no": None,
                             "a_text": a_lines[i1 + k], "b_text": None,
                             "kind": "delete"})
        elif tag == "insert":
            for k in range(j2 - j1):
                rows.append({"a_no": None, "b_no": j1 + k + 1,
                             "a_text": None, "b_text": b_lines[j1 + k],
                             "kind": "insert"})
        else:  # replace: 양쪽을 나란히 짝짓고 남는 쪽은 단독 행
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                has_a = i1 + k < i2
                has_b = j1 + k < j2
                kind = "replace" if (has_a and has_b) else ("delete" if has_a else "insert")
                rows.append({"a_no": i1 + k + 1 if has_a else None,
                             "b_no": j1 + k + 1 if has_b else None,
                             "a_text": a_lines[i1 + k] if has_a else None,
                             "b_text": b_lines[j1 + k] if has_b else None,
                             "kind": kind})
    if cancel is not None and cancel.is_set():
        raise Cancelled("사용자 취소")
    return rows


def diff_texts_with_opcodes(a_lines: list[str], b_lines: list[str],
                             fname_a: str, fname_b: str, ignore_ws: bool = False,
                             cancel=None, exact: bool = False
                             ) -> tuple[list[dict], dict, list[tuple]]:
    """행 단위 diff + opcode 재사용용. GUI는 이 함수를 써서 중복 계산을 피한다.

    일반 API는 diff_texts() 2값 반환을 유지한다.
    """
    a_id, b_id = _line_ids(a_lines, b_lines, ignore_ws)
    if cancel is not None and cancel.is_set():
        raise Cancelled("사용자 취소")
    opcodes, approx = _diff_opcodes(a_id, b_id, cancel, exact)
    findings: list[dict] = []
    n_equal = n_change = 0
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            n_equal += (i2 - i1)
            continue
        n_change += max(i2 - i1, j2 - j1)
        label = {"replace": "수정", "delete": "삭제", "insert": "추가"}[tag]
        a_ref = f"{i1 + 1}~{i2}" if i2 - i1 else f"{i1 + 1}(없음)"
        b_ref = f"{j1 + 1}~{j2}" if j2 - j1 else f"{j1 + 1}(없음)"
        detail = [f"[A {fname_a} {a_ref}]"]
        detail += [f"- {s}"[:300] for s in a_lines[i1:min(i2, i1 + 30)]]
        if i2 - i1 > 30:
            detail.append(f"... 외 {i2 - i1 - 30}행 생략")
        detail += [f"[B {fname_b} {b_ref}]"]
        detail += [f"+ {s}"[:300] for s in b_lines[j1:min(j2, j1 + 30)]]
        if j2 - j1 > 30:
            detail.append(f"... 외 {j2 - j1 - 30}행 생략")
        if tag == "replace" and (i2 - i1) <= 6 and (j2 - j1) <= 6:
            seg_len = sum(len(s) for s in a_lines[i1:i2] + b_lines[j1:j2])
            if seg_len <= 20000:
                detail.append("--- 단어 단위 차이 ([-삭제-]/[+추가+]) ---")
                detail += _inline_block(a_lines[i1:i2], b_lines[j1:j2])
        findings.append({"category": "차이점", "file": f"A:{a_ref} / B:{b_ref}",
                         "line": i1 + 1, "column": 0, "token": "",
                         "summary": f"[{label}] A {i2 - i1}행 <-> B {j2 - j1}행 "
                                    f"(A {a_ref} / B {b_ref})",
                         "detail": "\n".join(detail)})
    stats = {"equal_lines": n_equal, "changed_lines": n_change,
             "hunks": len(findings), "a_total": len(a_lines), "b_total": len(b_lines),
             "approx": approx}
    if cancel is not None and cancel.is_set():
        raise Cancelled("사용자 취소")
    return findings, stats, opcodes


def diff_texts_with_trace(a_lines: list[str], b_lines: list[str],
                          fname_a: str, fname_b: str, ignore_ws: bool = False,
                          cancel=None, exact: bool = False
                          ) -> tuple[list[dict], dict, list[tuple], dict]:
    """Harness-facing API with algorithm provenance and conservative quality class.

    Existing public APIs remain unchanged. `quality_class` describes the strongest
    guarantee supported by the actual path, not whether the opcode transform is valid.
    """
    a_id, b_id = _line_ids(a_lines, b_lines, ignore_ws)
    trace: list[dict] = []
    if cancel is not None and cancel.is_set():
        raise Cancelled("사용자 취소")
    opcodes, approx = _diff_opcodes(a_id, b_id, cancel, exact, trace=trace)
    findings: list[dict] = []
    n_equal = n_change = 0
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            n_equal += (i2 - i1)
            continue
        n_change += max(i2 - i1, j2 - j1)
        label = {"replace": "수정", "delete": "삭제", "insert": "추가"}[tag]
        a_ref = f"{i1 + 1}~{i2}" if i2 - i1 else f"{i1 + 1}(없음)"
        b_ref = f"{j1 + 1}~{j2}" if j2 - j1 else f"{j1 + 1}(없음)"
        detail = [f"[A {fname_a} {a_ref}]"]
        detail += [f"- {x}"[:300] for x in a_lines[i1:min(i2, i1 + 30)]]
        if i2 - i1 > 30:
            detail.append(f"... 외 {i2 - i1 - 30}행 생략")
        detail += [f"[B {fname_b} {b_ref}]"]
        detail += [f"+ {x}"[:300] for x in b_lines[j1:min(j2, j1 + 30)]]
        if j2 - j1 > 30:
            detail.append(f"... 외 {j2 - j1 - 30}행 생략")
        if tag == "replace" and (i2 - i1) <= 6 and (j2 - j1) <= 6:
            seg_len = sum(len(s) for s in a_lines[i1:i2] + b_lines[j1:j2])
            if seg_len <= 20000:
                detail.append("--- 단어 단위 차이 ([-삭제-]/[+추가+]) ---")
                detail += _inline_block(a_lines[i1:i2], b_lines[j1:j2])
        findings.append({"category": "차이점", "file": f"A:{a_ref} / B:{b_ref}",
                         "line": i1 + 1, "column": 0, "token": "",
                         "summary": f"[{label}] A {i2 - i1}행 <-> B {j2 - j1}행 "
                                    f"(A {a_ref} / B {b_ref})",
                         "detail": "\n".join(detail)})
    quality = _quality_from_trace(trace, approx)
    stats = {"equal_lines": n_equal, "changed_lines": n_change,
             "hunks": len(findings), "a_total": len(a_lines), "b_total": len(b_lines),
             "approx": approx, "quality_class": quality}
    trace_meta = {
        "api_version": HARNESS_API_VERSION,
        "quality_class": quality,
        "algorithm_path": [row["event"] for row in trace],
        "events": trace,
    }
    if cancel is not None and cancel.is_set():
        raise Cancelled("사용자 취소")
    return findings, stats, opcodes, trace_meta


def diff_texts(a_lines: list[str], b_lines: list[str],
               fname_a: str, fname_b: str, ignore_ws: bool = False,
               cancel=None, exact: bool = False) -> tuple[list[dict], dict]:
    """행 단위 diff. 기본 모드는 결정적 상한 안에서 정밀 비교한다.

    exact=True면 상한을 크게 완화해 끝까지 정밀 탐색을 시도한다(매우 느릴 수
    있음). 그래도 상한을 넘으면 근사 표시(approx=True)와 함께 coarse하게 돌려준다.
    1.4.2 이전과 같은 2값 반환을 유지한다. opcode 재사용이 필요하면
    diff_texts_with_opcodes()를 쓴다.
    """
    findings, stats, _ = diff_texts_with_opcodes(
        a_lines, b_lines, fname_a, fname_b, ignore_ws, cancel, exact)
    return findings, stats


def _endings(raw: str) -> tuple[str, bool]:
    crlf = raw.count("\r\n")
    lf = raw.count("\n") - crlf
    cr = raw.count("\r") - crlf
    kinds = [k for k, n in (("CRLF", crlf), ("LF", lf), ("CR", cr)) if n > 0]
    kind = kinds[0] if len(kinds) == 1 else ("혼합" if kinds else "없음(한 줄)")
    return kind, raw.endswith(("\n", "\r"))


def compare_with_opcodes(a_raw: str, b_raw: str, fname_a: str, fname_b: str,
                         db: dict, ignore_ws: bool = False, run_checks: bool = True,
                         progress=None, cancel=None, exact: bool = False
                         ) -> tuple[list[dict], dict, list[tuple]]:
    """compare() + opcode 재사용용. GUI 내부용으로 diff를 1회만 계산한다.

    일반 API는 compare() 2값 반환을 유지한다.
    """
    kind_a, trail_a = _endings(a_raw)
    kind_b, trail_b = _endings(b_raw)
    a_text = normalize_text(a_raw)
    b_text = normalize_text(b_raw)

    a_lines, b_lines = _split_text_lines(a_raw), _split_text_lines(b_raw)
    if progress is not None:
        progress("diff", 0, 1)
    findings, stats, diff_opcodes = diff_texts_with_opcodes(
        a_lines, b_lines, fname_a, fname_b, ignore_ws,
        cancel=cancel, exact=exact)
    stats.update({"typos": 0, "typo_kinds": 0, "hygiene": 0, "new_in_b": 0,
                  "typo_truncated": False, "pattern_caps": [],
                  "ending_a": kind_a, "ending_b": kind_b,
                  "trail_a": trail_a, "trail_b": trail_b})
    if kind_a != kind_b:
        findings.append({"category": "특이사항", "file": f"{fname_a} vs {fname_b}",
                         "line": 0, "column": 0, "token": "",
                         "summary": f"줄바꿈 형식 다름: A {kind_a} / B {kind_b}",
                         "detail": "두 파일의 줄바꿈 형식이 다릅니다. 보기에는 같아도 diff/빌드에 영향을 줄 수 있습니다."})
    if trail_a != trail_b:
        findings.append({"category": "특이사항", "file": f"{fname_b}", "line": 0,
                         "column": 0, "token": "",
                         "summary": f"파일 끝 개행 유무 다름: A {'있음' if trail_a else '없음'} / "
                                    f"B {'있음' if trail_b else '없음'}",
                         "detail": "파일 끝 개행 유무가 다릅니다. POSIX·Git 관례상 끝 개행을 권장합니다."})
    if run_checks:
        ta, ia = check_typos(a_text, db, fname_a,
                             progress=lambda p, d, t: progress("typo-a", d, t) if progress else None,
                             cancel=cancel)
        tb, ib = check_typos(b_text, db, fname_b,
                             progress=lambda p, d, t: progress("typo-b", d, t) if progress else None,
                             cancel=cancel)
        ha, ca = check_code_hygiene(a_text, db, fname_a, cancel=cancel)
        hb, cb = check_code_hygiene(b_text, db, fname_b, cancel=cancel)
        # B 신규 판정: 오타는 종류 키(토큰·제안, 라인 무관)로, 규칙은 (구분, 요약)으로.
        # A에 같은 종류가 있으면 B의 동일 종류는 신규가 아니다(건수 증가도 신규 아님).
        a_keys = {("typo", f["gkey"]) for f in ta if "gkey" in f}
        a_keys |= {(f["category"], f["summary"]) for f in ha}
        for f in tb:
            if ("typo", f.get("gkey")) not in a_keys:
                f["is_new"] = True
        for f in hb:
            if (f["category"], f["summary"]) not in a_keys:
                f["is_new"] = True
        findings += ta + tb + ha + hb
        # 오타 종류는 A/B 합집합으로 센다(같은 오타가 양쪽에 있어도 1종).
        # 사용자 패턴이 낸 오타 의심(gkey 없음)도 종류·발생 수에 합산한다.
        gkeys = ({f["gkey"] for f in ta if "gkey" in f}
                 | {f["gkey"] for f in tb if "gkey" in f})
        user_typos = [f for f in ha + hb
                      if f.get("category") == "오타 의심" and "gkey" not in f]
        # 사용자 오타 의심은 오타 통계에만 포함하고 hygiene에서는 제외(중복 방지)
        stats["typos"] = ia["occurrences"] + ib["occurrences"] + len(user_typos)
        stats["typo_kinds"] = len(gkeys) + len({f["summary"] for f in user_typos})
        stats["hygiene"] = len(ha) + len(hb) - len(user_typos)
        stats["new_in_b"] = sum(1 for f in tb + hb if f.get("is_new"))
        stats["typo_truncated"] = ia["truncated"] or ib["truncated"]
        stats["pattern_caps"] = sorted(set(ca["capped"] + cb["capped"]))
    for i, f in enumerate(findings, 1):
        f["no"] = i
    return findings, stats, diff_opcodes


# 구버전 호환 별칭 (보고서 제안 _compare_with_opcodes와 같은 역할)
_compare_with_opcodes = compare_with_opcodes
_diff_texts_with_opcodes = diff_texts_with_opcodes


def compare(a_raw: str, b_raw: str, fname_a: str, fname_b: str,
            db: dict, ignore_ws: bool = False, run_checks: bool = True,
            progress=None, cancel=None, exact: bool = False) -> tuple[list[dict], dict]:
    """두 파일 대조 + 오타/문법 검사. 1.4.2 이전과 같은 2값 반환을 유지한다.

    GUI처럼 opcode 재사용이 필요하면 compare_with_opcodes()를 쓴다.
    """
    findings, stats, _ = compare_with_opcodes(
        a_raw, b_raw, fname_a, fname_b, db, ignore_ws, run_checks,
        progress, cancel, exact)
    return findings, stats
