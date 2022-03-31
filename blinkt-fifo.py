#!/usr/bin/env python3
from inotify_simple import INotify, flags
from colorsys import hsv_to_rgb
from datetime import datetime
from time import time, sleep
import threading
import blinkt

isNight = False
brightness = [0.0] * blinkt.NUM_PIXELS

inotify = INotify()
watch_flags = flags.MODIFY
wd = inotify.add_watch('/etc/ledctrl', watch_flags)

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

def setLeds():
    global isNight
    try:
        # uses FIFO-based logic - the file is an instruction queue
        with open("/etc/ledctrl", "r+") as f:
            colours = f.readline().strip().split(" ")
            wholefile = f.read()

            # remove first line of file
            f.seek(0)
            f.write(wholefile)
            f.truncate()

            # if it is day, set colours accordingly
            # if it is night, set colours but with 0 brightness
            # so that they can be reshown later
            if not isNight:
                blinkt.set_pixel(int(colours[0]), int(colours[1]), int(colours[2]), int(colours[3]), float(colours[4]))
            else:
                blinkt.set_pixel(int(colours[0]), int(colours[1]), int(colours[2]), int(colours[3]), 0)
            blinkt.show()
    except ValueError:
        return

def checkNight():
    global isNight
    while True:
        hour = datetime.now().hour
        # when time is 10pm, set isNight to True, lower brightness and sleep for 1 hour
        # this makes sure that this code only runs once
        if hour == 22:
            isNight = True
            # save brightness in list
            for x in range(blinkt.NUM_PIXELS):
                brightness[x] = blinkt.get_pixel(x)[3]
            blinkt.set_brightness(0)
            sleep(3600)
        # when time is 7am, set isNight to False, restore brightness to default and sleep for 1 hour
        elif hour == 7:
            isNight = False
            for x in range(blinkt.NUM_PIXELS):
                curPixel = blinkt.get_pixel(x)
                r = curPixel[0]
                g = curPixel[1]
                b = curPixel[2]
                blinkt.set_pixel(x, r, g, b, brightness[x])
            sleep(3600)
        sleep(5*60)

nightMonitorThread = threading.Thread(target=checkNight)
nightMonitorThread.start()

rainbow()
while True:
    inotify.read()
    setLeds()
