#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# vim modeline: vim: shiftwidth=4 tabstop=4
#=================================================================
# main yawspi program
#=================================================================

# XXX todo:
# bugs:
# 3, station settings - threshold - does it change grad sensor slope? should
# it? recalculate values to 0..1?
# 6, ensure the smallest main loop time is one minute otherwise looking for
# next running times could fail - really?
# 7, show webpage 'wait' if user wants water station NOW from stations web
# page?
# 8, home page, table programs: when 'next run in' is now, nothing is
# shown
# 9, kdyz ukladani hladin do specialniho souboru, zrusit zapis do logu?
# 10, pred zacatkem napousteni zmerit hodnotu sensoru jestli neni plna stanice
# 11, po skonceni plneni upravit hodnoty pro web
# 13, YawspiHW prejmenovat na YawspiHAL, hw_control na HAL.py
# 14, kdyz se da water station now (z web stations), tak da status filling, pak
# kdyz se da casem refresh page, tak ukaze ze skoncil filling, ale senzor ma
# spatny stav, na to se musi dat check now. coz je napytel, protoze po filling
# uz musi mit senzor zmereny ne?
# 17, program water by level ignoruje cas platnosti programu
# 18, 'Desc': gv.hw.se_description(x) is updated only once during
# initialization

# standard modules:
from time import sleep
import arrow
import signal
import sys
import web
import thread
import pickle
import os
import pygal
# gv - 'global vars' - an empty module, used for storing vars (as attributes),
# that need to be 'global' across threads and between functions and classes:
import gv
# yawspi hardware control (hardware abstraction layer):
from hw_control import YawspiHW


# ------------------- various functions:
def sigterm_handler(_signo, _stack_frame):
    # Raises SystemExit(0):
    sys.exit(0)


def get_now_str_web():  # returns current date/time as string for home web page
    """ return current date and time as string for web

    Format is
    DD. MM. YYYY HH:MM:ss, dddd, MMMM, ZZ
    e.g. 2015 13:35:40, wednesday, january, +01
    \param Nothing
    \return string: date and time as string
    """
    return arrow.now('local').format('DD. MM. YYYY HH:mm:ss, dddd, MMMM, ZZ')


def quit(reason):  # performs safe quit
    """ perform safe quit of the YAWSPI

    1. switch water source off,
    2. switch valves off,
    3. release GPIO,
    4. save configuration, programs, hardware settings
    5. write quitting to log
    6. save log
    \param string: reason why quitting
    \return Nothing
    """
    gv.hw.so_switch(0)  # set water source off
    for i in range(gv.hw.StNo):
        gv.hw.st_switch(i, 0)  # switch valve off
    gv.hw.clean_up()  # cleans GPIO
    gs_save()  # save configuration
    prg_save()  # save programs
    hws_save()  # save hardware settings
    log_add('quitting, ' + reason)
    log_save()  # save log


def td_format(td_object):  # formats timedelta to nice string
        """ formats timedelta object to a nice string

        Format is in human readable form
        \param timedelta: difference of two arrow or datetime objects
        \return string: time difference as string
        """
        seconds = int(td_object.total_seconds())
        periods = [
            ('year',        60 * 60 * 24 * 365),
            ('month',       60 * 60 * 24 * 30),
            ('day',         60 * 60 * 24),
            ('hour',        60 * 60),
            ('minute',      60),
        ]
            #('second',      1)
        strings = []
        for period_name, period_seconds in periods:
                if seconds > period_seconds:
                        period_value, seconds = divmod(seconds, period_seconds)
                        if period_value == 1:
                                strings.append("%s %s" %
                                               (period_value, period_name)
                                               )
                        else:
                                strings.append("%s %ss" %
                                               (period_value, period_name)
                                               )
        return ", ".join(strings)


def check_and_set_time():  # check local and RTC time
    """
    Every week check local and RTC time and set one.

    If local time is smaller than 1.1.2000, set local according to RTC, else
    set RTC according local. It is done only once per week. Also checks RTC
    battery.
    \param None
    \return None
    """
    # check if last check was done at least one week before:
    if arrow.utcnow().replace(weeks=-1) > gv.lastRTCupdate:
        lcl = arrow.utcnow()
        if not gv.hw.RTC_get_bat():
            log_add(' <font color="red">RTC battery not OK!</font>')
        if lcl < arrow.get(2000, 1, 1):
            # update local time
            gv.hw.RTC_set_local()
            log_add('local time updated from RTC')
        else:
            # update RTC time
            gv.hw.RTC_set_RTC()
            log_add('RTC time updated from local')
        gv.lastRTCupdate = lcl


# ------------------- variables initializations/definitions:
def init_gs():  # initialize dictionary with general settings:
    """ initialize global variable gv.gs dictionary

    gv.gs contains basic settings of YAWSPI software:
    1. Name: configurable name of the system
    2. Version: yawspi version
    3. Enabled: operation enabled
    4. httpPort: http listening port of web server
    5. Location: city name for weather retrieval from internet \todo{not
        finished} XXX
    6. Logging: writing to log enabled
    7. LoggingLimit: maximal number of log lines to keep, 0 = no limit
    8. MLInterval: Main loop interval (s) - how often watering and water levels
        are checked.
    \param Nothing
    \return Nothing
    """
    gv.gs = {
        'Name': u'YAWSPI',
        'Version': u'0.1',
        'Enabled': True,
        'httpPort': 8080,
        'Location': u'Brno',
        'Logging': True,
        'LoggingLimit': 1000,
        'MLInterval': 60
    }


def init_hws():  # initialize dictionary with hw settings:
    """ Initialize global variable gv.hws dictionary with hardware data.

    gv.hws contains hardware related values, which can be mostly set by
    webserver:
    1. StData: list of dictionaries containing:
        1. Name: Station name
        2. LowThr: lower threshold - if sensors value is below, station is
        considered empty
        3. HighThr: upper threshold - if sensors value is above, station is
        considered full
        4. SaveData: boolean whether save measured and filling data
        5. Desc: sensor description generated by hardware abstraction layer
    2. SoData: dictionary containing:
        1. SaveData: boolean whether save measured data
    3. SeData: list of dictionaries containing:
        1. SaveData: ??? XXX
    \param Nothing
    \return Nothing
    \todo{check if SeData SaveData is not duplicit, and what is the difference
    to StData SaveData}
    """
    gv.hws = {
        'StData': [],
        'SoData': {
            'SaveData': True,
        },
        'SeData': {
            'SaveData': [],
        },
    }
    for x in range(gv.hw.StNo):
        gv.hws['StData'].append({
            'Name': 'station ' + str(x),
            'LowThr': 0.1,
            'HighThr': 0.9,
            'SaveData': True,
            'Desc': gv.hw.se_description(x)
        })


def init_cv():  # initialize dictionary with current values
    """ initialize global variable gv.cv dictionary with various current values

    gv.cv values are generated by some funtction and contains:
    1. TimeStr: current time as string for webpage generated by get_now_str_web
    2. SoWL: current water level of source
    3. StWL: list of numbers with current water level of stations
    4. PrgNR: list of arrow objects with next watering times of programs
    5. SeTemp: temperature weather sensor value
    6. SeRain: rain weather sensor value
    7. SeHumid: humidity weather sensor value
    8. SePress: pressure weather sensor value
    9. SeIllum: illuminance weather sensor value
    10. CurAct: what is software now doing
    11. xConstrain: x axis in history chart is constrained to xMin and xMax
    11. xMin: arrow time last shown x minimal value in history chart
    12. xMax: arrow time last shown x maximal value in history chart
    \param Nothing
    \return Nothing
    """
    gv.cv = {
        'TimeStr': get_now_str_web(),
        'SoWL': 0,
        'StWL': [0] * gv.hw.StNo,
        'PrgNR': [arrow.now('local')] * len(gv.prg),
        'SeTemp': -300,
        'SeRain': -300,
        'SeHumid': -300,
        'SePress': -300,
        'SeIllum': -300,
        'CurAct': '',
        'xConstrain': False,
        'xMin': arrow.now('local').replace(days=-2),
        'xMax': arrow.now('local'),
    }


