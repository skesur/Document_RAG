import os
import tempfile
from django.test import TransactionTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rag_app.models import Document, DocumentChunk, ChatSession, ChatMessage
from rag_app.services.document_parser import DocumentParser
from rag_app.services.text_chunker import TextChunker
from rag_app.services.vector_store import VectorStoreService
from rag_app.services.rag_pipeline import RAGPipeline


class DocumentRAGTestCase(TransactionTestCase):

    def setUp(self):
        self.sample_text = (
            "Cybernetics is a transdisciplinary approach for exploring regulatory and purposive systems. "
            "In the 21st century, neural networks and vector embeddings revolutionized artificial intelligence. "
            "RAG (Retrieval-Augmented Generation) optimizes the output of large language models by referencing authoritative knowledge bases."
        )

    def test_text_chunker(self):
        pages = [{"content": self.sample_text, "page_number": 1}]
        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk_pages(pages)
        self.assertTrue(len(chunks) > 0)
        self.assertEqual(chunks[0]["page_number"], 1)

    def test_vector_store_similarity(self):
        texts = [
            "Neural networks and vector embeddings are essential for semantic search.",
            "Photosynthesis is the process by which green plants make food from sunlight.",
            "Django is a high-level Python web framework that enables rapid development."
        ]
        embeddings = VectorStoreService.generate_embeddings(texts)
        self.assertEqual(len(embeddings), 3)

        chunks_data = [
            {"chunk_index": i, "content": texts[i], "embedding": embeddings[i], "page_number": 1}
            for i in range(len(texts))
        ]

        # Query related to AI/Neural search
        results = VectorStoreService.search_similar_chunks("Tell me about vector embeddings and neural models", chunks_data, top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["chunk_index"], 0)
        self.assertTrue(results[0]["similarity_score"] > 0.3)

    def test_pipeline_document_processing_and_qa(self):
        # Create a document file
        uploaded_file = SimpleUploadedFile(
            "cyber_ai_guide.txt",
            self.sample_text.encode('utf-8'),
            content_type="text/plain"
        )
        doc = Document.objects.create(
            title="Cyber AI Guide",
            file=uploaded_file,
            file_type="txt"
        )

        success = RAGPipeline.process_document(doc)
        self.assertTrue(success)
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'indexed')
        self.assertTrue(doc.total_chunks > 0)

        # Create session and query
        session = ChatSession.objects.create(document=doc, title="Test Session")
        result = RAGPipeline.answer_query(session, "What is RAG?")

        self.assertIn("answer", result)
        self.assertTrue(len(result["sources"]) > 0)
        self.assertEqual(session.messages.count(), 2)  # 1 user + 1 assistant

    def test_api_endpoints(self):
        # Test health check
        health_resp = self.client.get(reverse('rag_app:health_check'))
        self.assertEqual(health_resp.status_code, 200)
        self.assertEqual(health_resp.json()["status"], "healthy")

        # Test upload API
        file_data = SimpleUploadedFile(
            "api_test_doc.md",
            b"# Cyber System Architecture\nThis matrix system operates on high-speed vector retrieval.",
            content_type="text/markdown"
        )
        upload_resp = self.client.post(
            reverse('rag_app:api_upload') + '?sync=true',
            {'file': file_data, 'title': 'Matrix Architecture API Test'},
            format='multipart'
        )
        self.assertEqual(upload_resp.status_code, 201)
        data = upload_resp.json()
        self.assertTrue(data["success"])
        self.assertIn("session_id", data)

        # Test ask API
        session_id = data["session_id"]
        ask_resp = self.client.post(
            reverse('rag_app:api_chat_ask', kwargs={'session_id': session_id}),
            {'message': 'What does the matrix system operate on?'},
            content_type='application/json'
        )
        self.assertEqual(ask_resp.status_code, 200)
        self.assertIn("answer", ask_resp.json())
