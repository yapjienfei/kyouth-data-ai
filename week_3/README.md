# Resume Helper Chatbot

A containerized full-stack chat application that allows users to ask questions about resumes and job descriptions, optionally uploading PDF documents for AI-powered analysis. The system is built with a FastAPI frontend, a FastAPI backend, and Google Gemini as the AI model integration.

---

## Project Overview

The goal of this project is to build and containerize a full-stack chat application with three layers:

- **Frontend** — A FastAPI + Jinja2 server that serves an interactive chat UI (HTML/CSS/JS) and passes the backend URL to the browser via template variables.
- **Backend** — A FastAPI REST API that receives user messages and optional PDF text, constructs a prompt, and queries the Google Gemini API for a response.
- **AI Integration** — Google Gemini (via the `google-genai` SDK), with automatic model fallback and rate-limit tracking inherited from the Week 2 `prompt_model` module.

Both services are containerized with Docker and orchestrated with Docker Compose over a shared bridge network.

---

## Setup Instructions

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker | 24+ | Container runtime |
| Docker Compose | v2+ | Multi-container orchestration |
| `uv` *(optional)* | 0.8.0 | Local Python package manager (manual setup only) |
| Google AI API Key | — | Required to call Gemini models |

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd <repo-folder>
```

### 2. Configure Environment Variables

The backend requires a Google API key. Create a `.env` file at the repository root:

```bash
cp backend/src/week_2/.env.example .env
```

Then open `.env` and fill in your key:

```
GOOGLE_API_KEY=your-actual-api-key-here
```

> **Never commit `.env` to version control.** It is already listed in `.gitignore`.

A `.env.example` is provided at the root for reference (see below).

### 3. (Optional) Manual Setup with `uv`

If you want to run services locally without Docker:

**Backend:**
```bash
cd backend
pip install uv==0.8.0          # or use the installer: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --frozen
cp src/week_2/.env.example src/week_2/.env   # add your GOOGLE_API_KEY
uv run uvicorn --app-dir src --host 0.0.0.0 --port 8001 main:app
```

**Frontend:**
```bash
cd frontend
uv sync --frozen
cp .env.example .env             # set BACKEND_API_URL=http://localhost:8001
uv run uvicorn --app-dir src --host 0.0.0.0 --port 8000 main:app
```

---

## `.env.example`

Place this file at the repository root as `.env.example`:

```dotenv
# Google Gemini API Key — get one at https://aistudio.google.com/
# Copy this file to .env and fill in your key. NEVER commit .env!
GOOGLE_API_KEY=your-actual-api-key-here
```

The frontend also has its own `frontend/.env.example`:

```dotenv
# URL the frontend container uses to reach the backend
BACKEND_API_URL=http://localhost:8001

# FastAPI server bind settings
FRONTEND_HOST=0.0.0.0
FRONTEND_PORT=8000
```

---

## Usage

### Running with Docker Compose (recommended)

```bash
docker compose up --build
```

This builds both images and starts both services. To run in the background:

```bash
docker compose up --build -d
```

### Accessing the Application

| Service | URL |
|---------|-----|
| Chat UI (frontend) | http://localhost:8000 |
| Backend API root | http://localhost:8001 |
| Backend Swagger docs | http://localhost:8001/docs |

### Makefile Shortcuts

A root-level `Makefile` wraps common Docker Compose commands:

```bash
make up            # Start all services in background
make down          # Stop all services
make rebuild       # Clean, rebuild, and restart
make logs          # Tail all logs
make logs-frontend # Tail frontend logs only
make logs-backend  # Tail backend logs only
make health        # Ping health endpoints on both ports
make status        # Show running container status
```

### Expected Inputs and Outputs

**Text message only:**
1. Type a question in the chat box (e.g., *"What skills should I highlight for a data engineering role?"*).
2. Click **Send** or press Enter.
3. The AI returns a text response in the chat window, with the model name shown in the backend logs.

**PDF upload + question:**
1. Click **Attach PDF** and select a PDF file (max 10 MB).
2. The browser extracts the text using PDF.js and shows a preview.
3. Type a question about the document (e.g., *"What are the skill gaps in this resume?"*).
4. Click **Send** — the extracted text is sent alongside your message to the backend.
5. The AI responds in the context of the uploaded document.

---

## API / Function Reference

### Backend — `POST /chat`

**Endpoint:** `http://localhost:8001/chat`