def prg_get_new():  # returns dict with a new program
    """ return dictionary with a new program

    program dictionary contains:
    1. Name: string name of the program
    2. Enabled: boolean program is enabled
    3. Stations: list of stations numbers affected by program
    4. Mode: string mode of operation, possible values:
        1. waterlevel: according water level - start if all stations empty
        2. weekly: according calendar - start selected days of week
        3. interval: according calendar - start every nth day
    5. wlMinDelayH: integer, for waterlevel mode - not start sooner than
    (hours)
    6. wlEmptyDelayH, integer, for waterlevel mode - must be empty at least
    (hours)
    7. calwDays: list of integers, for weekly mode - start days in week (1 -
    Monday, 7 - Sunday):
    8. calwRepeatH: integer, for weekly mode - repeat during day every (hours):
    9. caliIntervalD: integer, for interval mode - repeat interval (days):
    10. caliRepeatH: integer, for interval mode - repeat during day every
    (hours):
    11. TimeFromH: integer, program valid from time of day (Hours):
    12. TimeFromM: integer, program valid from time of day (Minutes):
    13. TimeToH: integer, program valid to time of day (Hours):
    14. TimeToM: integer, program valid to time of day (Minutes):
    15. TimeLastRun: arrow, last run of program (for a new program is set 1 day
    to the past - i.e. equal to caliIntervalD
    16. FoundEmpty: boolean, all stations of the program was already found as
    empty? (for a new program is set as not yet found empty (False))
    17. TimeFoundEmpty: arrow, first time when found all stations of the
    program empty (usefull only for waterlevel mode, is used only if
    'FoundEmpty' is True)
    \param Nothing
    \return dict: default program dictionary
    """
    return {
        'Name': 'new program',
        'Enabled': False,
        'Stations': [],
        #'Mode': 'waterlevel',
        #'Mode': 'weekly',
        'Mode': 'interval',
        'wlMinDelayH': 1,
        'wlEmptyDelayH': 1,
        'calwDays': [1, 3, 5],
        'calwRepeatH': 5,
        'caliIntervalD': 1,
        'caliRepeatH': 5,
        'TimeFromH': 6,
        'TimeFromM': 0,
        'TimeToH': 19,
        'TimeToM': 0,
        'TimeLastRun': arrow.now('local').replace(days=-1),
        'FoundEmpty': False,
        'TimeFoundEmpty': arrow.now('local')
    }


# ------------------- watering program handling:
def prg_add():  # add a new program
    """ add a new program to the list of programs

    new program with default values is appended to the gv.prg and gv.cv is
    updated.
    \param Nothing
    \return Nothing
    """
    # append new program:
    gv.prg.append(prg_get_new())
    # increase list with next watering time for web server:
    gv.cv['PrgNR'].append(arrow.now('local'))


def prg_remove(index):  # remove a program
    """ remove a program from the list of programs

    remove program of index, update gv.cv
    \param index: integer of the program to remove
    \return Nothing
    """
    # remove program:
    gv.prg.pop(index)
    # decrease list with next watering time for web server:
    gv.cv['PrgNR'].pop(index)


def prg_is_water_time(index):  # return boolean if watering should start
    """ finds if watering should start

    Checks if program is enabled, than according program mode asks for watering
    time later than now. Checks if watering time is_in_time_span. Adds log if
    watering should start or not and why not

    \param int: index of the program
    \return bool: True if watering is due
    """
    prg = gv.prg[index]
    now = arrow.now('local')
    if not prg['Enabled']:
        # disabled program is not logged
        return False
    else:
        # if source empty, no action:
        if gv.cv['SoWL'] == 0:
            log_add('program "' + prg['Name'] +
                    '" (' + str(index) + '): ' +
                    'not ready for watering, source is empty!'
                    )
            return False
        now = arrow.now('local')
        isreadystr = 'program "' + prg['Name'] + \
                     '" (' + str(index) + '): ready for watering'
        notreadystr = 'program "' + prg['Name'] + '" (' + str(index) + '): '
        if prg['Mode'] == 'waterlevel':
            # water level mode:
            tmp = prg_lev_is_water_time(index, now)
            # next run not available in water level mode, string for web:
            tim = tmp[0] - arrow.now('local')
            if tim.total_seconds() < 0:
                gv.cv['PrgNR'][index] = 'Not yet empty'
            else:
                gv.cv['PrgNR'][index] = td_format(tim)
            if tmp[2]:
                log_add(isreadystr)
                return True
            else:
                log_add(notreadystr + tmp[1])
                return False
        elif prg['Mode'] == 'weekly':
            # weekly calendar mode:
            tmp = prg_wee_next_water_time(index, now)
            # generate next run in string for web:
            gv.cv['PrgNR'][index] = td_format(tmp[0] - arrow.now('local'))
            if is_in_time_span(index, now, tmp[0]):
                log_add(isreadystr)
                return True
            else:
                log_add(notreadystr + tmp[1])
                return False
        elif prg['Mode'] == 'interval':
            # interval mode:
            tmp = prg_int_next_water_time(index, now)
            # generate next run in string for web:
            gv.cv['PrgNR'][index] = td_format(tmp[0] - arrow.now('local'))
            if is_in_time_span(index, now, tmp[0]):
                log_add(isreadystr)
                return True
            else:
                log_add(notreadystr + tmp[1])
                return False
        else:
            raise NameError('unknown program type')


def prg_lev_is_water_time(index, now):  # checks if is watering time
    """ Checks if now is watering time for water level mode progam.

    Checks if all stations are empty, if so set FoundEmpty to True, if not set
    to False (also sets TimeFoundEmpty). Set to False is because if pot is
    found empty, and program waits some time, and someone waters it in between,
    than program would water even if stations are full.
    Than checks time from last watering and if time from found empty is long
    enough.

    \param int: index of program
    \param arrow: time after which next watering time is found
    \return tuple: (bool, string, arrow), bool True if program is ready for
    watering; string with description why program is not ready for watering if
    so; arrow time of next watering if possible, if not reutrn time smaller
    than input parameter
    """
    prg = gv.prg[index]
    # check if all stations in program are empty:
    # If FoundEmpty is false, routine still did not found all stations to be
    # empty
    allempty = True
    for st in prg['Stations']:
        # station is empty if value is lower than low threshold:
        if gv.cv['StWL'][st] > gv.hws['StData'][st]['LowThr']:
            allempty = False
    if not allempty:
        # return time in history to represent that it is impossible to know
        # when next watering will be
        tmp = now.replace(days=-1)
        # someone other could water the pot instead of YawsPi, so just to be
        # sure FoundEmpty is reseted:
        gv.prg[index]['FoundEmpty'] = False
        return (tmp, 'some stations still not empty', False)
    else:
        if prg['FoundEmpty'] is False:
            # all stations found empty for first time, remember time:
            gv.prg[index]['TimeFoundEmpty'] = now
            # and set it was already found empty:
            gv.prg[index]['FoundEmpty'] = True
    # stations found empty, so:
    # check if time from last watering is long enough:
    tmp = prg['TimeLastRun'].replace(hours=prg['wlMinDelayH'])
    if now <= tmp:
        return (tmp, 'not long enough from last watering', False)
    # check if stations are empty long enough:
    tmp = prg['TimeFoundEmpty'].replace(hours=prg['wlEmptyDelayH'])
    if now < tmp:
        return (tmp, 'stations not empty long enough', False)
    # all conditions ok, program is ready for watering:
    return (now, 'ready for watering', True)


def is_in_time_span(index, querytime, nextwatertime):  # times are equal?
    """ Checks if two times are equal within precision given by main loop
    interval gv.gs['MLInterval'].

    Precision is two times of mail loop interval (MLI).
    So True is returned if:
        1, querytime is later than TimeLastRun + 2*MLI
        1, querytime is later than nextwatertime - 2*MLI
        1, querytime is earlier than nextwatertime + 2*MLI

    \param int: index of program
    \param arrow: querytime is time for which should be determined if it is
    watering time
    \param arrow: nextwatertime is watering time later than query time
    \return bool: True if times equal
    """
    mli = gv.gs['MLInterval']
    tlr = gv.prg[index]['TimeLastRun']
    tmp = (
        querytime > tlr.replace(seconds=2 * mli)
        and
        nextwatertime > querytime.replace(seconds=-2 * mli)
        and
        nextwatertime < querytime.replace(seconds=+2 * mli)
    )
    return tmp


