ARG BUILD_FROM=alpine:3.18
FROM $BUILD_FROM

# betfairlightweight is pure Python – no compiler toolchain needed.
# py3-wheel speeds up pip installs of pure-Python wheels.
RUN \
  apk add --no-cache \
  bash \
  python3 \
  py3-pip \
  py3-wheel

RUN mkdir -p /usr/src/app /data

WORKDIR /usr/src/app

COPY ./requirements.txt /usr/src/app/
RUN pip3 install --no-cache-dir --prefer-binary -r /usr/src/app/requirements.txt

COPY ./run.sh /usr/src/app/
COPY ./main.py /usr/src/app/
COPY ./betting/ /usr/src/app/betting/

RUN chmod a+x /usr/src/app/run.sh

CMD ["/usr/src/app/run.sh"]
