import uuid
from django.db import models


class Document(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Matrix Upload'),
        ('processing', 'Processing & Vectorizing'),
        ('indexed', 'Fully Indexed & Online'),
        ('failed', 'Vectorization Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/%Y/%m/')
    file_type = models.CharField(max_length=20, default='txt')
    file_size = models.PositiveIntegerField(default=0, help_text="Size in bytes")
    total_chunks = models.PositiveIntegerField(default=0)
    total_characters = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, default='')
    topics_json = models.JSONField(default=list, blank=True)
    structure_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} [{self.status.upper()}]"

    @property
    def formatted_size(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.2f} MB"


class DocumentChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='chunks'
    )
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    page_number = models.PositiveIntegerField(null=True, blank=True)
    embedding = models.JSONField(null=True, blank=True, help_text="Float array representation of vector")
    token_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chunk_index']
        indexes = [
            models.Index(fields=['document', 'chunk_index']),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} ({self.document.title})"


class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='chat_sessions'
    )
    title = models.CharField(max_length=255, default='Cyberpunk Dialogue Matrix')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Session: {self.title} ({self.document.title})"


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User / Operator'),
        ('assistant', 'Cyber AI Assistant'),
        ('system', 'System / Matrix Protocol'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    sources = models.JSONField(default=list, blank=True, help_text="Retrieved chunks and similarity metrics")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role.upper()}] {self.content[:40]}..."
