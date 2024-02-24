ARG BUILD_FROM
FROM $BUILD_FROM

# Install requirements for add-on
RUN \
  apk add --no-cache \
    python3 \
    py3-pip


# Copy data for add-on
COPY run.sh /
COPY main.py /
COPY miner.py /

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]