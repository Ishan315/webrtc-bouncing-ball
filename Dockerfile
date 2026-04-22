FROM python:3.11-slim

# Install system dependencies for OpenCV and GStreamer/ffmpeg (needed by av/aiortc)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libavdevice-dev \
    libavfilter-dev \
    libavformat-dev \
    libavcodec-dev \
    libswresample-dev \
    libswscale-dev \
    libavutil-dev \
    openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Certificates (cert.pem and key.pem) are copied from the host to ensure 
# consistency with the hash pinned in main.js

EXPOSE 4433/tcp
EXPOSE 4433/udp
EXPOSE 50000/udp

CMD ["python", "server.py"]
