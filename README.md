# piSynapse 🚀
### Privacy-First, Self-Hosted AI Assistant on Edge Hardware

**piSynapse** (Private-Intelligence Synapse) is an open-source personal assistant framework built to run entirely on your own local hardware. It is optimized for edge computing devices, ensuring your data stays private, secure, and under your control.

---

## Philosophy

Most AI assistants today are locked behind subscriptions and centralized infrastructure. You either hand over your data or fall behind. piSynapse takes a different approach:

- **Your data stays yours.** Calendars, emails, and conversation history never leave your device.
- **Edge-first.** Built to run within the resource constraints of a Raspberry Pi 5.
- **Free forever.** Licensed under **GNU GPLv3** — can't be closed, repackaged, or commercialized.

---

## Features

- 📅 **Personal Calendar** — Connects to Nextcloud CalDAV for schedule management
- 📧 **Email Management** — Native Gmail IMAP/SMTP integration (read, send, search)
- 🌤️ **Local Weather** — Real-time forecasts via Open-Meteo (no tracking)
- 🧠 **Long-Term Memory** — Semantic deduplication with embeddings
- 🤖 **Self-Hosted LLM** — Ollama integration with local models
- 💬 **Tool-Calling Loop** — Custom XML-based tool execution (LLM-agnostic)

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|----------|
| **API** | FastAPI (async Python) | REST endpoints, event loop |
| **LLM** | Ollama + local models | Tool calling, conversation |
| **Storage** | SQLite + aiosqlite | Conversation history & memories |
| **Integrations** | Nextcloud CalDAV, Gmail IMAP/SMTP | Calendar & email |
| **Embeddings** | FastEmbed | Semantic deduplication, memory search |
| **Weather** | Open-Meteo API | Real-time forecasts |

---

## Project Structure

```text
piSynapse/
├── main.py                # FastAPI app, lifespan management
├── llm.py                 # LLM bridge, tool runner, system prompt
├── chat.py                # Chat endpoints (in routers/)
├── gmail.py               # Gmail IMAP/SMTP async wrapper
├── memory.py              # Session & long-term memory (SQLite)
├── embedding.py           # Semantic embeddings (FastEmbed)
├── nextcloud_auth.py      # CalDAV authentication
├── install.py             # Interactive setup wizard
├── debugtest.py           # Pipeline test suite
├── requirements.txt       # Python dependencies
├── example.env            # Configuration template
├── LICENSE                # GNU GPLv3
└── routers/
    ├── __init__.py
    └── chat.py            # Chat router (moved by install.py)
```

---

## Getting Started

### Quick Start (Automated)

```bash
# Clone the repository
git clone https://github.com/selfhoster-sh/piSynapse.git
cd piSynapse

# Run the interactive installer
python install.py
```

The installer will:
- ✅ Check Python version (requires 3.10+)
- ✅ Install Ollama (if needed)
- ✅ Guide you through LLM model selection
- ✅ Create virtual environment
- ✅ Install dependencies
- ✅ Configure .env with credentials

### Manual Setup

**1. Prerequisites**
```bash
# Install Ollama
curl https://ollama.com/install.sh | sh

# Pull a model
ollama pull gemma4:e2b
```

**2. Clone & Install**
```bash
git clone https://github.com/selfhoster-sh/piSynapse.git
cd piSynapse
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**3. Configure**
```bash
cp example.env .env
nano .env  # Edit with your credentials
```

**4. Setup Project Structure**
```bash
mkdir routers
mv chat.py routers/
```

**5. Run**
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Configuration

Edit `.env` to configure:

```env
# LLM
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=gemma4:e2b
LLM_TEMPERATURE=0.3

# Gmail (optional)
GMAIL_USER=your@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# Nextcloud (optional)
NEXTCLOUD_URL=https://cloud.example.com
NEXTCLOUD_USER=username
NEXTCLOUD_PASSWORD=app-password

# Personalization
ASSISTANT_USER=Your Name
DEFAULT_CITY=Istanbul

# Memory & History
MEMORY_SIMILARITY_THRESHOLD=0.68
HISTORY_LIMIT=20
MEMORY_LIMIT=10
```

> **Gmail Setup:** Enable 2FA, then generate an [App Password](https://myaccount.google.com/apppasswords).
> 
> **Nextcloud:** Create a dedicated [App Password](https://docs.nextcloud.com/server/latest/user_manual/en/session_management.html#app-passwords) in Security settings.

---

## API Usage

### Chat Endpoint

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What\'s on my calendar this week?",
    "session_id": "session_1",
    "user_id": "default"
  }'
```

**Response:**
```json
{
  "reply": "You have 3 events this week...",
  "session_id": "session_1",
  "history_length": 2,
  "memories_saved": 1
}
```

### List Memories

```bash
curl http://localhost:8000/chat/memories?user_id=default
```

### Clear History

```bash
curl -X DELETE http://localhost:8000/chat/history?session_id=session_1
```

### Health Check

```bash
curl http://localhost:8000/health
```

---

## Testing

Run the debug test suite:

```bash
python debugtest.py
```

This tests:
- ✅ Memory extraction (MEMORY: lines)
- ✅ Embeddings (FastEmbed loading)
- ✅ Database operations (SQLite)
- ✅ Semantic deduplication

---

## Memory Syntax

piSynapse can extract and store memories from model responses:

```
Hey John, I remember you're from Istanbul and you love Python!

MEMORY: [personal] Name is John, from Istanbul
MEMORY: [preference] Loves Python programming
```

The MEMORY lines are automatically removed from the displayed response and stored in the long-term memory database with semantic deduplication.

---

## Roadmap

- [ ] **Proton Mail** — Secure email integration via proton-bridge
- [ ] **Mobile App** — Native Android companion app
- [ ] **Mobile Skills** — Location awareness & context-aware commands
- [ ] **Advanced Tool-Calling** — Multi-step reasoning for complex queries
- [ ] **Local Dashboard** — Web UI for sessions, memory, and analytics
- [ ] **Voice I/O** — Speech-to-text and text-to-speech

---

## License

GNU General Public License v3.0 — See [LICENSE](LICENSE) for details.

piSynapse is **free, open-source, and will remain so** — guaranteed by GPLv3.

---

## Support

For issues, questions, or feature requests, open an issue on [GitHub](https://github.com/selfhoster-sh/piSynapse/issues).
