FROM debian:bookworm-slim

ENV LANG=en_US.UTF-8
ENV QGIS_PREFIX_PATH=/usr
ENV QGIS_SERVER_LOG_STDERR=1
ENV QGIS_SERVER_LOG_LEVEL=2
ENV TINI_VERSION=v0.19.0

RUN apt-get update \
    && apt-get install --no-install-recommends --no-install-suggests -y \
        ca-certificates \
        gnupg \
        locales \
        spawn-fcgi \
        wget \
        xauth \
        xvfb \
    && localedef -i en_US -f UTF-8 en_US.UTF-8 \
    && mkdir -m755 -p /etc/apt/keyrings \
    && wget -O /etc/apt/keyrings/qgis-archive-keyring.gpg https://qgis.org/downloads/qgis-archive-keyring.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/qgis-archive-keyring.gpg] https://qgis.org/debian bookworm main" > /etc/apt/sources.list.d/qgis.list \
    && apt-get update \
    && apt-get install --no-install-recommends --no-install-suggests -y qgis-server \
    && wget -O /tini https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini \
    && chmod +x /tini \
    && apt-get remove --purge -y gnupg wget \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m qgis

COPY cmd.sh /home/qgis/cmd.sh
RUN chmod 755 /home/qgis/cmd.sh && chown qgis:qgis /home/qgis/cmd.sh

USER qgis
WORKDIR /home/qgis

ENTRYPOINT ["/tini", "--"]
CMD ["/home/qgis/cmd.sh"]
