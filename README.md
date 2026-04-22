# WebRTC & WebTransport Bouncing Ball Tracker

A high-performance, real-time video tracking system. The server streams a bouncing ball via WebRTC (H.264), while the client tracks the ball and returns coordinates via WebTransport (HTTP/3) for real-time error calculation.

## Architecture
- **Backend**: Python (aiortc, aioquic, aiohttp)
- **Frontend**: Vanilla JS (WebTransport API, WebRTC API, Canvas API)
- **Signaling**: SDP exchange over WebTransport Bidirectional Streams
- **Telemetry**: Low-latency coordinate and error reporting over WebTransport

## 1. Local Development Setup

### Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Generate Certificates
WebTransport requires a specific ECDSA certificate for localhost development.
```bash
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout key.pem -out cert.pem -days 13 -nodes -subj '/CN=localhost'
```

### Run Server
```bash
python server.py
```

### Launch Client (Chrome)
You **must** use these flags for WebTransport to connect to a self-signed localhost certificate.
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --origin-to-force-quic-on=localhost:4433 \
  --ignore-certificate-errors \
  --webtransport-developer-mode \
  https://localhost:4433
```

## 2. Docker Deployment

### Build Image
```bash
docker build -t webrtc-server:latest .
```

### Run Container
```bash
docker run -it --rm \
  -p 4433:4433/tcp \
  -p 4433:4433/udp \
  -p 50000:50000/udp \
  webrtc-server:latest
```

## 3. Kubernetes (Minikube)
```bash
minikube start
eval $(minikube docker-env)
docker build -t webrtc-server:latest .
kubectl apply -f k8s-deployment.yaml
minikube service webrtc-service --url
```

## 4. Testing
```bash
pytest test_ball.py test_integration.py
```

## Design Decisions
- **Fixed Media Port (50000)**: Used to ensure WebRTC media can traverse Docker NAT without requiring range mapping.
- **Dual Protocol Listener**: The server listens on both TCP (initial web page load) and UDP (WebTransport/HTTP3) on port 4433.
- **SDP IP Hack**: Automatically replaces internal container IPs with `127.0.0.1` in signaling to ensure host-to-container connectivity.
- **Message Framing**: Implements newline-delimited JSON for robust data streaming over QUIC.
