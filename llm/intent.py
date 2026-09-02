"""Intent classification: embedding + keyword heuristics, optional LLM fallback."""
import asyncio
import logging
import re
from pathlib import Path

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

# Domain markers that can be detected in RECENT CONVERSATION TEXT to infer
# what a follow-up refers to when no tool-execution record exists. Conservative:
# distinctive tokens only ("notu"/"notlar", never bare "not" which collides
# with English negation). Used by resolve_resume_context as the fallback
# evidence source behind the authoritative per-session tool-audit record.
_GROUP_CTX_MARKERS: dict[str, tuple[str, ...]] = {
    "weather": ("hava", "derece", "sıcaklık", "sicaklik", "yağmur", "yagmur",
                "tahmin", "weather", "wetter", "météo", "meteo", "temperatur", "lluvia"),
    "email": _EMAIL_CTX_MARKERS,
    "calendar": ("takvim", "etkinlik", "randevu", "toplantı", "toplanti",
                 "meeting", "kalender", "termin", "calendar", "event"),
    "tasks": ("görev", "gorev", "yapılacak", "yapilacak", "todo", "task", "aufgabe"),
    "notes": ("notlar", "notu", "notta", "not defteri", "not defter", "note", "notizen"),
    "memory": ("hatırla", "hatirla", "hatırlama", "hatirlama", "remember"),
}

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


def _has_recent_context(history: list[dict], markers: tuple[str, ...]) -> bool:
    for m in history[-8:]:
        content = m.get("content") or m.get("text") or ""
        if not isinstance(content, str):
            continue
        low = content.lower()
        if any(mk in low for mk in markers):
            return True
    return False


def _has_recent_email_context(history: list[dict]) -> bool:
    return _has_recent_context(history, _EMAIL_CTX_MARKERS)


def contextual_email_followup(message: str, history: list[dict]) -> bool:
    """True if the message is a follow-up reference to a previously listed email."""
    if not _FOLLOWUP_RE.search(message):
        return False
    return _has_recent_email_context(history)


# ── contextual dependency ──────────────────────────────────────────────────────
# Some user utterances are ANAPHORIC follow-ups: they only make sense inside the
# conversation they reference ("devam edelim en son epostayı gönderiyordun").
# As standalone intent examples they say nothing about the requested tool and
# actively poison embedding routing (confirmed: they drag unrelated future
# queries into the tool group). Industry practice (curated few-shot sets +
# quality gates) rejects such examples instead of feeding them. The SAME gate
# is what the live classifier uses to defer such messages to the session
# resolver instead of trusting utterance-only embedding/keyword/LLM guesses.
_CONTEXT_OPENERS = (
    "devam edelim", "devam etmek istiyorum",
    "devam edelim mi", "devam et", "devam etsin",
    "sürdürelim", "sürdür", "kaldığımız yerden", "kaldığı yerden",
    "nerede kalmıştık", "nerede kalmışız", "yine", "şimdi de",
    "az önce", "önceki", "sıradaki", "diğer",
    # EN: phrase-level continuation openers (strongly anaphoric)
    "let's continue", "lets continue", "let us continue",
    "continue where we left off",
    "pick up where we left", "pick up where i left",
    "where were we", "where did we leave off",
    "carry on from where",
    # DE: phrase-level continuation openers
    "wo waren wir", "lass uns weitermachen", "lass uns dort weitermachen",
    "machen wir weiter wo", "wir waren wo",
    # FR
    "où en étions", "ou en etions", "on reprend où", "reprenons où",
    # ES
    "dónde estábamos", "donde estabamos", "sigamos", "continuemos",
)
# Progressive-past suffixes mark action-still-in-progress, which implies
# previous context ("düzenliyordun", "gönderiyordun", "yazıyordunuz").
_CONTEXT_PROGRESSIVE_PAST = re.compile(
    r"\b\w+(?:ıyor|iyor|uyor|üyor|yordun|yordunuz|yorduk|yordum)\b", re.IGNORECASE
)
# Reference to a previous by-gone action ("konuştuğumuz", "yaptığımız",
# "söylediğim", ...). Deliberately NOT including bare time markers like
# "en son" / "az önce" — those legitimately open fresh commands too
# ("en son mailleri göster"), so they must not gate alone.
_CONTEXT_ANAPHORIC = re.compile(
    r"(kaldığımız yerden|kaldığı yerden|hangi konudaydık|yaptığımız|"
    r"konuştuğumuz|bahsettiğim|söylediğim|yazdığım|düzenliyordun|"
    r"gönderiyordun|yapıyordun|listeliyordun|bakıyordun|izliyordun)",
    re.IGNORECASE,
)

