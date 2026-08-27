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
)

# Time/date signals that turn a reminder request into a calendar event.
# Numeric hours with the Turkish locative suffixes (9'da / 3'te / 09:00),
# clock words, day names and relative terms — EN/TR/DE/FR/ES, matching the
# embedding corpus languages.
_TIME_SIGNAL_PATTERN = re.compile(
    r"("
    # 9'da / 3'te / 9da / 09:00'da · also bare HH:MM clocks
    r"\b\d{1,2}(?::\d{2})?\s*'?[tdTD]?[ae]\b"
    r"|\b\d{1,2}:\d{2}(?:\s*'?[tdTD]?[ae]\b|\s*(?:am|pm)\b)?"
    r"|\b\d{1,2}\s*(?:saat|o'?clock|am|pm|uhr|heures?|hora)\b"
    # day names
    r"|\b(?:pazartesi|sal[ıi]|çarşamba|carsamba|perşembe|persembe|cuma|cumartesi|pazar"
    r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag"
    r"|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche"
    r"|lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)\b"
    # clock words on their own (saat dokuzda)
    r"|\b(?:saat|o'?clock|uhr|heure|hora)\b"
    # relative terms
    r"|\b(?:yarın|yarin|bugün|bugun|öbür gün|obur gun|haftaya|gelecek hafta|sonraki hafta"
    r"|akşam|aksam|sabah|öğle|öğlen|ogle|oglen|gece|hafta sonu|haftasonu"
    r"|\d+\s*(?:gün|saat|dakika)\s*sonra|sonraki\s+\d+\s*(?:gün|saat)"
    r"|tomorrow|today|tonight|next week|this week|this evening|this morning|this afternoon"
    r"|in\s+\d+\s*(?:hour|hours|minute|minutes|week|weeks|day|days)"
    r"|morgen|heute|übermorgen|ubermorgen|heute abend|nächste woche|naechste woche"
    r"|in\s+\d+\s*(?:stunde|stunden|minuten?|tag|tage|tagen|woche|wochen)"
    r"|demain|ce soir|cet après-midi|cette semaine|la semaine prochaine"
    r"|dans\s+\d+\s*(?:heure|heures|minute|minutes|jour|jours)"
    r"|mañana|manana|hoy|esta tarde|esta noche|la semana que viene"
    r"|en\s+\d+\s*(?:hora|horas|minuto|minutos|d[ií]a|d[ií]as))"
    r")",
    re.IGNORECASE,
)


def reminder_group(message: str) -> str | None:
    """Deterministically route reminder phrasings.

    Returns 'calendar' when a reminder verb/word appears together with a
    time or date signal, 'memory' for a bare 'remember this' recollection,
    and None when no reminder wording is present at all.
    """
    ml = message.lower()
    if not any(w in ml for w in _REMINDER_WORDS):
        return None
    return "calendar" if _TIME_SIGNAL_PATTERN.search(ml) else "memory"


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
    (["hava", "derece", "sıcaklık", "sicaklik", "tahmini", "yağmur", "yagmur", "rüzgar", "ruzgar", "kar", "bulut"], "weather"),
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
    reminder = reminder_group(message)
    if reminder:
        # A reminder with a time is calendar, period — never merge it with
        # memory just because "hatırlatıcı" contains "hatırla" as substring.
        return {reminder}
    return {group for kws, group in _KEYWORD_CHECKS
            if any(_kw_hit(kw, ml) for kw in kws)}


async def _classify_intent(message: str, query_embedding: bytes | None = None) -> tuple[str, str | None]:
    # Reminder routing is deterministic and trumps embedding/keywords so it
    # can never flip on margin noise ("perşembe saat 9'da hatırlat" -> memory).
    try:
        reminder = reminder_group(message)
        if reminder:
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
