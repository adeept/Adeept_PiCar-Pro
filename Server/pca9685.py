#!/usr/bin/env python3
# File name   : pca9685.py
# Website     : www.adeept.com
# Author      : Adeept
'''
Universal PCA9685 driver based on python3-smbus
No Adafruit Blinka dependencies.
Supports servos, DC motors, LED dimming.
'''
import time
from smbus import SMBus


class PCA9685:
    """PCA9685 16-channel 12-bit PWM chip driver"""
    _MODE1 = 0x00
    _PRESCALE = 0xFE
    _LED0_ON_L = 0x06
    _RESOLUTION = 4096
    _OSC_CLOCK = 25000000  # 25MHz internal oscillator

    def __init__(self, bus_num=1, address=0x40, freq=50):
        self.bus = SMBus(bus_num)
        self.addr = address
        # Reset chip
        self._write_reg(self._MODE1, 0x00)
        # Set default PWM frequency
        self.set_frequency(freq)

    def _write_reg(self, reg, value):
        self.bus.write_byte_data(self.addr, reg, value & 0xFF)

    def _read_reg(self, reg):
        return self.bus.read_byte_data(self.addr, reg)

    def set_frequency(self, freq):
        prescale = int(round(self._OSC_CLOCK / (self._RESOLUTION * freq)) - 1)
        # Enter sleep mode to update prescale
        old_mode = self._read_reg(self._MODE1)
        self._write_reg(self._MODE1, (old_mode & 0x7F) | 0x10)
        self._write_reg(self._PRESCALE, prescale)
        self._write_reg(self._MODE1, old_mode)
        time.sleep(0.005)
        # Enable auto-increment mode
        self._write_reg(self._MODE1, old_mode | 0xA1)

    def set_pwm(self, channel, on_count, off_count):
        base = self._LED0_ON_L + 4 * channel
        self._write_reg(base, on_count & 0xFF)
        self._write_reg(base + 1, (on_count >> 8) & 0xFF)
        self._write_reg(base + 2, off_count & 0xFF)
        self._write_reg(base + 3, (off_count >> 8) & 0xFF)

    def deinit(self):
        for ch in range(16):
            self.set_pwm(ch, 0, 0)
        self.bus.close()


class DCMotor:
    """H-bridge DC motor driver, compatible with adafruit_motor API"""
    SLOW_DECAY = 0
    FAST_DECAY = 1

    def __init__(self, pca_device, channel_pos, channel_neg):
        self._pca = pca_device
        self._ch_pos = channel_pos
        self._ch_neg = channel_neg
        self.decay_mode = self.SLOW_DECAY
        self._throttle = 0.0

    @property
    def throttle(self):
        return self._throttle

    @throttle.setter
    def throttle(self, value):
        value = max(-1.0, min(1.0, value))
        self._throttle = value
        pwm_val = int(abs(value) * (PCA9685._RESOLUTION - 1))

        if self.decay_mode == self.SLOW_DECAY:
            if value > 0:
                self._pca.set_pwm(self._ch_pos, 0, pwm_val)
                self._pca.set_pwm(self._ch_neg, 0, 0)
            elif value < 0:
                self._pca.set_pwm(self._ch_pos, 0, 0)
                self._pca.set_pwm(self._ch_neg, 0, pwm_val)
            else:
                self._pca.set_pwm(self._ch_pos, 0, 0)
                self._pca.set_pwm(self._ch_neg, 0, 0)
