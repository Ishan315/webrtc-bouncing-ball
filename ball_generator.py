import cv2
import numpy as np
import threading
import time
import math

class BallGenerator:
    def __init__(self, width=640, height=480, fps=30, ball_radius=20, ball_color=(0, 0, 255)):
        self.width = width
        self.height = height
        self.fps = fps
        self.ball_radius = ball_radius
        self.ball_color = ball_color  # BGR (Blue, Green, Red) - default is Red
        
        # Initial position and velocity
        self.x = width // 2
        self.y = height // 2
        self.vx = 200 # pixels per second
        self.vy = 150 # pixels per second
        
        self.last_update = time.time()
        self.running = False
        self._lock = threading.Lock()
        self._thread = None

    def start(self):
        if not self.running:
            self.running = True
            self.last_update = time.time()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join()

    def _run(self):
        dt = 1.0 / self.fps
        while self.running:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now
            
            with self._lock:
                # Update position
                self.x += self.vx * elapsed
                self.y += self.vy * elapsed
                
                # Bounce off walls
                if self.x - self.ball_radius < 0:
                    self.x = self.ball_radius
                    self.vx = -self.vx
                elif self.x + self.ball_radius > self.width:
                    self.x = self.width - self.ball_radius
                    self.vx = -self.vx
                
                if self.y - self.ball_radius < 0:
                    self.y = self.ball_radius
                    self.vy = -self.vy
                elif self.y + self.ball_radius > self.height:
                    self.y = self.height - self.ball_radius
                    self.vy = -self.vy
            
            # Sleep to maintain FPS
            time_to_sleep = max(0, dt - (time.time() - now))
            time.sleep(time_to_sleep)

    def get_frame(self):
        with self._lock:
            # Create a black frame
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            # Draw the ball
            cv2.circle(frame, (int(self.x), int(self.y)), self.ball_radius, self.ball_color, -1)
            return frame, (self.x, self.y)

    def get_current_pos(self):
        with self._lock:
            return (self.x, self.y)

    def compute_error(self, client_x, client_y):
        with self._lock:
            dx = self.x - client_x
            dy = self.y - client_y
            return math.sqrt(dx*dx + dy*dy)
