"""
video_to_header.py
------------------
Reads a video file (or directory of images), extracts frames as JPEG,
generates downscaled grayscale thumbnails for motion comparison, and
writes a C header file suitable for embedding in ESP32 flash.

The script automatically stops extracting frames when the cumulative
data size reaches the configured flash budget.  This means you never
need to pre-calculate how many frames will fit -- the script handles it.

Memory architecture on ESP32:
  - JPEG arrays: stored in flash, passed directly to MQTT (never decoded)
  - Thumbnail arrays: stored in flash, compared in pairs for motion detection
  - No JPEG decoder needed on the ESP32 at all

Usage:
    python video_to_header.py --input test_video.avi
                              --output ../header/video_frames.h
                              [--budget 700]       # KB available for frame data
                              [--quality 50]       # JPEG quality 0-100
                              [--thumb-width 40]   # thumbnail width
                              [--thumb-height 30]  # thumbnail height
"""

import argparse
import os
import sys

import cv2
import numpy as np


def frame_to_jpeg(frame_gray, quality):
    """Compress a grayscale frame to JPEG bytes."""
    ok, buf = cv2.imencode(".jpg", frame_gray,
                           [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


def frame_to_thumbnail(frame_gray, tw, th):
    """Resize a grayscale frame to a small thumbnail for motion comparison."""
    return cv2.resize(frame_gray, (tw, th), interpolation=cv2.INTER_AREA)


def bytes_to_c_array(data, var_name, is_const=True):
    """Convert raw bytes to a C array declaration string."""
    prefix = "const " if is_const else ""
    lines = [f"{prefix}unsigned char {var_name}[] = {{"]
    # Write 12 bytes per line, matching the existing images.h style
    for i in range(0, len(data), 12):
        chunk = data[i:i + 12]
        hex_vals = ", ".join(f"0x{b:02x}" for b in chunk)
        comma = "," if i + 12 < len(data) else ""
        lines.append(f"    {hex_vals}{comma}")
    lines.append("};")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Convert video to ESP32 C header with JPEG frames + thumbnails"
    )
    parser.add_argument("--input", required=True, help="Input video file")
    parser.add_argument("--output", default="../header/video_frames.h",
                        help="Output C header path")
    parser.add_argument("--budget", type=int, default=700,
                        help="Max data budget in KB (default 700)")
    parser.add_argument("--quality", type=int, default=50,
                        help="JPEG compression quality (default 50)")
    parser.add_argument("--thumb-width", type=int, default=40,
                        help="Thumbnail width (default 40)")
    parser.add_argument("--thumb-height", type=int, default=30,
                        help="Thumbnail height (default 30)")
    args = parser.parse_args()

    budget_bytes = args.budget * 1024
    tw, th = args.thumb_width, args.thumb_height
    thumb_size = tw * th  # bytes per thumbnail (1 byte per pixel, grayscale)

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video: {args.input}", file=sys.stderr)
        sys.exit(1)

    video_fps = int(cap.get(cv2.CAP_PROP_FPS)) or 10

    # ---------------------------------------------------------------
    # Pass 1: extract frames until budget is exhausted
    # ---------------------------------------------------------------
    frames = []          # list of (jpeg_bytes, thumbnail_ndarray)
    cumulative = 0
    idx = 0

    while True:
        ok, bgr = cap.read()
        if not ok:
            break

        # Convert to grayscale and resize to target resolution
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if len(bgr.shape) == 3 else bgr
        gray = cv2.resize(gray, (640, 480), interpolation=cv2.INTER_AREA)

        jpeg = frame_to_jpeg(gray, args.quality)
        thumb = frame_to_thumbnail(gray, tw, th)

        frame_cost = len(jpeg) + thumb_size
        if cumulative + frame_cost > budget_bytes:
            print(f"Budget reached at frame {idx}. Stopping extraction.")
            break

        frames.append((jpeg, thumb))
        cumulative += frame_cost
        idx += 1

    cap.release()

    if not frames:
        print("ERROR: No frames extracted.", file=sys.stderr)
        sys.exit(1)

    print(f"Extracted {len(frames)} frames, total data: {cumulative / 1024:.1f} KB "
          f"(budget: {args.budget} KB)")

    # ---------------------------------------------------------------
    # Pass 2: write C header
    # ---------------------------------------------------------------
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    with open(args.output, "w") as f:
        f.write("/* ==========================================================\n")
        f.write(" * AUTO-GENERATED by video_to_header.py -- DO NOT EDIT\n")
        f.write(f" * Source     : {os.path.basename(args.input)}\n")
        f.write(f" * Frames     : {len(frames)}\n")
        f.write(f" * FPS        : {video_fps}\n")
        f.write(f" * JPEG qual  : {args.quality}\n")
        f.write(f" * Thumb size : {tw}x{th}\n")
        f.write(f" * Total data : {cumulative / 1024:.1f} KB\n")
        f.write(" * ========================================================== */\n\n")

        f.write("#ifndef VIDEO_FRAMES_H\n")
        f.write("#define VIDEO_FRAMES_H\n\n")
        f.write("#include <stdint.h>\n\n")

        f.write(f"#define VIDEO_FRAME_COUNT  {len(frames)}\n")
        f.write(f"#define VIDEO_FPS          {video_fps}\n")
        f.write(f"#define THUMBNAIL_WIDTH    {tw}\n")
        f.write(f"#define THUMBNAIL_HEIGHT   {th}\n")
        f.write(f"#define THUMBNAIL_SIZE     ({tw} * {th})\n\n")

        # Write each frame's JPEG array and thumbnail array
        for i, (jpeg, thumb) in enumerate(frames):
            tag = f"{i:03d}"

            # JPEG data
            f.write(bytes_to_c_array(jpeg, f"frame_{tag}_jpg"))
            f.write(f"\nconst unsigned int frame_{tag}_jpg_len = {len(jpeg)};\n\n")

            # Thumbnail (raw grayscale pixels, row-major)
            thumb_bytes = thumb.flatten().tobytes()
            f.write(bytes_to_c_array(thumb_bytes, f"thumb_{tag}"))
            f.write("\n\n")

        # Write the struct type and lookup table
        f.write("/* Frame metadata struct */\n")
        f.write("typedef struct {\n")
        f.write("    const uint8_t *jpeg_data;\n")
        f.write("    uint32_t       jpeg_size;\n")
        f.write("    const uint8_t *thumbnail;\n")
        f.write("} video_frame_t;\n\n")

        f.write("static const video_frame_t video_frames[] = {\n")
        for i in range(len(frames)):
            tag = f"{i:03d}"
            comma = "," if i < len(frames) - 1 else ""
            f.write(f"    {{ frame_{tag}_jpg, frame_{tag}_jpg_len, thumb_{tag} }}{comma}\n")
        f.write("};\n\n")

        f.write("#endif /* VIDEO_FRAMES_H */\n")

    print(f"Header written: {args.output}")
    print(f"  Frames  : {len(frames)}")
    print(f"  FPS     : {video_fps}")
    print(f"  Data    : {cumulative / 1024:.1f} KB / {args.budget} KB budget")


if __name__ == "__main__":
    main()
