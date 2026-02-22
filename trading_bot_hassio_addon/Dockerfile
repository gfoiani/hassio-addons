ARG BUILD_FROM=alpine:3.13
FROM $BUILD_FROM

# Install system dependencies
# openjdk11-jre-headless  – Java runtime for Directa Darwin CommandLine (DCL.jar)
#                           (openjdk17 not available in Alpine 3.13; jdk11 suffices)
# netcat-openbsd           – used by run.sh to wait for Darwin sockets to be ready
# curl                     – used by run.sh to download DCL.jar on first run
RUN \
  apk add --no-cache \
  python3 \
  py3-pip \
  py3-wheel \
  gcc \
  musl-dev \
  python3-dev \
  libffi-dev \
  openssl-dev \
  openjdk11-jre-headless \
  netcat-openbsd \
  curl

RUN mkdir -p /usr/src/app /data

WORKDIR /usr/src/app

# Copy application files
COPY ./run.sh /usr/src/app/
COPY ./main.py /usr/src/app/
COPY ./requirements.txt /usr/src/app/
COPY ./trading/ /usr/src/app/trading/

RUN chmod a+x /usr/src/app/run.sh

CMD ["bash", "-c", "/usr/src/app/run.sh"]
