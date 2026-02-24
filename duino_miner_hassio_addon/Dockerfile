ARG BUILD_FROM=homeassistant/amd64-base:3.13
FROM $BUILD_FROM

# Install requirements for add-on
RUN \
  apk add --no-cache \
  libstdc++ gcompat \
  python3 \
  py3-pip && \
  pip3 install --no-cache-dir requests

# Copy application
COPY ./run.sh /
COPY ./main.py /
COPY ./miner.py /
COPY ./fasthash.py /

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
