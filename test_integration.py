import asyncio
import json
import pytest
from aiortc import RTCPeerConnection, RTCSessionDescription
from server import WebTransportServerProtocol
from ball_generator import BallGenerator

class MockQuicConnection:
    def __init__(self):
        self.configuration = type('obj', (object,), {
            'alpn_protocols': ['h3'],
            'is_client': False
        })
        self.tls_handler = None
        self._quic = self
        self._quic_logger = None
        self._network_logger = None

    def send_datagram(self, data): pass
    def close(self, error_code=0): pass
    def get_next_available_stream_id(self, is_unidirectional=False): return 1
    def send_stream_data(self, stream_id, data, end_stream=False):
        # Allow capturing data sent via quic directly
        if hasattr(self, 'sent_stream_data'):
            self.sent_stream_data.append(data)
@pytest.mark.asyncio
async def test_server_offer_handling():
    # This test verifies that the server can parse an SDP offer and generate an answer
    # by directly invoking the _handle_offer method on the protocol.

    quic_mock = MockQuicConnection()
    quic_mock.sent_stream_data = []
    protocol = WebTransportServerProtocol(quic=quic_mock)

    # Need to mock transmit because it's called after send_data
    protocol.transmit = lambda: None

    # Generate a VALID SDP offer using aiortc
    pc_client = RTCPeerConnection()
    pc_client.addTransceiver('video', direction='recvonly')
    offer = await pc_client.createOffer()

    # Simulate receiving an offer message
    await protocol._handle_offer(session_id=1, stream_id=1, sdp=offer.sdp)

    assert len(quic_mock.sent_stream_data) > 0
    response = json.loads(quic_mock.sent_stream_data[0].decode())
    assert response["type"] == "answer"
    assert "v=0" in response["sdp"]

    # Clean up
    await pc_client.close()
    if protocol._pc:
        await protocol._pc.close()


def test_ball_generator_error_math():
    gen = BallGenerator()
    gen.x = 100
    gen.y = 100
    # Perfect tracking
    assert gen.compute_error(100, 100) == 0
    # 3-4-5 triangle error
    assert gen.compute_error(103, 104) == 5.0
