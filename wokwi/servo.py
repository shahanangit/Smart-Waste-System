# Hey, trying to control that little SG90 servo with the pico. 
# Hopefully this doesn't fry the GPIO pin again.
from machine import Pin, PWM

# magic numbers for the pwm, don't totally remember why these work 
# but found them in some forum post ages ago
class Servo:
    _FREQ = 50
    _MIN_DUTY = 1638
    _MAX_DUTY = 7864

    def __init__(self, pin, min_angle=0, max_angle=180):
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.current_angle = None
        # calculate the multiplier for angles
        # check if division by zero is possible here if someone passes bad angles
        self._factor = (
            self._MAX_DUTY - self._MIN_DUTY
        ) / (self.max_angle - self.min_angle)
        self._pwm = PWM(Pin(pin))
        self._pwm.freq(self._FREQ)

# help to map angle to duty cycle
# doing it the long way just to make sure math is right

    def _duty(self, angle):
        return int(
            (angle - self.min_angle) * self._factor
        ) + self._MIN_DUTY

    def move(self, angle):
        angle = int(round(angle))
        if not self.min_angle <= angle <= self.max_angle:
            raise ValueError("servo angle out of range")
        if angle == self.current_angle:
            return
        self._pwm.duty_u16(self._duty(angle))
        self.current_angle = angle
