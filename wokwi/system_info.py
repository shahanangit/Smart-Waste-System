"""Lightweight system-health values included with telemetry.

The RP2040 temperature reported by Wokwi can be unrealistic, so it is treated as
observational data rather than a safety measurement.
"""

import machine
import gc
import os
import time

_BOOT_MS = time.ticks_ms()


def cpu_temperature_c():
    try:
        adc = machine.ADC(4)
        raw = adc.read_u16()
        voltage = raw * (3.3 / 65535)
        value = 27 - (voltage - 0.706) / 0.001721
        # Wokwi may report an unrealistic RP2040 temperature; keep it observable.
        return round(value, 1)
    except Exception:
        return None


def uptime_seconds():
    return max(0, time.ticks_diff(time.ticks_ms(), _BOOT_MS) // 1000)


def memory_info():
    gc.collect()
    return {
        "free_ram_bytes": gc.mem_free(),
        "allocated_ram_bytes": gc.mem_alloc(),
    }


def flash_info():
    try:
        stat = os.statvfs("/")
        return {
            "total_flash_bytes": stat[1] * stat[2],
            "free_flash_bytes": stat[0] * stat[3],
        }
    except Exception:
        return {
            "total_flash_bytes": None,
            "free_flash_bytes": None,
        }


def snapshot():
    data = {
        "cpu_temperature_c": cpu_temperature_c(),
        "cpu_frequency_mhz": machine.freq() / 1000000,
        "uptime_seconds": uptime_seconds(),
    }
    data.update(memory_info())
    data.update(flash_info())
    return data
