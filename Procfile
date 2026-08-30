web: python manage.py migrate --noinput && gunicorn document_rag.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
