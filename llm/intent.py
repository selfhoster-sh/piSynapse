"""Intent classification: embedding + keyword heuristics, optional LLM fallback."""
import asyncio
import logging
import re

from config import LITERT_BASE_URL, OLLAMA_BASE_URL, get

from .utils import _get_client

logger = logging.getLogger("piSynapse")

_FOLLOWUP_RE = re.compile(
    r"gelen|anlat|detayl[ıi]|içeri[gğ]ini|icerigini|oku|özetle|ozetle|ne yaz|yazan", re.IGNORECASE
)
_EMAIL_CTX_MARKERS = (
    "gönderen:", "konu:", "özet:", "e-posta", "eposta", "posta",
    "mail", "gelen kutusu", "mesaj", "email",
)

# -- Reminder disambiguation (calendar vs memory) --
#
# "hatırlat" / "remind" + a time or date ("perşembe saat 9'da hatırlat")
# is a calendar action; a bare "remember this" / "bunu hatırla" request is a
# memory fact. The distinction is deterministic (regex, no model call) so the
# routing can never flip on embedding noise for the ~80% of real reminder
# phrasings. Note the memory keyword "hatırla" must NOT substring-match the
# reminder family — handled in _kw_hit below.
_REMINDER_WORDS = (
    "hatırlat", "hatirlat", "hatırlatıcı", "hatirlatici", "hatırlatma",
    "remind", "reminder", "erinner", "rappelle", "rappel", "recuerd", "recuérd",
    "recordatorio",  # ES
)

# Additional reminder verbs outside the classic family ("alarm kur",
# "beni uyar", "haber ver", "asmayı unutma") so clock-anchored requests are
# not skipped just because the wording isn't literally "hatırlat".
_REMINDER_VERBS = (
    "alarm", "wecker",                                     # set an alarm (tr/en/de/fr/es)
    "uyar", "bildir", "haber ver",               # TR
    "unutm",                                     # unutma / unutmayı / unutmasın
    "don't forget", "dont forget", "do not forget",  # EN
    "nudge me", "ping me",
    "nicht vergessen", "vergess",                # DE
    "n'oublie", "oublie pas", "réveille", "reveille",   # FR
    "no olvides", "avísame", "avisame", "despiértame", "despiertame",
    "recuérdate", "recuerdate", "recuerda", "recordar",  # ES
)

# Negation patterns: explicit "don't remind" / "hatırlatma" should route to memory, not calendar
_NEGATION_PATTERN = re.compile(
    r"\b(?:hatırlatma|hatirlatma)\b"  # TR: "hatırlatma, sadece kaydet"
    r"|don['\']?t\s+remind\b"          # EN: "don't remind me"
    r"|do\s+not\s+remind\b"            # EN: "do not remind"
    r"|nicht\s+erinnern\b"             # DE: "nicht erinnern"
    r"|kein\s+wecker\b"                # DE: "kein wecker"
    r"|ne\s+rappelle\s+pas\b"          # FR: "ne rappelle pas"
    r"|pas\s+de\s+rappel\b"            # FR: "pas de rappel"
    r"|no\s+recuerdes\b"               # ES: "no recuerdes"
    r"|sin\s+recordatorio\b",          # ES: "sin recordatorio"
    re.IGNORECASE,
)

# A reminder becomes a CALENDAR event whenever it carries a temporal anchor.
# Any anchor (clock hour, date, relative day, month/date, duration-in-days)
# keeps it in the calendar; only reminders with NO temporal anchor at all stay
# in memory. Industry convention: clock -> timed event, bare day/date -> the
# model creates an all-day event rather than inventing an hour.

