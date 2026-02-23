ARG BUILD_FROM=alpine:3.13
FROM $BUILD_FROM

RUN \
  apk add --no-cache \
  bash \
  python3 \
  py3-pip \
  py3-wheel \
  py3-numpy \
  py3-pandas \
  gcc \
  musl-dev \
  python3-dev \
  libffi-dev \
  openssl-dev

RUN mkdir -p /usr/src/app /data

WORKDIR /usr/src/app

COPY ./requirements.txt /usr/src/app/
RUN pip3 install --no-cache-dir -r requirements.txt

COPY ./run.sh /usr/src/app/
COPY ./main.py /usr/src/app/
COPY ./trading/ /usr/src/app/trading/

RUN chmod a+x /usr/src/app/run.sh

CMD ["bash", "/usr/src/app/run.sh"]
