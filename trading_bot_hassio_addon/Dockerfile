ARG BUILD_FROM=alpine:3.18
FROM $BUILD_FROM

# TARGETARCH is a Docker BuildKit automatic ARG (set at build time, not runtime).
# Values: amd64, arm64, arm.  Use it to select the right Java package without
# relying on uname -m under QEMU emulation.
#
# py3-pandas/numpy/lxml  – pre-compiled Alpine packages; avoids slow QEMU compilation of C
#                          extensions on armv7/armhf (pandas from source can take 20+ min)
# openjdk11-jre-headless – Java runtime for Directa Darwin Engine (amd64 / aarch64)
# arm (armv7/armhf)      – Java not available on 32-bit Alpine; Directa broker not supported
#                          on these platforms; XTB broker works fine without Java
# curl                   – used by run.sh to download DCL.jar / Engine.jar at first run
# nc                     – already provided by busybox in Alpine
ARG TARGETARCH
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
  curl && \
  case "${TARGETARCH}" in \
    arm) echo "INFO: Java not available for 32-bit ARM; Directa broker not supported on this platform" ;; \
    *)   apk add --no-cache openjdk11-jre-headless ;; \
  esac

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
