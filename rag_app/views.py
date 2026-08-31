import os
import json
import logging
import threading
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.conf import settings
from django.db import connection
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

from rag_app.models import Document, DocumentChunk, ChatSession, ChatMessage
from rag_app.services.rag_pipeline import RAGPipeline
from rag_app.serializers import DocumentSerializer, ChatSessionSerializer

logger = logging.getLogger(__name__)


def _background_index_worker(document_id):
    """Background worker to index large documents without blocking HTTP requests."""
    try:
        from rag_app.models import Document
        doc = Document.objects.get(id=document_id)
        RAGPipeline.process_document(doc)
    except Exception as e:
        logger.exception(f"Background vectorization error on doc {document_id}: {e}")
    finally:
        connection.close()


# ==========================================
# PAGE VIEWS (CYBERPUNK FRONTEND)
# ==========================================

def index_view(request):
    """
    Main Cyberpunk Document Matrix & Upload Terminal.
    """
    documents = Document.objects.all().order_by('-created_at')
    has_groq = bool(getattr(settings, 'GROQ_API_KEY', '') or os.environ.get('GROQ_API_KEY'))

    context = {
        'documents': documents,
        'has_groq': has_groq,
        'embedding_model': getattr(settings, 'EMBEDDING_MODEL_NAME', 'all-MiniLM-L6-v2'),
    }
    return render(request, 'rag_app/upload.html', context)


def chat_view(request, document_id):
    """
    Interactive Cyber Chat Terminal for a specific document.
    """
    document = get_object_or_404(Document, id=document_id)
    
    # Auto create or fetch the most recent chat session for this doc
    session = document.chat_sessions.first()
    if not session:
        session = ChatSession.objects.create(
            document=document,
            title=f"Session: {document.title[:30]}"
        )

    all_docs = Document.objects.all().order_by('-created_at')
    messages = session.messages.all().order_by('created_at')

    context = {
        'document': document,
        'session': session,
        'all_docs': all_docs,
        'messages': messages,
        'embedding_model': getattr(settings, 'EMBEDDING_MODEL_NAME', 'all-MiniLM-L6-v2'),
    }
    return render(request, 'rag_app/chat.html', context)


# ==========================================
# REST API ENDPOINTS
# ==========================================

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def upload_document_api(request):
    """
    Fast API to upload a document and initiate high-speed background vector indexing.
    """
    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response(
            {"error": "No document file uploaded."},
            status=status.HTTP_400_BAD_REQUEST
        )

    ext = file_obj.name.split('.')[-1].lower()
    allowed_exts = ['pdf', 'txt', 'md', 'markdown', 'csv', 'json', 'log', 'py']
    if ext not in allowed_exts:
        return Response(
            {"error": f"Unsupported file format '.{ext}'. Supported: {', '.join(allowed_exts)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    title = request.POST.get('title') or file_obj.name

    # Create document record with processing status
    doc = Document.objects.create(
        title=title,
        file=file_obj,
        file_type=ext,
        file_size=file_obj.size,
        status='processing'
    )

    # Create initial chat session
    session = ChatSession.objects.create(
        document=doc,
        title=f"Session: {doc.title[:30]}"
    )

    is_sync = request.GET.get('sync') == 'true'
    if is_sync:
        _background_index_worker(str(doc.id))
    else:
        thread = threading.Thread(target=_background_index_worker, args=(str(doc.id),), daemon=True)
        thread.start()

    return Response({
        "success": True,
        "document_id": str(doc.id),
        "session_id": str(session.id),
        "title": doc.title,
        "status": "processing",
        "formatted_size": doc.formatted_size,
        "redirect_url": f"/chat/{doc.id}/"
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def chat_ask_api(request, session_id):
    """
    API to ask a question to a specific chat session with rich grounded response.
    """
    session = get_object_or_404(ChatSession, id=session_id)
    user_query = request.data.get('message', '').strip()
    custom_api_key = request.data.get('api_key', '').strip() or request.session.get('user_api_key', '')

    if not user_query:
        return Response(
            {"error": "Query message cannot be empty."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # If document is still processing in background
    if session.document.status == 'processing':
        return Response({
            "answer": "⚡ **Document is currently indexing in the matrix.** Please wait a moment and try again shortly.",
            "sources": [],
            "provider": "System"
        }, status=status.HTTP_200_OK)

    # Check if client requested streaming (?stream=true or Accept: text/event-stream)
    is_stream = request.GET.get('stream') == 'true' or 'text/event-stream' in request.headers.get('Accept', '')

    if is_stream:
        def event_stream():
            for event in RAGPipeline.stream_answer_query(session, user_query, custom_api_key=custom_api_key):
                yield f"data: {json.dumps(event)}\n\n"

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    result = RAGPipeline.answer_query(session, user_query, custom_api_key=custom_api_key)
    return Response(result, status=status.HTTP_200_OK)


@api_view(['POST'])
def reindex_document_api(request, document_id):
    """
    API to reindex an existing document with the upgraded chunker and hybrid embeddings.
    """
    doc = get_object_or_404(Document, id=document_id)
    doc.status = 'processing'
    doc.save(update_fields=['status'])

    thread = threading.Thread(target=_background_index_worker, args=(str(doc.id),), daemon=True)
    thread.start()

    return Response({
        "success": True,
        "status": "processing"
    })


@api_view(['GET'])
def document_status_api(request, document_id):
    """
    API to check real-time processing/indexing status of a document.
    """
    doc = get_object_or_404(Document, id=document_id)
    return Response({
        "id": str(doc.id),
        "status": doc.status,
        "total_chunks": doc.total_chunks,
        "total_characters": doc.total_characters,
        "error_message": doc.error_message
    })


@api_view(['DELETE', 'POST'])
def delete_document_api(request, document_id):
    """
    API to delete a document and all related chunks/sessions.
    """
    doc = get_object_or_404(Document, id=document_id)
    try:
        if doc.file and os.path.isfile(doc.file.path):
            os.remove(doc.file.path)
    except Exception as e:
        logger.warning(f"Could not delete physical file for doc {doc.id}: {e}")

    doc.delete()
    return Response({"success": True, "message": "Document wiped from matrix."})


def health_check(request):
    """
    Deployment health check endpoint.
    """
    return JsonResponse({
        "status": "healthy",
        "service": "Document_RAG Matrix Core",
        "version": "2.2.0"
    })
