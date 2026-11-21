FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
COPY software/chainlink/webapp/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    XDG_CONFIG_HOME=/data

RUN useradd --system --uid 10001 --create-home splitflap \
    && mkdir -p /data/splitflap-webapp \
    && chown -R splitflap:splitflap /data

COPY --from=builder /opt/venv /opt/venv
COPY software/chainlink/proto_gen/splitflap_pb2.py software/chainlink/proto_gen/nanopb_pb2.py /app/proto_gen/
COPY software/chainlink/webapp/app.py software/chainlink/webapp/protocol.py software/chainlink/webapp/serial_service.py /app/webapp/
COPY software/chainlink/webapp/static/ /app/webapp/static/

WORKDIR /app/webapp
USER splitflap
EXPOSE 8765
ENTRYPOINT ["/opt/venv/bin/python", "/app/webapp/app.py"]
CMD ["--host", "0.0.0.0", "--port", "8765"]