# Progressive-past / reference-to-action-in-progress in other languages. These
# are deliberately phrase/suffix-agnostic regex gates: unlike Turkish (whose
# "-ıyordu + -dun" suffixes mark an interrupted in-progress action), EN/DE/FR/ES
# express the same idea with auxiliary verbs ("we were …ing", "wo waren wir
# bei", "on était en train de", "estábamos a punto de") or with a demonstrative
# referring back to a just-discussed object ("the … i was …ing", "the one we
# were"). To keep the gate SAFE (user decision: narrow over broad), only
# strongly demonstrative / object-anchored patterns qualify — a bare "i was
# \w+ing" like "i was thinking about the weather" would wrongly swallow a fresh
# command, so it is excluded. Same caution as Turkish "az önce" / "önceki".
_CONTEXT_PROGRESSIVE_PAST_I18N = re.compile(
    r"the \w+ i was\s+\w+ing"             # EN demonstrative "the email i was sending"
    r"|the \w+ we were\s+\w+ing"          # EN "the notes we were editing"
    r"|the one i was\s+\w+ing"            # EN "the one i was reading"
    r"|the one we were\s+\w+ing"          # EN "the one we were on"
    r"|there we were\s+\w+ing"            # EN "there we were working on"
    r"|wir waren bei\s+\w+in\b"           # DE demonstrative progressive
    r"|wo waren wir stehen geblieben"     # DE "where we had left off"
    r"|celui que j['']?étais en train de\s+\w+"   # FR "the one i was …ing"
    r"|on était en train de\s+\w+"        # FR "we were in the middle of"
    r"|on était en train d['']\w+"        # FR with elision
    r"|estábamos\s+\w+ndo\b"              # ES gerund "estábamos enviando"
    r"|el \w+ que estaba\s+\w+ndo\b"      # ES "el correo que estaba escribiendo"
    r"|la \w+ que estaba\s+\w+ndo\b",     # ES feminine "la nota que estaba editando"
    re.IGNORECASE,
)


def _is_context_dependent(text: str) -> bool:
    """True when the utterance is an anaphoric follow-up, not a standalone intent.

    These carry no meaning outside their conversation and must never be fed to
    the corpus — see `_CONTEXT_OPENERS` for the phrase gates and
    `_CONTEXT_PROGRESSIVE_PAST` / `_CONTEXT_ANAPHORIC` (Turkish) plus
    `_CONTEXT_PROGRESSIVE_PAST_I18N` (EN/DE/FR/ES) for the verb-based gates.
    """
    t = text.strip().lower()
    if not t:
        return False
    for opener in _CONTEXT_OPENERS:
        if t.startswith(opener):
            return True
    if _CONTEXT_PROGRESSIVE_PAST.search(t):
        return True
    if _CONTEXT_ANAPHORIC.search(t):
        return True
    if _CONTEXT_PROGRESSIVE_PAST_I18N.search(t):
        return True
    return False