**Request body (JSON):**

```json
{
  "message": "What skills are needed for a data engineer?",
  "pdf_content": "Optional extracted text from a PDF...",
  "pdf_name": "resume.pdf",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | `string` | Yes | The user's chat message |
| `pdf_content` | `string` | No | Raw text extracted from a PDF (max ~4000 chars used) |
| `pdf_name` | `string` | No | Original filename for logging purposes |
| `timestamp` | `string` | No | ISO 8601 timestamp of the request |

**Response body (JSON):**

```json
{
  "response": "The AI's answer...",
  "model_used": "gemini-2.5-flash-lite",
  "status": "success"
}
```

| Field | Description |
|-------|-------------|
| `response` | The text answer from the AI model |
| `model_used` | Which Gemini model produced the answer (or `"none"` / `"error"` on failure) |
| `status` | `"success"` or `"error"` |

**Other backend endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Confirms the API is running |
| `GET` | `/health` | Health check used by Docker |

### Backend — Key Helper Functions (`backend/src/main.py`)

**`combine_prompt_with_pdf(user_message, pdf_content)`**
Builds the full prompt string. If `pdf_content` is present, it wraps it in document delimiters before appending the user's question. PDF text is truncated at 4 000 characters to stay within token limits.

**`call_ai_with_fallback(prompt, preferred_model)`**
Calls `prompt_model()` with the preferred model, then automatically retries with `gemini-2.5-flash` and `gemini-3-flash-preview` if the first model is rate-limited or errors. Returns a `(response_text, model_used)` tuple.

**`prompt_model(model, prompt)` (`backend/src/week_2/prompt_model.py`)**
Week-2 module that calls the Gemini API, checks rate limits before each call, and records usage afterwards. Supports `gemini-2.5-flash`, `gemini-2.5-flash-lite`, and `gemini-3-flash-preview`.

### Frontend — Key JavaScript Functions (`frontend/src/templates/chat_page.html`)

**`sendMessage()`**
Triggered by the Send button or Enter key. Reads `userInput.value` and the in-memory `uploadedPDFText`, builds the JSON payload, `fetch()`es `POST ${BACKEND_URL}/chat`, and calls `addMessageToChat()` with the response.

**`addMessageToChat(text, senderClass)`**
Creates a `<div class="message {senderClass}">` element containing the text and a timestamp, appends it to `#chatHistory`, and scrolls to the bottom.

**`extractPDFText(file)`**
Uses PDF.js to read the uploaded file as an `ArrayBuffer`, iterates over all pages with `getTextContent()`, and resolves a `Promise<string>` with the full concatenated text.

**`clearPDF()`**
Resets `uploadedPDFText` and `uploadedPDFName` to `null`, clears the file input, hides the attachment info panel, and notifies the user in chat.

### Frontend–Backend Communication over Docker Network

Both containers are attached to the `app-network` bridge network defined in `docker-compose.yml`. The frontend service references the backend using the **Docker service name** (`backend`) as the hostname inside the network. However, the current `docker-compose.yml` passes `BACKEND_API_URL=http://localhost:8001`, which works because port 8001 is published to the host and the browser makes the fetch call from the user's machine — not from inside the frontend container. For purely server-side calls, the URL would be `http://backend:8001`.

---

## Data / Assumptions

### JSON Message Structure

Every chat turn sends one JSON object and receives one JSON object (see the API reference above). No session state is maintained server-side — each request is self-contained.

### Data Flow

