FROM python:3.13-slim-bookworm AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.lock requirements.txt ./
RUN pip install --no-cache-dir -r requirements.lock

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LINAS_CONFIG_SOURCE=env \
    LINAS_LOG_FORMAT=json \
    PYTHONPYCACHEPREFIX=/tmp/pycache

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin linas

COPY --from=build /usr/local /usr/local
WORKDIR /app
COPY --chown=linas:linas . /app
USER 10001
EXPOSE 8003
ENTRYPOINT ["/app/scripts/container_entrypoint.sh"]
CMD ["api"]
