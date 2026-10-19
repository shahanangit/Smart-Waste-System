"""Ultrasonic sensor reading and fill-level smoothing.

Each compartment keeps its own moving-average filter so a noisy reading from one
sensor does not affect the other bins.
"""

from machine import Pin, time_pulse_us
import time


class UltrasonicSensor:
    def __init__(self, trigger_pin, echo_pin, timeout_us=30000):
        self.trigger = Pin(trigger_pin, Pin.OUT)
        self.echo = Pin(echo_pin, Pin.IN)
        self.timeout_us = timeout_us
        self.trigger.value(0)

    def read_cm(self):
        self.trigger.value(0)
        time.sleep_us(2)
        self.trigger.value(1)
        time.sleep_us(10)
        self.trigger.value(0)

        # MicroPython returns a negative value when the echo pulse times out.
        pulse = time_pulse_us(self.echo, 1, self.timeout_us)
        if pulse < 0:
            raise OSError("ultrasonic timeout")
        return (pulse * 0.0343) / 2.0


class MovingAverage:
    def __init__(self, size):
        self.size = max(1, int(size))
        self.values = []

    def add(self, value):
        self.values.append(float(value))
        if len(self.values) > self.size:
            self.values.pop(0)
        return self.average()

    def average(self):
        if not self.values:
            return None
        return sum(self.values) / len(self.values)


class SensorBank:
    def __init__(self, pin_map, calibration, window_size=5,
                 timeout_us=30000, min_cm=2.0, max_cm=400.0):
        self.calibration = calibration
        self.min_cm = float(min_cm)
        self.max_cm = float(max_cm)
        self.names = ["recycled", "green", "landfill"]
        self.sensors = {}
        self.filters = {}
        self.last = {}

        for name in self.names:
            pins = pin_map[name]
            self.sensors[name] = UltrasonicSensor(
                pins["trigger"], pins["echo"], timeout_us
            )
            self.filters[name] = MovingAverage(window_size)
            self.last[name] = {
                "distance_cm": None,
                "capacity_pct": None,
                "valid": False,
                "error": "not_read"
            }

    def _capacity(self, name, distance_cm):
        cfg = self.calibration[name]
        empty_cm = float(cfg["empty_cm"])
        full_cm = float(cfg["full_cm"])
        span = empty_cm - full_cm
        if span <= 0:
            raise ValueError("bad calibration for " + name)
        # Convert the calibrated distance range to 0-100% full.
        pct = ((empty_cm - distance_cm) / span) * 100.0
        return max(0.0, min(100.0, pct))

    def read_one(self, name):
        try:
            raw = self.sensors[name].read_cm()
            if raw < self.min_cm or raw > self.max_cm:
                raise ValueError("distance out of range")
            smoothed = self.filters[name].add(raw)
            capacity = self._capacity(name, smoothed)
            result = {
                "distance_cm": round(smoothed, 1),
                "capacity_pct": round(capacity, 1),
                "valid": True,
                "error": None
            }
        except Exception as exc:
            result = {
                "distance_cm": self.last[name].get("distance_cm"),
                "capacity_pct": self.last[name].get("capacity_pct"),
                "valid": False,
                "error": str(exc)
            }
        self.last[name] = result
        return result

    def snapshot(self):
        return {name: dict(self.last[name]) for name in self.names}
