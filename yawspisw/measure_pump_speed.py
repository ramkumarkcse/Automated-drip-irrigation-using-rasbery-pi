#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# vim modeline: vim: shiftwidth=4 tabstop=4
#
# scritp calculates pumping speed of the source and returns polynomial values
# for yawpi_hw_config.py
#
# you need a measuring glass (ideally of 1 l volume with marks per 0.2 l, if
# not good, change vols list) and source full of water. you will be prompted to
# get ready to fill specified volume. press enter when ready, wait till the
# measuring glass shows the specified volume and pres enter again. empty
# measuring glass. repeat. when finished, copy results to the
# yawpi_hw_config.py

import arrow
import numpy as np
from yawpi_hw_control import yawpihw

h = yawpihw()
vols = [0.2, 0.4, 0.6, 0.8, 1]
times = []
for v in vols:
    print '---------------------------------'
    print 'prepare to fill ' + str(v) + ' l'
    raw_input('press enter when ready')
    print 'Filling ' + str(v) + ' l ...'
    h.st_switch(0, 1)
    h.so_switch(1)
    start = arrow.now('local')
    raw_input('press enter when finished')
    h.so_switch(0)
    h.st_switch(0, 0)
    end = arrow.now('local')
    times.append((end - start).total_seconds())
    print 'total time to fill ' + str(v) + ' l was ' + str(times[-1])

timvec = np.array(times)
volvec = np.array(vols)
# fit model: volume = offset + rate1 * time + rate2 * time
p = np.polyfit(timvec, volvec, 2)
# fit model: time = offset + rate1 * volume + rate2 * volume
pr = np.polyfit(volvec, timvec, 2)
print '================================='
print 'fit to get liters per second:'
print 'slope is: ' + str(p[2])
print 'rate1 is: ' + str(p[1])
print 'rate2 is: ' + str(p[0])
print '---------------------------------'
print 'fit to get seconds for liter'
print 'slope is: ' + str(pr[2])
print 'rate1 is: ' + str(pr[1])
print 'rate2 is: ' + str(pr[0])
print '---------------------------------'
print 'the yawpi_hw_config.py should contain the following lines:'
print '\'FlowRate\': (' + str(p[2]) + ', ' + str(p[1]) + ', ' + str(p[0]) + '),'
print '\'FlowRateRev\': (' + str(pr[2]) + ', ' + str(pr[1]) + ', ' + str(pr[0]) + '),'
print 'as part of the following list (add after such line):'
print 'tmp[\'So\'] = {'