def is_contextual_followup(message: str) -> bool:
    """Public alias of the context-dependency gate used by the chat router."""
    return _is_context_dependent(message)


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
    (None, "hello hi hey good morning good evening how are you what's up nice to meet you thank you thanks please sorry excuse me goodbye see you later have a great day"),
    (None, "merhaba selam günaydın iyi akşamlar nasılsın naber tanıştığımıza memnun oldum teşekkürler lütfet özür dilerim hoşça kal görüşürüz iyi günler"),
    (None, "hallo guten morgen guten abend wie geht's dir freut mich danke bitte entschuldigung tschüss auf wiedersehen"),
    (None, "bonjour salut bonsoir comment ça va enchanté merci s'il vous plaît pardon au revoir à bientôt"),
    (None, "hola buenos días buenas tardes cómo estás encantado gracias por favor lo siento adiós hasta luego"),
]

_tool_embed_cache: list[tuple[str | None, str, bytes]] | None = None
_tool_embed_lock = asyncio.Lock()
# mtime of additions.jsonl when the cache was last built; a change triggers an
# automatic in-process rebuild, so corpus_feeder additions go LIVE without any
# service restart.
_tool_embed_mtime: float | None = None

_ADDITIONS_PATH = Path(__file__).resolve().parent.parent / "corpus_data" / "additions.jsonl"


def _additions_mtime() -> float | None:
    """Get the feeder additions file mtime, or None when absent/deleted."""
    try:
        return _ADDITIONS_PATH.stat().st_mtime if _ADDITIONS_PATH.exists() else None
    except OSError:
        return None


def _additional_corpus() -> list[tuple[str | None, str]]:
    """Load corpus examples appended by corpus_feeder.py (additions.jsonl).

    Returned fresh on each call; the embedding cache is rebuilt automatically
    (see _get_tool_embeddings) whenever this file changes, so a feeder run
    takes effect live without restarting the service.
    """
    try:
        if not _ADDITIONS_PATH.exists():
            return []
        out: list[tuple[str | None, str]] = []
        import json as _json
        for line in _ADDITIONS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = _json.loads(line)
            grp = rec.get("group")
            out.append((grp, rec.get("text", "")))
        return out
    except Exception:
        return []


def reset_tool_embed_cache() -> None:
    """Force the tool-embedding corpus to rebuild on the next classification.

    Used by the admin reload path and tests; safe under concurrent requests
    because the rebuild itself happens under _tool_embed_lock.
    """
    global _tool_embed_cache, _tool_embed_mtime
    _tool_embed_cache = None
    _tool_embed_mtime = None