# CLOCK anchors -> timed calendar event.
_CLOCK_SIGNAL_PATTERN = re.compile(
    r"("
    # numeric clocks: 9'da / 09:00'da / 9da / 19:30 / 8 Uhr / 9am
    r"\b\d{1,2}(?::\d{2})?\s*'?[tdTD]?[ae]\b"
    r"|\b\d{1,2}:\d{2}\b"
    r"|\b\d{1,2}\s*(?:saat|o'?clock|am|pm|uhr|heures?|hora)\b"
    r"|\b(?:saat|uhr|heure|hora)\s+\d{1,2}\b"
    # Turkish spelled-out cardinals: standalone ("sekiz buçukta") or glued
    # locative suffix ("sekizde" / "üçte" / "altıda" — no \b, one word)
    r"|\b(?:bir|iki|üç|uc|dört|dort|beş|bes|altı|alti|yedi|sekiz|dokuz"
    r"|on|on\s*bir|onbir|on\s*iki|oniki)\b\s*b[ıu]çuk\s*'?[td][ae]\b"
    r"|\b(?:bir|iki|üç|uc|dört|dort|beş|bes|altı|alti|yedi|sekiz|dokuz"
    r"|on|on\s*bir|onbir|on\s*iki|oniki)(?:'?)(?:da|de|ta|te)\b"
    # anchored relative durations near a clock: 10 dakika sonra / in 10 minutes
    r"|\b\d+\s*(?:dakika|saat)\s*sonra\b"
    r"|\bin\s+\d+\s*(?:hours?|minutes?)\b"
    r"|\bin\s+\d+\s*(?:stunden?|minuten?)\b"
    r"|\bdans\s+\d+\s*(?:heures?|minutes?)\b"
    r"|\ben\s+\d+\s*(?:horas?|minutos?)\b"
    # spelled-out durations (cardinal words): in one hour, in zwei Stunden, en una hora
    r"|\bin\s+(?:an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+hours?\b"
    r"|\bin\s+(?:an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+minutes?\b"
    r"|\bin\s+(?:ein|einer|eines|einen|zwei|drei|vier|f[üu]nf|sechs|sieben|acht|neun|zehn|elf|zwölf)\s+stunden?\b"
    r"|\bin\s+(?:ein|einer|eines|einen|zwei|drei|vier|f[üu]nf|sechs|sieben|acht|neun|zehn|elf|zwölf)\s+minuten?\b"
    r"|\bdans\s+(?:une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze)\s+heures?\b"
    r"|\bdans\s+(?:une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze)\s+minutes?\b"
    r"|\ben\s+(?:una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)\s+horas?\b"
    r"|\ben\s+(?:un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)\s+minutos?\b"
    # hour connectors: a las 9 / à 9 / um 8 / at 9
    r"|\b(?:a\s+las|à\s+(?:le?s?\s+)?|um|at)\s*\d{1,2}\b"
    # hour connectors with spelled-out numbers: um ein Uhr, a la una, à une heure
    r"|\bum\s+(?:ein|zwei|drei|vier|f[üu]nf|sechs|sieben|acht|neun|zehn|elf|zwölf)\s+uhr\b"
    r"|\ba\s+la\s+una\b"
    r"|\ba\s+las\s+(?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)\b"
    r"|\bà\s+(?:une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze)\s+heures?\b"
    # half past three + DE "halb zehn" (9:30)
    r"|\bhalf\s*past\s*(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"
    r"|\bhalb\s+(?:ein|zwei|drei|vier|f[üu]nf|sechs|sieben|acht|neun|zehn|elf|zwölf)\b"
    # single-instant clock words (noon family): öğle / gece yarısı (midnight)
    r"|\b(?:öğle|öğlen|ogle|oglen|gece yarısı|geceyarısı|noon|midday|midnight"
    r"|mittag|mitternacht|midi|minuit|mediodia|mediodía|medianoche)\b"
    r")",
    re.IGNORECASE,
)

