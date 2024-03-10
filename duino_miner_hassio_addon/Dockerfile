ARG BUILD_FROM
FROM $BUILD_FROM

# Install requirements for add-on
RUN \
  apk add --no-cache \
  libstdc++ gcompat \
  python3 \
  py3-pip

# Copy application
COPY ./run.sh /
COPY ./main.py /
COPY ./miner.py /
COPY ./fasthash.py /

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
