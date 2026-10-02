FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace/backend

COPY backend/requirements-live.txt /tmp/requirements-live.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-live.txt \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin kavach

COPY --chown=10001:10001 backend/app /workspace/backend/app
COPY --chown=10001:10001 backend/data /workspace/backend/data
COPY --chown=10001:10001 frontend /workspace/frontend

USER 10001:10001
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3)"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