# DATE anchors -> all-day calendar event: day names, relative day terms,
# month+day, numeric dates, and "in N days/weeks" across TR/EN/DE/FR/ES.
_DATE_SIGNAL_PATTERN = re.compile(
    r"("
    # day names — 5 languages ("pazar" = Sunday, not the market: exclude the
    # dative 'pazara/pazardan' form used for the bazaar)
    r"\b(?:pazartesi|sal[ıi]|çarşamba|carsamba|perşembe|persembe|cuma\b"
    r"|pazarları|cumartesi|pazar(?!a\b)"
    r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag"
    r"|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche"
    r"|lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)\b"
    # relative date-level terms
    r"|\b(?:yarın|yarin|bugün|bugun|öbür gün|obur gun|haftaya|gelecek hafta"
    r"|sonraki hafta|önümüzdeki hafta|onumuzdeki hafta|bu hafta|hafta sonu|haftasonu"
    r"|tomorrow|today|tonight|next week|this week|next month|this month"
    r"|the day after tomorrow|day after tomorrow"
    r"|morgen|heute|übermorgen|ubermorgen|nächste woche|naechste woche"
    r"|demain|ce soir|cette semaine|la semaine prochaine"
    r"|mañana|manana|hoy|la semana que viene|pasado mañana|pasado manana)\b"
    # time-of-day soft anchors (no clock hour): evening / morning / afternoon
    r"|\b(?:akşam|aksam|sabah|gece|evening|morning|afternoon"
    r"|abend|soir|apr[èe]s-midi|tarde|noche)\b"
    # "in N days/weeks" (5 languages) and TR "N gün sonra"
    r"|\bin\s+\d+\s*(?:days?|weeks?)\b"
    r"|\bin\s+\d+\s*(?:tagen?|wochen?)\b"
    r"|\bdans\s+\d+\s*(?:jours?|semaines?)\b"
    r"|\ben\s+\d+\s*(?:d[ií]as?|semanas?)\b"
    r"|\b\d+\s*(?:gün|gun|hafta)\s*(?:sonra|önce|once)\b"
    # month + day (TR/EN): 15 mart / march 5 / 05.03(2026)
    r"|\b\d{1,2}\s*(?:ocak|şubat|mart|nisan|mayıs|mayis|haziran|temmuz"
    r"|ağustos|agustos|eyl[üu]l|ekim|kasım|kasim|aralık|aralik)\b"
    r"|\b(?:janu|febru|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b"
    r"|\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b"
    # Turkish "ayın 15'inde" / "ayın 3'ün" / "her ayın 15'i"
    r"|\bay[ıi]n\s+\d{1,2}\b"
    r")",
    re.IGNORECASE,
)


def reminder_group(message: str) -> str | None:
    """Deterministically route reminder phrasings.

    Returns 'calendar' when a reminder wording appears with a temporal anchor
    — a clock hour (timed event) or a day/date (all-day event). 'memory'
    remains only for a bare recollection ('şunu hatırla') or a reminder with
    NO temporal anchor at all ('remind me to buy milk', 'eve dönünce...'),
    and None when no reminder wording is present.
    """
    ml = message.lower()
    if not (
        any(w in ml for w in _REMINDER_WORDS)
        or any(w in ml for w in _REMINDER_VERBS)
    ):
        return None
    # Explicit negation ("hatırlatma", "don't remind") -> memory, not calendar
    if _NEGATION_PATTERN.search(ml):
        return "memory"
    if _CLOCK_SIGNAL_PATTERN.search(ml) or _DATE_SIGNAL_PATTERN.search(ml):
        return "calendar"
    return "memory"


def _has_recent_email_context(history: list[dict]) -> bool:
    for m in history[-8:]:
        content = m.get("content") or m.get("text") or ""
        if not isinstance(content, str):
            continue
        low = content.lower()
        if any(mk in low for mk in _EMAIL_CTX_MARKERS):
            return True
    return False


def contextual_email_followup(message: str, history: list[dict]) -> bool:
    """True if the message is a follow-up reference to a previously listed email."""
    if not _FOLLOWUP_RE.search(message):
        return False
    return _has_recent_email_context(history)