async def _get_tool_embeddings() -> list[tuple[str | None, str, bytes]]:
    global _tool_embed_cache, _tool_embed_mtime
    # Fast path: cache hit AND the feeder's additions file is unchanged.
    mtime = _additions_mtime()
    if _tool_embed_cache is not None and mtime == _tool_embed_mtime:
        return _tool_embed_cache
    async with _tool_embed_lock:
        # Double-check under the lock: another task may have rebuilt meanwhile.
        mtime = _additions_mtime()
        if _tool_embed_cache is not None and mtime == _tool_embed_mtime:
            return _tool_embed_cache
        try:
            from embedding import embed_batch_async
            entries = list(_TOOL_EMBED_CORPUS) + _additional_corpus()
            descriptions = [desc for _, desc in entries]
            vecs = await embed_batch_async(descriptions)
            _tool_embed_cache = [(group, desc, vec) for (group, desc), vec in zip(entries, vecs)]
            _tool_embed_mtime = mtime
            logger.info(f"Tool embedding corpus loaded (intent routing, {len(entries)} entries, mtime={mtime})")
        except Exception as e:
            logger.warning(f"Tool embedding corpus failed: {e}, intent routing disabled")
            _tool_embed_cache = []
            _tool_embed_mtime = mtime
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
    (["hava", "derece", "sıcaklık", "sicaklik", "tahmini", "yağmur", "yagmur", "rüzgar", "ruzgar", "kar", "bulut", "forecast", "prognoz", "vorhersage", "prévisions", "pronóstico",
      "weather", "temperature", "rain", "snow", "humidity", "windy", "forecast"], "weather"),
    (["etkinlik", "takvim", "randevu", "toplantı", "olay",
      "event", "meeting", "appointment", "schedule", "calendar", "agenda"], "calendar"),
    # 'gönder' generic ama tek araç-evreninde gönderim=email; multi-domain
    # tespiti için de kritik ('hava durumunu maille gönder' sınıfı).
    (["email", "e-posta", "eposta", "posta", "gelen kutusu", "ileti", "mesaj", "mail",
      "gönder", "gonder", "send", "compose", "inbox", "draft"], "email"),
    (["görev", "gorev", "yapılacak", "yapilacak", "task", "todo", "yapmam gereken",
      "to-do", "deadline", "assignment", "chore"], "tasks"),
    # Bare "not" deliberately absent: it collides with English negation
    # ("I could NOT find it") and routed pure chat to the notes group.
    # Distinctive suffixed/frozen forms cover Turkish inflections instead.
    (["notlar", "notu", "nota", "not defteri", "not oluştur", "not al", "note",
      "not düş", "not yaz", "memo", "notes"], "notes"),
    (["hatırla", "hatirla", "unutma", "sakla", "kaydet", "remember", "don't forget", "save",
      "memorize", "recall"], "memory"),
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
    # Anaphoric follow-ups ("devam edelim son yaptığımız işe") cannot be routed
    # from the utterance alone: their words point at a previous conversation
    # turn, and embedding similarity on the fragment is ACTIVELY misleading
    # (field case: an anaphoric notes follow-up kept labelling as email, which
    # is what poisoned the corpus in the first place). Explicit domain keywords
    # still win — the user is naming the domain right now. Everything else is
    # deferred (returned as question) to the chat router's session resolver
    # (Layer 0: last tool executed; Layer 1: LLM + evidence verification)
    # instead of an utterance-only guess.
    try:
        if _is_context_dependent(message):
            ctx_groups = _hit_groups(message)
            if not ctx_groups:
                await _audit_intent(message, None, None, None, "context_dependent_deferred")
                logger.info(f"Context-dependent follow-up deferred (message={message!r})")
                return "question", None
            if len(ctx_groups) >= 2:
                await _audit_intent(message, ",".join(sorted(ctx_groups)), None, None,
                                    "context_dependent_multi")
                logger.info(f"Context-dependent follow-up with domains {sorted(ctx_groups)} — combined (message={message!r})")
                return "action", None
            group = next(iter(ctx_groups))
            await _audit_intent(message, group, None, None, "context_keyword")
            logger.info(f"Intent=action group={group} via keyword (context-dependent, message={message!r})")
            return "action", group
    except Exception as e:
        logger.warning(f"Context-dependent pre-check failed (non-fatal): {e}")
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
    # Runs ONLY for standalone (non-context-dependent) messages; anaphoric
    # follow-ups are deferred by the gate above and resolved by the router.
    if get("INTENT_LLM_FALLBACK", "off") == "on":
        answer = await _llm_classify_call(_INTENT_PROMPT, message, max_tokens=20)
        if answer is not None:
            valid_groups = {"weather", "email", "calendar", "tasks", "notes", "memory"}
            if answer in valid_groups:
                logger.info(f"Intent=action group={answer} via LLM (raw={answer!r})")
                return "action", answer
            logger.info(f"Intent=question via LLM (raw={answer!r})")
            return "question", None

    logger.info(f"Intent=question via default (embedding+keywords uncertain, message={message!r})")
    return "question", None


