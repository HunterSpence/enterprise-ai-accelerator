# NOTE: This Dockerfile is intentionally imperfect for demo purposes.
# Issues flagged by containerization_scorer:
#   - Base image not pinned to a digest (supply-chain risk)
#   - Uses python:3.9 (not slim variant — larger attack surface)
#   - Runs as root (no USER directive)
#   - No HEALTHCHECK directive
#   - Copies entire working directory (no .dockerignore equivalent)
FROM python:3.9

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_APP=app.py
ENV FLASK_ENV=production

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
