import threading
from django.apps import AppConfig


class RagAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rag_app'

    def ready(self):
        # Pre-warm embedding model in background at server start to eliminate cold-start latency
        def prewarm():
            try:
                from rag_app.services.vector_store import _get_neural_model
                _get_neural_model()
            except Exception:
                pass

        threading.Thread(target=prewarm, daemon=True).start()
