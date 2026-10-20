# NHM runtime image: Python 3.11 + Node 22 + the pinned Python dependencies. The repository itself is bind-mounted at /app by compose.yaml
# (the launcher needs the git history, the .env file and the data directory), so the image only carries the toolchain.
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates socat build-essential \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-dev.lock requirements-capstone-auth.lock requirements-hardware.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.14.0" \
 && /opt/venv/bin/pip install -r requirements-dev.lock -r requirements-capstone-auth.lock -r requirements-hardware.txt

ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=src:.
COPY docker/entrypoint.sh /usr/local/bin/nhm-entrypoint
# sitecustomize lives in site-packages because the launcher gives its child processes their own PYTHONPATH (src:.)
COPY docker/sitecustomize.py /opt/venv/lib/python3.11/site-packages/sitecustomize.py
RUN chmod +x /usr/local/bin/nhm-entrypoint
EXPOSE 4180
ENTRYPOINT ["nhm-entrypoint"]
CMD ["--durable"]
