print("================================")
print("PROG6002 ASSIGNMENT 2")
print("================================")

import time
import config as cfg
import system_info

from actuator import ServoController
from controller import SmartBinController
from mqtt_manager import MQTTManager
from sensors import SensorBank

sensors = SensorBank(
    cfg.SENSOR_PINS,
    cfg.CALIBRATION,
    window_size=cfg.MOVING_AVERAGE_WINDOW,
    timeout_us=cfg.SENSOR_TIMEOUT_US,
    min_cm=cfg.SENSOR_MIN_CM,
    max_cm=cfg.SENSOR_MAX_CM,
)


servo = ServoController(
    cfg.SERVO_PIN,
    neutral_angle=cfg.SERVO_NEUTRAL_ANGLE,
    sort_angles=cfg.SORT_ANGLES,
    hold_ms=cfg.SERVO_HOLD_MS,
    settle_ms=cfg.SERVO_SETTLE_MS,
)


controller = SmartBinController(
    cfg,
    sensors,
    servo
)



def on_message(topic, payload):
    print("MQTT RX", topic, payload)

    if topic in (
        cfg.DETECTION_TOPIC,
        cfg.CLASSIFICATION_TOPIC
    ):
        controller.handle_detection_payload(payload)

    elif topic == cfg.SERVO_COMMAND_TOPIC:
        controller.handle_servo_command(payload)

    else:
        print("MQTT Ignored topic:", topic)

def on_message(topic, payload):
    print("MQTT RX", topic, payload)

    if topic in (
        cfg.DETECTION_TOPIC,
        cfg.CLASSIFICATION_TOPIC
    ):
        controller.handle_detection_payload(payload)

    elif topic == cfg.SERVO_COMMAND_TOPIC:
        controller.handle_servo_command(payload)

    else:
        print("MQTT Ignored topic:", topic)


mqtt = MQTTManager(
    cfg,
    on_message
)

print("MQTT ready")

while True:

    controller.poll_one_sensor_if_due()

    mqtt.poll()

    servo.update()

    controller.process_detection_queue()


    if controller.telemetry_due():

        health = system_info.snapshot()

        health["mqtt_connected"] = mqtt.connected

        telemetry = controller.build_telemetry(
            mqtt.connected,
            len(mqtt.offline_queue),
            health
        )

        mqtt.publish(
            cfg.TELEMETRY_TOPIC,
            telemetry,
            retain=True,
            qos=1
        )

       ##print("[TELEMETRY]", telemetry)


    if controller.heartbeat_due():

        heartbeat = controller.build_heartbeat(
            mqtt.connected,
            len(mqtt.offline_queue)
        )

        mqtt.publish(
            cfg.HEARTBEAT_TOPIC,
            heartbeat,
            retain=False,
            qos=1
        )

        ##print("[HEARTBEAT]", heartbeat)

        


    time.sleep_ms(20)