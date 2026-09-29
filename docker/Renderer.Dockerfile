FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-impress poppler-utils fonts-dejavu-core fonts-liberation fontconfig && rm -rf /var/lib/apt/lists/*
ENV HOME=/tmp
WORKDIR /work