def prg_wee_next_water_time(index, starttime):  # returns next watering time
    """ Returns next watering time for program with weekend mode.

    Search for next watering time starts from starttime.
    \param int: index of program
    \param arrow: starttime after which next watering time is found
    \return tuple: (arrow, string), time of next watering, string with
    description why now is not next watering (in the case it is not).
    """
    prg = gv.prg[index]
    # check variables to prevent infinite while loops:
    if not bool(set(prg['calwDays']) & set(range(1, 8))):
        raise NameError('program does not contain any valid weekdays!')
    if not prg['calwRepeatH'] > 0:
        raise NameError('program repeat hour is not greater than zero!')
    reason = 'not valid day of week'
    # prepare time pointer
    t = starttime
    t = t.replace(hour=prg['TimeFromH'], minute=prg['TimeFromM'])
    t = t.floor('minute')
    # is t (same day as starttime) the valid week day?
    if t.isoweekday() in prg['calwDays']:
        ts = t
        # starttime is valid week of day,
        # add repeat interval till bigger than starttime:
        while not ts >= starttime:
            ts = ts.replace(hours=prg['calwRepeatH'])
        # if ts is still the same day as starttime:
        if ts.day == t.day:
            # if not later than 'program valid to' time:
            pvt = ts.replace(hour=prg['TimeToH'], minute=prg['TimeToM'])
            pvt = pvt.floor('minute')
            if ts <= pvt:
                # time of next watering time found, if ts is not the same as
                # starttime, only reason can be:
                reason = 'not valid time of a day'
                return (ts, reason)
        # date overflow, therefore starttime is later than TimeTo:
        reason = 'later than TimeTo'
        # add day and continue looking for valid weekday:
        t = t.replace(days=+1)
    # t is not valid weekday, add days till next valid weekday found:
    while not t.isoweekday() in prg['calwDays']:
        t = t.replace(days=+1)
    # set hour and minute to 'program valid from'
    return (t, reason)


def prg_int_next_water_time(index, starttime):  # returns next watering time
    """ Returns next watering time for program with interval mode.

    Search for next watering time starts from TimeLastRun, than it search for
    watering time later than starttime.

    \param int: index of program
    \param arrow: starttime after which next watering time is found
    \return tuple: (arrow, string), time of next watering, string with
    description why now is not next watering (in the case it is not).
    """
    # searching starts from timelastrun. after a change of program a
    # timelastrun must be set to now minus caliIntervalD!
    # XXX not finished description - is it correct description?

    prg = gv.prg[index]
    # check variables to prevent infinite while loops:
    if not prg['caliIntervalD'] > 0:
        raise NameError('program repeat day is not greater than zero!')
    if not prg['caliRepeatH'] > 0:
        raise NameError('program repeat hour is not greater than zero!')
    # get a day of last run:
    t = prg['TimeLastRun']
    t = t.replace(hour=prg['TimeFromH'], minute=prg['TimeFromM'])
    t = t.floor('minute')
    # add days till found day greater or equal to starttime:
    while t.floor('day') < starttime.floor('day'):
        t = t.replace(days=prg['caliIntervalD'])
    # found day is not equal to starttime?
    if not t.day == starttime.day:
        # found time is later day than starttime, return it:
        return (t, 'not valid day')
    # found day is equal to starttime, add hours till found time equal or
    # greater than starttime
    ts = t
    while ts < starttime:
        ts = ts.replace(hours=prg['caliRepeatH'])
    pvt = starttime.replace(hour=prg['TimeToH'], minute=prg['TimeToH'])
    # found time is greater then 'program valid to' time?
    if ts > pvt:
        # add caliIntervalD to previous found day and return it:
        t = t.replace(days=prg['caliIntervalD'])
        return(t,  'later than TimeTo')
    # found time is not grater then 'program valid to' time, return it:
    return(ts, 'not valid time of a day')


def prg_water(index):  # starts watering all stations in the program
    # fill stations in program:
    for st in gv.prg[index]['Stations']:
        station_fill(st)
    # save time of filling:
    gv.prg[index]['TimeLastRun'] = arrow.now('local')
    # set that station was not yet found empty:
    gv.prg[index]['FoundEmpty'] = False
    gv.prg[index]['TimeFoundEmpty'] = arrow.now('local').replace(days=-1)


# ------------------- configurations saving and loading:
def gs_load():  # load configuration file
    # general settings:
    if os.path.isfile(gv.gsfilepath):
        # if file exist load it:
        gsfile = open(gv.gsfilepath, 'r')
        gv.gs = pickle.load(gsfile)
        gsfile.close()
        log_add('general settings loaded from file')
    else:
        # if file do not exist initialize standard settings:
        init_gs()
        log_add('general settings initialized to default values')


def gs_save():  # save configuration file
    # general settings:
    if not os.path.isdir(gv.configdir):
        os.mkdir(gv.configdir)
    gsfile = open(gv.gsfilepath, 'w')
    pickle.dump(gv.gs, gsfile)
    gsfile.close()
    log_add('general settings saved to file')


def hws_load():  # load hardware settings file
    # general settings:
    if os.path.isfile(gv.hwsfilepath):
        # if file exist load it:
        hwsfile = open(gv.hwsfilepath, 'r')
        gv.hws = pickle.load(hwsfile)
        hwsfile.close()
        if len(gv.hws['StData']) != gv.hw.StNo:
            raise NameError('Number of stations in hardware settings file '
                            'do not match hardware configuration file. '
                            'Probably hardware settings pickle file should be '
                            'deleted?')
        log_add('hardware settings loaded from file')
    else:
        # if file do not exist initialize standard settings:
        init_hws()
        log_add('hardware settings initialized to default values')


def hws_save():  # save hardware settings to a file
    # hardware settings:
    if not os.path.isdir(gv.configdir):
        os.mkdir(gv.configdir)
    hwsfile = open(gv.hwsfilepath, 'w')
    pickle.dump(gv.hws, hwsfile)
    hwsfile.close()
    log_add('hardware settings saved to file')


def prg_load():  # load program file
    # general settings:
    if os.path.isfile(gv.prgfilepath):
        # if file exist load it:
        prgfile = open(gv.prgfilepath, 'r')
        gv.prg = pickle.load(prgfile)
        prgfile.close()
        log_add('programs loaded from file')
    else:
        # if file do not exist initialize standard settings:
        gv.prg = []
        log_add('programs initialized to default values')


def prg_save():  # save program file
    # general settings:
    if not os.path.isdir(gv.configdir):
        os.mkdir(gv.configdir)
    prgfile = open(gv.prgfilepath, 'w')
    pickle.dump(gv.prg, prgfile)
    prgfile.close()
    log_add('programs saved to file')


# ------------------- watering data related:
def check_data_folder():  # check folder with data files (creates it if needed)
    if not os.path.isdir(gv.datadir):
        os.mkdir(gv.datadir)


def data_filename(dname):  # returns file path and name of measured data
    """ Return file path and name of file with measured data

    \param string name containing number of station or source or sensor
    \return string path and name of data file
    """
    # station, source or sensor?
    if check_data_name(dname):
        # station?
        if dname in [str(i) for i in range(gv.hw.StNo)]:
            return gv.datadir + '/' + str(dname).format('%03d') + '.csv'
        else:
            return gv.datadir + '/' + dname + '.csv'
    else:
        raise NameError('unknown input into the data_filename(): '
                        + str(dname))


def save_station_level(index, value):  # save water level of a station
    if index in range(gv.hw.StNo):
        # saving data for this station enabled?:
        if gv.hws['StData'][index]['SaveData']:
            save_station_data_line(index, str(value) + '; water level (a. u.)')


def save_station_fill(index, value):  # save filled volume of a station
    # value is filled volume in liters
    if index in range(gv.hw.StNo):
        # saving data for this station enabled?:
        if gv.hws['StData'][index]['SaveData']:
            save_station_data_line(index, str(value) + '; fill volume (l)')


def save_station_data_line(index, string):  # save w. level/filling of station
    """ Save measured water level or filling amount of a station to a file
    together with time stamp, only if enabled by settings.

    \param int index with number of station
    \param str string with value and water level or filling information and
    unit
    \return Nothing
    """
    check_data_folder()
    if index in range(gv.hw.StNo):
        # saving data for this station enabled?:
        if gv.hws['StData'][index]['SaveData']:
            datafile = open(data_filename(str(index)), 'a')
            tmp = arrow.now('local').isoformat() + '; ' + string + '\n'
            datafile.writelines(tmp)
            datafile.close()


def save_source_level(value):  # save source water level
    """ Save measured water level of a source to a file together with
    time stamp, only if enabled by settings.

    \param float value of source water level
    \return Nothing
    """
    check_data_folder()
    # saving data for source enabled?:
    if gv.hws['SoData']['SaveData']:
        datafile = open(data_filename('source'), 'a')
        tmp = arrow.now('local').isoformat() + '; ' + str(value) + '\n'
        datafile.writelines(tmp)
        datafile.close()


