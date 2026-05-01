FROM python:3.13-slim

WORKDIR /build

COPY pyproject.toml /build/pyproject.toml
COPY README.md /build/README.md
COPY src /build/src

RUN pip install --no-cache-dir .

WORKDIR /app
COPY docker/harness/run_tracer.py /app/run_tracer.py

CMD ["sh", "-c", "browser-harness -c \"$(cat /app/run_tracer.py)\""]
