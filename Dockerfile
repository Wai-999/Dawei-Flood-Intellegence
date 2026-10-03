FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FLOOD_ENV=production FLOOD_DATABASE=/data/flood.sqlite3
WORKDIR /app
COPY requirements-production.txt /app/
RUN pip install --no-cache-dir -r requirements-production.txt && groupadd --gid 10001 flood && useradd --uid 10001 --gid 10001 --no-create-home flood && mkdir /data /backups && chown flood:flood /data /backups
COPY flood /app/flood
COPY database /app/database
COPY apps/dashboard /app/apps/dashboard
COPY deploy /app/deploy
RUN chmod 555 /app/deploy/entrypoint.sh
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -m flood.probe
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