# Prompt fed to the LLM when INTENT_LLM_FALLBACK=on
_INTENT_PROMPT = (
    "Classify the user's message into one of these categories:\n\n"
    "weather — check weather, temperature, forecast\n"
    "email — list, read, send, search emails\n"
    "calendar — create, list, update, change, delete calendar events\n"
    "tasks — create, list, complete, delete, search tasks\n"
    "notes — create, read, update, delete, list, search notes\n"
    "memory — save or recall memories/facts about the user\n"
    "question — general knowledge, opinions, conversation, coding help, translation, math, greetings\n\n"
    "A request phrased as a question (e.g. 'could you list...', 'can you check...') "
    "is still the action category if it involves personal data or tools.\n\n"
    "Respond with ONLY one word: weather, email, calendar, tasks, notes, memory, or question."
)

_TOOL_EMBED_CORPUS: list[tuple[str | None, str]] = [
    ("weather", "what is the weather, temperature, forecast, check weather in city, is it raining"),
    ("weather", "hava durumu, kac derece, sicaklik, hava tahmini, yagmur yagiyor mu"),
    ("weather", "wie ist das wetter, temperatur, vorhersage, regnet es"),
    ("weather", "quel temps fait-il, météo, température, prévisions, pleut-il"),
    ("weather", "cómo está el clima, temperatura, pronóstico, llueve"),
    ("weather", "الطقس، درجة الحرارة، توقعات الطقس"),
    ("email", "send email, check inbox, read mail, search emails, compose message, check my email"),
    ("email", "e-posta gönder, posta kutusu, e-posta oku, e-posta ara, mesaj oluştur"),
    ("email", "email senden, posteingang prüfen, nachrichten lesen, emails suchen"),
    ("email", "envoyer un email, boîte de réception, lire les messages, chercher des emails"),
    ("email", "enviar correo, bandeja de entrada, leer correos, buscar correos"),
    ("calendar", "create event, add meeting, list calendar, schedule appointment, what's on my calendar"),
    ("calendar", "change event, update event, modify event, reschedule, edit event, move event, shift event, change time, update time"),
    ("calendar", "could you change the event, can you update the time, would you reschedule, please change the time, edit my calendar"),
    ("calendar", "takvime ekle, etkinlik oluştur, randevu planla, takvimimi göster"),
    ("calendar", "etkinlik değiştir, etkinlik güncelle, saatini değiştir, ertele, yeniden planla, etkinlik düzenle"),
    ("calendar", "etkinlik sil, etkinlik kaldır, takvimden sil, iptal et"),
    ("calendar", "termin erstellen, meeting planen, kalender anzeigen, event eintragen"),
    ("calendar", "termin ändern, termin verschieben, termin aktualisieren, uhrzeit ändern"),
    ("calendar", "créer un événement, ajouter au calendrier, rendez-vous, mon agenda"),
    ("calendar", "modifier événement, changer l'heure, déplacer, reprogrammer"),
    ("calendar", "crear evento, añadir al calendario, reunión, qué tengo en el calendario"),
    ("calendar", "cambiar evento, modificar evento, actualizar evento, cambiar hora"),
    ("calendar", "remind me, set a reminder, reminder at 9am, remind me tomorrow, scheduled reminder, "
                  "hatırlat, hatırlatıcı kur, saat dokuzda hatırlat, "
                  "erinnere mich, rappel-moi, recuérdame, pon un recordatorio"),
    # Free-slot / available time
    ("calendar", "find free slot, when am i free, available time, free time slot, boş saat, uygun saat, wann passt es, freier slot, horaire libre, créneau libre, hueco libre, horario libre"),
    # Move / reschedule
    ("calendar", "move event, reschedule, shift meeting, change time, etkinliği taşı, ertele, yeniden planla, verschieben, verlegen, déplacer, reporter, mover, reprogramar"),
    # Cancel / delete
    ("calendar", "cancel event, delete event, iptal et, takvimden sil, absagen, stornieren, annuler, supprimer, cancelar, eliminar"),
    # Recurring
    ("calendar", "recurring event, weekly meeting, monthly reminder, tekrarlayan, her hafta, her ay, wiederkehrend, wöchentlich, récurrent, hebdomadaire, recurrente, semanal"),
    ("tasks", "create task, to-do list, complete task, delete task, search tasks, what do I need to do"),
    ("tasks", "görev oluştur, yapılacaklar listesi, görevi tamamla, görev ara, görev sil"),
    ("tasks", "aufgabe erstellen, to-do-liste, aufgabe erledigen, aufgabe suchen"),
    ("tasks", "créer une tâche, liste de tâches, terminer une tâche, chercher des tâches"),
    ("tasks", "crear tarea, lista de tareas, completar tarea, buscar tareas"),
    ("tasks", "update task, edit task, change due date, postpone task, mark task done"),
    ("tasks", "görev güncelle, görevi değiştir, görevi ertele, görev tarihini değiştir, görevi tamamlandı işaretle"),
    ("notes", "create note, show notes, edit note, delete note, list notes, search notes, note taking"),
    ("notes", "not oluştur, notlarımı göster, notu düzenle, not sil, not ara, not defteri"),
    # Verb-first TR patterns: chip-style phrasings ('not düş') previously had
    # no seed here and embedding drifted to calendar on mixed sentences.
    ("notes", "not düş, not yaz, not ekle, hatırlatıcı bırak"),
    ("notes", "notiz erstellen, notizen anzeigen, notiz bearbeiten, notiz suchen"),
    ("notes", "créer une note, afficher les notes, modifier une note, chercher des notes"),
    ("notes", "crear nota, mostrar notas, editar nota, buscar notas, bloc de notas"),
    ("memory", "remember this, save fact about me, store my preference, recall information, don't forget"),
    ("memory", "hatırla, tercihlerimi kaydet, kişisel bilgilerimi sakla, unutma"),
    ("memory", "merken, erinnere dich, speichere information, behalte das"),
    ("memory", "souviens-toi, retiens cette information, mémo, enregistre"),
    ("memory", "recuerda esto, guarda información sobre mí, no olvides"),
    (None, "general question, tell me a joke, explain, give advice, translate, help with code, solve math, what do you think, how does it work, fact, opinion"),
    (None, "genel soru, sohbet, fikir sor, komik bir şey söyle, yardım et, açıkla, ne düşünüyorsun"),
    (None, "allgemeine frage, gespräch, hilf mir, erkläre etwas, rate etwas, was denkst du"),
    (None, "question générale, conversation, aide-moi, explique quelque chose, donne ton avis"),
    (None, "pregunta general, conversación, ayúdame, explica algo, qué piensas"),
    (None, "سؤال عام، محادثة، ساعدني، اشرح لي"),
    (None, "what time is it, current date and time, tell me the time, today's date, what's the date"),
    (None, "saat kaç, bugün günlerden ne, tarih nedir, saati söyle, bugünün tarihi"),
    (None, "wie spät ist es, welches datum haben wir, wieviel uhr ist es"),
    (None, "quelle heure est-il, quelle est la date, donner l'heure"),
    (None, "qué hora es, qué fecha es hoy, dime la hora"),
    ("utility", "what time is it, current time, what date, today's date, saat kaç, bugün günlerden ne, wie spät, quelle heure, qué hora"),
    ("utility", "weather forecast, should i bring umbrella, hava nasıl, regnet es, va pleuvoir, va llover, şemsiye lazım mı"),
    (None, "hello hi hey good morning good evening how are you what's up nice to meet you thank you thanks please sorry excuse me goodbye see you later have a great day"),
    (None, "merhaba selam günaydın iyi akşamlar nasılsın naber tanıştığımıza memnun oldum teşekkürler lütfet özür dilerim hoşça kal görüşürüz iyi günler"),
    (None, "hallo guten morgen guten abend wie geht's dir freut mich danke bitte entschuldigung tschüss auf wiedersehen"),
    (None, "bonjour salut bonsoir comment ça va enchanté merci s'il vous plaît pardon au revoir à bientôt"),
    (None, "hola buenos días buenas tardes cómo estás encantado gracias por favor lo siento adiós hasta luego"),
]

