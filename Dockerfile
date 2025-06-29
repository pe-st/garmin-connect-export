FROM python:3.13-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python3", "gcexport.py"]

# Default command if no arguments are provided to `docker run`
CMD ["--help"]
