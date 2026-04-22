import asyncio
import json
import logging
import os
import ssl
import time
from typing import Dict, Optional

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ProtocolNegotiated, QuicEvent
from aioquic.h3.connection import H3Connection
from aioquic.h3.events import H3Event, HeadersReceived, WebTransportStreamDataReceived, DatagramReceived

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCRtpSender, RTCConfiguration, RTCIceServer
from ball_generator import BallGenerator
from video_track import BallVideoStreamTrack

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("server")

# Configuration
HOST = "0.0.0.0"
PORT = 4433
CERT_FILE = "cert.pem"
KEY_FILE = "key.pem"

ball_gen = BallGenerator(fps=30)

import re
import socket
import asyncio.base_events

# Monkeypatch asyncio to use a fixed port for WebRTC media to work with Docker NAT
_original_create_datagram_endpoint = asyncio.base_events.BaseEventLoop.create_datagram_endpoint

async def _patched_create_datagram_endpoint(self, protocol_factory, local_addr=None, **kwargs):
    if local_addr and len(local_addr) == 2 and local_addr[1] == 0:
        # Force port 50000 for WebRTC media
        local_addr = (local_addr[0], 50000)
        logger.info(f"Forcing WebRTC port to {local_addr[1]} on {local_addr[0]}")
    return await _original_create_datagram_endpoint(self, protocol_factory, local_addr=local_addr, **kwargs)

asyncio.base_events.BaseEventLoop.create_datagram_endpoint = _patched_create_datagram_endpoint

class WebTransportServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._h3: Optional[H3Connection] = None
        self._pc: Optional[RTCPeerConnection] = None
        self._buffers: Dict[int, bytes] = {}

    def quic_event_received(self, event: QuicEvent) -> None:
        logger.debug(f"QUIC event: {type(event).__name__}")
        if isinstance(event, ProtocolNegotiated):
            logger.info(f"ALPN Negotiated: {event.alpn_protocol}")
            self._h3 = H3Connection(self._quic, enable_webtransport=True)

        if self._h3 is not None:
            try:
                for h3_event in self._h3.handle_event(event):
                    logger.debug(f"H3 event: {type(h3_event).__name__}")
                    self._handle_h3_event(h3_event)
            except Exception as e:
                logger.error(f"Error in H3 event handling: {e}", exc_info=True)

    def _handle_h3_event(self, event: H3Event) -> None:
        if isinstance(event, HeadersReceived):
            headers = {k.decode(): v.decode() for k, v in event.headers}
            logger.info(f"HTTP/3 Headers received: {headers}")
            method = headers.get(":method")
            path = headers.get(":path")
            protocol = headers.get(":protocol")
            
            if method == "CONNECT" and protocol == "webtransport":
                logger.info(f"WebTransport CONNECT request for path: {path}")
                self._h3.send_headers(
                    stream_id=event.stream_id,
                    headers=[
                        (b":status", b"200"),
                        (b"sec-webtransport-http3-draft", b"draft02"),
                    ],
                )
                self.transmit()
                logger.info(f"Accepted WebTransport connection on stream {event.stream_id}")
            elif path == "/" or path == "/index.html":
                self._serve_file(event.stream_id, "index.html", "text/html")
            elif path == "/main.js":
                self._serve_file(event.stream_id, "main.js", "application/javascript")
            else:
                self._h3.send_headers(
                    stream_id=event.stream_id,
                    headers=[(b":status", b"404")],
                    end_stream=True,
                )

        elif isinstance(event, WebTransportStreamDataReceived):
            # Buffer data per stream
            if event.stream_id not in self._buffers:
                self._buffers[event.stream_id] = b""
            
            self._buffers[event.stream_id] += event.data
            
            # Process complete messages (delimited by newline)
            while b"\n" in self._buffers[event.stream_id]:
                line, self._buffers[event.stream_id] = self._buffers[event.stream_id].split(b"\n", 1)
                if line:
                    asyncio.ensure_future(self._handle_data(event.session_id, event.stream_id, line))

    def _serve_file(self, stream_id: int, filename: str, content_type: str):
        try:
            with open(filename, "rb") as f:
                data = f.read()
            self._h3.send_headers(
                stream_id=stream_id,
                headers=[
                    (b":status", b"200"),
                    (b"content-type", content_type.encode()),
                    (b"content-length", str(len(data)).encode()),
                ],
            )
            self._h3.send_data(stream_id=stream_id, data=data, end_stream=True)
            self.transmit()
        except Exception as e:
            logger.error(f"Error serving {filename}: {e}")

    async def _handle_data(self, session_id: int, stream_id: int, data: bytes):
        try:
            message = json.loads(data.decode())
            m_type = message.get("type")

            if m_type == "offer":
                await self._handle_offer(session_id, stream_id, message["sdp"])
            elif m_type == "coordinates":
                self._handle_coordinates(session_id, stream_id, message["x"], message["y"])
        except Exception as e:
            logger.error(f"Error handling data: {e}")

    async def _handle_offer(self, session_id: int, stream_id: int, sdp: str):
        logger.info("Received SDP offer")
        
        # Configure STUN server for the server-side as well
        config = RTCConfiguration(
            iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
        )
        self._pc = RTCPeerConnection(configuration=config)

        # Add video track
        video_track = BallVideoStreamTrack(ball_gen)
        transceiver = self._pc.addTransceiver(video_track, direction="sendonly")

        # Force H.264 if available
        capabilities = RTCRtpSender.getCapabilities("video")
        codecs = capabilities.codecs
        h264_codecs = [c for c in codecs if c.mimeType == "video/H264"]
        if h264_codecs:
            transceiver.setCodecPreferences(h264_codecs)
            logger.info("Forced H.264 codec")


        @self._pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state is {self._pc.connectionState}")
            if self._pc.connectionState == "failed":
                await self._pc.close()

        # Set remote description
        offer = RTCSessionDescription(sdp=sdp, type="offer")
        await self._pc.setRemoteDescription(offer)

        # Create answer
        answer = await self._pc.createAnswer()
        await self._pc.setLocalDescription(answer)

        # SDP Hack: Replace internal container IPs with 127.0.0.1 for Docker compatibility
        # This ensures candidates like "a=candidate:... 172.17.0.2 50000 typ host" 
        # become "a=candidate:... 127.0.0.1 50000 typ host"
        modified_sdp = self._pc.localDescription.sdp
        
        # Get container internal IP
        try:
            internal_ip = socket.gethostbyname(socket.gethostname())
            logger.info(f"Container internal IP detected as: {internal_ip}")
            modified_sdp = modified_sdp.replace(internal_ip, "127.0.0.1")
        except Exception as e:
            logger.error(f"Could not detect internal IP: {e}")
            # Fallback to broad replacement
            import re
            modified_sdp = re.sub(r'(172\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)', '127.0.0.1', modified_sdp)

        # Send answer back with newline
        response = json.dumps({
            "type": "answer",
            "sdp": modified_sdp
        }) + "\n"
        self._quic.send_stream_data(stream_id, response.encode(), end_stream=False)
        self.transmit()

    def _handle_coordinates(self, session_id: int, stream_id: int, x: float, y: float):
        error = ball_gen.compute_error(x, y)
        response = json.dumps({
            "type": "error",
            "error": error
        }) + "\n"
        self._quic.send_stream_data(stream_id, response.encode(), end_stream=False)
        self.transmit()

import signal

from aiohttp import web

async def serve_static(request):
    path = request.path
    if path == "/":
        path = "/index.html"
    filename = path.lstrip("/")
    if os.path.exists(filename):
        return web.FileResponse(filename)
    return web.Response(status=404)

async def run_tcp_server():
    app = web.Application()
    app.router.add_get("/{tail:.*}", serve_static)
    
    # Use the same SSL context for TCP
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT, ssl_context=ssl_context)
    await site.start()
    logger.info(f"TCP server started on https://{HOST}:{PORT}")

async def main():
    configuration = QuicConfiguration(
        is_client=False,
        alpn_protocols=["h3"],
    )
    configuration.load_cert_chain(CERT_FILE, KEY_FILE)
    
    ball_gen.start()
    logger.info("Ball generator started")

    # Start both TCP (for web app) and UDP (for WebTransport)
    await asyncio.gather(
        serve(
            HOST,
            PORT,
            configuration=configuration,
            create_protocol=WebTransportServerProtocol,
        ),
        run_tcp_server()
    )
    
    # Handle signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(sig)))

    await asyncio.Future()  # run forever

async def shutdown(sig):
    logger.info(f"Received signal {sig.name}, stopping server...")
    ball_gen.stop()
    # Find all tasks and cancel them
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for t in tasks: t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    loop = asyncio.get_event_loop()
    loop.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
