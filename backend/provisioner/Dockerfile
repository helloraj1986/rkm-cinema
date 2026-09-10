FROM python:3.11-slim

WORKDIR /app

# Shared config layer (build context = ./backend) so the provisioner uses the
# SAME MEDIA_LIBRARY_N_* parser as the api — one source of truth, no copies.
COPY config/media_libraries.py /app/config/media_libraries.py
COPY provisioner/provision.py /app/provision.py

ENV PYTHONPATH=/app

CMD ["python", "/app/provision.py"]