_tool_embed_cache: list[tuple[str | None, str, bytes]] | None = None
_tool_embed_lock = asyncio.Lock()


async def _get_tool_embeddings() -> list[tuple[str | None, str, bytes]]:
    global _tool_embed_cache
    if _tool_embed_cache is not None:
        return _tool_embed_cache
    async with _tool_embed_lock:
        if _tool_embed_cache is not None:
            return _tool_embed_cache
        try:
            from embedding import embed_batch_async
            descriptions = [desc for _, desc in _TOOL_EMBED_CORPUS]
            vecs = await embed_batch_async(descriptions)
            _tool_embed_cache = [(group, desc, vec) for (group, desc), vec in zip(_TOOL_EMBED_CORPUS, vecs)]
            logger.info("Tool embedding corpus loaded (intent routing)")
        except Exception as e:
            logger.warning(f"Tool embedding corpus failed: {e}, intent routing disabled")
            _tool_embed_cache = []
        return _tool_embed_cache


# Short/ambiguous keywords matched with space boundaries — bare substring
# collided with common words ('çıkar' contains 'kar'; 'kart' too).
_AMBIGUOUS_KW = {"kar"}

# "hatırla" (remember) must not swallow the reminder family ("hatırlat",
# "hatırlatıcı", "hatırlatma") — those route to calendar via reminder_group()
# when a time/date is present and to memory otherwise, never as an
# accidental substring hit.
_HATIRLA_NOT_REMIND = re.compile(r"hatırla(?!t)", re.IGNORECASE)


