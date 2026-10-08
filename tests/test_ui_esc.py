"""static/ui.js esc() — XSS escape regresyon korkuluğu.

2026-09-03'teki 7609519 (Web Worker/Sanitizer commit'i) esc() zincirini
birebir no-op'a çevirmişti (replace(/&/g,'&')), 168 çağrı noktasının tamamını
korumasız bıraktı. Bu test, zinciri kaynaktan çıkarıp davranışını doğrular;
no-op'a dönen her sürüm burada düşer.
"""
import re
from pathlib import Path

UI_JS = Path(__file__).resolve().parent.parent / "static" / "ui.js"

EXPECTED_PAIRS = [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"),
                  ('"', "&quot;"), ("'", "&#39;")]


def _esc_pairs() -> list[tuple[str, str]]:
    src = UI_JS.read_text(encoding="utf-8")
    m = re.search(r"function esc\(s\)\{ return (.*?) \}", src)
    assert m, "esc() function not found in static/ui.js"
    return re.findall(r"\.replace\(/(.+?)/g,'([^']*)'\)", m.group(1))


def _esc(s):
    """esc() zincirini JS semantiğiyle (String(s||'')) Python'da uygular."""
    val = str(s) if s else ""
    for pat, rep in _esc_pairs():
        val = val.replace(pat, rep)
    return val


def test_esc_chain_is_not_noop():
    pairs = _esc_pairs()
    assert pairs == EXPECTED_PAIRS, (
        f"esc() replacement chain changed: {pairs!r} != {EXPECTED_PAIRS!r}. "
        "Every replace must map to a DIFFERENT entity (no-op = XSS hole)."
    )


def test_esc_escapes_html_specials():
    assert _esc("<b>") == "&lt;b&gt;"
    assert _esc("a & b") == "a &amp; b"
    assert _esc('"quoted"') == "&quot;quoted&quot;"
    assert _esc("it's") == "it&#39;s"
    assert _esc("<script>alert('x')</script>") == (
        "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;"
    )


def test_esc_ampersand_first_no_double_escaping():
    # & must be replaced FIRST, otherwise later entities get re-escaped.
    assert _esc("&lt;") == "&amp;lt;"  # literal 4-char input, not '<'


def test_esc_js_falsy_semantics():
    assert _esc(None) == ""
    assert _esc("") == ""
    assert _esc(0) == ""  # JS: String(0||'') === ''
    assert _esc("ok") == "ok"


def test_esc_never_passes_angle_brackets_through():
    # 168 call sites interpolate esc() output into innerHTML templates;
    # a raw '<' in output would reopen the XSS hole.
    for payload in ("<img onerror=x>", "<script>alert(1)</script>",
                    "<a href='#'>", "</div><svg onload=1>"):
        out = _esc(payload)
        assert "<" not in out, (payload, out)
        assert ">" not in out, (payload, out)
