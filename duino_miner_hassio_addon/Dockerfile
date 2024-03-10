ARG BUILD_FROM
FROM $BUILD_FROM

# Install requirements for add-on
RUN \
  apk add --no-cache \
  libstdc++ gcompat \
  python3 \
  py3-pip


RUN mkdir -p /usr/src/app

WORKDIR /usr/src/app

# Copy application
COPY ./run.sh /usr/src/app/
COPY ./main.py /usr/src/app/
COPY ./miner.py /usr/src/app/
COPY ./fasthash.py /usr/src/app/

VOLUME /usr/src/app

RUN chmod a+x /usr/src/app/run.sh

CMD ["sh", "-c", "./run.sh"]
