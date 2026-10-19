"""Small non-blocking servo controller used by the sorting flap.

The main loop calls update() repeatedly, so the servo can hold, return to neutral
and settle without stopping sensor reads or MQTT processing.
"""

from machine import Pin, PWM
import time


class ServoController:
    def __init__(self, pin, neutral_angle=0, sort_angles=None,
                 hold_ms=1200, settle_ms=500):
        self.pwm = PWM(Pin(pin))
        self.pwm.freq(50)
        self.neutral_angle = int(neutral_angle)
        self.sort_angles = sort_angles or {
            "recycled": 45,
            "green": 90,
            "landfill": 135,
        }
        self.hold_ms = int(hold_ms)
        self.settle_ms = int(settle_ms)
        self.state = "IDLE"
        self.angle = self.neutral_angle
        self.active_label = None
        self.started_ms = None
        self.returned_ms = None
        self.last_event_id = None
        self.set_angle(self.neutral_angle)

    @staticmethod
    def _duty_for_angle(angle):
        # Typical SG90 pulse range ~0.5-2.5 ms at 50 Hz.
        min_us = 500
        max_us = 2500
        # Convert degrees to the pulse width expected by a typical SG90 servo.
        pulse_us = min_us + (max_us - min_us) * (angle / 180.0)
        return int((pulse_us / 20000.0) * 65535)

    def set_angle(self, angle):
        angle = int(angle)
        if angle < 0 or angle > 180:
            raise ValueError("angle must be 0..180")
        self.pwm.duty_u16(self._duty_for_angle(angle))
        self.angle = angle

    def start_sort(self, label, event_id=None):
        if self.state != "IDLE":
            return False
        if label not in self.sort_angles:
            raise ValueError("unsupported label")
        self.active_label = label
        self.last_event_id = event_id
        self.set_angle(self.sort_angles[label])
        self.started_ms = time.ticks_ms()
        self.state = "HOLDING"
        return True

    def update(self):
        # No sleep is used here; the main loop keeps running while the flap moves.
        now = time.ticks_ms()
        if self.state == "HOLDING":
            if time.ticks_diff(now, self.started_ms) >= self.hold_ms:
                self.set_angle(self.neutral_angle)
                self.returned_ms = now
                self.state = "RETURNING"
        elif self.state == "RETURNING":
            if time.ticks_diff(now, self.returned_ms) >= self.settle_ms:
                self.state = "IDLE"
                self.active_label = None
        return self.state
