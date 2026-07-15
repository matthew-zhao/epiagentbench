FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --no-create-home --uid 65532 --shell /usr/sbin/nologin agent \
    && mkdir -p /work /scratch \
    && chown 65532:65532 /work /scratch

# Deliberately copy only the public client. The evaluator package, generator,
# Starsim, parameters, seeds, oracle, scorer, and tests are absent.
COPY src/epiagentbench_client /usr/local/lib/python3.13/site-packages/epiagentbench_client

USER 65532:65532
WORKDIR /scratch
ENTRYPOINT ["python", "-I", "/work/agent.py"]
