#!/usr/bin/python
# -*- coding: utf-8 -*-

# library for temperature/humidity sensor DHT11 over i2c bus
# this is not realtime reading, therefore about 1/3 or 1/2 of readings is
# incorrect
# thus the reading is done till correct reading, maximally 20 times

import RPi.GPIO as GPIO
import time


def bin2dec(string_num):
    return int(string_num, 2)


class DHT11(object):
    def __init__(self, pin):
        GPIO.setmode(GPIO.BOARD)
        self.pin = pin

    def onereading(self):
        data = []

        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, GPIO.HIGH)
        time.sleep(0.025)
        GPIO.output(self.pin, GPIO.LOW)
        time.sleep(0.02)

        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        for i in range(0, 500):
            data.append(GPIO.input(self.pin))

        bit_count = 0
        count = 0
        HumidityBit = ""
        TemperatureBit = ""
        crc = ""

        try:
            while data[count] == 1:
                count = count + 1

            for i in range(0, 32):
                bit_count = 0

                while data[count] == 0:
                    count = count + 1

                while data[count] == 1:
                    bit_count = bit_count + 1
                    count = count + 1

                if bit_count > 3:
                    if i >= 0 and i < 8:
                        HumidityBit = HumidityBit + "1"
                    if i >= 16 and i < 24:
                        TemperatureBit = TemperatureBit + "1"
                else:
                    if i >= 0 and i < 8:
                        HumidityBit = HumidityBit + "0"
                    if i >= 16 and i < 24:
                        TemperatureBit = TemperatureBit + "0"

        except:
            return (-1, -274, "ERR_RANGE")

        try:
            for i in range(0, 8):
                bit_count = 0

                while data[count] == 0:
                    count = count + 1

                while data[count] == 1:
                    bit_count = bit_count + 1
                    count = count + 1

                if bit_count > 3:
                    crc = crc + "1"
                else:
                    crc = crc + "0"
        except:
            return (-1, -274, "ERR_RANGE")

        Humidity = bin2dec(HumidityBit)
        Temperature = bin2dec(TemperatureBit)

        if int(Humidity) + int(Temperature) - int(bin2dec(crc)) == 0:
            return (Humidity, Temperature, "")
        else:
            return (-1, -274, "ERR_CRC")

    def meas(self):
        for i in range(1, 20):
            r = self.onereading()
            if r[2] == "":
                return r
            time.sleep(0.05)
        return (-1, -274, "ERR_MULTIPLE")

if __name__ == '__main__':  # testing code
    datapin = 13
    c = DHT11(datapin)
    # repeatedly measure temperature and humidity and print results:
    while True:
        r = c.meas()
        t = "Humidity: " + str(r[0]) + "%"
        t = t + ", Temperature: " + str(r[1]) + "℃ "
        t = t + ", Error: " + str(r[2])
        print t
        time.sleep(0.5)
    exit(0)
