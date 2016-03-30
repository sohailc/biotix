import time
import os
import h5py
import numpy
import copy
import os

errorLevels = ["info", "warning", "error"]

errStyleSheet = """
error {
    font-weight:bold;
    color: red;
}

warning {
    font-weight:bold;
    color: orange;
}

info {
    font-weight:bold;
    color: green;
}
"""

htmlHeader = """
<!DOCTYPE html>
<html>
<head>
<title>Vitriolix Log File</title>
</head>
<body>
<link rel=\"stylesheet\" type=\"text/css\" href=\"error.css\"/>
"""


def logPrintMessages(messageText, logFile):
    path = os.path.dirname(logFile)

    if not os.path.exists(path):
        os.mkdir(path)

    errStyleSheetFileName = os.path.join(path, "error.css")

    if not os.path.exists(errStyleSheetFileName):
        fh = open(errStyleSheetFileName, "w")
        fh.write(errStyleSheet)
        fh.close()

    if not os.path.exists(logFile):
        fh = open(logFile, "w")
        fh.write(htmlHeader)
    else:
        fh = open(logFile, "a")

    timeStamp = time.strftime("%Y%m%d-%H%M%S")

    for errorLevel in errorLevels:
        messageText = messageText.replace(errorLevel, "<{errorLevel}>{errorLevel}</{errorLevel}>".format(
            errorLevel=errorLevel))

    toWrite = "{timeStamp}: {messageText}<br> \n".format(timeStamp=timeStamp, messageText=messageText)

    fh.write(toWrite)
    fh.close()

    return


class dataLogger(object):
    def __init__(self, logFileName, systemState, logKeys, maxLogLinesPerSet=10000):

        self.systemState = systemState
        self.logKeys = logKeys

        # Each data set in our HDF5 file will have a time stamp. We want each data set to contain at most
        # maxLogLinesPerSet lines
        self.maxLogLinesPerSet = maxLogLinesPerSet

        # We will not continuously write data to the HDF5 file, but write to a buffer first instead
        self.dataBuffer = dict()
        # initialise the buffer
        for k in self.logKeys:
            self.dataBuffer[k] = []

        self.maxLogLinesInBuffer = 5
        self.linesWritten = 0  # Every time when linesWritten % maxLogLinesInBuffer == 0, the buffer is reset
        # And every time linesWritten == maxLogLinesPerSet, a new set is made with the current time stamp.
        # self.linesWritten is then reset to zero

        self.logFileName = logFileName

        self.logFile = None
        self.logData = None

    def _findMostRecentLogData(self):

        mostRecentDateStamp = 0
        mostRecentDateString = ""

        for dateString in self.logFile:

            try:
                dateStruct = time.strptime(dateString, "%Y%m%d-%H%M%S")
            except ValueError:
                continue

            dateStamp = time.mktime(dateStruct)

            if dateStamp > mostRecentDateStamp:
                mostRecentDateStamp = dateStamp
                mostRecentDateString = dateString

        if mostRecentDateString == "":
            return self._makeNewDataSet()
        else:
            return self.logFile[mostRecentDateString]

    def _makeNewDataSet(self):

        dateStringNow = time.strftime("%Y%m%d-%H%M%S")

        for k in self.logKeys:
            logDataPath = "{}/{}".format(dateStringNow, k)
            self.logFile.create_dataset(logDataPath, (0, 1), maxshape=(None, 1), dtype=numpy.float64)

        return self.logFile[dateStringNow]

    def _writeBufferToFile(self):

        self.logFile = h5py.File(self.logFileName, "a")
        self.logData = self._findMostRecentLogData()

        if self.linesWritten >= self.maxLogLinesPerSet:
            self.logData = self._makeNewDataSet()
            self.linesWritten = 0

        for k in self.logKeys:
            m = self.logData[k].shape[0]
            self.logData[k].resize(m + len(self.dataBuffer[k]), axis=0)
            self.logData[k][m:, 0] = numpy.array(self.dataBuffer[k])
            self.dataBuffer[k] = []

        self.logFile.close()
        self.logFile = None
        self.logData = None

    def _getValueFromSystemStateGivenKey(self, key):

        # e.g. key can be "DAQINPUT.Pressure/currentValue". Get the value systemState[DAQINPUT.Pressure][currentValue]
        dictTmp = self.systemState

        for k in key.split("/"):

            if k not in dictTmp.keys():
                return None

            dictTmp = dictTmp[k]

            if type(dictTmp) != dict:
                break

        return dictTmp

    def doLog(self, additionalKeys=None):

        if not additionalKeys:
            additionalKeys = dict()

        if self.linesWritten % self.maxLogLinesInBuffer == 0 and self.linesWritten:
            self._writeBufferToFile()  # will also reset the buffer

        for k in self.logKeys:

            if k in additionalKeys:
                value = additionalKeys[k]
            else:
                value = eval(self.logKeys[k])  # self._getValueFromSystemStateGivenKey(self.logKeys[k])

            self.dataBuffer[k].append(value)

        self.linesWritten += 1

    def getLogData(self):

        self.logFile = h5py.File(self.logFileName, "a")
        self.logData = self._findMostRecentLogData()

        logDataCopy = dict()

        for k in self.logData:
            logDataCopy[k] = numpy.array(self.logData[k])

        self.logFile.close()
        self.logFile = None
        self.logData = None

        return logDataCopy

    def setAttrs(self, key, value):

        if self.logFile == None:
            self.logFile = h5py.File(self.logFileName, "a")
            self.logFile.attrs[key] = value
            self.logFile.close()
            self.logFile = None
        else:
            self.logFile.attrs[key] = value

    def close(self):
        self._writeBufferToFile()