def save_sensor_value(dname, value):  # save measured sensor value
    """ Save measured value of a sensor to a file together with time stamp,
    only if enabled by settings.

    \param str name of sensor
    \param float value of sensor
    \return Nothing
    """
    check_data_folder()
    if dname in gv.hw.Sensors:
        # save data for this sensor enabled?:
        if dname in gv.hws['SeData']['SaveData']:
            datafile = open(data_filename(dname), 'a')
            tmp = arrow.now('local').isoformat() + '; ' + str(value) + '\n'
            datafile.writelines(tmp)
            datafile.close()


def load_data_file(dname):  # loads data from data file
    """ Loads data from saved data file with history of station, sensor or
    source.

    \param str name of station, sensor or source
    \return list of lists: [arrow time, value, whole data line]
    """
    data = []
    if os.path.isfile(data_filename(dname)):
        # file should be closed automatically when using with statement
        with open(data_filename(dname)) as f:
            for line in f:
                # parse and convert data:
                line = line.split(';')
                line[0] = arrow.get(line[0])
                line[1] = float(line[1])
                # parse possible other data
                data.append(line)
    return data


def check_data_name(dname):  # checks string is station or sensor or source
    """ Checks if input string is station or sensor or source

    Correct input is '0', '1', '2', ... as station number (range of
    gv.hw.StNo), or 'source' as source, or one of sensors: 'illum', 'temp',
    'rain', 'humid', 'press' (one of in gv.hw.Sensors).

    \param string name string to check
    \return boolean true if input is station or sensor or source
    """
    # suppose name is not ok:
    res = False
    # check if indexstr contains number of station:
    if dname in [str(i) for i in range(gv.hw.StNo)]:
        res = True
    # check if name contains sensor:
    elif dname in gv.hw.Sensors:
        res = True
    # check if name contains source:
    elif dname == 'source':
        res = True
    return res


def make_chart(name, constrain, xmin, xmax):  # generate history chart
    """ Generates history chart

    Generates history chart of station or sensor or source. If constrain is
    true, chart will be limited by times xmin and xmax.
    \param string name - number of station or source or sensors like illum,
    press etc.
    \param bool constrain if true use xmin and xmax parameters as chart
    constrains
    \param arrow xmin low value of xaxis
    \param arrow xmax high value of xaxis
    \return string xml/svg chart for embedding into webpage
    """
    # check input:
    if not check_data_name(name):
        return 'Unknown station or sensor'
    # measured data:
    data = load_data_file(name)
    ax1 = []
    ax2 = []
    # secondary axis will be used?
    secondY = False
    # set values according what to plot
    if name in [str(i) for i in range(gv.hw.StNo)]:
        # it is station:
        gtitle = gv.hws['StData'][int(name)]['Name'] + \
            ' (' + str(name) + ')'
        y1title = 'water level (a. u.)'
        # parse station data:
        for tmp in data:
            if tmp[2].find('level') > -1:
                # found water level data, apply constrains:
                if (constrain and tmp[0] >= xmin and tmp[0] <= xmax) \
                        or (not constrain):
                    ax1.append((tmp[0].datetime, tmp[1]))
            elif tmp[2].find('fill') > -1:
                # found water filling data, apply constrains:
                if (constrain and tmp[0] >= xmin and tmp[0] <= xmax) \
                        or (not constrain):
                    ax2.append((tmp[0].datetime, tmp[1]))
        if len(ax2) > 0:
            y2title = 'fill volume (l)'
            secondY = True
    else:
        # it is sensor or source:
        if name == 'source':
            gtitle = 'water source'
            y1title = 'water level (a. u.)'
        elif name == 'temp':
            gtitle = 'ambient temperature'
            y1title = 'deg C'
        elif name == 'humid':
            gtitle = 'ambient humidity'
            y1title = '%'
        elif name == 'press':
            gtitle = 'ambient pressure'
            y1title = 'Pa'
        elif name == 'rain':
            gtitle = 'rain'
            y1title = '(a. u.)'
        elif name == 'illum':
            gtitle = 'ambient light'
            y1title = 'lux'
        else:
            # not identified what to plot (shouldn't happen, just for sure):
            raise NameError('Error - unknown string in name in make_chart')
        # change arrow datatype to datetime:
        for tmp in data:
            # apply constrains:
            if (constrain and tmp[0] >= xmin and tmp[0] <= xmax) or \
                    (not constrain):
                ax1.append((tmp[0].datetime, tmp[1]))
    # initialize chart:
    chart = pygal.DateTimeLine(style=pygal.style.CleanStyle,
                               legend_at_bottom=True,
                               print_values=False,
                               show_x_guides=True,
                               show_y_guides=True,
                               x_label_rotation=20,
                               x_label_format='%a %d.%m. %H:%M',
                               x_value_formatter=
                               lambda dt: dt.strftime('%a %d.%m. %H:%M'),
                               title=gtitle,
                               y_title=y1title,
                               show_legend=False,
                               human_readable=True,
                               )
    # create line:
    chart.add('water level', ax1, fill=True)
    if secondY:
        # add sedondary line and setup axes:
        chart.add('filling',
                  ax2, secondary=True,
                  dots_size=6,
                  stroke=False,
                  )
        # pygal do not shows secondary title:
        chart.config(show_legend=True,
                     y_title=y1title + ' / ' + y2title,
                     # XXX not working in pygal:
                     # secondary_title='aaa',
                     )
    return chart.render()


# ------------------- log related:
def log_add(line):  # add string to a log buffer
    if gv.gs['Logging']:
        # add time to the log line:
        tmp = '<br>' + arrow.now('local').isoformat() + '; ' + line + '\n'
        # hopefully this is atomic operation so no collisions between threads
        # can occur:
        gv.logbuffer = gv.logbuffer + [tmp]


def log_save():  # saves log to a file
    # this function should be called only from main thread (not webserver
    # thread) to prevent thread collisions
    # write only if buffer is not empty:
    if gv.gs['Logging'] and len(gv.logbuffer) > 0:
        if not os.path.isdir(gv.configdir):
            os.mkdir(gv.configdir)
        if os.path.isfile(gv.prgfilepath):
            logfile = open(gv.logfilepath, 'a')
        else:
            logfile = open(gv.logfilepath, 'w')
        # this is not atomic XXX! :
        tmp = gv.logbuffer
        gv.logbuffer = []
        # write buffer to a file:
        logfile.writelines(tmp)
        logfile.close()
        # XXX how to limit lines in log file?


def log_get():  # returns full log (load file and add buffer)
    tmp = ['']
    if gv.gs['Logging'] and os.path.isfile(gv.logfilepath):
        logfile = open(gv.logfilepath, 'r')
        # read file and append actual buffer:
        tmp = logfile.readlines() + gv.logbuffer
        logfile.close()
    return tmp


# ------------------- hardware related functions:
# (can be called only from main thread)
def sensors_get_all():  # measures water levels of barrel and all stations
    gv.cv['CurAct'] = 'reading sensors'
    if __name__ != "__main__":
        raise NameError('sensors_get_all() called outside main thread!')
    # get source water level:
    gv.cv['SoWL'] = gv.hw.so_level()
    save_source_level(gv.cv['SoWL'])
    log_add('water source is ' + str(gv.cv['SoWL'] * 100) + '% full')
    # stations water level:
    for i in range(gv.hw.StNo):
        # XXX tady dat threshold (nebo nekam jinam)?
        gv.cv['StWL'][i] = gv.hw.se_level(i)
        save_station_level(i, gv.cv['StWL'][i])
        log_add('station "' + gv.hws['StData'][i]['Name'] + '" (' + str(i) +
                ') is ' + str(gv.cv['StWL'][i] * 100) + '% full')
    # weather sensors:
    gv.cv['SeTemp'] = gv.hw.se_temp()
    save_sensor_value('temp', gv.cv['SeTemp'])
    gv.cv['SeHumid'] = gv.hw.se_humid()
    save_sensor_value('humid', gv.cv['SeHumid'])
    gv.cv['SeRain'] = gv.hw.se_rain()
    save_sensor_value('rain', gv.cv['SeRain'])
    gv.cv['SePress'] = gv.hw.se_press()
    save_sensor_value('press', gv.cv['SePress'])
    gv.cv['SeIllum'] = gv.hw.se_illum()
    save_sensor_value('illum', gv.cv['SeIllum'])


