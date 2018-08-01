#!/usr/bin/python
# -*- coding: utf-8 -*-

# library for pressure/temperature sensro BMP180 over i2c bus

# based on the script from astromik.org, all credit goes to him, all faults are
# mine. K>

import smbus
from time import sleep

# constants of the BMP180 chip from datasheet:
# chip i2c address:
ADDR = 0x77
# maximal conversion time (in seconds):
TMAXTIME = 0.0045
# maximal conversion time (in seconds):
PMAXTIME = (0.0045, 0.0075, 0.0135, 0.0255)
# calibration constants registers adresses:
AC1MSB = 0xAA
AC1LSB = 0xAB
AC2MSB = 0xAC
AC2LSB = 0xAD
AC3MSB = 0xAE
AC3LSB = 0xAF
AC4MSB = 0xB0
AC4LSB = 0xB1
AC5MSB = 0xB2
AC5LSB = 0xB3
AC6MSB = 0xB4
AC6LSB = 0xB5
B1MSB = 0xB6
B1LSB = 0xB7
B2MSB = 0xB8
B2LSB = 0xB9
MBMSB = 0xBA
MBLSB = 0xBB
MCMSB = 0xBC
MCLSB = 0xBD
MDMSB = 0xBE
MDLSB = 0xBF
# start measurement register:
START = 0xF4
# start conversions constants:
TSTART = 0x2E
PSTART = 0x34
# result registers adresses:
RMSB = 0xF6
RLSB = 0xF7
RXLSB = 0xF8


