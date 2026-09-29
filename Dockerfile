FROM node:22-bookworm-slim AS ui
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-impress poppler-utils fonts-dejavu-core fonts-liberation fontconfig && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .
COPY examples/ ./examples/
COPY LICENSE ./LICENSE
COPY third_party/ ./third_party/
COPY --from=ui /build/dist ./frontend/dist/
RUN useradd -u 10001 -m designer && mkdir /data && chown designer:designer /data
USER designer
ENV LCT_RENDERER=local LCT_DATA_DIR=/data LCT_APP_ROOT=/app PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["lct-design", "serve", "--host", "0.0.0.0", "--port", "8000", "--data", "/data"]