```
User types message + optionally uploads PDF
        │
        ▼
Browser (PDF.js) extracts PDF text client-side
        │
        ▼
JavaScript builds JSON payload and POSTs to http://localhost:8001/chat
        │
        ▼
Backend: combine_prompt_with_pdf() merges message + PDF context
        │
        ▼
Backend: call_ai_with_fallback() → prompt_model() → Gemini API
        │
        ▼
ChatResponse JSON returned to browser
        │
        ▼
addMessageToChat() renders AI reply in the chat window
```

### Assumptions

- **PDF format:** PDFs must contain selectable text. Scanned image-only PDFs will yield empty extraction.
- **PDF size:** Capped at 10 MB by the frontend. Only the first ~4 000 characters of extracted text are sent to the AI.
- **User message length:** No hard limit is enforced, but very long messages consume Gemini tokens and may trigger rate limits.
- **API key:** A valid `GOOGLE_API_KEY` with access to the Gemini models listed above is required. Without it, the backend returns an error message rather than crashing.
- **Rate limits:** The Week-2 `RateLimiter` reads limits from an optional `rate_limits.txt` file. If the file is absent, rate limiting is disabled and all requests pass through.
- **Stateless chat:** No conversation history is stored. Each message is an independent single-turn prompt. The AI has no memory of prior turns.
- **AI model integration:** The system reuses the `prompt_model` function from the Week 2 assignment as-is, meaning only Gemini models are supported. The fallback list is hard-coded in `call_ai_with_fallback`.

---

## Testing

### Backend — `curl` / Postman

**Basic text message:**
```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is Python used for?"}'
```

Expected response:
```json
{"response": "...", "model_used": "gemini-2.5-flash-lite", "status": "success"}
```

**Message with PDF content:**
```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What skills are listed in this resume?",
    "pdf_content": "Technical Skills: Python, SQL, Docker, Kubernetes",
    "pdf_name": "resume.pdf"
  }'
```

**Health check:**
```bash
curl http://localhost:8001/health
# Expected: {"status":"healthy","service":"backend-chat"}
```

**Error case — empty message:**
```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": ""}'
```
Expect a 422 Unprocessable Entity from FastAPI validation (empty string fails the `str` type requirement when combined with no `pdf_content`).

### Frontend — Manual Browser Tests

| Test | Steps | Expected |
|------|-------|----------|
| Send text message | Type a question, click Send | Bot reply appears in chat |
| Send on Enter | Type a question, press Enter | Bot reply appears in chat |
| Upload valid PDF | Click Attach PDF, select a `.pdf` | Extraction summary shown; confirmation in chat |
| Upload oversized file | Select a PDF > 10 MB | Alert: "File too large. Maximum size is 10MB" |
| Upload non-PDF | Select a `.docx` or `.jpg` | Alert: "Please select a PDF file" |
| Ask about PDF | Upload PDF, then ask a question | AI responds with context from the document |
| Remove PDF | Click ✕ Remove after uploading | Attachment panel hidden; next message sent without PDF |
| Backend unreachable | Stop the backend, send a message | Error message displayed in chat (does not crash UI) |

### Verifying Frontend–Backend Communication in Docker

```bash
# 1. Start both services
docker compose up --build -d

# 2. Check both are healthy
make health
# or:
curl -s http://localhost:8000/health
curl -s http://localhost:8001/health

# 3. Send a chat message from outside Docker
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, are you working?"}'

# 4. Open http://localhost:8000 in a browser and send a message through the UI

# 5. Confirm backend logs show the received message
make logs-backend
```

---

## Limitations

