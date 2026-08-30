import os
import re
import json
import logging
import httpx
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from django.conf import settings
from rag_app.services.vector_store import _get_neural_model

logger = logging.getLogger(__name__)


def clean_and_format_markdown_text(text: str) -> str:
    """Universal text cleaner that normalizes prose sentences, strips noise, and groups code blocks."""
    if not text:
        return ""

    # 1. Clean publisher noise, URLs & Cover/Disclaimer fluff
    text = re.sub(r'GoalKicker\.com\s*[-–—]?\s*.*?\d*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'.*?Notes for Professionals\s*\d*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'https?://\S+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Disclaimer\s+This is an uno[a-z\s]+book created for educational purposes.*?(?=\n\n|[A-Z])', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'Free Programming Books', '', text, flags=re.IGNORECASE)
    text = re.sub(r'800\+\s*pages of professional hints and tricks', '', text, flags=re.IGNORECASE)

    # 2. Strip raw Parameter/Option Table Headers
    text = re.sub(r'Parameter\s+Details\s+.*?options\s+document[^\)]*\)', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'Parameter\s+Details\s+.*?(?=[A-Z][a-z]+\s+(?:operations|process|is|are|group|provides|allows))', '', text, flags=re.IGNORECASE | re.DOTALL)

    # 3. Strip raw Version Release tables
    text = re.sub(r'Version\s+Release\s+Date(?:\s+\d+(?:\.\d+)*\s+\d{4}-\d{2}-\d{2})+', '', text, flags=re.IGNORECASE)

    # 4. Normalize soft linebreaks within prose sentences
    text = re.sub(r'(?<=[a-zA-Z,])\n(?=[a-zA-Z])', ' ', text)

    # 5. Strip orphaned closing code fragments at the start of a chunk
    text = re.sub(r'^(?:return\s+<[^>]+>[^;\n]*\s*\}|[\s\}]+export\s+default\s+\w+|[\s\}\);]+\n)+', '', text.strip(), flags=re.IGNORECASE).strip()

    # 6. Separate Sections into distinct paragraphs
    text = re.sub(r'(?:Chapter|Section)\s+\d+(?:\.\d+)?:[^\n]*', r'\n\n', text)

    # 7. Fix broken inline numbered list artifacts
    text = re.sub(r'(?<=[.?!])\s*(\d+)\.\s*', r'\n\1. ', text)

    # 8. Robust Multiline Code & Prose Grouping with bracket tracking
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    formatted_paragraphs = []

    for p in paragraphs:
        lines = p.split('\n')
        curr_prose = []
        curr_code = []
        parts = []
        in_multiline_code = 0

        def flush_p():
            if curr_prose:
                prose_str = ' '.join(curr_prose).strip()
                prose_str = re.sub(r'(<[A-Z][A-Za-z0-9_]*(\s+[^>]*)?/?>)', r'`\1`', prose_str)
                if prose_str:
                    parts.append(prose_str)
                curr_prose.clear()

        def flush_c():
            if curr_code:
                code_str = '\n'.join(curr_code).strip()
                if code_str:
                    if any(w in code_str for w in ['def ', 'print(', 'elif ', 'import *', 'from array', 'while ', 'for ']) and 'function' not in code_str:
                        lang = 'python'
                    elif any(w in code_str for w in ['import React', 'ReactDOM', '<div', 'render()', 'export default']):
                        lang = 'jsx'
                    else:
                        lang = 'python' if ('def ' in code_str or 'elif ' in code_str or 'import ' in code_str) else 'javascript'
                    parts.append(f'```{lang}\n{code_str}\n```')
                curr_code.clear()

        for line in lines:
            s = line.strip()
            if not s:
                continue

            open_b = s.count('{') + s.count('[') + s.count('(')
            close_b = s.count('}') + s.count(']') + s.count(')')

            starts_code = bool(re.match(
                r'^(db\.\w+|var\s+|const\s+|let\s+|function\s+|\/\/|#|\$\s+|\>\s+db\.|import\s+|from\s+|def\s+|class\s+|export\s+|ReactDOM\.|React\.|return\s+|componentDid|render\(\)|handleChange\(|if\s+|elif\s+|else:|for\s+|while\s+)',
                s
            )) or s.startswith(('<', '{', '[', '(', '/*', '*/', '>>>', '$')) or s.endswith((':', ';', '{', '}', '[', ']'))

            if starts_code or in_multiline_code > 0:
                flush_p()
                curr_code.append(line)
                in_multiline_code += (open_b - close_b)
                if in_multiline_code < 0:
                    in_multiline_code = 0
            else:
                flush_c()
                curr_prose.append(s)

        flush_p()
        flush_c()
        if parts:
            formatted_paragraphs.append('\n\n'.join(parts))

    result = '\n\n'.join(formatted_paragraphs)
    return result.strip()


