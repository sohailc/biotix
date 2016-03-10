import time
import multiprocessing
import comedi
import re
import math

import warnings

dataAcquisitionRefreshTime = 0.1  # [s]

def fxn():
    warnings.warn("deprecated", DeprecationWarning)

def convertDAQVoltageToSIAndVV(deviceInfo, value, deviceType):

    if "D" in deviceInfo["CHANNEL"]:
        return value

    params = deviceInfo["PARAMS"]

    if deviceInfo["METHOD"] == "LINEAR":

        return sum([p * value ** i for i, p in enumerate(params)])

    elif deviceInfo["METHOD"] == "LOG":

        if deviceType == "OUTPUT":
            return (math.log(value / params[0]) - params[2]) / params[1]
        elif deviceType == "INPUT":
            return params[0] * 10**(params[1] * value + params[2])

class NationalInstrumentsDevice:
    def __init__(self, biotixProgram):

        self.systemState = biotixProgram.systemState
        self.logFile = biotixProgram.logFile
        connector = self.systemState["NIDAQConnector"]
        nationalInstrumentsDevice = self.systemState["NIDAQDevice"]
        self.GUI = None
        self.device = comedi.comedi_open(nationalInstrumentsDevice)

        self.initError = "OK"

        if not self.device:
            comedi.comedi_perror("comedi_open")
            self.initError = "NOK: Unable to open DAQ device"

        if self.initError == "OK":
            self.nConnectors = 2
            self.connector = connector
            self.devrange = 0
            self.aref = comedi.AREF_GROUND

            self.outputDeviceNames = [name for name in self.systemState.keys() if "DAQOUTPUT" in name]
            self.inputDeviceNames = [name for name in self.systemState.keys() if "DAQINPUT" in name]

            for deviceName in self.outputDeviceNames:
                self.setOutput("%s=0" % deviceName)

    def _setAO(self, channel, voltage):

        if isinstance(channel, str):
            if len(channel) == 2:
                channel = int(channel[1])

        if voltage < -10.0 or voltage > 10.0:
            return "error: Set AO: value %.3f V out of range" % voltage

        subDevice = comedi.comedi_find_subdevice_by_type(self.device,comedi.COMEDI_SUBD_AO, 0)
        cr = comedi.comedi_get_range(self.device, subDevice, channel, 0)
        maxData = comedi.comedi_get_maxdata(self.device, subDevice, channel)
        value = comedi.comedi_from_phys(voltage, cr, maxData)

        nChannels = comedi.comedi_get_n_channels(self.device, subDevice)
        nChannelPerConnector = nChannels/self.nConnectors

        channelStr = str(channel)
        channel += nChannelPerConnector*self.connector

        if channel > nChannels:
            print "error: %s invalid analog output channel"%channelStr
            return 0

        comedi.comedi_data_write(self.device,
                                 subDevice,
                                 channel,
                                 self.devrange,
                                 self.aref,
                                 value)

    def _getAI(self, channel):

        if isinstance(channel, str):
            if len(channel) == 2:
                channel = int(channel[1])

        subDevice = comedi.comedi_find_subdevice_by_type(self.device,comedi.COMEDI_SUBD_AI, 0)

        nChannels = comedi.comedi_get_n_channels(self.device, subDevice)
        nChannelPerConnector = nChannels/self.nConnectors

        channelStr = str(channel)
        channel += nChannelPerConnector*self.connector

        if channel > nChannels:
            print "error: %s invalid analog input channel"%channelStr
            return 0

        readResult = comedi.comedi_data_read(self.device,
                                             subDevice,
                                             channel,
                                             self.devrange,
                                             self.aref)

        cr = comedi.comedi_get_range(self.device, subDevice, channel, 0)
        maxData = comedi.comedi_get_maxdata(self.device, subDevice, channel)
        raw = readResult[1]
        voltage = comedi.comedi_to_phys(raw, cr, maxData)

        return voltage

    def _setDO(self, channel, value):

        if isinstance(channel, str):
            if len(channel) == 2:
                channel = int(channel[1])

        if not value in [0, 1]:
            print "error: value must be either 0 or 1 for digital IO"
            return 0

        subDevice = comedi.comedi_find_subdevice_by_type(self.device,comedi.COMEDI_SUBD_DIO, 0)
        nChannels = comedi.comedi_get_n_channels(self.device, subDevice)

        if not channel in range(nChannels):
            print "error: channel must be between 0 and ", nChannels
            return 0

        nChannelPerConnector = nChannels/(2*self.nConnectors)

        comedi.comedi_dio_config(self.device,
                                 subDevice,
                                 channel+ nChannelPerConnector*self.connector,
                                 comedi.COMEDI_OUTPUT)

        comedi.comedi_dio_write(self.device,
                                subDevice,
                                channel+ nChannelPerConnector*self.connector,
                                value)

    def _translate(self, message):

        # For example, translate the message "HV=-1000" to "ni.setAO(0,value)"
        # where value is the value to put on the DAQ output to achieve -1000 V
        # from the FUG

        translatedMessage = ""
        err = ""
        deviceName = ""
        value = 0

        for _ in [1]:

            m = re.search("(.*)=(.*)", message)

            if not m:
                err = "Message %s not understood" % message
                break

            deviceName = m.groups()[0]
            value = m.groups()[1]


            if not deviceName in self.outputDeviceNames:
                err = "Message %s not understood" % message
                break

            device = self.systemState[deviceName]

            if "A" in device["CHANNEL"]:
                setFunction = self._setAO
                tp = float
            else:
                setFunction = self._setDO
                tp = int

            try:
                value = tp(value)
            except:
                err = "Cannot convert %s to type %s" % (value, tp)
                break

            err = "OK"

            translatedMessage = (setFunction, [device["CHANNEL"],
                                               convertDAQVoltageToSIAndVV(device, value, "OUTPUT")])

        return err, translatedMessage, deviceName, value

    def setOutput(self, message):

        err, translatedMessage, deviceName, value = self._translate(message)

        if err == "OK":
            setFunction, args = translatedMessage
            setFunction(*args)
            d = self.systemState[deviceName]
            d["currentValue"] = value
            self.systemState[deviceName] = d

    def updateSystemState(self):

        for device in self.inputDeviceNames:

            channel = self.systemState[device]["CHANNEL"]
            voltage = self._getAI(channel)
            SIValue = convertDAQVoltageToSIAndVV(self.systemState[device], voltage, "INPUT")

            d = self.systemState[device]
            d["currentValue"] = SIValue
            self.systemState[device] = d
            self.systemState["time"] = {"currentValue": time.time(), "UNIT": "unix time"}


