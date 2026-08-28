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


def test_reminder_with_clock_is_calendar():
    assert li_mod.reminder_group("bana perşembe için bir hatırlatıcı kur, saat 9'da") == "calendar"
    assert li_mod.reminder_group("yarın saat 3'te dişçi hatırlat") == "calendar"
    assert li_mod.reminder_group("cumartesi sabah 09:00'da toplantıyı hatırlat") == "calendar"
    assert li_mod.reminder_group("remind me to pay the bills tomorrow at 9am") == "calendar"
    assert li_mod.reminder_group("erinnere mich am Freitag um 8 Uhr") == "calendar"
    assert li_mod.reminder_group("rappelle-moi lundi à 8 heures") == "calendar"
    # spelled-out clock, categorical noon, and non-classic reminder verbs
    assert li_mod.reminder_group("sekizde su içmeyi hatırlat") == "calendar"
    assert li_mod.reminder_group("sekiz buçukta ilaç hatırlat") == "calendar"
    assert li_mod.reminder_group("remind me at noon to call mom") == "calendar"
    assert li_mod.reminder_group("akşam 6'da haber ver") == "calendar"
    assert li_mod.reminder_group("saat 9'da alarm kur") == "calendar"
    assert li_mod.reminder_group("do not forget the meds at 9 o'clock") == "calendar"


def test_reminder_with_date_only_is_calendar():
    # day/relative/month date anchors with no clock hour -> calendar
    # (all-day event per industry convention: Google Calendar, Apple Reminders)
    assert li_mod.reminder_group("gelecek hafta pazartesi toplantıyı hatırlat") == "calendar"
    assert li_mod.reminder_group("yarın su içmeyi hatırlat") == "calendar"
    assert li_mod.reminder_group("recuérdame llamar a mamá el domingo") == "calendar"
    assert li_mod.reminder_group("remind me next Monday to send the proposal") == "calendar"
    assert li_mod.reminder_group("15 mart için dişçi randevusu hatırlat") == "calendar"
    assert li_mod.reminder_group("remind me in 3 days to check the invoice") == "calendar"
    assert li_mod.reminder_group("3 gün sonra faturaları ödemeyi hatırlat") == "calendar"


def test_reminder_without_temporal_anchor_is_memory():
    # reminders WITHOUT any temporal anchor stay in memory
    assert li_mod.reminder_group("bunu hatırlat: eve döndüğümde çamaşırları as") == "memory"
    assert li_mod.reminder_group("remind me to buy milk") == "memory"
    assert li_mod.reminder_group("çamaşır asmayı unutma eve dönünce") == "memory"


def test_pazar_as_market_is_not_a_date():
    # "pazar" dative form = the bazaar/market, not Sunday
    assert li_mod.reminder_group("pazara gitmeyi unutma") == "memory"
    assert li_mod.reminder_group("pazardan soğan almayı unutma") == "memory"
    assert li_mod.reminder_group("pazar günü su içmeyi hatırlat") == "calendar"


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
    assert li_mod._keyword_group("yarın saat 8'de su içmeyi hatırlat") == "calendar"
    assert li_mod._keyword_group("gelecek hafta pazartesi toplantıyı hatırlat") == "calendar"
    assert li_mod._keyword_group("bunu hatırlat: eve döndüğümde çamaşırları as") == "memory"
    assert li_mod._keyword_group("remind me to buy milk") == "memory"


def test_hit_groups_no_memory_collision_on_reminder():
    # "hatırlatıcı" must not combine {'memory'} with {'calendar'} via the
    # "hatırla" substring, which would widen the toolset for no reason.
    assert li_mod._hit_groups("bana perşembe için bir hatırlatıcı kur, saat 9'da") == {"calendar"}


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
    # day/date-only reminder (no clock) -> calendar all-day deterministically
    assert asyncio.run(li_mod._classify_intent("gelecek hafta pazartesi toplantıyı hatırlat")) == ("action", "calendar")
    assert asyncio.run(li_mod._classify_intent("yarın su içmeyi hatırlat")) == ("action", "calendar")
    # spelled-out clock still routes to calendar deterministically
    assert asyncio.run(li_mod._classify_intent("sekizde su içmeyi hatırlat")) == ("action", "calendar")
    # Reminder + a second domain -> combined toolset, not calendar alone.
    assert asyncio.run(li_mod._classify_intent(
        "yarın saat 9'da toplantıyı hatırlat ve görev oluştur"))[0] == "action"