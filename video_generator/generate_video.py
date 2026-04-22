"""
generate_video.py
-----------------
Generates a synthetic 640x480 grayscale test video with alternating
motion and static segments.  Output: test_video.avi (MJPEG codec).

Motion segments: white squares move across the frame.
Static segments: objects remain stationary.

This creates clear boundaries for the ESP32 motion-detection algorithm
to validate against.

Usage:
    python generate_video.py [--output test_video.avi]
                             [--fps 10]
                             [--duration 30]
"""

import argparse
import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def draw_square(img, cx, cy, size, color=255):
    """Draw a filled square centered at (cx, cy)."""
    half = size // 2
    x1 = max(0, cx - half)
    y1 = max(0, cy - half)
    x2 = min(img.shape[1], cx + half)
    y2 = min(img.shape[0], cy + half)
    img[y1:y2, x1:x2] = color


def lerp(a, b, t):
    """Linear interpolation between a and b.  t in [0, 1]."""
    return int(a + (b - a) * t)


# ---------------------------------------------------------------------------
# Segment definitions
# ---------------------------------------------------------------------------
# Each segment is (duration_sec, description, generator_function).
# The generator yields one frame at a time.

def static_segment(fps, duration, objects):
    """Yield identical frames with objects at fixed positions."""
    num_frames = int(fps * duration)
    for _ in range(num_frames):
        frame = np.zeros((480, 640), dtype=np.uint8)
        for (cx, cy, sz) in objects:
            draw_square(frame, cx, cy, sz)
        yield frame


def moving_segment(fps, duration, static_objs, moving_obj):
    """
    Yield frames where one object moves linearly from start to end.
    moving_obj: (start_cx, start_cy, end_cx, end_cy, size)
    """
    num_frames = int(fps * duration)
    sx, sy, ex, ey, sz = moving_obj
    for i in range(num_frames):
        t = i / max(1, num_frames - 1)
        frame = np.zeros((480, 640), dtype=np.uint8)
        # Draw static objects first
        for (cx, cy, s) in static_objs:
            draw_square(frame, cx, cy, s)
        # Draw moving object
        draw_square(frame, lerp(sx, ex, t), lerp(sy, ey, t), sz)
        yield frame


# ---------------------------------------------------------------------------
# Full scene composition
# ---------------------------------------------------------------------------

def generate_scene(fps, target_duration):
    """
    Build a repeating pattern of static / motion segments until
    we reach target_duration seconds worth of frames.

    Pattern per cycle (~15 s at default):
      1. Static  3 s  – one square at left
      2. Moving  4 s  – square slides left → right
      3. Static  2 s  – square rests at right
      4. Moving  3 s  – square slides right → left, second square drops top → bottom
      5. Static  3 s  – both squares stationary
    """

    frames_needed = int(fps * target_duration)
    frames_emitted = 0

    while frames_emitted < frames_needed:
        # --- Segment 1: static, single object ---
        for f in static_segment(fps, 3, [(120, 240, 50)]):
            yield f
            frames_emitted += 1
            if frames_emitted >= frames_needed:
                return

        # --- Segment 2: square moves left → right ---
        for f in moving_segment(fps, 4, [], (120, 240, 520, 240, 50)):
            yield f
            frames_emitted += 1
            if frames_emitted >= frames_needed:
                return

        # --- Segment 3: static, square at right ---
        for f in static_segment(fps, 2, [(520, 240, 50)]):
            yield f
            frames_emitted += 1
            if frames_emitted >= frames_needed:
                return

        # --- Segment 4: square returns, second square drops ---
        # We approximate this by yielding custom frames.
        n4 = int(fps * 3)
        for i in range(n4):
            t = i / max(1, n4 - 1)
            frame = np.zeros((480, 640), dtype=np.uint8)
            # Square A moves right → left
            draw_square(frame, lerp(520, 120, t), 240, 50)
            # Square B drops top → bottom
            draw_square(frame, 320, lerp(60, 420, t), 40)
            yield frame
            frames_emitted += 1
            if frames_emitted >= frames_needed:
                return

        # --- Segment 5: static, two objects ---
        for f in static_segment(fps, 3, [(120, 240, 50), (320, 420, 40)]):
            yield f
            frames_emitted += 1
            if frames_emitted >= frames_needed:
                return


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic test video")
    parser.add_argument("--output", default="test_video.avi", help="Output file")
    parser.add_argument("--fps", type=int, default=10, help="Frames per second")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds")
    args = parser.parse_args()

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(args.output, fourcc, args.fps, (640, 480), False)

    if not writer.isOpened():
        raise RuntimeError(f"Cannot open VideoWriter for {args.output}")

    frame_count = 0
    for frame in generate_scene(args.fps, args.duration):
        writer.write(frame)
        frame_count += 1

    writer.release()

    print(f"Video saved: {args.output}")
    print(f"  Resolution : 640x480 grayscale")
    print(f"  FPS        : {args.fps}")
    print(f"  Frames     : {frame_count}")
    print(f"  Duration   : {frame_count / args.fps:.1f} s")


if __name__ == "__main__":
    main()
