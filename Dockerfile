FROM python:3.12-alpine as base
RUN apk add --no-cache git build-base
WORKDIR /app
ENV PYTHONUNBUFFERED=0
COPY requirements.txt ./
RUN pip install -U -r requirements.txt

FROM base as debug
ENV DEBUG=1
ENV LOG_LEVEL=DEBUG
RUN pip install debugpy
CMD ["/bin/sh", "-c", "python -m debugpy --wait-for-client --listen 0.0.0.0:5678 ./src/main.py bot -c ./config.toml"]

FROM base as prod
COPY ./src ./
CMD ["/bin/sh", "-c", "python ./main.py"]
