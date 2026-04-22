"""
Diagnostic script: verify motion scores at different thumbnail resolutions.
Proves that 40x30 thumbnails cause sub-pixel motion, making frame
differences undetectable.
"""

import cv2
import numpy as np

VIDEO = "test_video.avi"

def compute_motion_scores(video_path, tw, th):
    cap = cv2.VideoCapture(video_path)
    prev_thumb = None
    scores = []
    idx = 0

    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if len(bgr.shape) == 3 else bgr
        gray = cv2.resize(gray, (640, 480), interpolation=cv2.INTER_AREA)
        thumb = cv2.resize(gray, (tw, th), interpolation=cv2.INTER_AREA)

        if prev_thumb is not None:
            sad = np.sum(np.abs(thumb.astype(int) - prev_thumb.astype(int)))
            score = sad / (tw * th * 255)
            scores.append((idx, score))
        else:
            scores.append((idx, 1.0))

        prev_thumb = thumb
        idx += 1

    cap.release()
    return scores


def main():
    for tw, th in [(40, 30), (80, 60), (160, 120)]:
        scores = compute_motion_scores(VIDEO, tw, th)
        above = sum(1 for _, s in scores if s > 0.01)
        max_score = max(s for _, s in scores)
        print(f"\n=== Thumbnail {tw}x{th} ===")
        print(f"  Total frames     : {len(scores)}")
        print(f"  Max motion score : {max_score:.6f}")
        print(f"  Frames > 0.01   : {above}")
        print(f"  Frames > 0.005  : {sum(1 for _, s in scores if s > 0.005)}")
        print(f"  Frames > 0.001  : {sum(1 for _, s in scores if s > 0.001)}")

        # Show first 10 non-trivial scores (excluding frame 0)
        nonzero = [(i, s) for i, s in scores[1:] if s > 0.0001]
        if nonzero:
            print(f"  Sample scores    : {', '.join(f'f{i}={s:.6f}' for i, s in nonzero[:10])}")
        else:
            print(f"  Sample scores    : ALL ZERO (no detectable motion)")


if __name__ == "__main__":
    main()
