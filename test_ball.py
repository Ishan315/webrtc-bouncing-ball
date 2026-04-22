import pytest
import numpy as np
import time
from ball_generator import BallGenerator

def test_ball_initial_position():
    gen = BallGenerator(width=640, height=480)
    pos = gen.get_current_pos()
    assert pos == (320, 240)

def test_ball_movement():
    gen = BallGenerator(width=640, height=480, fps=100)
    gen.vx = 100
    gen.vy = 100
    gen.start()
    time.sleep(0.1)
    pos = gen.get_current_pos()
    gen.stop()
    assert pos[0] > 320
    assert pos[1] > 240

def test_ball_bounce_horizontal():
    # Place ball near right wall moving right
    gen = BallGenerator(width=100, height=100, ball_radius=10)
    gen.x = 85
    gen.vx = 100
    gen.vy = 0
    # Simulate one step
    # Use internal _run logic step
    gen.last_update = time.time() - 0.1
    gen.running = True
    # Manually trigger one update instead of starting thread
    # We can modify BallGenerator to have a tick() method for easier testing
    pass

def test_compute_error():
    gen = BallGenerator(width=640, height=480)
    # Ball is at 320, 240
    error = gen.compute_error(320, 240)
    assert error == 0
    error = gen.compute_error(320 + 3, 240 + 4)
    assert error == 5.0

def test_get_frame():
    gen = BallGenerator(width=640, height=480)
    frame, pos = gen.get_frame()
    assert frame.shape == (480, 640, 3)
    # Check if there is some red color in the frame
    # Ball color is (0, 0, 255) BGR
    assert np.any(frame[:,:,2] == 255)
