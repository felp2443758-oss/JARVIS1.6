"""Face recognition using the `face_recognition` library (dlib under the hood)."""
from __future__ import annotations
import io
from typing import List, Optional

import cv2
import face_recognition
import numpy as np


def capture_frame(camera_index: int = 0):
    cap = cv2.VideoCapture(camera_index)
    try:
        for _ in range(5):
            cap.read()  # warm-up
        ok, frame = cap.read()
        if not ok:
            return None
        return frame
    finally:
        cap.release()


def embed_face_from_frame(frame) -> Optional[List[float]]:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locs = face_recognition.face_locations(rgb)
    if not locs:
        return None
    encs = face_recognition.face_encodings(rgb, locs)
    if not encs:
        return None
    return encs[0].tolist()  # 128-d vector


def capture_embedding(camera_index: int = 0) -> Optional[List[float]]:
    frame = capture_frame(camera_index)
    if frame is None:
        return None
    return embed_face_from_frame(frame)
