"""Draws a short video of a fictional number plate, for trying the upload flow.

    python make_demo_video.py            # writes ../uploads/demo_inspection.avi
    python make_demo_video.py GJ05EF4321 # use a different plate text

The plate is only drawn text on a white box. A YOLO model trained on real
plates may or may not detect it - use a real clip for a proper demo.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

plate_text = sys.argv[1] if len(sys.argv) > 1 else "GJ01AB1234"
output = Path(__file__).resolve().parents[1] / "uploads" / "demo_inspection.avi"
output.parent.mkdir(exist_ok=True)

width, height, fps, seconds = 640, 360, 20, 3
writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))

for i in range(fps * seconds):
    frame = np.full((height, width, 3), 70, dtype=np.uint8)
    x = 120 + i  # the "vehicle" drifts to the right
    cv2.rectangle(frame, (x, 150), (x + 380, 250), (255, 255, 255), -1)
    cv2.rectangle(frame, (x, 150), (x + 380, 250), (0, 0, 0), 3)
    cv2.putText(frame, plate_text, (x + 15, 218), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 4)
    writer.write(frame)

writer.release()
print(f"Wrote {output}")