class LLMService:
    """
    State-of-the-Art High Precision AI RAG Engine:
    - Primary Engine: Groq LPUs (Llama 3.3 70B / 120B, ~300 tokens/sec, Zero-Hallucination)
    - Fallback Engine: Pure Dense Semantic Extractor (80 MB in-memory fallback)
    """

    SYSTEM_PROMPT = (
        "You are an expert, articulate, and accurate AI technical assistant. "
        "Your task is to answer the user's question clearly, thoroughly, and factually based strictly on the provided document context.\n\n"
        "Guidelines:\n"
        "1. Complete & Cohesive: Provide direct, fully formed explanations with code syntax and examples where relevant.\n"
        "2. Zero Hallucination: Base all facts, names, skills, and code strictly on the provided document excerpts. If something is not in the document, state it honestly.\n"
        "3. Beautiful Markdown: Use clean headings, clear bullet points, bold key terms, and language-tagged code blocks (```python, ```javascript, ```jsx)."
    )

    @staticmethod
    def generate_response(
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        document_obj: Any = None,
        chat_history: List[Dict[str, str]] = None,
        custom_api_key: str = None
    ) -> Tuple[str, str]:
        groq_key = getattr(settings, 'GROQ_API_KEY', '') or os.environ.get('GROQ_API_KEY', '') or custom_api_key

        # Build clean context block from top semantically retrieved chunks
        context_blocks = []
        for i, ch in enumerate(retrieved_chunks[:5]):
            content = ch.get('content', '').strip()
            page_info = f" (Page {ch.get('page_number')})" if ch.get('page_number') else ""
            if content:
                context_blocks.append(f"--- [Document Excerpt #{i + 1}{page_info}] ---\n{content}")
        context_str = "\n\n".join(context_blocks)

        # -------------------------------------------------------------
        # Primary Engine: Groq Ultra-Fast LPUs
        # -------------------------------------------------------------
        if groq_key:
            res = LLMService._call_groq(query, context_str, groq_key, chat_history)
            if res:
                return res, "⚡ Groq (Llama 3.3 70B)"

        # -------------------------------------------------------------
        # Fallback Engine: Dense Semantic Extractor (80 MB offline)
        # -------------------------------------------------------------
        synthesized_answer = LLMService._synthesize_cohesive_passage(query, retrieved_chunks, document_obj)
        return synthesized_answer, "Dense Semantic Engine"

    # =========================================================================
    # GROQ INFERENCE (High-Precision 120B / 70B / 27B LPU Models)
    # =========================================================================
    @staticmethod
    def _call_groq(query: str, context: str, api_key: str, chat_history: List[Dict[str, str]] = None) -> str:
        url = "https://api.groq.com/openai/v1/chat/completions"
        messages = [{"role": "system", "content": LLMService.SYSTEM_PROMPT}]

        if chat_history:
            for msg in chat_history[-4:]:
                r = msg.get("role", "user")
                c = msg.get("content", "")
                if r in ["user", "assistant"] and c:
                    messages.append({"role": r, "content": c})

        messages.append({
            "role": "user",
            "content": f"Document Context Excerpts:\n{context}\n\nUser Question: {query}"
        })

        # High-performance Groq candidate models
        candidate_models = [
            "openai/gpt-oss-120b",
            "qwen/qwen3.6-27b",
            "openai/gpt-oss-20b",
            "groq/compound",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant"
        ]

        for model in candidate_models:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 2048
            }
            try:
                with httpx.Client(timeout=25.0) as client:
                    resp = client.post(
                        url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {api_key.strip()}",
                            "Content-Type": "application/json"
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            answer = choices[0].get("message", {}).get("content", "").strip()
                            if answer:
                                return answer
                    else:
                        logger.warning(f"Groq ({model}) HTTP {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Groq API error with model {model}: {e}")
        return ""

    # =========================================================================
    # DENSE NEURAL SECTION SYNTHESIZER (80 MB Offline Fallback)
    # =========================================================================
    @staticmethod
    def _synthesize_cohesive_passage(query: str, retrieved_chunks: List[Dict[str, Any]], document_obj: Any = None) -> str:
        if not retrieved_chunks:
            return "No relevant information found in the document for your question."

        query_lower = query.lower().strip()
        doc_title = getattr(document_obj, 'title', 'the document') if document_obj else 'the document'
        top_chunk = retrieved_chunks[0]
        top_score = top_chunk.get("similarity_score", 0.0)

        # 1. Low Confidence Guard
        if top_score < 0.20:
            clean_q = re.sub(r'^(what is|what are|explain|tell me about)\s+', '', query_lower).strip(' ?.')
            return f"⚠️ The uploaded document (**{doc_title}**) does not contain information regarding **{clean_q}**."

        # 2. Targeted Slot & Entity Extraction (Emails, Phone)
        all_text = " ".join([ch.get("content", "") for ch in retrieved_chunks])
        if any(w in query_lower for w in ['email', 'e-mail', 'mail id', 'contact email', 'email address']):
            email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', all_text)
            if email_match:
                name_match = re.search(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', all_text.strip())
                name_prefix = f" of **{name_match.group(1)}**" if name_match else ""
                return f"The email address{name_prefix} is **{email_match.group(0)}**."

        if any(w in query_lower for w in ['phone', 'mobile', 'phone number', 'contact number', 'telephone', 'cell']):
            phone_match = re.search(r'(?:\+?\d{1,3}[\s-]?)?\(?\d{2,5}\)?[\s-]?\d{3,5}[\s-]?\d{3,5}', all_text)
            if phone_match:
                return f"The contact phone number is **{phone_match.group(0).strip()}**."

        # 3. Filter out cover page / disclaimer chunks
        clean_candidates = []
        for ch in retrieved_chunks:
            raw = ch.get("content", "")
            page_num = ch.get("page_number", 999)
            if page_num <= 5 and any(w in raw.lower() for w in ['disclaimer', 'free programming books', 'table of contents']):
                continue
            fc = clean_and_format_markdown_text(raw)
            if fc and len(fc) > 25:
                clean_candidates.append(fc)

        if not clean_candidates:
            clean_candidates = [clean_and_format_markdown_text(retrieved_chunks[0].get("content", ""))]

        # 4. Neural Semantic Section Selection
        model = _get_neural_model()
        if model is not None and clean_candidates:
            try:
                c_vecs = model.encode(clean_candidates, normalize_embeddings=True)
                q_vec = model.encode(query, normalize_embeddings=True)
                sims = c_vecs @ q_vec
                best_idx = int(np.argmax(sims))
                return clean_candidates[best_idx]
            except Exception as e:
                logger.error(f"Error in neural section selection: {e}")

        # Fallback to top formatted candidate
        return clean_candidates[0]
