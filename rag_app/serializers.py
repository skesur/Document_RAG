from rest_framework import serializers
from rag_app.models import Document, DocumentChunk, ChatSession, ChatMessage


class DocumentSerializer(serializers.ModelSerializer):
    formatted_size = serializers.ReadOnlyField()

    class Meta:
        model = Document
        fields = [
            'id', 'title', 'file', 'file_type', 'file_size',
            'formatted_size', 'total_chunks', 'total_characters',
            'status', 'error_message', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'file_size', 'total_chunks', 'total_characters', 'status', 'error_message', 'created_at', 'updated_at']


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = ['id', 'chunk_index', 'content', 'page_number', 'token_count']


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'sources', 'created_at']


class ChatSessionSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)
    document_title = serializers.CharField(source='document.title', read_only=True)

    class Meta:
        model = ChatSession
        fields = ['id', 'document', 'document_title', 'title', 'messages', 'created_at', 'updated_at']
