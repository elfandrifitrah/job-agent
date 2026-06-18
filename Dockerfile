FROM python:3.12

WORKDIR /app

# Install lightweight Python deps (heavy AI/automation loaded lazily at runtime)
COPY requirements-hf.txt ./
RUN pip install --no-cache-dir --default-timeout=120 -r requirements-hf.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data/chroma /app/data/cvs /app/data/cover_letters /app/data/screenshots

EXPOSE 7860

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860} --log-level info