def station_fill(index):  # fill water into one station
    gv.cv['CurAct'] = 'filling station ' + str(index)
    # XXX st_fill by mel vracet i odhadnuty objem, a ten pak ukladat do dat
    if __name__ != "__main__":
        raise NameError('station_fill() called outside main thread!')
    log_add('preparing to fill station "' + gv.hws['StData'][i]['Name'] +
            '" (' + str(index) + ')')
    # get filling time in seconds according to station capacity:
    filltime = gv.hw.fill_time(index)
    # set sssafety bound to 10 %:
    filltime = filltime * 1.1
    try:
        realfilltime = gv.hw.st_fill(index, gv.hws['StData'][index]['HighThr'])
    except:   # XXX tohle je mozna blbost, try mozna uvnitr station fill?
        gv.hw.so_switch(0)
        raise NameError('Error when filling station!')
    tmp = 'station "' + gv.hws['StData'][i]['Name'] + '" (' + str(index) + \
          ') was filled, filled volume (calculated from time) was ' + \
          str(gv.hw.filled_volume(realfilltime)) + ' l, filling time was ' + \
          str(realfilltime) + ' s, time limit was ' + str(filltime) + ' s'
    if realfilltime > filltime:
        tmp = tmp + ', time limit EXCEEDED!'
    save_station_fill(i, gv.hw.filled_volume(realfilltime))
    log_add(tmp)


# ------------------- web pages definitions:
class WebHome:  # home page with status informations
    def GET(self):
        # update time string:
        gv.cv['TimeStr'] = get_now_str_web()
        return render.home(gv)

    def POST(self):
        response = web.input()  # get user response
        simpleredirect = {
            'reload': '/',
            'options': '/options',
            'stations': '/stations',
            'programs': '/programs',
            'history': '/history',
            'log': '/log',
            'reboot': '/reboot',
        }
        if response.keys()[0] in simpleredirect:
            raise web.seeother(simpleredirect[response.keys()[0]])
        elif 'breakmainloop' in response:
            # user required for main loop break, add flag:
            if not 'askforbreak' in gv.flags:
                gv.flags = gv.flags + ['askforbreak']
            # reload this page
            raise web.seeother('/')
        elif 'start' in response:
            gv.gs['Enabled'] = 1
            raise web.seeother('/')
        elif 'stop' in response:
            gv.gs['Enabled'] = 0
            raise web.seeother('/')
        # if any unknown response, reload home page:
        raise web.seeother('/')


class WebOptions:  # options page to change settings
    def __init__(self):
        self.frm = web.form.Form(  # definitions of all input fields
            web.form.Textbox(
                'Name',
                web.form.regexp('.+', 'At least one character'),
                description='System name:',
                title='User name of the system, such as A super garden etc.',
            ),
            web.form.Textbox(
                'httpPort',
                web.form.Validator('(integer 0 and greater)',
                                   lambda x: int(x) >= 0),
                description='http port of web pages:',
                title='Port of the web server. Default is 8080. Web ' +
                'address of YAWSPI is http://xxx.xxx.xxx.xxx:port/ .',
            ),
            web.form.Textbox(
                'Location',
                description='City location of the system:',
                title='Name of the city is used for weather retrieval ' +
                'from weather service.'
            ),
            web.form.Checkbox(
                'Logging',
                description='Logging:',
                title='Enable or disable logging of events.',
            ),
            web.form.Textbox(
                'LoggingLimit',
                web.form.Validator('(integer greater than 0)',
                                   lambda x: int(x) > 0),
                description='Limit logs to number of lines:',
                title='Maximal number of lines in the log, usefull ' +
                'to prevent large files.'
            ),
            web.form.Textbox(
                'MLInterval',
                web.form.Validator('(integer greater than 1)',
                                   lambda x: int(x) > 1),
                description='Main loop interval in seconds:',
                title='How often YAWSPI checks for water levels and ' +
                'if watering is due',
            ),
            web.form.Checkbox(
                'SourceData',
                description='Save source water level data:',
                title='Enable or disable logging of source water level data.',
            ),
            web.form.Checkbox(
                'TempData',
                description='Save temperature data:',
                title='Enable or disable logging of temperature data.',
            ),
            web.form.Checkbox(
                'HumidData',
                description='Save humidity data:',
                title='Enable or disable logging of humidity data.',
            ),
            web.form.Checkbox(
                'PressData',
                description='Save pressure data:',
                title='Enable or disable logging of pressure data.',
            ),
            web.form.Checkbox(
                'RainData',
                description='Save rain data:',
                title='Enable or disable logging of rain data.',
            ),
            web.form.Checkbox(
                'IllumData',
                description='Save illumination data:',
                title='Enable or disable logging of illumination data.',
            ),
        )

    def GET(self):
        frm = self.frm()
        # set default values of forms to current global values:
        frm.Name.value = gv.gs['Name']
        frm.httpPort.value = gv.gs['httpPort']
        frm.Location.value = gv.gs['Location']
        frm.Logging.checked = gv.gs['Logging']
        frm.LoggingLimit.value = gv.gs['LoggingLimit']
        frm.MLInterval.value = gv.gs['MLInterval']
        frm.SourceData.checked = gv.hws['SoData']['SaveData']
        frm.TempData.checked = 'temp' in gv.hws['SeData']['SaveData']
        frm.HumidData.checked = 'humid' in gv.hws['SeData']['SaveData']
        frm.PressData.checked = 'press' in gv.hws['SeData']['SaveData']
        frm.RainData.checked = 'rain' in gv.hws['SeData']['SaveData']
        frm.IllumData.checked = 'illum' in gv.hws['SeData']['SaveData']
        return render.options(gv, frm)

    def POST(self):
        frm = self.frm()
        response = web.input()  # get user response
        if 'submit' in response:
            if not frm.validates():  # if not validated
                # set default values of forms to user response (so input of all
                # fields is not lost if one field is not validated)
                frm.Name.value = response['Name']
                frm.httpPort.value = response['httpPort']
                frm.Location.value = response['Location']
                frm.Logging.checked = 'Logging' in response
                frm.LoggingLimit.value = response['LoggingLimit']
                return render.options(gv, frm)
            else:
                # write new values to global variables:
                gv.gs['Name'] = response['Name']
                gv.gs['httpPort'] = int(response['httpPort'])
                gv.gs['Location'] = response['Location']
                gv.gs['Logging'] = 'Logging' in response
                gv.gs['LoggingLimit'] = int(response['LoggingLimit'])
                gv.gs['MLInterval'] = int(response['MLInterval'])
                gv.hws['SeData']['SaveData'] = []
                gv.hws['SoData']['SaveData'] = 'SourceData' in response
                if 'TempData' in response:
                    gv.hws['SeData']['SaveData'].append('temp')
                if 'HumidData' in response:
                    gv.hws['SeData']['SaveData'].append('humid')
                if 'PressData' in response:
                    gv.hws['SeData']['SaveData'].append('press')
                if 'RainData' in response:
                    gv.hws['SeData']['SaveData'].append('rain')
                if 'IllumData' in response:
                    gv.hws['SeData']['SaveData'].append('illum')
                log_add('options changed by user')
                # save configuration to a file:
                gs_save()
                raise web.seeother('/')
        # if cancel or any unknown response, go to home page:
        raise web.seeother('/')


class WebReboot:  # show reboot question
    def GET(self):
        return render.reboot()

    def POST(self):
        response = web.input()  # get user response
        if 'reboot' in response:
            # send keyboard interrupt to main thread:
            thread.interrupt_main()
            # call system reboot in 1 minute
            # XXX causes error, but it is working. it is some problem of
            # threading package?
            os.system('/sbin/shutdown -r +1')
            # quit this thread with webserver:
            sys.exit(0)
        # if cancel or any unknown response, go to home page:
        raise web.seeother('/')


class WebLog:  # show log
    def GET(self):
        tmp = log_get()
        #reverse list and serialize it:
        # XXX zkusit pres [8:0:-1]
        tmp.reverse()
        tmp = ''.join(tmp)
        return render.log(tmp)

    def POST(self):
        response = web.input()  # get user response
        if 'reload' in response:  # if reload pressed, reload page
            raise web.seeother('/log')
        # if cancel or any unknown response, go to home page:
        raise web.seeother('/')


class WebStations:  # shows list of stations
    def GET(self):
        return render.stations(gv)

    def POST(self):
        response = web.input()  # get user response
        for i in range(gv.hw.StNo):
            if str(i) in response:
                return web.seeother('changestation' + str(i))
            flag = 'askforrun' + str(i)
            if flag in response:
                if not flag in gv.flags:
                    gv.flags = gv.flags + [flag]
                raise web.seeother('/')
        # if cancel or any unknown response, go to home page:
        raise web.seeother('/')