def _kw_hit(kw: str, ml: str) -> bool:
    if kw == "hatırla":
        return bool(_HATIRLA_NOT_REMIND.search(ml))
    if kw in _AMBIGUOUS_KW:
        return f" {kw} " in f" {ml} "
    return kw in ml


async def _audit_intent(message: str, chosen_group: str | None,
                        best_sim: float | None, margin: float | None,
                        source: str) -> None:
    """Fire-and-forget ambiguity record. Never raises, never delays routing."""
    try:
        from db import log_intent_audit
        await log_intent_audit(message[:500], chosen_group, best_sim, margin, source)
    except Exception as e:
        logger.warning(f"Intent audit skipped (source={source}): {e}")


_KEYWORD_CHECKS = (
    (["hava", "derece", "sıcaklık", "sicaklik", "tahmini", "yağmur", "yagmur", "rüzgar", "ruzgar", "kar", "bulut", "forecast", "prognoz", "vorhersage", "prévisions", "pronóstico"], "weather"),
    (["etkinlik", "takvim", "randevu", "toplantı", "olay"], "calendar"),
    # 'gönder' generic ama tek araç-evreninde gönderim=email; multi-domain
    # tespiti için de kritik ('hava durumunu maille gönder' sınıfı).
    (["email", "e-posta", "eposta", "posta", "gelen kutusu", "ileti", "mesaj", "mail",
      "gönder", "gonder"], "email"),
    (["görev", "gorev", "yapılacak", "yapilacak", "task", "todo", "yapmam gereken"], "tasks"),
    # Bare "not" deliberately absent: it collides with English negation
    # ("I could NOT find it") and routed pure chat to the notes group.
    # Distinctive suffixed/frozen forms cover Turkish inflections instead.
    (["notlar", "notu", "nota", "not defteri", "not oluştur", "not al", "note",
      "not düş", "not yaz"], "notes"),
    (["hatırla", "hatirla", "unutma", "sakla", "kaydet", "remember", "don't forget", "save"], "memory"),
    # Utility: pure info questions needing real-time data (no personal data action)
    (["saat kaç", "saat kac", "bugün günlerden ne", "tarih nedir", "saati söyle", "bugünün tarihi",
      "what time", "what date", "today's date", "current time",
      "wie spät", "welches datum", "wieviel uhr",
      "quelle heure", "quelle date", "donne l'heure",
      "qué hora", "qué fecha", "dime la hora",
      "hava nasıl", "hava nasil", "should i bring", "şemsiye", "semsiye", "umbrella",
      "regnet es", "va pleuvoir", "va llover"], "utility"),
)