- **No conversation history:** The AI treats every message as a fresh single-turn prompt. It cannot refer to anything said earlier in the same chat session.
- **No user authentication:** Anyone who can reach port 8000 can use the chatbot. There is no login, session management, or per-user rate limiting.
- **PDF quality depends on selectable text:** Scanned PDFs or PDFs with text stored as images will produce empty or garbage extraction via PDF.js.
- **PDF truncation:** Only the first 4 000 characters of extracted PDF text reach the AI. Long resumes or dense documents will have content silently cut off.
- **Rate limits on Gemini free tier:** The fallback logic cycles through three Gemini models, but all share the same Google account quota. Heavy usage will exhaust all models and return an error.
- **Temperature and model configuration are fixed:** AI creativity and response style cannot be adjusted from the UI.
- **No persistent storage:** Chat messages, uploaded PDFs, and usage statistics disappear when the containers stop.
- **Single-user design:** The application was built for personal/demo use. No horizontal scaling or concurrent session support is implemented.
- **Frontend is a single HTML file:** There is no build step, bundler, or frontend framework. Complex UI changes require editing raw HTML/CSS/JS.
- **`BACKEND_API_URL` points to localhost:** In the current `docker-compose.yml`, the frontend container receives `http://localhost:8001`, which works because the browser (running on the host) makes the fetch request. A true server-side proxy would require `http://backend:8001` and additional routing.

---

## Architecture Reflection

### Design Choices

**Microservices split (frontend / backend):**
The frontend and backend are intentionally separated into two independent services. This mirrors real-world production architectures and allows each service to be developed, deployed, and scaled independently. The frontend only renders HTML and proxies the backend URL to the browser — it contains no AI logic. The backend contains all business logic and has no knowledge of the UI. This clean boundary makes it straightforward to swap either layer (e.g., replace the HTML frontend with a React app) without touching the other.

**Docker + Docker Compose:**
Containerising each service solves the "works on my machine" problem. Each Dockerfile pins the Python version (3.14.5), installs dependencies via `uv`, and exposes a well-known port. Docker Compose adds a shared `app-network` bridge so the services can address each other by name, and the `depends_on` directive ensures the backend starts before the frontend. This makes the entire stack reproducible with a single command.

**Reusing the Week 2 `prompt_model` module:**
Rather than rewriting Gemini integration from scratch, the backend imports `prompt_model` directly from `backend/src/week_2/`. This keeps AI logic consolidated and allows the backend to inherit rate-limit tracking and model fallback logic without duplication.

### Trade-offs

**Ease of deployment vs. performance:**
Docker Compose with `--reload` enabled on both services prioritises developer ergonomics over raw performance. In production, reload mode should be disabled and the number of Uvicorn workers increased.

**Simplicity vs. features:**
The chat interface is a single self-contained HTML file. This is fast to build and requires no npm build step, but makes it harder to add rich features (typing indicators, markdown rendering, multi-turn context) compared to a framework like React or Vue.

**Client-side PDF extraction vs. server-side:**
PDF text is extracted entirely in the browser using PDF.js. This avoids sending binary files over the network and keeps the backend stateless, but means extraction quality is subject to browser-side library limitations and cannot leverage server-side OCR tools.

### Improvements with More Time

- **Add conversation history:** Maintain a session-level message array on the backend (or in a database) and include prior turns in each Gemini prompt for genuine multi-turn dialogue.
- **Replace localhost URL with internal Docker hostname:** Change `BACKEND_API_URL` to `http://backend:8001` and add a reverse proxy (e.g., Nginx) in the frontend container so the browser calls the frontend service, which forwards to the backend — fully contained within the Docker network.
- **Persist chat history:** Introduce a lightweight database (SQLite or PostgreSQL) to store conversations per session, enabling users to resume previous chats.
- **Use a proper frontend framework:** Migrating the UI to React or Vue would enable component reuse, better state management, and markdown rendering for AI responses.
- **Add server-side PDF parsing:** Use a Python library such as `pypdf` or `pdfminer` on the backend to handle scanned PDFs via OCR and remove the 4 000-character truncation.
- **Deploy to the cloud:** Package the Compose stack for deployment on a cloud platform (e.g., AWS ECS, Google Cloud Run, or Railway) with environment secrets managed via the platform's secrets manager rather than a local `.env` file.
- **Streaming responses:** Use Gemini's streaming API and Server-Sent Events to display the AI's answer word-by-word, improving perceived responsiveness.
