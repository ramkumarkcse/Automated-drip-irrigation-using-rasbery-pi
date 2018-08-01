#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# vim modeline: vim: shiftwidth=4 tabstop=4
import smbus
import datetime
import os
import sys

#==============================================================
# library for control of RTC chip PCF8563 over i2c bus
#==============================================================

# based on the script from astromik.org, all credit goes to him, all faults are
# mine. K>
#  Program pro ovladani RTC obvodu PCF8563 pres I2C komunikaci

ADR = 0x51       # I2C ADResa obvodu PCF8563


class RTC8563(object):
    def __init__(self, verbose):  # initialize
        """
        Initialize class.

        \param verbose boolean, if set to True, print time to the console
        \return None
        """
        self.bus = smbus.SMBus(1)   # novejsi varianta RasPi (512MB)
        #bus = smbus.SMBus(0)   # starsi varianta RasPi (256MB)
        self.verbose = verbose

    def addr(self):  # return i2c address
        """
        Return i2c address of the RTC8563

        \param None
        \return address integer, hexadecimal
        """
        return ADR

    def write(self):  # set time OS->RTC
        """
        Set time from OS to RTC

        \param None
        \return None
        """
        # podprogram pro ulozeni systemoveho casu z RasPi do RTC obvodu
        # 1Hz vystup:
        self.bus.write_byte_data(ADR, 0x0D, 0b10000011)
        # normalni rezim pocitani casu:
        self.bus.write_byte_data(ADR, 0x00, 0)

        # cas se d RTC uklada prepocteny na GMT casovou zonu
        # zjisteni aktualniho casu v RasPi (prepocteno na GMT casovou zonu):
        datcas = datetime.datetime.utcnow()

        # roky 00 az 99 - registr 0x08
        rokhi = int((datcas.year - 2000) / 10)
        roklo = datcas.year - 2000 - (10 * rokhi)
        self.bus.write_byte_data(ADR, 0x08, (rokhi * 16) + roklo)

        # mesice a rozlisovaci bit pro stoleti - registr 0x07
        meshi = int((datcas.month) / 10)
        meslo = datcas.month - (10 * meshi)
        if datcas.year > 1999:
            stoleti = 0
        else:
            stoleti = 128
        self.bus.write_byte_data(ADR, 0x07, (meshi * 16) + meslo + stoleti)

        # dny v tydnu - registr 0x06
        # funkce weekday v pythonu vraci 0=pondeli ... 6=nedele
        dvt = datetime.datetime.utcnow().weekday()
        self.bus.write_byte_data(ADR, 0x06, dvt)

        # dny v mesici - registr 0x05
        denhi = int(datcas.day / 10)
        denlo = datcas.day - (10 * denhi)
        self.bus.write_byte_data(ADR, 0x05, (denhi * 16) + denlo)

        # hodiny - registr 0x04
        hodhi = int(datcas.hour / 10)
        hodlo = datcas.hour - (10 * hodhi)
        self.bus.write_byte_data(ADR, 0x04, (hodhi * 16) + hodlo)

        # minuty - registr 0x03
        minhi = int(datcas.minute / 10)
        minlo = datcas.minute - (10 * minhi)
        self.bus.write_byte_data(ADR, 0x03, (minhi * 16) + minlo)

        # sekundy - registr 0x02
        # zaroven se zapisem sekund do RTC se nuluje bit pro testovani napeti
        # baterie
        sekhi = int(datcas.second / 10)
        seklo = datcas.second - (10 * sekhi)
        self.bus.write_byte_data(ADR, 0x02, (sekhi * 16) + seklo)

        if self.verbose:
            print "Systemovy cas v RasPi :", datcas, "UTC"
            print "Systemovy cas byl prekopirovan do RTC obvodu."

    def info(self, nastav_cas=False):  # get time from RTC, and RTC->OS
        """
        Read time from RTC, and optionally set RTC time to OS.

        \param nastav_cas boolean, if set to True, RTC time is set to operating
        system
        \return (RTCtime, battery) tuple, first is time in RTC, second boolean,
        if True, baterry is OK, else battery voltage is too low, battery
        should be replaced
        """
        # podprogram pro zjisteni casu v obvodu RTC a jeho zobrazeni, nebo
        # nastaveni casu v RasPi podle RTC

        # nazevdne se prizpusobuje Pythonu - funkci weekday   (0=pondeli ....
        # 6=nedele)
        # (RTC obvod by mel podle kat.listu ty dny posunute)
        nazevdne = ['pondeli', 'utery', 'streda', 'ctvrtek',
                    'patek', 'sobota', 'nedele']

        # datcas bude obsahovat aktualni datum a cas v UTC (GMT):
        datcas = datetime.datetime.utcnow()
        if self.verbose:
            print "Systemovy cas v RasPi :", datcas, "UTC"

        rtc = self.bus.read_i2c_block_data(ADR, 0x00)

        # sekundy:
        sek = ((rtc[0x02] & 0b01110000) >> 4) * 10 + (rtc[0x02] & 0b00001111)
        # minuty
        min = ((rtc[0x03] & 0b01110000) >> 4) * 10 + (rtc[0x03] & 0b00001111)
        # hodiny
        hod = ((rtc[0x04] & 0b00110000) >> 4) * 10 + (rtc[0x04] & 0b00001111)
        # dny v mesici
        den = ((rtc[0x05] & 0b00110000) >> 4) * 10 + (rtc[0x05] & 0b00001111)

        # den v tydnu : 0=Po  1=Ut ..... 6=Ne
        dvt = (rtc[0x06] & 0b00000111)

        # mesic
        mes = ((rtc[0x07] & 0b00010000) >> 4) * 10 + (rtc[0x07] & 0b00001111)
        # rok
        rok = ((rtc[0x08] & 0b11110000) >> 4) * 10 + (rtc[0x08] & 0b00001111)

        # v nejvyssim bitu registru c.0 je informace o napeti:
        napeti = ((rtc[0x02] & 0b10000000))
        if napeti == 0:
            napetis = "Napeti je OK"
            napeti = True
        else:
            napetis = "Napeti kleslo pod predepsanou uroven"
            napeti = False
        if self.verbose:
            print napetis

        # v nejvyssim bitu registru c.7 je informace o stoleti 20. nebo 21.
        stoleti = ((rtc[0x07] & 0b10000000))
        if stoleti == 0:
            stoleti = 2000
        else:
            stoleti = 1900

        txtcas = str(hod) + ":" + \
            str(min).rjust(2, "0") + ":" + \
            str(sek).rjust(2, "0")
        txtdat = str(nazevdne[dvt]) + "  " +  \
            str(den) + "." + str(mes) + "." + \
            str(stoleti + rok) + " "
        if self.verbose:
            print "Cas v RTC:  " + txtdat + "  " + txtcas + " UTC"

        # pokud je parametr tohoto podprogramu True, nastavi se RasPi podle RTC
        if (nastav_cas is True):
            if self.verbose:
                print "Cas v RasPi byl nastaven na:"
            prikaz = "sudo date -u " + (str(mes).rjust(2, "0") +
                                        str(den).rjust(2, "0") +
                                        str(hod).rjust(2, "0") +
                                        str(min).rjust(2, "0") +
                                        str(stoleti + rok) + "." +
                                        str(sek).rjust(2, "0"))
            if not self.verbose:
                prikaz = prikaz + ' > /dev/null'
            os.system(prikaz)
        # generate rtc time as datetime:
        return (datetime.datetime(stoleti + rok, mes, den, hod, min, int(sek)),
                napeti)


if __name__ == '__main__':  # testing code
    s = RTC8563(True)
    # vyhodnoceni predavaneho parametru pri spousteni programu
    # odchytavani chyby, ktera by vznikla pri chybejicim parametru:
    try:
        # parametr spousteneho programu do promenne "akce":
        akce = sys.argv[1]
    except:
        # kdyz parametr chybi, je nahrazen prazdnym retezcem
        akce = ""

    # prevod parametru na mala pismena:
    akce = akce.lower()

    # rozeskoky pri ruznych akcich
    if (akce == "-i"):
        # jen zobrazeni casu v RasPi a RTC:
        s.info()
    elif (akce == "-pi2rtc"):
        # zapis casu do RTC obvodu podle RasPi
        s.write()
    elif (akce == "-rtc2pi"):
        # nastaveni RasPi podle RTC
        s.info(True)
    else:
        # pri jakemkoli jinem parametru se zobrazi napoveda
        print "Pripustne parametry:"
        print "... -i        INFO - Jen zobrazi cas v RasPi a v RTC"
        print "... -pi2rtc   Zapise cas z RasPi do RTC"
        print "... -rtc2pi   Zapise cas z RTC do RasPi"
