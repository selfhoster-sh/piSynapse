"""POST /chat/execute — the manual (confirm) tool-run path. Was 0%.

Runs outside the model loop, so it owns its own audit + verification +
save + link flow. Exercised with fakes: success, confirm-param rejection,
tool exception (still audited), no-audit-id path, and the 500 wrapper.
"""
import asyncio
import types

import pytest
from fastapi import HTTPException

import routers.chat as rc


def _install(monkeypatch, *, run_result=("OK", None), run_raises=False,
             confirm_err=None, audit_id=7, verify_status="verified"):
    calls = {"linked": [], "saved": [], "verify": []}

    async def fake_run_tool(name, params, context=None):
        if run_raises:
            raise RuntimeError("tool blew up")
        return run_result

    async def fake_verify(tool, params, result, success, **kw):
        calls["verify"].append((tool, success, kw.get("error")))
        return (audit_id, verify_status)

    async def fake_save(session_id, role, content, **kw):
        calls["saved"].append((role, content))
        return 42

    async def fake_link(msg_id, audit_ids):
        calls["linked"].append((msg_id, list(audit_ids)))

    import tool_verification
    import tools

    monkeypatch.setattr(tools, "run_tool", fake_run_tool)
    monkeypatch.setattr(tools, "is_tool_success", lambda r: not str(r).startswith("ERROR"))
    monkeypatch.setattr(tools, "validate_confirm_params", lambda tool, params: confirm_err)
    monkeypatch.setattr(tool_verification, "run_verification", fake_verify)
    monkeypatch.setattr(rc, "save_message", fake_save)
    monkeypatch.setattr(rc, "link_audits_to_message", fake_link)
    return calls


def _exec(tool="list_notes", params=None, session_id="s1"):
    req = rc.ExecuteRequest(session_id=session_id, tool=tool, params=params or {})
    fake_request = types.SimpleNamespace(state=types.SimpleNamespace(user_id="tester"))
    return asyncio.run(rc.execute_action(req, fake_request))


def test_successful_execution_saves_links_and_reports_status(monkeypatch):
    calls = _install(monkeypatch, run_result=("Notlar listelendi", None))
    resp = _exec()
    assert resp.reply == "Notlar listelendi"
    assert resp.verification_status == "verified"
    assert ("assistant", "Notlar listelendi") in calls["saved"]
    assert calls["linked"] == [(42, [7])]


def test_confirm_tool_invalid_params_400(monkeypatch):
    _install(monkeypatch, confirm_err="missing recipient")
    with pytest.raises(HTTPException) as exc:
        _exec(tool="send_email", params={})
    assert exc.value.status_code == 400


def test_tool_exception_is_audited_as_failure(monkeypatch):
    calls = _install(monkeypatch, run_raises=True)
    resp = _exec()
    assert resp.reply.startswith("ERROR:")
    # verification saw success=False and the error text
    tool, success, error = calls["verify"][0]
    assert success is False and error and error.startswith("ERROR:")
    assert ("assistant", resp.reply) in calls["saved"]


def test_no_audit_id_skips_linking(monkeypatch):
    calls = _install(monkeypatch, audit_id=None, verify_status=None)
    resp = _exec()
    assert resp.verification_status is None
    assert calls["linked"] == []


def test_unexpected_failure_wrapped_as_500(monkeypatch):
    _install(monkeypatch)

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(rc, "save_message", boom)
    with pytest.raises(HTTPException) as exc:
        _exec()
    assert exc.value.status_code == 500
