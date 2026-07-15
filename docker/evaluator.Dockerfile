FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STARSIM_INSTALL_FONTS=0 \
    HOME=/tmp \
    NUMBA_CACHE_DIR=/tmp/numba \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /opt/epiagentbench
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir '.[starsim]'

# This image is trusted. Episode-specific secrets should be injected at run
# time, never baked into the image or mounted into the agent container.
RUN useradd --no-create-home --uid 65531 --shell /usr/sbin/nologin evaluator
USER 65531:65531
