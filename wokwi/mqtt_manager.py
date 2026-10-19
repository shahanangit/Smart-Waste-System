import json
import time
import network

from machine import unique_id
from ubinascii import hexlify
from umqttsimple import MQTTClient


class MQTTManager:
    def __init__(self, cfg, callback):
        self.cfg = cfg
        self.callback = callback

        self.wlan = network.WLAN(network.STA_IF)

        self.client = None
        self.connected = False

        self.offline_queue = []

        self.next_reconnect_ms = 0
        self.backoff_ms = cfg.RECONNECT_MIN_MS

        self.client_id = "pico-{}-{}-{}".format(
            cfg.TEAM_ID,
            cfg.DEVICE_ID,
            hexlify(unique_id()).decode()
        )


    @staticmethod
    def _bytes(value):
        if value is None or isinstance(value, bytes):
            return value

        return str(value).encode()


    def _validate_settings(self):
        if not self.cfg.TEAM_ID or self.cfg.TEAM_ID == "teamXX":
            raise ValueError("Set TEAM_ID in config.py")

        if not self.cfg.MQTT_BROKER:
            raise ValueError("MQTT broker is missing")

        if not self.cfg.MQTT_USERNAME:
            raise ValueError("MQTT username is missing")

        if not self.cfg.MQTT_PASSWORD:
            raise ValueError("MQTT password is missing")


    def connect_wifi(self):
        self.wlan.active(True)

        if self.wlan.isconnected():
            return True

        self.wlan.connect(
            self.cfg.WIFI_SSID,
            self.cfg.WIFI_PASSWORD
        )

        deadline = time.ticks_add(
            time.ticks_ms(),
            15000
        )

        while not self.wlan.isconnected():

            if time.ticks_diff(
                deadline,
                time.ticks_ms()
            ) <= 0:

                return False

            time.sleep_ms(200)

        return True


    def _on_mqtt(self, topic, payload):
        if isinstance(topic, bytes):
            topic = topic.decode()

        if isinstance(payload, bytes):
            payload = payload.decode()

        self.callback(topic, payload)


    def connect(self):
        self._validate_settings()

        if not self.connect_wifi():
            raise OSError("Wi-Fi unavailable")

        self.client = MQTTClient(
            client_id=self._bytes(self.client_id),
            server=self.cfg.MQTT_BROKER,
            port=self.cfg.MQTT_PORT,
            user=self._bytes(self.cfg.MQTT_USERNAME),
            password=self._bytes(self.cfg.MQTT_PASSWORD),
            keepalive=self.cfg.MQTT_KEEPALIVE,
            ssl=True,
            ssl_params={
                "server_hostname": self.cfg.MQTT_BROKER
            }
        )

        self.client.set_callback(
            self._on_mqtt
        )

        self.client.connect()


        self.client.subscribe(
            self.cfg.SERVO_COMMAND_TOPIC.encode(),
            qos=1
        )




        self.client.subscribe(
            self.cfg.DETECTION_TOPIC.encode(),
            qos=1
        )


        self.client.subscribe(
            self.cfg.CLASSIFICATION_TOPIC.encode(),
            qos=1
        )

        self.connected = True
        self.backoff_ms = self.cfg.RECONNECT_MIN_MS

        print(
            "MQTT connected as",
            self.client_id
        )

        self.flush_queue()

        return True


    def disconnect(self):
        try:
            if self.client:
                self.client.disconnect()

        except Exception:
            pass

        self.client = None
        self.connected = False


    def schedule_reconnect(self):
        self.connected = False

        self.next_reconnect_ms = time.ticks_add(
            time.ticks_ms(),
            self.backoff_ms
        )

        self.backoff_ms = min(
            self.backoff_ms * 2,
            self.cfg.RECONNECT_MAX_MS
        )


    def ensure_connected(self):
        if self.connected:
            return True

        if time.ticks_diff(
            time.ticks_ms(),
            self.next_reconnect_ms
        ) < 0:

            return False

        try:
            return self.connect()

        except Exception as exc:

            print(
                "MQTT reconnect failed:",
                exc
            )

            self.schedule_reconnect()

            return False


    def poll(self):
        if not self.ensure_connected():
            return

        try:
            self.client.check_msg()

        except Exception as exc:

            print(
                "MQTT connection lost:",
                exc
            )

            self.disconnect()
            self.schedule_reconnect()


    def _queue(
        self,
        topic,
        text,
        retain,
        qos
    ):

        if retain:

            self.offline_queue = [
                item
                for item in self.offline_queue
                if item[0] != topic
            ]

        self.offline_queue.append(
            (
                topic,
                text,
                retain,
                qos
            )
        )

        while len(
            self.offline_queue
        ) > self.cfg.OFFLINE_QUEUE_LIMIT:

            self.offline_queue.pop(0)


    def publish(
        self,
        topic,
        payload,
        retain=False,
        qos=1,
        queue_if_offline=True
    ):

        if isinstance(payload, str):
            text = payload
        else:
            text = json.dumps(payload)

        if not self.ensure_connected():

            if queue_if_offline:
                self._queue(
                    topic,
                    text,
                    retain,
                    qos
                )

            return False

        try:

            self.client.publish(
                topic.encode(),
                text.encode(),
                retain=retain,
                qos=qos
            )

            return True

        except Exception as exc:

            print(
                "MQTT publish failed:",
                exc
            )

            self.disconnect()
            self.schedule_reconnect()

            if queue_if_offline:
                self._queue(
                    topic,
                    text,
                    retain,
                    qos
                )

            return False


    def flush_queue(self):
        if (
            not self.connected
            or not self.client
            or not self.offline_queue
        ):
            return

        pending = self.offline_queue

        self.offline_queue = []

        for index, item in enumerate(pending):

            topic, text, retain, qos = item

            try:

                self.client.publish(
                    topic.encode(),
                    text.encode(),
                    retain=retain,
                    qos=qos
                )

            except Exception as exc:

                print(
                    "MQTT queue flush stopped:",
                    exc
                )

                self.offline_queue = (
                    pending[index:]
                    + self.offline_queue
                )

                self.disconnect()
                self.schedule_reconnect()

                return