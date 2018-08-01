#!/usr/bin/python

# library for illuminance sensor BH1750 over i2c bus

# based on the script from astromik.org, all credit goes to him, all faults are
# mine. K>

import smbus
from time import sleep

# addresses from datasheet
# ADDR(0) is for case ADDR pin is connected to GND
ADDR = (0x23, 0x5C)


class BH1750(object):
    def __init__(self, rpiversion, addrtohigh):  # initialization
        # initialize bus with correct number:
        # for newer version of RPi with 512 MB of RAM set to 1
        # for old one with 256 MB set to 0
        if rpiversion in (0, 1):
            self.bus = smbus.SMBus(1)
        else:
            raise NameError('incorrect rpi version')
        if addrtohigh:
                self.addr = ADDR[1]
        else:
                self.addr = ADDR[0]

    def meas(self):  # measure illuminance
        i = self.bus.read_i2c_block_data(self.addr, 0x11)
        sleep(0.120)
        self.i = (i[1] + (256 * i[0])) / 1.2
        return self.i

if __name__ == '__main__':  # testing code
    # set RPI version properly!:
    s = BH1750(1, 0)
    while True:
        i = s.meas()
        print "illuminance is " + str(i) + " lx"
        sleep(0.5)
