ARG BUILD_FROM=alpine:3.18
FROM $BUILD_FROM

# py3-pandas / py3-numpy – pre-compiled Alpine packages; avoids QEMU compilation of C
#                          extensions (pandas from source can take 20+ min under emulation)
# All pip packages (requests, pytz, websocket-client) are pure Python – no gcc needed.
# Market data uses direct Yahoo Finance HTTP calls (trading/data.py) instead of yfinance,
# eliminating the lxml/frozendict/peewee C-extension chain entirely.
# openjdk11-jre-headless – Java runtime for Directa Darwin Engine
# curl                   – used by run.sh to download DCL.jar / Engine.jar at first run
# nc                     – already provided by busybox in Alpine
RUN \
  apk add --no-cache \
  bash \
  python3 \
  py3-pip \
  py3-pandas \
  py3-numpy \
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