class DAQServer():

    def __init__(self, biotixProgram):

        self.DAQRequestQueue = multiprocessing.Queue()
        self.parentQuitConnection, self.childQuitConnection = multiprocessing.Pipe()

        self.DAQServerProc = multiprocessing.Process(target=self._server, args=(self.DAQRequestQueue,))
        self.DAQServerProc.deamon = True

        self.ni = NationalInstrumentsDevice(biotixProgram)
        self.initError = self.ni.initError
        self.GUI = None

    def connectToGUI(self, GUI):
        self.GUI = GUI

    def start(self):
        self.DAQServerProc.start()
        time.sleep(2.0)  # wait for everything to start

        if not self.GUI:
            print "warning: Starting DAQ server without real time monitoring"
            return

        plots = {"Pressure":        {"plotType": ["semiLogY"],
                                     "xDataSource": "time" ,
                                     "yDataSource":"self.systemState[\"DAQINPUT.Pressure\"]"},
                 "HV":              {"plotType": [],
                                     "xDataSource": "time",
                                     "yDataSource": "self.systemState[\"DAQINPUT.HV\"]"},
                 "HV current":      {"plotType": [],
                                     "xDataSource": "time",
                                     "yDataSource": "self.systemState[\"DAQINPUT.HVCurrent\"]"},
                 "nano ampere":     {"plotType": [],
                                     "xDataSource": "time",
                                     "yDataSource": "self.systemState[\"DAQINPUT.NanoAmp\"]"}}

        self.GUI.addRealTimePlot(plots)

    def stop(self):
        self.parentQuitConnection.send("quit")
        self.DAQServerProc.join()

    def sendRequest(self, request):
        self.DAQRequestQueue.put(request)

    def _server(self, requestQueue):

        tb = time.time()

        while True:

            time.sleep(0.01)  # prevent this loop from hogging the CPU

            if self.childQuitConnection.poll():
                print "info: Stopping DAQ server"
                break

            if time.time() - tb > dataAcquisitionRefreshTime:

                while requestQueue.qsize():
                    request = requestQueue.get()
                    self.ni.setOutput(request)

                self.ni.updateSystemState()

                tb = time.time()
        return

