from machine import ADC
import utime

_temp = ADC(4)
_factor = 3.3 / 65535


def cpu_temperature_c():
    voltage = _temp.read_u16() * _factor
    temp = 27 - (voltage - 0.706) / 0.001721
    return round(temp, 1)


def uptime_seconds(start_ms):
    return utime.ticks_diff(utime.ticks_ms(), start_ms) // 1000


def iso_timestamp():
    t = utime.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )
