FROM python:3.11.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    TMPDIR=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1

WORKDIR /app

COPY requirements.txt requirements.lock /app/
RUN python -m pip install --no-cache-dir --only-binary=:all: --no-deps -r /app/requirements.lock \
    && python -m pip check

# Only the runtime belongs in the image; no datasets, reports, or credentials.
COPY harness/ /app/harness/
COPY run_agent.py /app/run_agent.py

# Fail at build time if the real SDK cannot load with the locked dependencies.
RUN python -c "from harness.workflow_runner import load_sdk; load_sdk()" \
    && rm -rf /tmp/openjiuwen_logs

ENTRYPOINT ["python"]
CMD ["/app/run_agent.py", "--tasks-dir", "/data/tasks"]
