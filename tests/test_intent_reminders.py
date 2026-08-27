"""Reminder routing: 'hatırlat/remind + time' -> calendar, else memory.

Regression for the eval finding where "bana perşembe için bir hatırlatıcı
kur, saat 9'da" landed in the memory group (substring hit on "hatırla") and
the model dumped a junk save_memory instead of creating a calendar event.
"""

import asyncio

import pytest

import db as dbmod
import llm.intent as li_mod


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "iaudit.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def test_reminder_with_time_is_calendar():
    assert li_mod.reminder_group("bana perşembe için bir hatırlatıcı kur, saat 9'da") == "calendar"
    assert li_mod.reminder_group("yarın saat 3'te dişçi hatırlat") == "calendar"
    assert li_mod.reminder_group("cumartesi sabah 09:00'da toplantıyı hatırlat") == "calendar"
    assert li_mod.reminder_group("remind me to pay the bills tomorrow at 9am") == "calendar"
    assert li_mod.reminder_group("erinnere mich am Freitag um 8 Uhr") == "calendar"
    assert li_mod.reminder_group("rappelle-moi lundi à 8 heures") == "calendar"
    assert li_mod.reminder_group("recuérdame llamar a mamá el domingo") == "calendar"


def test_reminder_without_time_is_memory():
    assert li_mod.reminder_group("bunu hatırlat: eve döndüğümde çamaşırları as") == "memory"
    assert li_mod.reminder_group("remind me to buy milk") == "memory"


def test_bare_remember_is_not_a_reminder_rule():
    # "hatırla" is a memory recollection, not the reminder family.
    assert li_mod.reminder_group("şunu hatırla: en sevdiğim renk mavi") is None


def test_keyword_hati̇rla_does_not_swallow_reminder_family():
    assert li_mod._kw_hit("hatırla", "hatırlat") is False
    assert li_mod._kw_hit("hatırla", "hatırlatıcı") is False
    assert li_mod._kw_hit("hatırla", "hatırlatma") is False
    assert li_mod._kw_hit("hatırla", "şunu hatırla bunu") is True


def test_keyword_group_routes_reminder_time_to_calendar():
    assert li_mod._keyword_group("bana perşembe için bir hatırlatıcı kur, saat 9'da") == "calendar"
    assert li_mod._keyword_group("yarın su içmeyi hatırlat") == "calendar"
    assert li_mod._keyword_group("bunu hatırlat: eve döndüğümde çamaşırları as") == "memory"


def test_hit_groups_no_memory_collision_on_reminder():
    # "hatırlatıcı" must not combine {'memory'} with {'calendar'} via the
    # "hatırla" substring, which would widen the toolset for no reason.
    assert li_mod._hit_groups("bana perşembe için bir hatırlatıcı kur") == {"calendar"}


def test_hit_groups_reminder_plus_other_domain_stays_combined():
    # A reminder that also carries another domain keeps the union so
    # multi-domain routing still offers the matching tools.
    groups = li_mod._hit_groups("yarın saat 9'da toplantıyı hatırlat ve görev oluştur")
    assert "calendar" in groups and "tasks" in groups
    assert li_mod._hit_groups("perşembe saat 9'da hatırlat") == {"calendar"}


def test_classify_reminder_never_consults_embedding(audit_db, monkeypatch):
    # Deterministic routing must fire before embedding can flip it — this is
    # the exact eval case that previously produced save_memory junk.
    monkeypatch.setattr(li_mod, "_tool_embed_cache", [])
    monkeypatch.setattr(li_mod, "get", lambda k, d=None: {"INTENT_LLM_FALLBACK": "off"}.get(k, d))

    assert asyncio.run(li_mod._classify_intent("bana perşembe için bir hatırlatıcı kur, saat 9'da")) == ("action", "calendar")
    assert asyncio.run(li_mod._classify_intent("şunu hatırla: en sevdiğim renk mavi")) == ("action", "memory")
    assert asyncio.run(li_mod._classify_intent("bunu hatırlat: eve döndüğümde çamaşırları as")) == ("action", "memory")
    # Reminder + a second domain -> combined toolset, not calendar alone.
    assert asyncio.run(li_mod._classify_intent(
        "yarın saat 9'da toplantıyı hatırlat ve görev oluştur"))[0] == "action"