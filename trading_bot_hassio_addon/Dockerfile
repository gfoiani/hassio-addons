ARG BUILD_FROM=alpine:3.18
FROM $BUILD_FROM

# Install system dependencies
# py3-pandas/numpy/lxml  – pre-compiled Alpine packages; avoids slow QEMU compilation of C extensions
#                          on armv7/armhf (pandas from source via QEMU can take 20+ minutes)
# openjdk11-jre-headless – Java runtime for Directa Darwin CommandLine (DCL.jar)
# curl                   – used by run.sh to download DCL.jar on first run
# nc                     – already provided by busybox in Alpine
RUN \
  apk add --no-cache \
  bash \
  python3 \
  py3-pip \
  py3-wheel \
  py3-pandas \
  py3-numpy \
  py3-lxml \
  gcc \
  musl-dev \
  python3-dev \
  libffi-dev \
  openssl-dev \
  openjdk11-jre-headless \
  curl

RUN mkdir -p /usr/src/app /data

WORKDIR /usr/src/app

# Copy application files
COPY ./run.sh /usr/src/app/
COPY ./main.py /usr/src/app/
COPY ./requirements.txt /usr/src/app/
COPY ./trading/ /usr/src/app/trading/

RUN pip3 install --no-cache-dir --prefer-binary -r /usr/src/app/requirements.txt

RUN chmod a+x /usr/src/app/run.sh

CMD ["/usr/src/app/run.sh"]
