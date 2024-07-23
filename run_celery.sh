celery -A app.celery beat --loglevel=info
celery -A app.celery worker -l info -E