"""
generate_video.py
-----------------
Generates a synthetic 640x480 grayscale test video with a short burst of
obvious motion inside a mostly static sequence. Output: test_video.avi
(MJPEG codec).

Motion segments: white squares move across the frame.
Static segments: objects remain stationary.

This creates clear boundaries for the ESP32 motion-detection algorithm
to validate against.

Usage:
    python generate_video.py [--output test_video.avi]
                             [--fps 10]
                             [--frames 128]
                             [--motion-start 56]
                             [--motion-frames 16]
                             [--step-pixels 30]
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
# Scene composition
# ---------------------------------------------------------------------------


def generate_scene(total_frames, motion_start, motion_frames, step_pixels):
    """Yield a mostly static sequence with a short burst of large motion."""
    total_frames = max(1, int(total_frames))
    motion_start = max(0, min(int(motion_start), total_frames - 1))
    motion_frames = max(0, min(int(motion_frames), total_frames - motion_start))

    start_x = 120
    y = 240
    square_size = 50
    final_x = start_x + (motion_frames * step_pixels)

    for idx in range(total_frames):
        frame = np.zeros((480, 640), dtype=np.uint8)

        if idx < motion_start:
            cx = start_x
        elif idx < motion_start + motion_frames:
            # Move 30 pixels per frame by default so the thumbnail differences
            # are obvious even after downscaling to 40x30.
            cx = start_x + ((idx - motion_start + 1) * step_pixels)
        else:
            cx = final_x

        draw_square(frame, cx, y, square_size)
        yield frame


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic test video")
    parser.add_argument("--output", default="test_video.avi", help="Output file")
    parser.add_argument("--fps", type=int, default=10, help="Frames per second")
    parser.add_argument(
        "--frames", type=int, default=128, help="Total frames in the output video"
    )
    parser.add_argument(
        "--motion-start",
        type=int,
        default=56,
        help="Frame index where the motion burst begins",
    )
    parser.add_argument(
        "--motion-frames",
        type=int,
        default=16,
        help="Number of frames used for explicit motion",
    )
    parser.add_argument(
        "--step-pixels",
        type=int,
        default=30,
        help="How far the object moves each motion frame",
    )
    args = parser.parse_args()

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(args.output, fourcc, args.fps, (640, 480), False)

    if not writer.isOpened():
        raise RuntimeError(f"Cannot open VideoWriter for {args.output}")

    frame_count = 0
    for frame in generate_scene(
        args.frames, args.motion_start, args.motion_frames, args.step_pixels
    ):
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
