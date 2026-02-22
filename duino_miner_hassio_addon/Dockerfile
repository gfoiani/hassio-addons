ARG BUILD_FROM
FROM $BUILD_FROM

# Install requirements for add-on
RUN \
  apk add --no-cache \
  libstdc++ gcompat \
  python3 \
  py3-pip && \
  pip3 install --no-cache-dir requests


RUN mkdir -p /usr/src/app

WORKDIR /usr/src/app

# Copy application
COPY ./run.sh /usr/src/app/
COPY ./main.py /usr/src/app/
COPY ./miner.py /usr/src/app/
COPY ./fasthash.py /usr/src/app/

VOLUME /usr/src/app

RUN chmod a+x /usr/src/app/run.sh

CMD ["bash", "-c", "/usr/src/app/run.sh"]