class WebChangeStation:  # change station settings
    def __init__(self):
        self.frm = web.form.Form(  # definitions of all input fields
            web.form.Textbox(
                'Name',
                web.form.regexp('.+', 'At least one character'),
                description='Station name:',
                title='User name of the station, such as Rose, turnips etc.',
            ),
            web.form.Textbox(
                'LowThr',
                web.form.Validator('(number from 0 to 100)',
                                   lambda x: float(x) >= 0),
                web.form.Validator('(number from 0 to 100)',
                                   lambda x: float(x) <= 100),
                description='Low Threshold (%)',
                title='If sensor output is below this value, ' +
                'station is considered empty.',
            ),
            web.form.Textbox(
                'HighThr',
                web.form.Validator('(number from 0 to 100)',
                                   lambda x: float(x) >= 0),
                web.form.Validator('(number from 0 to 100)',
                                   lambda x: float(x) <= 100),
                description='High Threshold (%)',
                title='If sensor output is above this value, ' +
                'station is considered full.',
            ),
            web.form.Checkbox(
                'SaveData',
                description='Save measured and filling data',
                title='If checked, all water level data and filling data' +
                ' will be saved to a file',
            ),
        )

    def GET(self, indexstr):
        frm = self.frm()
        # check if index of required station is valid:
        if indexstr in [str(i) for i in range(gv.hw.StNo)]:
            # set default values of forms to current global values:
            index = int(indexstr)
            frm.Name.value = gv.hws['StData'][index]['Name']
            frm.LowThr.value = gv.hws['StData'][index]['LowThr'] * 100
            frm.HighThr.value = gv.hws['StData'][index]['HighThr'] * 100
            frm.SaveData.checked = gv.hws['StData'][index]['SaveData']
        else:
            # incorrect station, set to -1, web template will report error:
            index = -1
        return render.changestation(gv, frm, index, indexstr)

    def POST(self, indexstr):
        frm = self.frm()
        response = web.input()  # get user response
        if 'submit' in response:
            if indexstr in [str(i) for i in range(gv.hw.StNo)]:
                index = int(indexstr)
                if not frm.validates():  # if not validated
                    # set default values of forms to user response (so input of
                    # all fields is not lost if one field is not validated)
                    frm.Name.value = response['Name']
                    frm.LowThr.value = response['LowThr']
                    frm.HighThr.value = response['HighThr']
                    frm.SaveData.checked = 'SaveData' in response
                    return render.changestation(gv, frm, index, '')
                else:
                    # write new values to global variables:
                    tmp = gv.hws['StData'][index]
                    tmp['Name'] = response['Name']
                    tmp['LowThr'] = float(frm.LowThr.value) / 100
                    tmp['HighThr'] = float(frm.HighThr.value) / 100
                    tmp['SaveData'] = 'SaveData' in response
                    gv.hws['StData'][index] = tmp
                    log_add('settings of station "' +
                            gv.hws['StData'][index]['Name'] + '" (' +
                            str(index) + ') was changed by user')
                    # save configuration:
                    hws_save()
                    raise web.seeother('/stations')
            else:
                index = -1
            return render.changestation(gv, frm, index, indexstr)
        # if cancel or any unknown response, go to home page:
        raise web.seeother('/stations')


class WebPrograms:  # shows list of programs
    def GET(self):
        return render.programs(gv)

    def POST(self):
        response = web.input()  # get user response
        if 'add' in response:
            prg_add()
            return web.seeother('programs')
        if 'check' in response:
            return web.seeother('checkprograms')
        if response.keys()[0] in ['c' + str(i) for i in range(len(gv.prg))]:
            # change program:
            return web.seeother('changeprogram' + response.keys()[0][1:])
        if response.keys()[0] in ['r' + str(i) for i in range(len(gv.prg))]:
            # remove program and reload page:
            prg_remove(int(response.keys()[0][1:]))
            return web.seeother('programs')
        # if cancel or any unknown response, go to home page:
        raise web.seeother('/')


class WebChangeProgram:  # change program settings
    def __init__(self):
        self.frm = web.form.Form(  # definitions of all input fields
            web.form.Textbox(
                'Name',
                web.form.regexp('.+', 'At least one character'),
            ),
            web.form.Textbox(
                'wlMinDelayH',
                web.form.Validator('(real number greater than 0)',
                                   lambda x: float(x) >= 0),
                size="3",
            ),
            web.form.Textbox(
                'wlEmptyDelayH',
                web.form.Validator('(real number greater than 0)',
                                   lambda x: float(x) >= 0),
                size="3",
            ),
            web.form.Checkbox(
                'calwDays1',
            ),
            web.form.Checkbox(
                'calwDays2',
            ),
            web.form.Checkbox(
                'calwDays3',
            ),
            web.form.Checkbox(
                'calwDays4',
            ),
            web.form.Checkbox(
                'calwDays5',
            ),
            web.form.Checkbox(
                'calwDays6',
            ),
            web.form.Checkbox(
                'calwDays7',
            ),
            web.form.Textbox(
                'caliIntervalD',
                web.form.Validator('(integer number greater than 0)',
                                   lambda x: int(x) > 0),
                size="3",
            ),
            web.form.Textbox(
                'calwRepeatH',
                web.form.Validator('(real number from 0 to 23.99)',
                                   lambda x: float(x) >= 0),
                web.form.Validator('(real number from 0 to 23.99)',
                                   lambda x: float(x) < 24),
                size="3",
            ),
            web.form.Textbox(
                'caliRepeatH',
                web.form.Validator('(real number from 0 to 23.99)',
                                   lambda x: float(x) >= 0),
                web.form.Validator('(real number from 0 to 23.99)',
                                   lambda x: float(x) < 24),
                size="3",
            ),
            web.form.Textbox(
                'TimeFromH',
                web.form.Validator('(integer number from 0 to 23)',
                                   lambda x: int(x) >= 0),
                web.form.Validator('(integer number from 0 to 23)',
                                   lambda x: int(x) <= 23),
                size="3",
            ),
            web.form.Textbox(
                'TimeFromM',
                web.form.Validator('(integer number from 0 to 59)',
                                   lambda x: int(x) >= 0),
                web.form.Validator('(integer number from 0 to 59)',
                                   lambda x: int(x) <= 59),
                size="3",
            ),
            web.form.Textbox(
                'TimeToH',
                web.form.Validator('(integer number from 0 to 23)',
                                   lambda x: int(x) >= 0),
                web.form.Validator('(integer number from 0 to 23)',
                                   lambda x: int(x) <= 23),
                size="3",
            ),
            web.form.Textbox(
                'TimeToM',
                web.form.Validator('(integer number from 0 to 59)',
                                   lambda x: int(x) >= 0),
                web.form.Validator('(integer number from 0 to 59)',
                                   lambda x: int(x) <= 59),
                size="3",
            ),
        )

    def GET(self, indexstr):
        frm = self.frm()
        # check if index of required program is valid:
        if indexstr in [str(i) for i in range(len(gv.prg))]:
            index = int(indexstr)
            # set default values of forms to current global values:
            frm.Name.value = gv.prg[index]['Name']
            frm.wlMinDelayH.value = gv.prg[index]['wlMinDelayH']
            frm.wlEmptyDelayH.value = gv.prg[index]['wlEmptyDelayH']
            frm.calwDays1.checked = 1 in gv.prg[index]['calwDays']
            frm.calwDays2.checked = 2 in gv.prg[index]['calwDays']
            frm.calwDays3.checked = 3 in gv.prg[index]['calwDays']
            frm.calwDays4.checked = 4 in gv.prg[index]['calwDays']
            frm.calwDays5.checked = 5 in gv.prg[index]['calwDays']
            frm.calwDays6.checked = 6 in gv.prg[index]['calwDays']
            frm.calwDays7.checked = 7 in gv.prg[index]['calwDays']
            frm.caliIntervalD.value = gv.prg[index]['caliIntervalD']
            frm.calwRepeatH.value = gv.prg[index]['calwRepeatH']
            frm.caliRepeatH.value = gv.prg[index]['caliRepeatH']
            frm.TimeFromH.value = gv.prg[index]['TimeFromH']
            frm.TimeFromM.value = gv.prg[index]['TimeFromM']
            frm.TimeToH.value = gv.prg[index]['TimeToH']
            frm.TimeToM.value = gv.prg[index]['TimeToM']
        else:
            # incorrect program, set to -1, web template will report error:
            index = -1
        return render.changeprogram(gv, frm, index, indexstr)

    def POST(self, indexstr):
        frm = self.frm()
        response = web.input()  # get user response
        if 'submit' in response:
            if indexstr in [str(i) for i in range(len(gv.prg))]:
                index = int(indexstr)
                if not frm.validates():  # if not validated
                    # set default values of forms to user response (so input of
                    # all fields is not lost if one field is not validated)
                    frm.Name.value = response['Name']
                    frm.wlMinDelayH.value = response['wlMinDelayH']
                    frm.wlEmptyDelayH.value = response['wlEmptyDelayH']
                    frm.calwDays1.checked = 'calwDays1' in response
                    frm.calwDays2.checked = 'calwDays2' in response
                    frm.calwDays3.checked = 'calwDays3' in response
                    frm.calwDays4.checked = 'calwDays4' in response
                    frm.calwDays5.checked = 'calwDays5' in response
                    frm.calwDays6.checked = 'calwDays6' in response
                    frm.calwDays7.checked = 'calwDays7' in response
                    frm.caliIntervalD.value = response['caliIntervalD']
                    frm.calwRepeatH.value = response['calwRepeatH']
                    frm.caliRepeatH.value = response['caliRepeatH']
                    frm.TimeFromH.value = response['TimeFromH']
                    frm.TimeFromM.value = response['TimeFromM']
                    frm.TimeToH.value = response['TimeToH']
                    frm.TimeToM.value = response['TimeToM']
                    return render.changeprogram(gv, frm, index, indexstr)
                else:
                # write new values to global variables:
                    p = gv.prg[index]
                    p['Name'] = response['Name']
                    if response['Enabled'] == 'On':
                        p['Enabled'] = True
                    else:
                        p['Enabled'] = False
                    p['Mode'] = response['Mode']
                    if not (p['Mode'] == 'waterlevel'
                            or p['Mode'] == 'weekly'
                            or p['Mode'] == 'interval'):
                        p['Mode'] == 'waterlevel'
                    p['wlMinDelayH'] = float(response['wlMinDelayH'])
                    p['wlEmptyDelayH'] = float(response['wlEmptyDelayH'])
                    # parse weekdays, sort, remove duplicates and save:
                    tmp = []
                    for i in range(1, 8):
                        if 'calwDays' + str(i) in response:
                            tmp.append(i)
                    # sort and remove duplicates:
                    p['calwDays'] = list(set(sorted(tmp)))
                    p['caliIntervalD'] = int(response['caliIntervalD'])
                    p['calwRepeatH'] = float(response['calwRepeatH'])
                    p['caliRepeatH'] = float(response['caliRepeatH'])
                    # set from and to times:
                    p['TimeFromH'] = int(response['TimeFromH'])
                    p['TimeFromM'] = int(response['TimeFromM'])
                    p['TimeToH'] = int(response['TimeToH'])
                    p['TimeToM'] = int(response['TimeToM'])
                    # for calendar interval mode set TimeLastRun for today
                    # minus caliIntervalD:
                    if p['Mode'] == 'interval':
                        t = arrow.now('local')
                        t = t.replace(hour=p['TimeFromH'],
                                      minute=p['TimeFromM'])
                        t = t.floor('minute')
                        t = t.replace(days=-1 * p['caliIntervalD'])
                        p['TimeLastRun'] = t
                    # parse selected stations
                    tmp = []
                    for i in response:
                        if i[0] == 's':
                            try:
                                num = int(i[1:])
                                tmp.append(num)
                            except ValueError:
                                pass
                    # sort and remove duplicates:
                    p['Stations'] = list(set(sorted(tmp)))
                    gv.prg[index] = p
                    # log change:
                    log_add('settings of program ' + str(index)
                            + ' (' + gv.prg[index]['Name'] + ')'
                            + ' was changed by user')
                    # save configuration
                    prg_save()
                    raise web.seeother('/programs')
            else:
                index = -1
            return render.changeprogram(gv, frm, -1,
                                        indexstr, 'waterlevel')
        # if cancel or any unknown response, go to home page:
        raise web.seeother('/programs')


