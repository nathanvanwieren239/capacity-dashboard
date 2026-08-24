# Launch Tracker
#
# Single-stage build. The application is pure Python with no compiled
# dependencies, so there is nothing to build and nothing to strip out.
#
# NOTE FOR DEPLOYMENT: /app/data must be a mounted volume. Everything the
# application writes — the database, the audit log and the backup snapshots —
# lives there. If it stays inside the container it is destroyed on every
# redeploy, silently. See docker-compose.yml and DEPLOY.md.

FROM python:3.12-slim

# Do not write .pyc files, do not buffer stdout (so logs appear immediately).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so code changes do not invalidate the pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code. Anything not needed at runtime is excluded by
# .dockerignore — notably data/, .git/ and the local virtualenv.
COPY . .

# Run as an unprivileged user. The data directory is created and handed to
# that user so a mounted volume is writable.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 tracker \
    && mkdir -p /app/data \
    && chown -R tracker:tracker /app

USER tracker

EXPOSE 8501

# Streamlit's own health endpoint. Container orchestrators use this to know
# when the app is genuinely ready rather than merely started.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4).status==200 else 1)"

# headless          no attempt to open a browser
# address 0.0.0.0   listen on all interfaces so the port mapping works
# gatherUsageStats  telemetry off (also set in .streamlit/config.toml)
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
