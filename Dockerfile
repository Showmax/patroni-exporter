FROM  python:3.6.9-alpine3.10

WORKDIR /app

COPY patroni_exporter.py .
COPY requirements.txt .

RUN pip install -r requirements.txt   

ENTRYPOINT [ "python",  "patroni_exporter.py"]
