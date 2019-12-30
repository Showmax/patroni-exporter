FROM  python:3.6-alpine

# use dumb-init as container supervisor
RUN apk add dumb-init

WORKDIR "/app"

COPY patroni_exporter.py .
COPY requirements.txt .

RUN pip install \
	--no-cache-dir \
	-r requirements.txt

ENTRYPOINT [ "/usr/bin/dumb-init",  "--", "/app/patroni_exporter.py" ]
