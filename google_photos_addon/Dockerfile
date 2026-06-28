ARG BUILD_FROM=ghcr.io/hassio-addons/base-python:13.0.0
FROM $BUILD_FROM

# Copy data for add-on
COPY . /app
WORKDIR /app
RUN pip3 install --no-cache-dir .

COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
