import logging
from typing import Dict, Any, List, Generator
from django.conf import settings
from rag_app.models import Document, DocumentChunk, ChatSession, ChatMessage
from rag_app.services.document_parser import DocumentParser
from rag_app.services.text_chunker import TextChunker
from rag_app.services.vector_store import VectorStoreService
from rag_app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    Main Orchestration Pipeline for Document Ingestion, Indexing, and Streaming Q&A.
    """

    @staticmethod
    def process_document(document: Document) -> bool:
        """
        Parses document, extracts chunks, computes embeddings, and stores them in DB.
        """
        try:
            document.status = 'processing'
            document.save(update_fields=['status'])

            file_path = document.file.path
            file_type = document.file_type or document.file.name.split('.')[-1]

            # 1. Parse pages
            pages = DocumentParser.parse_file(file_path, file_type=file_type)

            # 2. Chunk pages with context window
            chunk_size = getattr(settings, 'RAG_CHUNK_SIZE', 1500)
            chunk_overlap = getattr(settings, 'RAG_CHUNK_OVERLAP', 150)
            chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            raw_chunks = chunker.chunk_pages(pages)

            if not raw_chunks:
                raise ValueError("No text content could be extracted into chunks.")

            # 3. Generate dense embeddings in batches
            texts = [c["content"] for c in raw_chunks]
            embeddings = VectorStoreService.generate_embeddings(texts)

            # 4. Save chunks to database in bulk
            document.chunks.all().delete()

            chunk_objects = []
            total_chars = 0
            for idx, c in enumerate(raw_chunks):
                emb = embeddings[idx] if idx < len(embeddings) else None
                total_chars += len(c["content"])
                chunk_objects.append(
                    DocumentChunk(
                        document=document,
                        chunk_index=c["chunk_index"],
                        content=c["content"],
                        page_number=c.get("page_number"),
                        embedding=emb,
                        token_count=c.get("token_count", 0),
                    )
                )

            DocumentChunk.objects.bulk_create(chunk_objects, batch_size=250)

            # 5. Update document status
            document.total_chunks = len(chunk_objects)
            document.total_characters = total_chars
            document.status = 'indexed'
            document.error_message = None
            document.save()
            return True

        except Exception as e:
            logger.exception(f"Failed to process document {document.id}: {e}")
            document.status = 'failed'
            document.error_message = str(e)
            document.save()
            return False

    @staticmethod
    def answer_query(session: ChatSession, query: str, custom_api_key: str = None) -> Dict[str, Any]:
        """
        Executes hybrid RAG retrieval and synchronous response generation.
        """
        document = session.document
        top_k = getattr(settings, 'RAG_TOP_K', 6)

        # 1. Fetch chunks for document
        chunks_qs = document.chunks.all().values('id', 'chunk_index', 'content', 'page_number', 'embedding')
        chunks_list = list(chunks_qs)

        if not chunks_list:
            fallback_msg = "⚠️ Document has not been indexed yet or contains no readable chunks."
            assistant_msg = ChatMessage.objects.create(
                session=session,
                role='assistant',
                content=fallback_msg,
                sources=[]
            )
            return {
                "answer": fallback_msg,
                "sources": [],
                "provider": "System",
                "message_id": str(assistant_msg.id),
            }

        # 2. Hybrid vector search: find top-k relevant chunks
        ranked_chunks = VectorStoreService.search_similar_chunks(query, chunks_list, top_k=top_k)

        # 3. Format source citations
        source_citations = []
        for ch in ranked_chunks:
            source_citations.append({
                "chunk_index": ch.get("chunk_index"),
                "page_number": ch.get("page_number", 1),
                "similarity_score": ch.get("similarity_score", 0.0),
                "snippet": ch.get("content", "")[:280] + "..." if len(ch.get("content", "")) > 280 else ch.get("content", ""),
                "full_text": ch.get("content", "")
            })

        # 4. Fetch recent chat history
        recent_messages = session.messages.order_by('-created_at')[:6]
        chat_history = [
            {"role": m.role, "content": m.content}
            for m in reversed(recent_messages)
        ]

        # 5. Call LLM Service
        answer_text, provider_used = LLMService.generate_response(
            query=query,
            retrieved_chunks=ranked_chunks,
            document_obj=document,
            chat_history=chat_history,
            custom_api_key=custom_api_key
        )

        # 6. Save user message & assistant message
        ChatMessage.objects.create(
            session=session,
            role='user',
            content=query,
            sources=[]
        )

        assistant_msg = ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=answer_text,
            sources=source_citations
        )

        session.save()

        return {
            "answer": answer_text,
            "sources": source_citations,
            "provider": provider_used,
            "message_id": str(assistant_msg.id),
        }

    @staticmethod
    def stream_answer_query(session: ChatSession, query: str, custom_api_key: str = None) -> Generator[Dict[str, Any], None, None]:
        """
        Executes hybrid RAG retrieval and streams token-by-token chunks (ChatGPT/Claude style).
        Yields structured SSE event dictionaries:
          - {'type': 'meta', 'sources': [...], 'provider': '...'}
          - {'type': 'token', 'token': '...'}
          - {'type': 'done', 'answer': '...', 'message_id': '...'}
        """
        document = session.document
        top_k = getattr(settings, 'RAG_TOP_K', 6)

        chunks_qs = document.chunks.all().values('id', 'chunk_index', 'content', 'page_number', 'embedding')
        chunks_list = list(chunks_qs)

        if not chunks_list:
            fallback_msg = "⚠️ Document has not been indexed yet or contains no readable chunks."
            ChatMessage.objects.create(session=session, role='user', content=query, sources=[])
            msg = ChatMessage.objects.create(session=session, role='assistant', content=fallback_msg, sources=[])
            yield {"type": "meta", "sources": [], "provider": "System"}
            yield {"type": "token", "token": fallback_msg}
            yield {"type": "done", "answer": fallback_msg, "message_id": str(msg.id)}
            return

        # 1. Fast hybrid retrieval
        ranked_chunks = VectorStoreService.search_similar_chunks(query, chunks_list, top_k=top_k)

        # 2. Format citations
        source_citations = []
        for ch in ranked_chunks:
            source_citations.append({
                "chunk_index": ch.get("chunk_index"),
                "page_number": ch.get("page_number", 1),
                "similarity_score": ch.get("similarity_score", 0.0),
                "snippet": ch.get("content", "")[:280] + "..." if len(ch.get("content", "")) > 280 else ch.get("content", ""),
                "full_text": ch.get("content", "")
            })

        # Send metadata header first
        provider_badge = "Groq (Llama 3.3 70B)" if (getattr(settings, 'GROQ_API_KEY', '') or custom_api_key) else "Dense Semantic Engine"
        yield {"type": "meta", "sources": source_citations, "provider": provider_badge}

        # 3. Chat history
        recent_messages = session.messages.order_by('-created_at')[:6]
        chat_history = [
            {"role": m.role, "content": m.content}
            for m in reversed(recent_messages)
        ]

        # 4. Stream tokens
        full_tokens = []
        stream_gen = LLMService.stream_response(
            query=query,
            retrieved_chunks=ranked_chunks,
            document_obj=document,
            chat_history=chat_history,
            custom_api_key=custom_api_key
        )

        for token in stream_gen:
            full_tokens.append(token)
            yield {"type": "token", "token": token}

        full_answer = "".join(full_tokens).strip()

        # 5. Persist messages in DB
        ChatMessage.objects.create(
            session=session,
            role='user',
            content=query,
            sources=[]
        )
        assistant_msg = ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=full_answer,
            sources=source_citations
        )
        session.save()

        yield {"type": "done", "answer": full_answer, "message_id": str(assistant_msg.id)}