class WebCheckPrograms:  # shows plan of programs for next 2 weeks
    def GET(self):
        # plan from now:
        tstart = arrow.now('local')
        # till next two weeks:
        tmax = tstart.replace(weeks=2)
        lst = []
        for i in range(len(gv.prg)):
            if gv.prg[i]['Enabled'] and gv.prg[i]['Mode'] != 'waterlevel':
                # generate next waterings
                t = tstart
                # to prevent infinite loop:
                cnt = 0
                while t < tmax:
                    # to prevent infinite loop:
                    cnt = cnt + 1
                    if cnt > 1400:
                        raise NameError('Too many waterings in two weeks,' +
                                        ' probably internal error')
                    # get next watering according program mode:
                    if gv.prg[i]['Mode'] == 'weekly':
                        tmp = prg_wee_next_water_time(i, t)
                    elif gv.prg[i]['Mode'] == 'interval':
                        tmp = prg_int_next_water_time(i, t)
                    # create a line of the resulting web table:
                    s = tmp[0].format('YYYY-MM-DD HH:mm:ss ddd') + \
                        ':&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp </td><td>' + \
                        gv.prg[i]['Name']
                    lst.append(s)
                    # add second to move in programs:
                    t = tmp[0].replace(seconds=+1)
        # sort the list (it is year-month-date-time, so sorting of strings
        # gives required result)
        lst.sort()
        # string to embed in web page:
        s = ''
        for i in range(len(lst)):
            # create full html table:
            s = s + '<tr><td>' + lst[i] + '</td></tr>'
        if len(s) == 0:
            s = 'No programs exists, or only water level programs enabled ' + \
                '(these are not shown), or all programs are disabled.'
        return render.checkprograms(s)

    def POST(self):
        raise web.seeother('/programs')


class WebHistory:  # to select history of what
    def GET(self):
        return render.history(gv)

    def POST(self):
        response = web.input()  # get user response
        # XXX check here correct web? not needed really
        return web.seeother('historychart' + response.keys()[0])


