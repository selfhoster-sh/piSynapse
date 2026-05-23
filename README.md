# piSynapse 🚀
### Privacy-First, Self-Hosted AI Assistant on Edge Hardware

"piSynapse (Private-Intelligence Synapse) is an open-source personal assistant framework built to run entirely on your own local hardware. It is optimized for edge computing devices, ensuring your data never leaves your control."

---

## Philosophy

Most AI assistants today are locked behind subscriptions and centralized infrastructure. You either hand over your data or fall behind. piSynapse takes a different approach:

- **Your data stays yours.** Calendars, emails, and conversation history never leave your device.
- **Edge-first.** Built to run within the resource constraints of a Raspberry Pi 5.
- **Free forever.** Licensed under **GNU GPLv3** — can't be closed, repackaged, or commercialized.

---

## Features
- **Personal Calendar:** Connects to Nextcloud to manage your schedule.
- **Email Management:** Reads and sends emails through your personal Gmail account.
- **Local Weather:** Get real-time weather updates without tracking scripts.
- **Self-Hosted AI:** Runs locally on your device with Ollama, keeping your data private.
## Stack

---

- **API:** FastAPI (Python 3.x), fully async
- **LLM:** Ollama running `gemma4:e2b` locally
- **Storage:** Conversation history and long-term memory via `aiosqlite`
- **Integrations:** Nextcloud CalDAV (`caldav` + `vobject`) and Gmail IMAP/SMTP via asyncio thread pools
- **Tool Calling:** Custom text-parsing loop instead of native tool-calling schemas — LLM-agnostic, lighter on context, works across small local models

---

## Structure

```text
piSynapse/
├── main.py             # FastAPI entry point
├── llm.py              # Tool parser, system prompt, Ollama bridge
├── gmail.py            # Async IMAP/SMTP wrapper
├── nextcloud_auth.py   # CalDAV connection
├── memory.py           # Session and long-term memory (aiosqlite)
├── requirements.txt
├── .env
├── LICENSE             # GNU GPLv3
└── routers/
    └── chat.py         # Chat endpoints and response sanitization
```

---

## Setup

### 1. Install Ollama and pull the model
```bash
ollama run gemma4:e2b
```

### 2. Clone and install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp example.env .env
nano .env
```

> For Gmail, enable 2FA and generate an **App Password**. For Nextcloud, generate a dedicated **App Password** from your security settings.

### 4. Run
```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## Test

```bash
curl -X POST http://localhost:8000/chat/ \
     -H "Content-Type: application/json" \
     -d '{"message": "whats on my calendar this week?"}'
```

---

---

## Roadmap

piSynapse is a living, evolving ecosystem. Here is what I am working on to bring more privacy and functionality to your edge hardware:

- [ ] **Proton Mail Integration:** Secure and private email management via `proton-bridge`.
- [ ] **Mobile App (Android):** A native, privacy-focused companion app to access PiSynapse on the go.
- [ ] **Mobile Skills:** Location-aware intelligence and context-aware mobile commands.
- [ ] **Advanced Tool-Calling:** Enhancing the custom text-parsing loop for better accuracy with complex multi-step queries.
- [ ] **Local Dashboard:** A simple UI to monitor memory usage, active sessions, and history.

---

## License

GNU General Public License v3. See `LICENSE` for details.
