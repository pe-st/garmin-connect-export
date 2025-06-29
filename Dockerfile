FROM python:3.13-slim@sha256:f2fdaec50160418e0c2867ba3e254755edd067171725886d5d303fd7057bbf81

WORKDIR /app

# Install deps first to improve caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENTRYPOINT ["python3", "gcexport.py"]

# Default command if no arguments are provided to `docker run`
CMD ["--help"]
