# ⚡ DOCUMENT_RAG // CYBERPUNK MATRIX

A production-ready, ultra-fast **Document Retrieval-Augmented Generation (RAG)** application built with **Django 6**, 384-dimensional dense vector embeddings, **Groq LPU AI inference (`Llama 3.3 70B`)**, and a sleek **Cyberpunk Neon HUD** interface.

![Cyberpunk RAG Theme](https://img.shields.io/badge/Theme-Cyberpunk%20Neon-00f0ff?style=for-the-badge)
![Django 6](https://img.shields.io/badge/Django-6.0-00ff9f?style=for-the-badge&logo=django)
![AI Engine](https://img.shields.io/badge/Groq%20AI-Llama%203.3%2070B%20%7C%20120B-ff0055?style=for-the-badge)
![Vector Engine](https://img.shields.io/badge/Vector-Dense%20Cosine%20(384--dim)-fcee0a?style=for-the-badge)
![Production Ready](https://img.shields.io/badge/Deployment-Docker%20%7C%20Render%20%7C%20Gunicorn-00f0ff?style=for-the-badge)

---

## 🌌 Key Highlights & Features

1. **Multi-Format Document Ingestion:**
   - Supports **PDF**, **TXT**, **Markdown**, **CSV**, **JSON**, and code files.
   - Smart recursive character chunker with semantic boundaries and page-number metadata tracking.

2. **Hybrid Vector Retrieval Engine:**
   - Embeds text into **384-dimensional dense vectors** via `all-MiniLM-L6-v2`.
   - Real-time **Cosine Similarity ($\cos \theta$)** calculation in vector space.
   - Sub-second retrieval with confidence scoring and page-attributed source packets.

3. **Ultra-Fast Grounded Generation:**
   - Powered by **Groq LPU** (`Llama 3.3 70B` / `openai/gpt-oss-120b`) delivering ~300 tokens/sec.
   - Grounded context synthesis with strict anti-hallucination prompting.
   - Offline fallback synthesizer (`Dense Semantic Engine`) when offline.

4. **100% Secure & Private:**
   - **Zero AI Model Training:** Uploaded documents are never used for AI training.
   - Full document management and instant permanent deletion controls.

5. **Cyberpunk HUD Frontend:**
   - Dark carbon neon theme with cyan and magenta glowing accents.
   - Interactive chat terminal with streaming typing indicator and collapsible citation packets.

6. **Production & Cloud Ready:**
   - Ready to deploy with `render.yaml`, `Procfile`, `Dockerfile`, and `docker-compose.yml`.
   - `whitenoise` static asset compression and caching.

---

## 📁 Architecture Overview

```
document_rag/
├── manage.py
├── requirements.txt            # Pinned production dependencies
├── .env.example                # Sample environment variables
├── Dockerfile                  # Multi-stage production container
├── docker-compose.yml          # Containerized local/server orchestration
├── Procfile                    # Render / Railway process definition
├── render.yaml                 # 1-Click Render blueprint
├── document_rag/
│   ├── settings.py             # WhiteNoise + RAG settings + ENV loader
│   ├── urls.py                 # Root URL configuration
│   └── wsgi.py
├── rag_app/
│   ├── models.py               # Document, DocumentChunk, ChatSession, ChatMessage
│   ├── views.py                # Cyber UI views & REST API endpoints
│   ├── urls.py                 # App routes & Health check
│   ├── serializers.py          # DRF serializers
│   ├── tests.py                # Automated RAG test suite
│   ├── services/
│   │   ├── document_parser.py  # Multi-format document extractor
│   │   ├── text_chunker.py     # Recursive semantic chunker
│   │   ├── vector_store.py     # 384-dim vector embeddings & Cosine similarity
│   │   ├── llm_service.py      # Groq LPU AI inference adapter
│   │   └── rag_pipeline.py     # Orchestration pipeline
│   ├── static/rag_app/
│   │   ├── css/cyberpunk.css   # Cyberpunk Neon HUD styles & animations
│   │   └── js/
│   │       ├── upload.js       # Matrix scanner & drag-drop upload
│   │       └── chat.js         # Cyber terminal & markdown engine
│   └── templates/rag_app/
│       ├── base.html           # Sci-Fi layout & header HUD
│       ├── upload.html         # Document Ingestion HUD
│       └── chat.html           # Dialogue Terminal & Data Packets
```

---

## 🚀 Getting Started

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/YOUR_USERNAME/document-rag.git
cd document-rag
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Add your free Groq API key (from [console.groq.com/keys](https://console.groq.com/keys)):
```ini
GROQ_API_KEY=gsk_your_groq_api_key_here
```

### 3. Run Database Migrations
```bash
python manage.py migrate
```

### 4. Start Development Server
```bash
python manage.py runserver
```
Navigate to: **`http://127.0.0.1:8000/`**

---

## 🧪 Running Automated Tests
```bash
python manage.py test
```

---

## 🚢 Production Deployment (Render)

1. Push this repository to GitHub.
2. In [Render Dashboard](https://dashboard.render.com/), create a **New Web Service** and select your repository.
3. Configure:
   - **Build Command:** `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - **Start Command:** `python manage.py migrate --noinput && gunicorn document_rag.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
4. Set Environment Variable:
   - `GROQ_API_KEY` = `gsk_your_groq_api_key`
5. Deploy! 🎉

---

## 📡 REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/documents/upload/` | Ingest and vectorize a new document (`multipart/form-data`) |
| `GET` | `/api/documents/<uuid:id>/status/` | Get indexing status and chunk metrics |
| `POST` | `/api/documents/<uuid:id>/delete/` | Delete document and associated vectors |
| `POST` | `/api/chat/<uuid:session_id>/ask/` | Query the document with RAG grounding (`{"message": "..."}`) |
| `GET` | `/health/` | Health check probe |

---

## ⚡ License
MIT License. Free for open-source and commercial use.
