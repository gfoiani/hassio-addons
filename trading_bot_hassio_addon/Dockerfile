ARG BUILD_FROM=alpine:3.13
FROM $BUILD_FROM

# Install system dependencies
# openjdk8-jre  – Java runtime for Directa Darwin CommandLine (DCL.jar)
#                 (openjdk11 is not available for armv7 in Alpine 3.13; jdk8 suffices)
# curl          – used by run.sh to download DCL.jar on first run
# nc            – already provided by busybox in Alpine (no separate package needed)
RUN \
  apk add --no-cache \
  bash \
  python3 \
  py3-pip \
  py3-wheel \
  gcc \
  musl-dev \
  python3-dev \
  libffi-dev \
  openssl-dev \
  openjdk8-jre \
  curl

RUN mkdir -p /usr/src/app /data

WORKDIR /usr/src/app

# Copy application files
COPY ./run.sh /usr/src/app/
COPY ./main.py /usr/src/app/
COPY ./requirements.txt /usr/src/app/
COPY ./trading/ /usr/src/app/trading/

RUN pip3 install --no-cache-dir -r /usr/src/app/requirements.txt

RUN chmod a+x /usr/src/app/run.sh

CMD ["/usr/src/app/run.sh"]