async def _llm_classify_call(system: str, user: str, max_tokens: int = 20) -> str | None:
    """Run a single-token-budget LLM classification call (litert or ollama).

    Shared by the _classify_intent fallback and the evidence-verified
    follow-up resolver (llm_resolve_with_evidence). Returns the normalized,
    lowercased raw content or None on any failure — never raises.
    """
    backend = (get("LLM_BACKEND", "litert") or "litert").strip().lower()
    client = _get_client()
    model_name = get("LLM_MODEL", "gemma4-e2b")
    payload = {
        "model": model_name.replace(":", "-") if backend == "litert" else model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "max_tokens": max_tokens,
        "max_completion_tokens": max_tokens,
    }
    try:
        if backend == "litert":
            url = f"{LITERT_BASE_URL}/v1/chat/completions"
        else:
            # Explicit think=False: thinking-capable models (gemma4) otherwise
            # burn the tiny num_predict budget on hidden reasoning -> slow,
            # always-empty classification.
            payload["think"] = False
            payload["options"] = {"temperature": 0, "num_predict": max_tokens, "num_ctx": 512}
            payload["keep_alive"] = get("LLM_KEEP_ALIVE", "4h")
            url = f"{OLLAMA_BASE_URL}/api/chat"
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        rj = resp.json()
        if backend == "litert":
            return rj["choices"][0]["message"]["content"].strip().lower()
        return rj["message"]["content"].strip().lower()
    except Exception as e:
        logger.warning(f"Intent classification via LLM failed: {e}, falling back to question")
        return None


# ── contextual follow-up resolver (Layer 0 / Layer 1) ─────────────────────────
# When _is_context_dependent() defers a message, the chat router resolves it from
# the SESSION, never the utterance alone:
#   Layer 0 — deterministic: the last successfully executed tool of the session
#             is what "devam edelim" refers to; mapped to its group via
#             TOOL_TO_GROUP. No model call, no guess.
#   Layer 1 — LLM verdict WITH history + evidence verification: the model must
#             produce a supporting verbatim fragment from the conversation and
#             only a history-backed verdict is trusted (the "don't trust chance"
#             principle — a fabricated evidence gets discarded, not routed).
# Shared utility tools (get_datetime lives in every group) are never evidence.


