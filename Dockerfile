FROM python:3.11.2 as base
WORKDIR /app
ENV PYTHONUNBUFFERED=0
COPY requirements.txt ./
RUN pip install -U -r requirements.txt

FROM base as prod
COPY ./src ./
CMD ["/bin/bash", "-c", "python ./main.py"]

FROM base as debug
ENV DEBUG=1
ENV LOG_LEVEL=DEBUG
RUN pip install debugpy
CMD ["/bin/bash", "-c", "python -m debugpy --wait-for-client --listen 0.0.0.0:5678 ./src/main.py bot -c ./config.toml"]
