FROM python:3.6-alpine

# use dumb-init as container supervisor
RUN apk add dumb-init

WORKDIR "/app"

COPY patroni_exporter.py .
COPY requirements.txt .

RUN pip install \
	--no-cache-dir \
	-r requirements.txt

# run application process with non-root user
RUN addgroup -S patroni_exporter \
	&& adduser -H -S -G patroni_exporter patroni_exporter

USER patroni_exporter

ENTRYPOINT [ "/usr/bin/dumb-init",  "--", "/app/patroni_exporter.py" ]
