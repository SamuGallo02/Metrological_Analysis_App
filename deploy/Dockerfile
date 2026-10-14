# Image of the server: standard library only, no dependencies to install.
FROM python:3.12-slim
WORKDIR /app
COPY common ./common
COPY server ./server
# Data (database, files, backups, logs) lives in the volume mounted on /data.
ENV AM_DATA=/data PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 analisi && mkdir /data && chown analisi /data
USER analisi
VOLUME /data
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8765/api/health', timeout=4)" || exit 1
# Behind a reverse proxy (see Caddyfile): --trust-proxy takes the real client address from X-Forwarded-For.
CMD ["sh", "-c", "python -m server --data \"$AM_DATA\" serve --host 0.0.0.0 --port 8765 --trust-proxy"]
