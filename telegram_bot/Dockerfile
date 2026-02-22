FROM python:3.12-slim

# Non bufferizzare stdout/stderr: i log appaiono subito in docker logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice dell'applicazione
COPY main.py .

# Porta su cui uvicorn ascolta (sovrascrivibile con -e PORT=xxxx)
ENV PORT=8000

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