class BMP180(object):
    def __init__(self, rpiversion, acc_mode):  # initialization
        # initialize bus with correct number:
        # for newer version of RPi with 512 MB of RAM set to 1
        # for old one with 256 MB set to 0
        if rpiversion in (0, 1):
            self.bus = smbus.SMBus(1)
        else:
            raise NameError('incorrect rpi version')

        # measurement time safety multiplier:
        self.safety_coeff = 1.1
        # accuracy mode determining pressure measurement time and accuracy:
        # you can set number from 0 to 3.
        # check corect value:
        if not acc_mode in (0, 1, 2, 3):
            # select most accurate mode in the case of bad user input:
            self.acc_mode = 3
        else:
            self.acc_mode = acc_mode

        # read out calibration constants from the chip:
        self.ac1 = (self.bus.read_byte_data(ADDR, AC1MSB) * 256) \
            + self.bus.read_byte_data(ADDR, AC1LSB)
        self.ac2 = (self.bus.read_byte_data(ADDR, AC2MSB) * 256) \
            + self.bus.read_byte_data(ADDR, AC2LSB)
        self.ac3 = (self.bus.read_byte_data(ADDR, AC3MSB) * 256) \
            + self.bus.read_byte_data(ADDR, AC3LSB)
        self.ac4 = (self.bus.read_byte_data(ADDR, AC4MSB) * 256) \
            + self.bus.read_byte_data(ADDR, AC4LSB)
        self.ac5 = (self.bus.read_byte_data(ADDR, AC5MSB) * 256) \
            + self.bus.read_byte_data(ADDR, AC5LSB)
        self.ac6 = (self.bus.read_byte_data(ADDR, AC6MSB) * 256) \
            + self.bus.read_byte_data(ADDR, AC6LSB)

        self.b1 = (self.bus.read_byte_data(ADDR, B1MSB) * 256) \
            + self.bus.read_byte_data(ADDR, B2LSB)
        self.b2 = (self.bus.read_byte_data(ADDR, B2MSB) * 256) \
            + self.bus.read_byte_data(ADDR, B2LSB)

        self.mb = (self.bus.read_byte_data(ADDR, MBMSB) * 256) \
            + self.bus.read_byte_data(ADDR, MBLSB)
        self.mc = (self.bus.read_byte_data(ADDR, MCMSB) * 256) \
            + self.bus.read_byte_data(ADDR, MCLSB)
        self.md = (self.bus.read_byte_data(ADDR, MDMSB) * 256) \
            + self.bus.read_byte_data(ADDR, MDLSB)

        # some calibartion constants are negative hence change to
        # "signed short" type is required:
        if(self.ac1 & 0x8000):
            self.ac1 = -0x10000 + self.ac1
        if(self.ac2 & 0x8000):
            self.ac2 = -0x10000 + self.ac2
        if(self.ac3 & 0x8000):
            self.ac3 = -0x10000 + self.ac3

        if(self.b1 & 0x8000):
            self.b1 = -0x10000 + self.b1
        if(self.b2 & 0x8000):
            self.b2 = -0x10000 + self.b2

        if(self.mb & 0x8000):
            self.mb = -0x10000 + self.mb
        if(self.mc & 0x8000):
            self.mc = -0x10000 + self.mc
        if(self.md & 0x8000):
            self.md = -0x10000 + self.md

    def meas_temp(self):  # measure temperature
        # order to start temperature measurement:
        self.bus.write_byte_data(ADDR, START, TSTART)
        # wait for measurement:
        # maximal measurement time is 4.5 ms:
        sleep(TMAXTIME * self.safety_coeff)
        # read out result registers
        tepmsb = self.bus.read_byte_data(ADDR, RMSB)
        teplsb = self.bus.read_byte_data(ADDR, RLSB)

        # calculate true temperature in degrees of celsius:
        ut = (tepmsb << 8) + teplsb
        x1 = (ut - self.ac6) * self.ac5 / 2 ** 15
        x2 = (self.mc * 2 ** 11) / (x1 + self.md)
        self.b5 = x1 + x2
        self.t = ((self.b5 + 8) / 2 ** 4) / 10.0
        return self.t

    def meas_press(self):  # measure pressure
        # order to start pressure measurement:
        val = PSTART + (self.acc_mode << 6)
        self.bus.write_byte_data(ADDR, START, val)

        # wait for measurement:
        sleep(PMAXTIME[self.acc_mode] * self.safety_coeff)

        # read out result registers:
        tlakmsb = self.bus.read_byte_data(ADDR, RMSB)
        tlaklsb = self.bus.read_byte_data(ADDR, RLSB)
        tlakxlsb = self.bus.read_byte_data(ADDR, RXLSB)

        # calculate absolute pressure:
        # based on algorithm in the catalogue list of BMP180 chip

        up = ((tlakmsb << 16) + (tlaklsb << 8) + tlakxlsb) \
            >> (8 - self.acc_mode)

        b6 = self.b5 - 4000
        x1 = (self.b2 * (b6 * b6 / 2 ** 12)) / 2 ** 11
        x2 = self.ac2 * b6 / 2 ** 11
        x3 = x1 + x2
        b3 = (((self.ac1 * 4 + x3) << self.acc_mode) + 2.0) / 4
        x1 = self.ac3 * b6 / 2 ** 13
        x2 = (self.b1 * (b6 * b6 / 2 ** 12)) / 2 ** 16
        x3 = ((x1 + x2) + 2) / 2 ** 2

        b4 = self.ac4 * (x3 + 32768) / 2 ** 15
        b7 = (up - b3) * (50000 >> self.acc_mode)
        if (b7 < 0x80000000):
            p = (b7 * 2) / b4
        else:
            p = (b7 / b4) * 2

        x1 = (float(p) / 256) * (float(p) / 256)
        x1 = (x1 * 3038) / 2 ** 16
        x2 = (-7357 * p) / 2 ** 16

        self.p = p + (x1 + x2 + 3791) / 2 ** 4
        return self.p

if __name__ == '__main__':  # testing code
    # set RPI version properly!:
    s = BMP180(1, 3)
    # only for information - print out of calibration constants:
    print s.ac1, s.ac2, s.ac3, s.ac4, s.ac5, s.ac6, \
        s.b1, s.b2, s.mb, s.mc, s.md

    # repeatedly measure temperature and pressure and print results:
    while True:
        t = s.meas_temp()
        p = s.meas_press()
        print "{:.2f}".format(t) + " °C,  " + str(p) + " Pa"
        sleep(0.5)
