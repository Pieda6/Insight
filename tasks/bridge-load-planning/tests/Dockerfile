FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b

RUN pip install --no-cache-dir pytest==9.1.1 pytest-json-ctrf==0.5.2

# Build context is tests/: test.sh, test_outputs.py, engine.py, expected.json, data/.
COPY . /tests/

# Parent of every declared artifact path.
RUN mkdir -p /app
