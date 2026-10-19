# Configuration settings for our smart bin setup
# NOTE: Make sure not to commit actual cloud passwords to git again lol (good thing this is just hivemq sandbox
from secrets import MQTT_BROKER, MQTT_USERNAME, MQTT_PASSWORD

TEAM_ID = "teamSV"
DEVICE_ID = "bin01"
PHONE_ID = "teamSV-tablet01"
# wifi credentials for Wokwi simulator
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASSWORD = ""

try:
    from secrets import MQTT_BROKER, MQTT_USERNAME, MQTT_PASSWORD
except ImportError:
    MQTT_BROKER = "YOUR_CLUSTER.s1.eu.hivemq.cloud"
    MQTT_USERNAME = "YOUR_MQTT_USERNAME"
    MQTT_PASSWORD = "YOUR_MQTT_PASSWORD"

MQTT_PORT = 8883
MQTT_SSL = True
MQTT_KEEPALIVE = 45
# Building topic strings using old school format because it's easy to read

TOPIC_ROOT = "prog6002/{}/{}".format(TEAM_ID, DEVICE_ID)
TELEMETRY_TOPIC = TOPIC_ROOT + "/telemetry"
HEARTBEAT_TOPIC = TOPIC_ROOT + "/heartbeat"
SERVO_COMMAND_TOPIC = TOPIC_ROOT + "/command/servo"
DETECTION_TOPIC = TOPIC_ROOT + "/detection"
CLASSIFICATION_TOPIC = "prog6002/2026/{}/{}/classification".format(TEAM_ID, DEVICE_ID)

# Keep these pins and calibration values the same as the working Assessment 1 circuit.
SENSOR_PINS = {
    "recycled": {"trigger": 2, "echo": 3},
    "green": {"trigger": 4, "echo": 5},
    "landfill": {"trigger": 6, "echo": 7},
}
SERVO_PIN = 27

CALIBRATION = {
    "recycled": {"empty_cm": 35.0, "full_cm": 5.0},
    "green": {"empty_cm": 35.0, "full_cm": 5.0},
    "landfill": {"empty_cm": 35.0, "full_cm": 5.0},
}

MOVING_AVERAGE_WINDOW = 5
SENSOR_TIMEOUT_US = 30000
SENSOR_MIN_CM = 2.0
SENSOR_MAX_CM = 400.0
SENSOR_POLL_MS = 350

SERVO_NEUTRAL_ANGLE = 0
SORT_ANGLES = {"recycled": 45, "green": 90, "landfill": 135}
SERVO_HOLD_MS = 1200
SERVO_SETTLE_MS = 500

TELEMETRY_INTERVAL_MS = 5000
HEARTBEAT_INTERVAL_MS = 15000
RECONNECT_MIN_MS = 2000
RECONNECT_MAX_MS = 30000
OFFLINE_QUEUE_LIMIT = 20

MIN_DETECTION_CONFIDENCE = 0.80
SEEN_EVENT_LIMIT = 100
DETECTION_QUEUE_LIMIT = 5
ENFORCE_TIMESTAMP_FRESHNESS = False
MAX_EVENT_AGE_S = 30

ALERT_ON_PCT = 85.0
ALERT_OFF_PCT = 80.0
DEFAULT_LOCATION = None

