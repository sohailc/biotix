import serial
import os
import time


class Arduino(object):
    def __init__(self, deviceString="", baud=9600):

        self.initError = False

        if deviceString == "":
            self.device = self._findDevice(baud)
        else:
            self.device = serial.Serial(deviceString, baud, timeout=1)

        if self.device is None:
            self.initError = True

    def _findDevice(self, baud):

        port_list = [i for i in os.listdir("/dev/") if "ttyACM" in i]

        device = None
        found = False
        for port in port_list:

            port = os.path.join("/dev/", port)

            device = serial.Serial(port, baud, timeout=1)
            response = ""

            for _ in range(10):

                device.write("n")
                response = device.readline().strip()

                if response != "":
                    break

            if "Arduino Uno" in response:
                found = True
                break

        if device is None:
            return None

        if not found:
            device.close()
            return None
        else:
            return device

    def read(self):

        self.device.write("r")

        d1 = self.device.readline().strip().split(",")
        numbers1 = [int(i) for i in d1 if i != '']

        d2 = self.device.readline().strip().split(",")
        numbers2 = [int(i) for i in d2 if i != '']

        return numbers1, numbers2

    def close(self):
        self.device.close()
