"""Core smart-bin behaviour.

This controller joins the sensor state, classification messages and servo action.
It validates incoming events before they are allowed to move the sorting flap.
"""

import json
import time


class SmartBinController:
    def __init__(self, cfg, sensors, servo):
        self.cfg = cfg
        self.sensors = sensors
        self.servo = servo
        self.sequence = 0
        self.heartbeat_sequence = 0
        self.sensor_index = 0
        self.last_sensor_ms = 0
        self.last_telemetry_ms = 0
        self.last_heartbeat_ms = 0
        self.detection_queue = []
        self.seen_ids = []
        self.last_location = cfg.DEFAULT_LOCATION
        self.alert_state = {
            "recycled": False,
            "green": False,
            "landfill": False,
        }
        self.sort_counts = {"recycled": 0, "green": 0, "landfill": 0}
        self.metrics = {
            "accepted": 0,
            "rejected": 0,
            "duplicates": 0,
            "queue_drops": 0,
            "last_validation_ms": None,
            "last_queue_ms": None,
            "last_receive_to_servo_ms": None,
            "last_inference_ms": None,
            "last_confidence": None,
            "last_label": None,
            "last_event_id": None,
            "latency_samples_ms": [],
        }

    def _remember(self, event_id):
        # Keep a bounded list so a QoS retry cannot move the servo twice.
        self.seen_ids.append(event_id)
        if len(self.seen_ids) > self.cfg.SEEN_EVENT_LIMIT:
            self.seen_ids.pop(0)

    def _iso_now(self):
        try:
            y, m, d, hh, mm, ss, _, _ = time.gmtime()
            return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (y, m, d, hh, mm, ss)
        except Exception:
            return None

    def _timestamp_epoch(self, text):
        if not isinstance(text, str) or len(text) < 19:
            raise ValueError("timestamp")
        try:
            date_part = text[:10]
            time_part = text[11:19]
            y, m, d = [int(x) for x in date_part.split("-")]
            hh, mm, ss = [int(x) for x in time_part.split(":")]
            return time.mktime((y, m, d, hh, mm, ss, 0, 0))
        except Exception:
            raise ValueError("timestamp")

    def _check_freshness(self, event):
        if not self.cfg.ENFORCE_TIMESTAMP_FRESHNESS:
            return
        event_s = self._timestamp_epoch(event.get("timestamp"))
        age_s = time.time() - event_s
        if age_s < -5 or age_s > self.cfg.MAX_EVENT_AGE_S:
            raise ValueError("stale detection")

    def poll_one_sensor_if_due(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_sensor_ms) < self.cfg.SENSOR_POLL_MS:
            return
        name = self.sensors.names[self.sensor_index]
        self.sensors.read_one(name)
        self.sensor_index = (self.sensor_index + 1) % len(self.sensors.names)
        self.last_sensor_ms = now

    def _update_alerts(self, snapshot):
        # Hysteresis: switch on at 85%, but do not clear until below 80%.
        for name, reading in snapshot.items():
            pct = reading.get("capacity_pct")
            if pct is None:
                continue
            previous = self.alert_state[name]
            self.alert_state[name] = (
                pct >= self.cfg.ALERT_OFF_PCT if previous
                else pct >= self.cfg.ALERT_ON_PCT
            )

    def build_telemetry(self, mqtt_connected, offline_queue_depth, system_snapshot):
        snapshot = self.sensors.snapshot()
        self._update_alerts(snapshot)
        distances = {}
        capacities = {}
        valid = {}
        errors = {}

        for name, reading in snapshot.items():
            distances[name] = reading.get("distance_cm")
            capacities[name] = reading.get("capacity_pct")
            valid[name] = bool(reading.get("valid"))
            errors[name] = reading.get("error")

        self.sequence += 1
        payload = {
            "schema_version": 1,
            "sequence": self.sequence,
            "device_id": self.cfg.DEVICE_ID,
            "timestamp": self._iso_now(),
            "capacities": capacities,
            "capacity_pct": capacities,
            "distance_cm": distances,
            "sensor_valid": valid,
            "sensor_error": errors,
            "high_fill_alert": dict(self.alert_state),
            "servo": {
                "angle": self.servo.angle,
                "state": self.servo.state,
                "active_label": self.servo.active_label,
                "last_event_id": self.servo.last_event_id,
            },
            "system": system_snapshot,
            "mqtt_connected": bool(mqtt_connected),
            "offline_queue_depth": int(offline_queue_depth),
            "validation": dict(self.metrics),
            "sorting": {"counts": dict(self.sort_counts)},
        }
        if self.last_location:
            payload.update(self.last_location)
        return payload

    def build_heartbeat(self, mqtt_connected, offline_queue_depth):
        self.heartbeat_sequence += 1
        return {
            "schema_version": 1,
            "sequence": self.heartbeat_sequence,
            "device_id": self.cfg.DEVICE_ID,
            "timestamp": self._iso_now(),
            "state": "online" if mqtt_connected else "offline",
            "servo_state": self.servo.state,
            "offline_queue_depth": offline_queue_depth,
        }

    def telemetry_due(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_telemetry_ms) >= self.cfg.TELEMETRY_INTERVAL_MS:
            self.last_telemetry_ms = now
            return True
        return False

    def heartbeat_due(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_heartbeat_ms) >= self.cfg.HEARTBEAT_INTERVAL_MS:
            self.last_heartbeat_ms = now
            return True
        return False

    def _normalise_classification(self, event):
        # Both Week 4 message formats are accepted and converted to one internal shape.
        if not isinstance(event, dict):
            raise ValueError("payload object")

        # Direct Week 4 contract.
        if event.get("schema_version") == 1 and "label" in event:
            return event

        # Repository-guided classifier contract.
        if event.get("schema_version") == 2:
            mapping = {
                "yellow": "recycled",
                "green": "green",
                "red": "landfill",
            }
            bin_name = event.get("bin")
            return {
                "schema_version": 1,
                "event_id": event.get("event_id") or (
                    str(event.get("device_id", "phone")) + "-" + str(event.get("sequence", "0"))
                ),
                "bin_id": event.get("bin_id") or self.cfg.DEVICE_ID,
                "label": mapping.get(bin_name, "unknown"),
                "confidence": event.get("confidence"),
                "source": event.get("device_id", "classifier"),
                "timestamp": event.get("timestamp"),
                "latitude": event.get("latitude"),
                "longitude": event.get("longitude"),
                "accuracy_m": event.get("accuracy_m"),
                "inference_ms": event.get("inference_ms"),
            }

        raise ValueError("schema version")

    def _validate_location(self, event):
        lat = event.get("latitude")
        lon = event.get("longitude")
        accuracy = event.get("accuracy_m")

        if lat is None and lon is None:
            return None
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            raise ValueError("location type")
        if lat < -90 or lat > 90 or lon < -180 or lon > 180:
            raise ValueError("location range")
        if accuracy is not None and (
            not isinstance(accuracy, (int, float)) or accuracy < 0
        ):
            raise ValueError("location accuracy")

        return {
            "latitude": float(lat),
            "longitude": float(lon),
            "accuracy_m": accuracy,
        }

    def _validate_detection(self, event):
        if event.get("schema_version") != 1:
            raise ValueError("version")
        if event.get("bin_id") != self.cfg.DEVICE_ID:
            raise ValueError("bin")

        label = event.get("label")
        if label not in self.cfg.SORT_ANGLES:
            raise ValueError("label")

        confidence = event.get("confidence")
        if not isinstance(confidence, (int, float)):
            raise ValueError("confidence type")
        if confidence < self.cfg.MIN_DETECTION_CONFIDENCE or confidence > 1.0:
            raise ValueError("confidence")

        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id")
        if len(event_id) > 96:
            raise ValueError("event_id length")

        self._check_freshness(event)
        location = self._validate_location(event)
        if location:
            event["validated_location"] = location
        return event

    def handle_detection_payload(self, payload_text):
        received_ms = time.ticks_ms()
        try:
            raw = json.loads(payload_text)
            event = self._normalise_classification(raw)
            event = self._validate_detection(event)
            validated_ms = time.ticks_ms()
            self.metrics["last_validation_ms"] = time.ticks_diff(validated_ms, received_ms)

            if event["event_id"] in self.seen_ids:
                self.metrics["duplicates"] += 1
                print("[DETECTION] duplicate ignored:", event["event_id"])
                return False

            if len(self.detection_queue) >= self.cfg.DETECTION_QUEUE_LIMIT:
                self.metrics["queue_drops"] += 1
                raise ValueError("queue full")

            location = event.get("validated_location")
            if location:
                self.last_location = location

            self._remember(event["event_id"])
            event["received_ms"] = received_ms
            event["queued_ms"] = time.ticks_ms()
            self.detection_queue.append(event)
            self.metrics["accepted"] += 1
            self.metrics["last_inference_ms"] = event.get("inference_ms")
            self.metrics["last_confidence"] = event.get("confidence")
            self.metrics["last_label"] = event.get("label")
            self.metrics["last_event_id"] = event.get("event_id")
            print("[DETECTION] accepted:", event["event_id"], event["label"])
            return True

        except Exception as exc:
            self.metrics["rejected"] += 1
            print("[DETECTION] rejected:", exc)
            return False

    def handle_servo_command(self, payload_text):
        try:
            try:
                data = json.loads(payload_text)
                angle = int(data["angle"]) if isinstance(data, dict) else int(data)
            except Exception:
                angle = int(payload_text)

            if angle < 0 or angle > 180:
                raise ValueError("angle out of range")
            if self.servo.state != "IDLE":
                raise ValueError("servo busy")

            self.servo.set_angle(angle)
            print("[SERVO] manual angle:", angle)
            return True
        except Exception as exc:
            print("[SERVO] rejected command:", exc)
            return False

    def process_detection_queue(self):
        # Only start the next item when the previous servo cycle is completely finished.
        if self.servo.state != "IDLE" or not self.detection_queue:
            return False

        event = self.detection_queue.pop(0)
        start_ms = time.ticks_ms()
        self.metrics["last_queue_ms"] = time.ticks_diff(start_ms, event["queued_ms"])
        self.metrics["last_receive_to_servo_ms"] = time.ticks_diff(start_ms, event["received_ms"])
        samples = self.metrics["latency_samples_ms"]
        samples.append(self.metrics["last_receive_to_servo_ms"])
        if len(samples) > 20:
            samples.pop(0)

        started = self.servo.start_sort(event["label"], event["event_id"])
        if started:
            self.sort_counts[event["label"]] += 1
            print({
                "event_id": event["event_id"],
                "label": event["label"],
                "validation_ms": self.metrics["last_validation_ms"],
                "queue_ms": self.metrics["last_queue_ms"],
                "receive_to_servo_ms": self.metrics["last_receive_to_servo_ms"],
                "servo_angle": self.servo.angle,
            })
        return started
