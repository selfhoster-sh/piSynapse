"""Tests for the piServe LiteRT HTTP server (validation logic only — no engine).

piServe depends on litert_lm, which only installs on the target device. When
missing we inject a minimal stub so the pure-HTTP logic stays testable here.
"""

import importlib.util
import sys
import types


def _ensure_litert_stub():
    if importlib.util.find_spec("litert_lm") is not None:
        return
    if "litert_lm" in sys.modules:
        return

    def _auto_init(self, **kwargs):
        self.__dict__.update(kwargs)

    engine_mod = types.ModuleType("litert_lm.engine")
    engine_mod.Engine = type("Engine", (), {})

    iface_mod = types.ModuleType("litert_lm.interfaces")
    for name in ("Backend", "SamplerConfig", "ThinkingConfig", "Tool"):
        setattr(iface_mod, name, type(name, (), {"__init__": _auto_init}))

    pkg = types.ModuleType("litert_lm")
    pkg.engine = engine_mod
    pkg.interfaces = iface_mod
    sys.modules["litert_lm"] = pkg
    sys.modules["litert_lm.engine"] = engine_mod
    sys.modules["litert_lm.interfaces"] = iface_mod


_ensure_litert_stub()


def _make_handler(model_id="gemma4-e2b"):
    import litert_serve.server as srv

    h = object.__new__(srv.Handler)
    sent = {}
    h._send_json = lambda status, obj: sent.update(status=status, obj=obj)
    h.model_id = model_id
    return h, sent


def test_unknown_model_rejected_with_409_and_allowed_list():
    h, sent = _make_handler()
    ok = h._validate_model({"model": "gpt-4o"})
    assert ok is False
    assert sent["status"] == 409
    assert "gpt-4o" in sent["obj"]["error"]["message"]
    assert sent["obj"]["error"]["allowed_models"] == ["gemma4-e2b"]


def test_missing_model_silently_falls_back_to_loaded_model():
    h, sent = _make_handler()
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert h._validate_model(body) is True
    assert body["model"] == "gemma4-e2b"
    assert sent == {}


def test_empty_string_model_falls_back_loaded_model():
    h, _ = _make_handler()
    body = {"model": "   "}
    assert h._validate_model(body) is True
    assert body["model"] == "gemma4-e2b"


def test_exact_loaded_model_passes():
    h, sent = _make_handler()
    assert h._validate_model({"model": "gemma4-e2b"}) is True
    assert sent == {}


# -- finish_reason mapping --

def _finish_reason(*args, **kwargs):
    import litert_serve.server as srv

    return srv._finish_reason(*args, **kwargs)


def test_finish_reason_length_from_engine_keys():
    for key in ("finish_reason", "stop_reason", "done_reason", "reason"):
        assert _finish_reason({key: "length"}) == "length"
        assert _finish_reason({key: "max_tokens"}) == "length"


def test_finish_reason_tool_calls_wins_over_truncation():
    assert _finish_reason({"stop_reason": "length"}, saw_tool_calls=True) == "tool_calls"
    assert _finish_reason({"tool_calls": [1], "stop_reason": "length"}) == "tool_calls"


def test_finish_reason_defaults_to_stop():
    assert _finish_reason(None) == "stop"
    assert _finish_reason({}) == "stop"
    assert _finish_reason({"finish_reason": "stop"}) == "stop"
    assert _finish_reason(saw_tool_calls=False) == "stop"


# -- conversation cache (session_id reuse) --

def _fake_conv(tag: str):
    conv = types.SimpleNamespace()
    conv.tag = tag
    conv.closed = False
    conv.close = lambda: setattr(conv, "closed", True)
    return conv


def _set_cache_max(n):
    import litert_serve.server as srv
    srv._cfg["conversation_cache_max"] = n
    srv.Handler._conv_cache.clear()


def test_cache_disabled_when_max_zero():
    import litert_serve.server as srv
    _set_cache_max(0)
    assert srv.Handler._cache_max() == 0
    assert srv.Handler._cached_conversation("s1") is None
    conv = _fake_conv("a")
    srv.Handler._preserve_conversation("s1", conv)
    assert srv.Handler._conv_cache == {}
    assert conv.closed is False


def test_cache_preserves_and_returns_same_conversation():
    import litert_serve.server as srv
    _set_cache_max(4)
    conv = _fake_conv("a")
    srv.Handler._preserve_conversation("s1", conv)
    got = srv.Handler._cached_conversation("s1")
    assert got is conv
    assert got.closed is False


def test_cache_evicts_least_recently_used():
    import litert_serve.server as srv
    _set_cache_max(2)
    a, b = _fake_conv("a"), _fake_conv("b")
    srv.Handler._preserve_conversation("s1", a)
    srv.Handler._preserve_conversation("s2", b)
    # Touch s1 (MRU), push s3 -> s2 becomes LRU and is evicted.
    assert srv.Handler._cached_conversation("s1") is a
    srv.Handler._preserve_conversation("s3", _fake_conv("c"))
    assert b.closed is True
    assert srv.Handler._cached_conversation("s2") is None
    assert srv.Handler._cached_conversation("s1") is a
    assert srv.Handler._cached_conversation("s3") is not None
