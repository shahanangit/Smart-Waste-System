# Smart Waste Management System

A smart IoT-based waste sorting and monitoring system developed for the PROG6002 Programming Internet of Things project.

The system combines a Raspberry Pi Pico W simulation, smartphone-based AI waste classification, MQTT communication, GPS data, automated servo sorting, ultrasonic bin-level monitoring, and a web dashboard.

## System Overview

The system is designed around three waste categories:

- Recycled
- Green Waste
- Landfill

The overall workflow is:

```text
Smartphone Camera
      ↓
AI Waste Classification
      ↓
GPS Location
      ↓
HiveMQ MQTT
      ↓
Raspberry Pi Pico W
      ↓
Servo Sorting
      ↓
Ultrasonic Bin Monitoring
      ↓
Web Dashboard
```

## Features

- Smartphone-based waste classification
- GPS location capture
- Secure MQTT communication using HiveMQ Cloud
- Raspberry Pi Pico W simulation using Wokwi
- Three HC-SR04 ultrasonic sensors
- SG90 servo-based automatic waste sorting
- Real-time bin fill-level monitoring
- Moving-average sensor filtering
- MQTT telemetry and heartbeat messages
- Detection confidence validation
- Duplicate event protection
- Offline/reconnection handling
- High-fill alerts for bins above 85%
- Multi-bin dashboard monitoring
- GPS map display
- Historical bin-level visualisation
- Collection monitoring and route support

## Project Structure

```text
Smart-Waste-System/
│
├── dashboard/
│   └── Web dashboard for monitoring smart bins
│
├── phone_gateway/
│   └── Smartphone camera, AI classification, GPS and MQTT gateway
│
├── wokwi/
│   ├── main.py
│   ├── config.py
│   ├── controller.py
│   ├── mqtt_manager.py
│   ├── actuator.py
│   ├── sensors.py
│   ├── system_info.py
│   ├── umqttsimple.py
│   ├── diagram.json
│   └── secrets_example.py
│
└── README.md
```

## Hardware Simulation

The smart bin is simulated in Wokwi using:

- Raspberry Pi Pico W
- 3 × HC-SR04 ultrasonic sensors
- SG90 servo motor
- Voltage divider resistors for ultrasonic sensor echo lines

Each ultrasonic sensor monitors the capacity of one waste compartment.

The servo automatically directs classified waste into the appropriate compartment.

### Servo Angles

| Waste Type | Servo Angle |
|---|---:|
| Recycled | 45° |
| Green | 90° |
| Landfill | 135° |

## MQTT Communication

The system uses HiveMQ Cloud for MQTT communication.

Main topics for `bin01` include:

```text
prog6002/teamSV/bin01/detection
prog6002/teamSV/bin01/telemetry
prog6002/teamSV/bin01/heartbeat
prog6002/teamSV/bin01/command/servo
```

Additional simulated bins can use the same structure:

```text
prog6002/teamSV/bin02/telemetry
prog6002/teamSV/bin03/telemetry
prog6002/teamSV/bin04/telemetry
```

## Smartphone Gateway

The smartphone gateway acts as the AI and location gateway for the system.

It:

1. Captures an image using the smartphone camera.
2. Classifies the waste item using the trained AI model.
3. Determines the waste category.
4. Collects GPS location information.
5. Creates a JSON detection event.
6. Publishes the event to HiveMQ.
7. The Pico W receives the event and moves the servo to the correct compartment.

Example detection message:

```json
{
  "schema_version": 1,
  "event_id": "test-valid-001",
  "bin_id": "bin01",
  "label": "recycled",
  "confidence": 0.95,
  "source": "smartphone"
}
```

## Telemetry

The Pico W publishes telemetry containing information such as:

- Bin capacity percentage
- Sensor status
- Distance measurements
- High-fill alerts
- Servo state
- Sorting counts
- MQTT connection status
- GPS location when available

Example:

```json
{
  "schema_version": 1,
  "device_id": "bin01",
  "capacity_pct": {
    "recycled": 25,
    "green": 40,
    "landfill": 92
  },
  "sensor_valid": {
    "recycled": true,
    "green": true,
    "landfill": true
  }
}
```

## Dashboard

The web dashboard provides a visual interface for monitoring the smart waste system.

It displays:

- Recycled, Green and Landfill fill levels
- Multiple smart bins
- High-fill collection alerts
- Sorting statistics
- GPS bin locations
- Map information
- Historical usage information
- MQTT events and system status

Bins above the configured fill threshold can be identified for collection.

## Running the Wokwi Simulation

The repository does not contain real MQTT credentials.

Create:

```text
wokwi/secrets.py
```

using `secrets_example.py` as a template:

```python
MQTT_BROKER = "YOUR_CLUSTER.s1.eu.hivemq.cloud"
MQTT_USERNAME = "YOUR_MQTT_USERNAME"
MQTT_PASSWORD = "YOUR_MQTT_PASSWORD"
```

Do not commit `secrets.py` to GitHub.

Then start the Wokwi simulation.

A successful connection should display a message similar to:

```text
MQTT connected as pico-teamSV-bin01-...
```

## Security

Sensitive HiveMQ credentials are excluded from this repository.

The `.gitignore` prevents files such as:

```text
secrets.py
.DS_Store
__pycache__/
*.pyc
```

from being committed.

## Technologies

- Raspberry Pi Pico W
- MicroPython
- Wokwi
- HiveMQ Cloud
- MQTT
- HTML
- CSS
- JavaScript
- Smartphone Camera
- AI Image Classification
- GPS
- GitHub

## Team

Developed as part of the PROG6002 Programming Internet of Things project.

**Team ID:** `teamSV`

## Repository

Smart Waste Management System  
GitHub: `https://github.com/shahanangit/Smart-Waste-System`