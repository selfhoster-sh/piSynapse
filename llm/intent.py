"""Intent classification: embedding + keyword heuristics, optional LLM fallback."""
import asyncio
import logging
import os

from config import LITERT_BASE_URL, LLM_KEEP_ALIVE, LLM_MODEL, OLLAMA_BASE_URL
from .utils import _get_client

logger = logging.getLogger("piSynapse")

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
    ("calendar", "değiştirir misin, günceller misin, düzenler misin, saatini değiştirir misin, zamanını değiştirir misin"),
    ("calendar", "etkinlik sil, etkinlik kaldır, takvimden sil, iptal et"),
    ("calendar", "termin erstellen, meeting planen, kalender anzeigen, event eintragen"),
    ("calendar", "termin ändern, termin verschieben, termin aktualisieren, uhrzeit ändern"),
    ("calendar", "kannst du den termin ändern, bitte die uhrzeit ändern"),
    ("calendar", "créer un événement, ajouter au calendrier, rendez-vous, mon agenda"),
    ("calendar", "modifier événement, changer l'heure, déplacer, reprogrammer"),
    ("calendar", "peux-tu modifier l'événement, changer l'heure"),
    ("calendar", "crear evento, añadir al calendario, reunión, qué tengo en el calendario"),
    ("calendar", "cambiar evento, modificar evento, actualizar evento, cambiar hora"),
    ("calendar", "podrías cambiar el evento, puedes modificar la hora"),
    ("tasks", "create task, to-do list, complete task, delete task, search tasks, what do I need to do"),
    ("tasks", "görev oluştur, yapılacaklar listesi, görevi tamamla, görev ara, görev sil"),
    ("tasks", "aufgabe erstellen, to-do-liste, aufgabe erledigen, aufgabe suchen"),
    ("tasks", "créer une tâche, liste de tâches, terminer une tâche, chercher des tâches"),
    ("tasks", "crear tarea, lista de tareas, completar tarea, buscar tareas"),
    ("notes", "create note, show notes, edit note, delete note, list notes, search notes, note taking"),
    ("notes", "not oluştur, notlarımı göster, notu düzenle, not sil, not ara, not defteri"),
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
            _tool_embed_cache = [
                (group, desc, vec.astype("float32").tobytes())
                for (group, desc), vec in zip(_TOOL_EMBED_CORPUS, vecs)
            ]
            logger.info("Tool embedding corpus loaded (intent routing)")
        except Exception as e:
            logger.warning(f"Tool embedding corpus failed: {e}, intent routing disabled")
            _tool_embed_cache = []
        return _tool_embed_cache


async def _classify_intent(message: str) -> tuple[str, str | None]:
    try:
        from embedding import cosine_similarity, embed_async
        corpus = await _get_tool_embeddings()
        if corpus:
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
                    logger.info(f"Intent=action group={best_group} via embedding (sim={best_sim:.2f}, margin={margin:.2f})")
                    return "action", best_group
                logger.info(f"Intent=question via embedding (sim={best_sim:.2f}, margin={margin:.2f})")
                return "question", None
            logger.info(f"Embedding uncertain (sim={best_sim:.2f}, margin={margin:.2f}), trying keyword heuristics")
    except Exception as e:
        logger.warning(f"Embedding intent routing failed: {e}")

    weather_kw = ["hava", "derece", "sıcaklık", "sicaklik", "tahmini", "yağmur", "yagmur", "rüzgar", "ruzgar", "kar", "bulut"]
    if any(kw in message.lower() for kw in weather_kw):
        logger.info(f"Intent=action group=weather via keyword (message={message!r})")
        return "action", "weather"

    cal_kw = ["etkinlik", "takvim", "randevu", "toplantı", "olay"]
    if any(kw in message.lower() for kw in cal_kw):
        logger.info(f"Intent=action group=calendar via keyword (message={message!r})")
        return "action", "calendar"

    email_kw = ["email", "e-posta", "posta", "gelen kutusu", "ileti", "mesaj", "mail"]
    if any(kw in message.lower() for kw in email_kw):
        logger.info(f"Intent=action group=email via keyword (message={message!r})")
        return "action", "email"

    task_kw = ["görev", "gorev", "yapılacak", "yapilacak", "task", "todo", "yapmam gereken"]
    if any(kw in message.lower() for kw in task_kw):
        logger.info(f"Intent=action group=tasks via keyword (message={message!r})")
        return "action", "tasks"

    note_kw = ["not", "notlar", "not defteri"]
    if any(kw in message.lower() for kw in note_kw):
        logger.info(f"Intent=action group=notes via keyword (message={message!r})")
        return "action", "notes"

    memory_kw = ["hatırla", "hatirla", "unutma", "sakla", "kaydet", "remember", "don't forget", "save"]
    if any(kw in message.lower() for kw in memory_kw):
        logger.info(f"Intent=action group=memory via keyword (message={message!r})")
        return "action", "memory"

    # Optional LLM fallback — improves accuracy but adds ~15s delay before streaming starts.
    if os.getenv("INTENT_LLM_FALLBACK", "off") == "on":
        backend = (os.environ.get("LLM_BACKEND") or "ollama").strip().lower()
        client = _get_client()
        payload = {
            "model": LLM_MODEL.replace(":", "-") if backend == "litert" else LLM_MODEL,
            "messages": [
                {"role": "system", "content": _INTENT_PROMPT},
                {"role": "user", "content": message},
            ],
            "stream": False,
        }
        if backend == "litert":
            url = f"{LITERT_BASE_URL}/v1/chat/completions"
        else:
            payload["options"] = {"temperature": 0, "num_predict": 20, "num_ctx": 512}
            payload["keep_alive"] = LLM_KEEP_ALIVE
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
