from aiortc import MediaStreamTrack
from av import VideoFrame
import fractions
import time

class BallVideoStreamTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, ball_generator):
        super().__init__()
        self.ball_generator = ball_generator
        self._timestamp = 0

    async def recv(self):
        # Determine current timestamp
        if self._timestamp == 0:
            self._start_time = time.time()
        
        # Get frame from generator
        img, _ = self.ball_generator.get_frame()
        
        # Convert to av.VideoFrame
        frame = VideoFrame.from_ndarray(img, format="bgr24")
        
        # Set pts and time_base for smooth playback
        now = time.time()
        # Using 90000 Hz clock for WebRTC
        pts = int((now - self._start_time) * 90000)
        frame.pts = pts
        frame.time_base = fractions.Fraction(1, 90000)
        
        self._timestamp += 1
        
        # We need to control the rate at which we return frames to match the desired FPS
        # However, aiortc's recv is called by the encoder.
        # To avoid over-consuming or under-consuming, we might need a small sleep if we are too fast,
        # but usually the encoder's demand drives this.
        # Since our BallGenerator runs in its own thread at a fixed FPS, 
        # get_frame() always returns the latest state.
        
        return frame
