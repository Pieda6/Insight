FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b

RUN pip install --no-cache-dir numpy==2.1.3 scipy==1.14.1 ortools==9.11.4210

WORKDIR /app

COPY data /app/data
COPY reference /app/reference
RUN mkdir -p /app/output
