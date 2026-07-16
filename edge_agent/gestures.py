"""MediaPipe-based hand-gesture controller for the J.A.R.V.I.S. Edge Agent.

Recognized gestures (mapped to local actions):
  • OPEN_PALM   → "stop" / cancel current speaking
  • CLOSED_FIST → "mute / unmute"
  • THUMB_UP    → "next track" (also: confirm)
  • THUMB_DOWN  → "previous track" (also: cancel)
  • VICTORY     → "screenshot"
  • POINTING_UP → "wake JARVIS"
  • ILOVEYOU    → "easter egg"

Usage:
    from gestures import GestureController
    GestureController(on_gesture=lambda g: print(g)).start()
"""
from __future__ import annotations
import os
import threading
import time
from typing import Callable, Optional

import cv2
import mediapipe as mp


class GestureController:
    def __init__(self, on_gesture: Callable[[str], None], camera_index: int = 0,
                 cooldown_s: float = 1.0, show_window: bool = False):
        self.on_gesture = on_gesture
        self.camera_index = camera_index
        self.cooldown_s = cooldown_s
        self.show_window = show_window
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _classify(self, landmarks) -> Optional[str]:
        """Lightweight rule-based classifier on hand landmarks.
        Avoids the heavier MediaPipe Tasks bundle (~100 MB)."""
        if not landmarks:
            return None
        # Indices: 4=thumb_tip, 8=index_tip, 12=middle_tip, 16=ring_tip, 20=pinky_tip
        # Compare tip.y to PIP (proximal joint) y to detect "extended"
        def y(i): return landmarks[i].y
        thumb_up = y(4) < y(3) < y(2)
        index_up = y(8) < y(6)
        middle_up = y(12) < y(10)
        ring_up = y(16) < y(14)
        pinky_up = y(20) < y(18)

        fingers = [index_up, middle_up, ring_up, pinky_up]
        n_up = sum(fingers) + (1 if thumb_up else 0)

        if n_up == 5:
            return "OPEN_PALM"
        if not any(fingers) and not thumb_up:
            return "CLOSED_FIST"
        if thumb_up and not any(fingers):
            return "THUMB_UP"
        if (not thumb_up) and (landmarks[4].y > landmarks[3].y) and not any(fingers):
            return "THUMB_DOWN"
        if index_up and middle_up and not ring_up and not pinky_up:
            return "VICTORY"
        if index_up and not middle_up and not ring_up and not pinky_up and not thumb_up:
            return "POINTING_UP"
        if index_up and pinky_up and thumb_up and not middle_up and not ring_up:
            return "ILOVEYOU"
        return None

    def _loop(self):
        cap = cv2.VideoCapture(self.camera_index)
        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.6, min_tracking_confidence=0.5)
        last_gesture = None
        last_fired = 0.0
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05); continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = hands.process(rgb)
                rgb.flags.writeable = True
                gesture = None
                if results.multi_hand_landmarks:
                    gesture = self._classify(results.multi_hand_landmarks[0].landmark)
                now = time.time()
                if gesture and gesture != last_gesture and (now - last_fired) > self.cooldown_s:
                    try:
                        self.on_gesture(gesture)
                    except Exception as e:
                        print(f"[gestures] handler error: {e}")
                    last_gesture, last_fired = gesture, now
                elif not gesture:
                    last_gesture = None
                if self.show_window:
                    cv2.imshow("JARVIS Gestures", frame)
                    if cv2.waitKey(1) & 0xFF == 27:  # ESC
                        break
        finally:
            cap.release()
            if self.show_window:
                cv2.destroyAllWindows()

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[gestures] MediaPipe hand tracker started")

    def stop(self):
        self._stop.set()


if __name__ == "__main__":
    GestureController(on_gesture=lambda g: print(f">>> {g}"), show_window=True).start()
    while True:
        time.sleep(1)
