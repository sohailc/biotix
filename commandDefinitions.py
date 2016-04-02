import time
import os
import traceback


class MeasurixCommand(object):
    def __init__(self, args, messageQueue, measurixProgram, recipeInfo, childConnection=None):

        import multiprocessing

        self.args = args
        self.name = self.__class__.__name__

        if not childConnection:
            self.parentConnection, self.childConnection = multiprocessing.Pipe()
        else:  # This happens if the Measurix command is called from another Measurix command.
            self.childConnection = childConnection
            self.parentConnection = None

        self.proc = multiprocessing.Process(target=self.protectedWorker)
        self.sendMessageQueue = messageQueue

        self.measurixProgram = measurixProgram
        self.systemState = measurixProgram.systemState
        self.GUI = measurixProgram.GUI

        if "outputDir" in recipeInfo.keys():
            self.outputDirectory = recipeInfo["outputDir"]

        self.recipeInfo = recipeInfo
        self.stopMessageReceived = False

    def protectedWorker(self):

        try:

            if self.name.startswith("startProcess"):
                self.sendMessage({"type": "continue", "PID": os.getpid()})

            self.worker()
            self.sendMessage({"type": "done", "PID": os.getpid()})

        except Exception, e:
            self.sendMessage({"type": "exception", "PID": os.getpid(), "exception": e})

            timeStamp = time.strftime("%Y%m%d-%H%M%S")
            crashLog = self.systemState["crashLog"].format(timeStamp=timeStamp)

            with open(crashLog, "w") as fh:
                traceback.print_exc(None, fh)

    def worker(self):
        pass  # we implement this in inheriting classes

    def checker(self, noHardwareCheck=False):

        inputCheckResult = self.inputChecker()

        if inputCheckResult != "OK" or not self.measurixProgram or noHardwareCheck:
            return inputCheckResult

        return self.hardwareChecker()

    def inputChecker(self):
        return "OK"

    def hardwareChecker(self):
        return "OK"

    def sendMessage(self, message):
        self.sendMessageQueue.put(message)

    def sendRecipeAbortMessage(self):
        self.sendMessage({"type": "abort", "PID": os.getpid()})

    def receiveMessage(self):

        if self.childConnection.poll():
            return self.childConnection.recv()

        return None

    def receiveStopMessage(self, timeout=0.0):

        t0 = time.time()
        tNow = t0

        while tNow - t0 <= timeout:
            time.sleep(0.01)  # prevent this loop from hogging the CPU
            if self.receiveMessage() == "stop":
                self.stopMessageReceived = True
                return 1
            tNow = time.time()

        return None

    def start(self):

        if not self.measurixProgram:
            print "cannot start if not connected to a program"

        self.proc.start()
        return self.proc.pid

    def cleanUp(self):
        self.proc.join()

    def abort(self):
        self.proc.terminate()
        self.proc.join()

    def reportGenerator(self):  # This will be optionally implemented in inheriting classes
        return None


class stopProcessStub(object):
    def __init__(self, obj):
        self.obj = obj

    def start(self):
        self.obj.parentConnection.send("stop")
        return None

    def inputChecker(self):
        return "OK"

    def reportGenerator(self):
        return


##################################################################################################################
class execute_sleep(MeasurixCommand):
    def worker(self):
        print "info: sleeping for %.1f seconds" % self.args[0]

        if self.receiveStopMessage(self.args[0]):
            return

    def inputChecker(self):

        if map(type, self.args) != [float]:
            return "Single floating point argument required"

        return "OK"


################################################################################################################

class startProcess_arduino(MeasurixCommand):
    def worker(self):

        import numpy as np
        import writeLog

        showArduino = {"pot_meter": {"plotType": [],
                                     "yDataSource": "self.systemState[\"arduino\"][\"measurement\"][\"pot_meter\"]",
                                     "plotTitle": "pot meter",
                                     "xDataSource": "time"},
                       "LSR": {"plotType": [],
                               "yDataSource": "self.systemState[\"arduino\"][\"measurement\"][\"light_resistor\"]",
                               "plotTitle": "light sensitive resistor",
                               "xDataSource": "time"}}

        logKeys = {"pot_meter [Ohm]": "arduino/measurement/pot_meter/currentValue",
                   "LSR [Ohm]": "arduino/measurement/light_resistor/currentValue"}

        logFile = os.path.join(self.outputDirectory, "arduino_log.h5")
        print("info: saving to log file {}".format(logFile))
        logger = writeLog.dataLogger(logFile, self.systemState, logKeys)

        plotsShown = False

        while not self.receiveStopMessage(0.5):

            numbers1, numbers2 = self.device.read()

            measurement = {"pot_meter": {"currentValue": np.mean(numbers1), "UNIT": "Ohm"},
                           "light_resistor": {"currentValue": np.mean(numbers2), "UNIT": "Ohm"}}

            self.systemState["arduino"] = {"baud": self.baud,
                                           "measurement": measurement}

            logger.doLog()

            if not plotsShown:
                self.GUI.addRealTimePlot(showArduino)
                plotsShown = True

        self.device.close()

    def hardwareChecker(self):

        from arduino import Arduino

        baud = int(self.systemState["arduino"]["baud"])

        self.device = Arduino(baud=baud)

        if self.device.initError:
            return "Error: No arduino device found"

        self.baud = baud

        print("info: Communicating with arduino")
        return "OK"

    def inputChecker(self):
        return "OK"

################################################################################################################

class startProcess_webcam(MeasurixCommand):

    def worker(self):

        import pygame
        import pygame.camera
        import Image
        import os

        showCamera = {"camera": {"plotType": ["image"],
                                 "imageDataSource": "self.systemState[\"camera\"][\"data\"]",
                                 "plotTitle": "web cam"}}

        resolution = self.args
        camera = pygame.camera.Camera(self.camera_device, resolution)
        camera.start()

        plotsShown = False
        frame_count = 0

        outputDirectory = os.path.join(self.outputDirectory, "frames")

        if not os.path.exists(outputDirectory):
            os.mkdir(outputDirectory)

        print("info: saving frames to {}".format(outputDirectory))

        while not self.receiveStopMessage(0.5):

            image = camera.get_image()
            image_data = pygame.surfarray.array3d(image)
            frame = image_data[..., 0][:, ::-1].T
            self.systemState["camera"] = {"data": frame}

            image_file = os.path.join(outputDirectory, "frame-{}.jpeg".format(str(frame_count)))

            pil_image = Image.fromarray(image_data)
            pil_image.save(image_file)
            frame_count += 1

            if not plotsShown:
                self.GUI.addRealTimePlot(showCamera)
                plotsShown = True

        camera.stop()

    def hardwareChecker(self):

        import pygame
        import pygame.camera

        pygame.init()
        pygame.camera.init()

        clist = pygame.camera.list_cameras()
        if not clist:
            return "Error: No camera's detected"

        self.camera_device = clist[0]

        return "OK"

    def inputChecker(self):

        try:
            import pygame
        except ImportError:
            return "Error: you need pygame installed for this to work"

        if [type(i) for i in self.args] != [int, int]:
            return "Error: Two arguments specifying resolution is required"

        return "OK"