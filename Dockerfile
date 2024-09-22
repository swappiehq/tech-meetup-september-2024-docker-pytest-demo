# This is a very simple demo Dockerfile file that does only that:
# 1) install `docker` & `docker compose`
# 2) install python packages
# 3) and copy the whole project to the /demo folder inside image
FROM python:3.12-alpine
RUN apk add docker docker-compose
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . /demo
WORKDIR /demo