class WebHistoryChart:  # chart with history and xaxis change
    def __init__(self):
        self.frm = web.form.Form(  # definitions of all input fields
            web.form.Textbox(
                'xminY',
                web.form.Validator('(integer 0 and greater)',
                                   lambda x: int(x) >= 0),
                size="4",
            ),
            web.form.Textbox(
                'xminM',
                web.form.Validator('(integer 1 to 12)',
                                   lambda x: int(x) >= 1),
                web.form.Validator('(integer 1 to 12)',
                                   lambda x: int(x) <= 12),
                size="2",
            ),
            web.form.Textbox(
                'xminD',
                web.form.Validator('(integer 1 to 31)',
                                   lambda x: int(x) >= 1),
                web.form.Validator('(integer 0 and greater)',
                                   lambda x: int(x) <= 31),
                size="2",
            ),
            web.form.Textbox(
                'xminH',
                web.form.Validator('(real number from 0 to 23.99)',
                                   lambda x: float(x) >= 0),
                web.form.Validator('(real number from 0 to 23.99)',
                                   lambda x: float(x) < 24),
                size="5",
            ),
            web.form.Textbox(
                'xmaxY',
                web.form.Validator('(integer 0 and greater)',
                                   lambda x: int(x) >= 0),
                size="4",
            ),
            web.form.Textbox(
                'xmaxM',
                web.form.Validator('(integer 1 to 12)',
                                   lambda x: int(x) >= 1),
                web.form.Validator('(integer 1 to 12)',
                                   lambda x: int(x) <= 12),
                size="2",
            ),
            web.form.Textbox(
                'xmaxD',
                web.form.Validator('(integer 1 to 31)',
                                   lambda x: int(x) >= 1),
                web.form.Validator('(integer 0 and greater)',
                                   lambda x: int(x) <= 31),
                size="2",
            ),
            web.form.Textbox(
                'xmaxH',
                web.form.Validator('(real number from 0 to 23.99)',
                                   lambda x: float(x) >= 0),
                web.form.Validator('(real number from 0 to 23.99)',
                                   lambda x: float(x) < 24),
                size="5",
            ),
        )

    def GET(self, dname):
        frm = self.frm()
        # check if required web address is valid
        if not check_data_name(dname):
            # incorrect webpage, go to home page:
            # XXX should generate error? and changestation? and changeprogram?
            # one of these does!
            raise web.seeother('/')
        # set form values:
        frm.xminY.value = gv.cv['xMin'].year
        frm.xminM.value = gv.cv['xMin'].month
        frm.xminD.value = gv.cv['xMin'].day
        frm.xminH.value = gv.cv['xMin'].hour + gv.cv['xMin'].minute / 60 + \
            gv.cv['xMin'].second / 3600
        frm.xmaxY.value = gv.cv['xMax'].year
        frm.xmaxM.value = gv.cv['xMax'].month
        frm.xmaxD.value = gv.cv['xMax'].day
        frm.xmaxH.value = gv.cv['xMax'].hour + gv.cv['xMax'].minute / 60 + \
            gv.cv['xMax'].second / 3600
        # get chart:
        chartstr = make_chart(dname, gv.cv['xConstrain'],
                              gv.cv['xMin'], gv.cv['xMax'])
        # render web page:
        return render.historychart(frm, chartstr)

    def POST(self, dname):
        frm = self.frm()
        response = web.input()  # get user response
        if 'setminmax' in response:
            gv.cv['xConstrain'] = True
            # set default values of forms to user response
            frm.xminY.value = response['xminY']
            frm.xminM.value = response['xminM']
            frm.xminD.value = response['xminD']
            frm.xminH.value = response['xminH']
            frm.xmaxY.value = response['xmaxY']
            frm.xmaxM.value = response['xmaxM']
            frm.xmaxD.value = response['xmaxD']
            frm.xmaxH.value = response['xmaxH']
            if not frm.validates():  # if not validated
                return render.historychart(frm, 'Incorrect input')
            else:
                # calculate xmin and xmax as arrow time
                minutes = float(frm.xminH.value) % 1 % 60
                seconds = minutes % 1 % 60
                gv.cv['xMin'] = arrow.Arrow(int(frm.xminY.value),
                                            int(frm.xminM.value),
                                            int(frm.xminD.value),
                                            int(frm.xminH.value),
                                            int(minutes),
                                            int(seconds)
                                            )
                minutes = float(frm.xmaxH.value) % 1 % 60
                seconds = minutes % 1 % 60
                gv.cv['xMax'] = arrow.Arrow(int(frm.xmaxY.value),
                                            int(frm.xmaxM.value),
                                            int(frm.xmaxD.value),
                                            int(frm.xmaxH.value),
                                            int(minutes),
                                            int(seconds)
                                            )
        else:
            if 'back' in response:
                raise web.seeother('history')
            elif 'last2days' in response:
                gv.cv['xConstrain'] = True
                gv.cv['xMax'] = arrow.now('local')
                gv.cv['xMin'] = gv.cv['xMax'].replace(days=-2)
            elif 'last2weeks' in response:
                gv.cv['xConstrain'] = True
                gv.cv['xMax'] = arrow.now('local')
                gv.cv['xMin'] = gv.cv['xMax'].replace(days=-14)
            elif 'fullrange' in response:
                gv.cv['xConstrain'] = False
                # if any unknown response, go to history page:
            else:
                raise NameError('Error - unknown response in history ' +
                                'chart page')
                raise web.seeother('/history')
            frm.xminY.value = gv.cv['xMin'].year
            frm.xminM.value = gv.cv['xMin'].month
            frm.xminD.value = gv.cv['xMin'].day
            frm.xminH.value = gv.cv['xMin'].hour + \
                gv.cv['xMin'].minute / 60 + \
                gv.cv['xMin'].second / 3600
            frm.xmaxY.value = gv.cv['xMax'].year
            frm.xmaxM.value = gv.cv['xMax'].month
            frm.xmaxD.value = gv.cv['xMax'].day
            frm.xmaxH.value = gv.cv['xMax'].hour + \
                gv.cv['xMax'].minute / 60 + \
                gv.cv['xMax'].second / 3600
        # get chart:
        chartstr = make_chart(dname, gv.cv['xConstrain'],
                              gv.cv['xMin'], gv.cv['xMax'])
        # render web page:
        return render.historychart(frm, chartstr)


# ------------------- code run in both threads:
# list of web pages:
urls = (
    '/', 'WebHome',
    '/options', 'WebOptions',
    '/reboot', 'WebReboot',
    '/log', 'WebLog',
    '/history', 'WebHistory',
    '/historychart(.*)', 'WebHistoryChart',
    '/stations', 'WebStations',
    '/changestation(.*)', 'WebChangeStation',
    '/programs', 'WebPrograms',
    '/checkprograms', 'WebCheckPrograms',
    '/changeprogram(.*)', 'WebChangeProgram',
)

if __name__ == "__main__":
    # ------------------- code run only in main thread:
    # start signal catching:
    signal.signal(signal.SIGTERM, sigterm_handler)
    # initialize basic global values:
    gv.configdir = "config"
    gv.datadir = "data"
    gv.gsfilepath = gv.configdir + "/sd.pkl"
    gv.hwsfilepath = gv.configdir + "/hws.pkl"
    gv.prgfilepath = gv.configdir + "/prg.pkl"
    gv.logfilepath = gv.configdir + "/log.txt"
    gv.logbuffer = []
    gv.flags = []
    # set last update of RTC to history, so update will be run after every
    # start of yawspi:
    gv.lastRTCupdate = arrow.get(2001, 1, 1)
    # load system configuration:
    gs_load()
    # cannot add log line before knowing logging is enabled, and this settings
    # was loaded by gs_load():
    log_add('<b>starting</b>')
    # initialize hw:
    # maybe do not put hw to gv.hw and ensure web server cannot touch
    # hardware... # XXX
    gv.hw = YawspiHW()
    # check time
    check_and_set_time()
    if gv.hw.WithHW != 1:
            # not running on RPi, simulation mode set
            tmp = 'no GPIO module was loaded, running in no-hardware mode'
            print tmp
            log_add(tmp)
    # load hardware settings:
    hws_load()
    # load programs:
    prg_load()

    # initialize dictionary with current values:
    init_cv()
    gv.cv['CurAct'] = 'initializing'

    # web server initialization:
    # XXX debug mode
    web.config.debug = 1
    app = web.application(urls, globals())
    # run web server in separate thread:
    thread.start_new_thread(app.run, ())

    # -------------------------------- main program loop
    try:
        # generate time of next loop iteration
        loopendtime = arrow.now('local')
        loopendtime = loopendtime.replace(seconds=+gv.gs['MLInterval'])
        loopendtime = loopendtime.floor('second')
        while True:
            # generate values for web:
            # measure water levels:
            sensors_get_all()
            # if web thread asked for break, do it:

            # watering
            if gv.gs['Enabled']:
                # check progs if watering should start:
                for i in range(len(gv.prg)):
                    if prg_is_water_time(i):
                        # if program should water now, do it:
                        prg_water(i)
            # check RTC time
            check_and_set_time()
            # dump log buffer into a file
            log_save()

            # wait for next loop iteration
            # (time.sleep(60) is not good because catching KeyboardInterrupt
            # exception (end from web thread) would take up to 60 seconds)
            while arrow.now('local') < loopendtime:
                gv.cv['CurAct'] = 'waiting for next main loop iteration in ' \
                                  + loopendtime.isoformat()
                # if some flag from webserver:
                # if web thread asked for break, do it:
                if 'askforbreak' in gv.flags:
                    gv.flags.remove('askforbreak')
                    break
                # if web thread asked for watering of station:
                for i in range(gv.hw.StNo):
                    flag = 'askforrun' + str(i)
                    if flag in gv.flags:
                        # water now!
                        station_fill(i)
                        gv.flags.remove(flag)
                sleep(1)
            # generate next loopend time, and it will be multiple of MLInterval
            # from last time. This prevents that a loop takes MLInterval +
            # watering time (which can take loooong)
            if arrow.now('local') >= loopendtime:
                # this happens only if waiting for next iteration was not
                # broken by web:
                loopendtime = loopendtime.replace(seconds=+gv.gs['MLInterval'])
                loopendtime = loopendtime.floor('second')
                # ensure loopendtime is not in the past, some watering can take
                # loooong time:
                while loopendtime < arrow.now('local'):
                    loopendtime = loopendtime.replace(
                        seconds=+gv.gs['MLInterval']
                    )
    except KeyboardInterrupt:
        # keyboard interrupt or reboot pressed in webserver
        # (system is rebooted when called from web page, but not when python is
        # run from command line and Ctrl+c is pressed)
        # perform safe quit:
        quit('reboot in webserver or keyboard interrupt')
    except SystemExit:
        # got kill signal
        # perform safe quit:
        quit('got signal kill')
    except:
        # something strange happened
        # perform safe quit:
        quit('unknown reason')
        # and raise error again to show error in console:
        raise
    # and that's all folks!
else:
    # ------------------- code run only in web thread:
    # render of templates:
    # (this runs webserver)
    render = web.template.render('templates/')