async def _last_executed_tool_group(session_id: str) -> str | None:
    """Determine the group of the last successfully executed tool in a session.

    "Successfully executed" means *either* the tool is outside the backend
    verification scope (no verification_status is ever produced for it, so a
    successful heuristic result stands) *or* it is a verified create
    (``verified`` / ``verified_by_fallback``). An unconfirmed create
    (``unverified`` / ``verification_failed``) must NOT anchor the session —
    the audit check rejects these just like a failed call.
    """
    try:
        from db import get_db
        from tools.definitions import TOOL_GROUPS, TOOL_TO_GROUP

        db = await get_db()
        async with db.execute(
            """SELECT a.tool_name FROM tool_audit_log a
               JOIN conversations m ON m.id = a.conversation_id
               WHERE m.session_id = ? AND a.conversation_id IS NOT NULL
                 AND a.is_summary = 0 AND a.success = 1
                 AND (a.verification_status IS NULL
                      OR a.verification_status IN ('verified', 'verified_by_fallback'))
               ORDER BY a.id DESC LIMIT 1""",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        tool = row[0]
        # Tools shared across groups (get_datetime) carry no domain evidence.
        membership = sum(1 for names in TOOL_GROUPS.values() for n in names if n == tool)
        if membership > 1:
            return None
        return TOOL_TO_GROUP.get(tool)
    except Exception as e:
        logger.warning(f"Last-tool resolver failed (non-fatal): {e}")
        return None


async def resolve_resume_context(message: str, history: list[dict],
                                 session_id: str | None = None) -> str | None:
    """Layer 0: deterministically route an anaphoric follow-up, no model call.

    Returns the group the follow-up refers to, or None when there is no
    evidence in the session (genuinely ambiguous — caller moves to Layer 1).
    """
    if not _is_context_dependent(message):
        return None
    if session_id:
        group = await _last_executed_tool_group(session_id)
        if group:
            return group
    for group, markers in _GROUP_CTX_MARKERS.items():
        if _has_recent_context(history, markers):
            return group
    return None


_INTENT_EVIDENCE_PROMPT = (
    "The user's message refers to continuing an earlier task. Using only the "
    "supplied conversation history, decide which tool domain must be resumed.\n\n"
    "Domains: weather, email, calendar, tasks, notes, memory.\n"
    'Reply with ONLY JSON: {"group": "<domain>", "evidence": "<verbatim short '
    'fragment from the conversation supporting your choice>"}.\n'
    'If the history gives no support, group MUST be "question" and evidence '
    'MUST be "" (empty).'
)

_INTENT_JSON_RE = re.compile(
    r'"group"\s*:\s*"?([a-z]+)"?\s*,\s*"evidence"\s*:\s*"([^"]*)"', re.IGNORECASE
)

# High-frequency words that prove nothing about domain evidence.
_EVIDENCE_STOPWORDS = {
    "the", "and", "that", "with", "from", "this", "what", "for", "you",
    "user", "your", "want", "would", "said", "because", "about", "them",
    "then", "gibi", "icin", "için", "bir", "bunu", "şey", "var", "dedin",
}


def _verify_evidence(evidence: str, message: str, history: list[dict]) -> bool:
    """True when the model's supporting evidence actually matches the history.

    Numeric bar: at least half the substantive evidence tokens (minimum 1) must
    appear verbatim in the recent conversation window. A hallucinated quote
    ("you asked me to send the weekly report" with no such text anywhere) has
    zero overlap and is rejected — the fallback never guesses.
    """
    tokens = re.findall(r"[\wçğıöşüÇĞİÖŞÜ@.']+", (evidence or "").lower())
    tokens = [t for t in tokens if len(t) > 3 and t not in _EVIDENCE_STOPWORDS]
    unique = set(tokens)
    if not unique:
        return False
    window = (message + " " + " ".join(
        (m.get("content") or m.get("text") or "") for m in history[-8:]
    )).lower()
    present = sum(1 for t in unique if t in window)
    return present >= max(1, (len(unique) + 1) // 2)


async def llm_resolve_with_evidence(message: str, history: list[dict]) -> tuple[str, str | None]:
    """Layer 1: LLM verdict on a deferred follow-up, gated by evidence.

    The model sees the recent history and returns {group, evidence}; the
    evidence must be verifiable against the conversation for the group to be
    accepted. Unverified verdicts degrade to "question" and are audit-logged
    (source llm_rejected_evidence) so the correction data accumulates for the
    corpus without ever misrouting a session.
    """
    if get("INTENT_LLM_FALLBACK", "off") != "on":
        return "question", None
    valid_groups = {"weather", "email", "calendar", "tasks", "notes", "memory"}
    try:
        snippets = []
        for m in history[-8:]:
            role = m.get("role") or m.get("type") or "?"
            content = (m.get("content") or m.get("text") or "").strip()
            if content:
                snippets.append(f"{role}: {content[:200]}")
        if not snippets:
            return "question", None
        user_body = message + "\n\nConversation (most recent first):\n" + "\n".join(snippets)
        raw = await _llm_classify_call(_INTENT_EVIDENCE_PROMPT, user_body, max_tokens=120)
        if not raw:
            return "question", None
        m = _INTENT_JSON_RE.search(raw)
        if not m:
            await _audit_intent(message, None, None, None, "llm_rejected_evidence")
            logger.info(f"LLM evidence response unparsable (raw={raw!r}) — question")
            return "question", None
        group, evidence = m.group(1).lower(), m.group(2)
        if group == "question":
            return "question", None
        if group in valid_groups and _verify_evidence(evidence, message, history):
            await _audit_intent(message, group, None, None, "llm_verified")
            logger.info(f"Intent=action group={group} via LLM with verified evidence (message={message!r})")
            return "action", group
        await _audit_intent(message, group, None, None, "llm_rejected_evidence")
        logger.info(f"LLM verdict {group!r} discarded — evidence unverified (message={message!r})")
        return "question", None
    except Exception as e:
        logger.warning(f"LLM evidence resolution failed (non-fatal): {e}")
        return "question", None