def _keyword_group(message: str) -> str | None:
    """Cheap substring heuristics. Order matters: first hit wins."""
    ml = message.lower()
    reminder = reminder_group(message)
    if reminder:
        return reminder
    for kws, group in _KEYWORD_CHECKS:
        if any(_kw_hit(kw, ml) for kw in kws):
            return group
    return None


def _hit_groups(message: str) -> set[str]:
    """All groups whose keywords appear in the message."""
    ml = message.lower()
    groups = {group for kws, group in _KEYWORD_CHECKS
              if any(_kw_hit(kw, ml) for kw in kws)}
    reminder = reminder_group(message)
    if reminder:
        # 'hatırlatıcı' must never re-enter memory via the 'hatırla' substring,
        # but a reminder may still coexist with another domain ('... hatırlat
        # ve görev oluştur') — keep the union so multi-domain routing sees it.
        groups.add(reminder)
    return groups


def tool_group_keys() -> tuple[str, ...]:
    """Canonical machine-readable group keys of the tool taxonomy.

    Derived from _KEYWORD_CHECKS — the same table _hit_groups enumerates —
    so the API contract can never drift from the intent classifier's own
    group set. Sorted for a stable, order-independent response.
    """
    return tuple(sorted({group for _, group in _KEYWORD_CHECKS}))


