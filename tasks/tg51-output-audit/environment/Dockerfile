FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b

RUN pip install --no-cache-dir numpy==2.2.6 scipy==1.15.3

WORKDIR /app

COPY data /app/data
COPY tg51calc /app/tg51calc
RUN mkdir -p /app/output
