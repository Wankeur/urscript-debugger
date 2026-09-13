FROM python:3.12-slim

RUN useradd --create-home --shell /usr/sbin/nologin licenseserver
WORKDIR /app
COPY server.py .
RUN chown -R licenseserver:licenseserver /app
USER licenseserver

ENV LICENSE_DB_PATH=/data/licenses.db
EXPOSE 8080
CMD ["python3", "server.py"]