async def _classify_intent(message: str, query_embedding: bytes | None = None) -> tuple[str, str | None]:
    # Reminder routing is deterministic and trumps embedding/keywords so it
    # can never flip on margin noise ("perşembe saat 9'da hatırlat" -> memory).
    try:
        reminder = reminder_group(message)
        if reminder:
            others = _hit_groups(message) - {reminder}
            if others:
                # "... hatırlat ve görev oluştur" — a reminder plus another
                # domain needs the combined toolset, not calendar alone.
                await _audit_intent(message, ",".join(sorted({reminder} | others)), None, None,
                                    "reminder_multi")
                logger.info(f"Reminder {reminder} + other domains {sorted(others)} — combined (message={message!r})")
                return "action", None
            await _audit_intent(message, reminder, None, None, "reminder_rule")
            logger.info(f"Intent=action group={reminder} via reminder rule (message={message!r})")
            return "action", reminder
    except Exception as e:
        logger.warning(f"Reminder pre-check failed (non-fatal): {e}")
    # Multi-domain free text ("hava durumu bilgisini maille gönder"): two or
    # more distinct groups matched → offer the COMBINED toolset so the model
    # can chain tools itself. Single-group routing would strand the second
    # domain (field case: weather fetched but send_email never offered).
    try:
        hit_groups = _hit_groups(message)
        if len(hit_groups) >= 2:
            logger.info(f"Multi-domain keyword hits {sorted(hit_groups)} — combined tools (message={message!r})")
            await _audit_intent(message[:500], ",".join(sorted(hit_groups)), None, None,
                                "multi_domain_combined")
            return "action", None
    except Exception as e:
        logger.warning(f"Multi-domain pre-check failed (non-fatal): {e}")


    try:
        from embedding import cosine_similarity, embed_async
        corpus = await _get_tool_embeddings()
        if corpus:
            if query_embedding is not None:
                msg_vec = query_embedding  # already computed upstream (shared)
            else:
                msg_vec = await embed_async(message)
            best_sim = 0.0
            second_sim = 0.0
            best_group = None
            for group, _desc, emb_bytes in corpus:
                sim = cosine_similarity(msg_vec, emb_bytes)
                if sim > best_sim:
                    second_sim = best_sim
                    best_sim = sim
                    best_group = group
                elif sim > second_sim:
                    second_sim = sim
            margin = best_sim - second_sim
            if best_sim >= 0.50 and margin >= 0.05:
                if best_group is not None:
                    # Thin margins flip easily on near-neighbour phrases; when a
                    # keyword fires for a DIFFERENT group, trust it.
                    # (Real-world case: a notes request routed to memory at margin .06.)
                    if margin < 0.10:
                        kw_group = _keyword_group(message)
                        if kw_group and kw_group != best_group:
                            logger.info(
                                f"Embedding chose {best_group} but keyword says {kw_group} "
                                f"(sim={best_sim:.2f}, margin={margin:.2f}) -> keyword wins (message={message!r})"
                            )
                            await _audit_intent(message, kw_group, best_sim, margin, "thin_margin")
                            return "action", kw_group
                    if margin < 0.10:
                        await _audit_intent(message, best_group, best_sim, margin, "thin_margin")
                    logger.info(f"Intent=action group={best_group} via embedding (sim={best_sim:.2f}, margin={margin:.2f}, message={message!r})")
                    return "action", best_group
                logger.info(f"Intent=question via embedding (sim={best_sim:.2f}, margin={margin:.2f}, message={message!r})")
                return "question", None
            logger.info(f"Embedding uncertain (sim={best_sim:.2f}, margin={margin:.2f}), trying keyword heuristics")
    except Exception as e:
        logger.warning(f"Embedding intent routing failed: {e}")

    kw_group = _keyword_group(message)
    if kw_group:
        await _audit_intent(message, kw_group, None, None, "keyword_fallback")
        logger.info(f"Intent=action group={kw_group} via keyword (message={message!r})")
        return "action", kw_group

    # Optional LLM fallback — improves accuracy but adds ~15s delay before streaming starts.
    if get("INTENT_LLM_FALLBACK", "off") == "on":
        backend = (get("LLM_BACKEND", "litert") or "litert").strip().lower()
        client = _get_client()
        model_name = get("LLM_MODEL", "gemma4-e2b")
        payload = {
            "model": model_name.replace(":", "-") if backend == "litert" else model_name,
            "messages": [
                {"role": "system", "content": _INTENT_PROMPT},
                {"role": "user", "content": message},
            ],
            "stream": False,
            "max_tokens": 20,
            "max_completion_tokens": 20,
        }
        if backend == "litert":
            url = f"{LITERT_BASE_URL}/v1/chat/completions"
        else:
            # Explicit think=False: thinking-capable models (gemma4) otherwise
            # burn the tiny num_predict budget on hidden reasoning -> slow,
            # always-empty classification.
            payload["think"] = False
            payload["options"] = {"temperature": 0, "num_predict": 20, "num_ctx": 512}
            payload["keep_alive"] = get("LLM_KEEP_ALIVE", "4h")
            url = f"{OLLAMA_BASE_URL}/api/chat"
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            rj = resp.json()
            if backend == "litert":
                answer = rj["choices"][0]["message"]["content"].strip().lower()
            else:
                answer = rj["message"]["content"].strip().lower()
            valid_groups = {"weather", "email", "calendar", "tasks", "notes", "memory"}
            if answer in valid_groups:
                logger.info(f"Intent=action group={answer} via LLM (raw={answer!r})")
                return "action", answer
            if "question" in answer:
                logger.info(f"Intent=question via LLM (raw={answer!r})")
                return "question", None
            logger.info(f"Intent=question via LLM (raw={answer!r})")
            return "question", None
        except Exception as e:
            logger.warning(f"Intent classification via LLM failed: {e}, falling back to question")

    logger.info(f"Intent=question via default (embedding+keywords uncertain, message={message!r})")
    return "question", None
