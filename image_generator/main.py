import numpy as np
import cv2
import os
import random

# --- CONFIG ---
WIDTH = 640
HEIGHT = 480
DOT_SIZE = 32
NUM_IMAGES = 10
DOTS_PER_IMAGE = 3
JPEG_QUALITY = 50
OUTPUT_DIR = "./../images/"

# Create output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)


def generate_image(width, height, dot_size, num_dots):
    """
    Generate a grayscale image with black background and random white squares.
    """
    img = np.zeros((height, width), dtype=np.uint8)

    for _ in range(num_dots):
        x = random.randint(0, width - dot_size)
        y = random.randint(0, height - dot_size)

        img[y:y + dot_size, x:x + dot_size] = 255

    return img


def save_as_jpeg(img, filename, quality):
    """
    Compress and save image as JPEG.
    """
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]

    # Encode image into JPEG format in memory
    success, encoded_img = cv2.imencode('.jpg', img, encode_param)

    if not success:
        raise RuntimeError("JPEG encoding failed")

    # Write to file
    with open(filename, 'wb') as f:
        f.write(encoded_img.tobytes())

    return len(encoded_img)


def main():
    for i in range(NUM_IMAGES):
        img = generate_image(WIDTH, HEIGHT, DOT_SIZE, DOTS_PER_IMAGE)

        filename = os.path.join(OUTPUT_DIR, f"frame_{i:03d}.jpg")

        size_bytes = save_as_jpeg(img, filename, JPEG_QUALITY)

        print(f"Generated: {filename} | Size: {size_bytes/1024:.2f} KB")


if __name__ == "__main__":
    main()