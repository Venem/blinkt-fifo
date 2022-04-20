#!/usr/bin/env python3
from inotify_simple import INotify, flags
from colorsys import hsv_to_rgb
from datetime import datetime
from time import time, sleep
from os import stat, path, mknod, chmod
from subprocess import Popen, DEVNULL
from sys import argv
import threading
import blinkt

### MEGA TODOs:
## TODO 1:
# read a configuration file for options and set all variables from that
# user should not even have to touch this file - just "make install",
# "systemctl enable --now blinkt-fifo.service", any additional configuration
# for any light modules and that's it

## PLEASE READ
# for a FIFO system, where all light commands are stored in a queue, use
# echo "" >> /etc/blinkt.fifo
# which appends it to the end of the file

# please abstain from using
# echo "" > /etc/blinkt.fifo
# since the single bracket overwrites the whole file and commands in the queue
# may be skipped

# for a FILO system, in which newer commands are prioritised over older, use
# echo "" >>/etc/blinkt.fifo
# which appends to the top of the file (note the lack of space after the angled
# brackets)

## TODO 2:
# do cron inside python to minimalise files edited by end user - should be
# configurable inside file (thus TODO 1 must be implemented first)


# clear lights if --stop arg is passed
# useful in systemd module
if len(argv) > 1 and argv[1] == "--stop":
    blinkt.clear()
    blinkt.show()
    exit()


## TODO: read these options from a configuration file
# set some flags and instantiate lists/variables
isNight = False
lastopen = 0
brightness = [0.0] * blinkt.NUM_PIXELS

# programs to start (initially used a script called blinkt-init but deprecated
# in favour of the ability to build everything into main script)
# the empty values are for further configuration - notice that there are 8 in total,
# one for each light and the position in the list corresponds to the location of
# that light
# eventually, this will be set through the configuration file, which will have a section
# for "reserving" certain lights for more complicated modules like blinkt-pihole
# hopefully, it will detect that the light is in use by blinkt-pihole since I aim to use
# the same file for configuration - this will also make it easier to add custom modules
modules = ["", "/usr/bin/blinkt-weather", "", "", "", "", "/usr/bin/blinkt-www https://manoila.co.uk", "/usr/bin/blinkt-cpu"]

# defaultBrightness is used when an invalid brightness is passed
defaultBrightness = 0.5

# time in hours when lights are stopped and started
timeStopLights = 22
timeStartLights = 7

# disable night-time by toggling this
alwaysOn = False

# interval on which to check if it is night (in minutes)
nightCheckInterval = 5

# location of the file
fifo = "/etc/blinkt.fifo"


# create fifo
if not path.exists(fifo):
    mknod(fifo)
    chmod(fifo, 0o0666)

# set up inotify watcher on fifo file
inotify = INotify()
watch_flags = flags.MODIFY
wd = inotify.add_watch(fifo, watch_flags)


# startup sequence
def rainbow():
    for i in range(100, 0, -1):
        spacing = 360.0 / 16.0
        hue = 0
        hue = int(time() * 100) % 360
        for x in range(blinkt.NUM_PIXELS):
            offset = x * spacing
            h = ((hue + offset) % 360) / 360.0
            r, g, b = [int(c * 255) for c in hsv_to_rgb(h, 1.0, 1.0)]
            blinkt.set_pixel(x, r, g, b, i/100)
        blinkt.show()
    blinkt.clear()

# function that actually sets the leds
def setLeds():
    global isNight, lastopen
    # stupid fix for inotify detecting file changes when not supposed to (see where function is called)
    timeSinceOpen = stat(fifo).st_mtime 
    if timeSinceOpen == lastopen:
        return
    lastopen = timeSinceOpen
    try:
        # uses FIFO-based logic - the file is an instruction queue
        with open(fifo, "r+") as f:
            colours = f.readline().strip().split(" ")
            wholefile = f.read()

            # remove first line of file
            f.seek(0)
            f.write(wholefile)
            f.truncate()

            # TODO: use defaultBrightness if invalid float is detected

            # if it is day, set colours accordingly
            if not isNight:
                blinkt.set_pixel(int(colours[0]), int(colours[1]), int(colours[2]), int(colours[3]), float(colours[4]))
            # if it is night, set colours but with 0 brightness so that they can be shown
            # later and store the brightness in a list
            else:
                blinkt.set_pixel(int(colours[0]), int(colours[1]), int(colours[2]), int(colours[3]), 0)
                brightness[int(colours[0])] = float(colours[4])
            blinkt.show()
            # end of function
    # catching exception is more efficient than validating each colour's data type
    except ValueError:
        return
        # end of function

def checkNight():
    global isNight
    while True:
        hour = datetime.now().hour
        # when time approaches night, set isNight to True, lower brightness
        if (hour >= timeStopLights or hour < timeStartLights) and not isNight:
            isNight = True
            # save brightness in list
            for x in range(blinkt.NUM_PIXELS):
                brightness[x] = blinkt.get_pixel(x)[3]
            blinkt.set_brightness(0)
            blinkt.show()
            # wait for an hour to stop if statement from triggering again
            sleep(3600)
        # when time approaches day, set isNight to False, restore brightness to the values in the list
        elif (hour >= timeStartLights and hour < timeStopLights) and isNight:
            isNight = False
            for x in range(blinkt.NUM_PIXELS):
                curPixel = blinkt.get_pixel(x)
                r = curPixel[0]
                g = curPixel[1]
                b = curPixel[2]
                # no need for a fallback default brightness
                blinkt.set_pixel(x, r, g, b, brightness[x])
            # wait for an hour to stop if statement from triggering again
            blinkt.show()
            sleep(3600)
        sleep(nightCheckInterval*60)


# start timing script on its own thread
if not alwaysOn:
    nightMonitorThread = threading.Thread(target=checkNight)
    nightMonitorThread.start()

# startup sequence
if not (len(argv) > 1 and argv[1] == "--no-rainbow"):
    rainbow()

# clean out any that may have accumulated while script was not running
for i in range(25):
    setLeds()

# start modules and pass location in list through (this is the light that it will manage)
# <module> <light> <fifo>
for modIndex in range(len(modules)):
    if not modules[modIndex] == "":
#        Popen([modules[modIndex], str(modIndex), fifo], stdout=DEVNULL, stderr=DEVNULL)
        Popen(modules[modIndex].split() + [str(modIndex), fifo])

while True:
    # inotify is overengineered for this job. It detects file changes even when
    # setLeds() is running and the inotify.read() is not which unfortunately leads
    # to an endless loop of led-setting even when the file isn't changed.
    inotify.read()
    setLeds()
