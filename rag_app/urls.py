from django.urls import path
from rag_app import views

app_name = 'rag_app'

urlpatterns = [
    # UI Views
    path('', views.index_view, name='index'),
    path('chat/<uuid:document_id>/', views.chat_view, name='chat'),

    # REST APIs
    path('api/documents/upload/', views.upload_document_api, name='api_upload'),
    path('api/documents/<uuid:document_id>/status/', views.document_status_api, name='api_document_status'),
    path('api/documents/<uuid:document_id>/delete/', views.delete_document_api, name='api_document_delete'),
    path('api/chat/<uuid:session_id>/ask/', views.chat_ask_api, name='api_chat_ask'),
    
    # System Health
    path('health/', views.health_check, name='health_check'),
]
