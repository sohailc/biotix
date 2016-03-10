import time
import os
import traceback
import numpy

class BiotixCommand(object):
    def __init__(self, args, messageQueue, biotixProgram, recipeInfo, childConnection=None):

        import multiprocessing

        self.args = args
        self.name = self.__class__.__name__

        if not childConnection:
            self.parentConnection, self.childConnection = multiprocessing.Pipe()
        else:  # This happens if the Biotix command is called from another Biotix command.
            # For example, as happens in "bringHardwareInSafeMode" and "setHVSeries"
            self.childConnection = childConnection
            self.parentConnection = None

        self.proc = multiprocessing.Process(target=self.protectedWorker)
        self.sendMessageQueue = messageQueue

        self.biotixProgram = biotixProgram
        self.systemState = biotixProgram.systemState
        self.GUI = biotixProgram.GUI

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

        if inputCheckResult != "OK" or not self.biotixProgram or noHardwareCheck:
            return inputCheckResult

        return self.hardwareChecker()

    def inputChecker(self):
        return "OK"

    def hardwareChecker(self):
        return "OK"

    def sendMessage(self, message):
        self.sendMessageQueue.put(message)

    def sendRecipeAbortMessage(self):
        self.sendMessage({"type": "abort",  "PID": os.getpid()})

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

        if not self.biotixProgram:
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
class execute_sleep(BiotixCommand):
    def worker(self):
        print "info: sleeping for %.1f seconds" % self.args[0]

        if self.receiveStopMessage(self.args[0]):
            return

    def inputChecker(self):

        if map(type, self.args) != [float]:
            return "Single floating point argument required"

        return "OK"

################################################################################################################

class execute_arduino(BiotixCommand):
	
	def worker(self):
		
		import numpy as np
		
		showArduino = {"pot_meter": {	"plotType": [],
										"yDataSource": "self.systemState[\"arduino\"][\"measurement\"][\"pot_meter\"]",
										"plotTitle": "pot meter",
										"xDataSource": "time"},
                       "LSR":  { "plotType": [],
								  "yDataSource": "self.systemState[\"arduino\"][\"measurement\"][\"light_resistor\"]",
								  "plotTitle": "light sensative resistor",
								  "xDataSource": "time"}}
		
		plotsShown = False
		
		while not self.receiveStopMessage(0.5):
			
			numbers1, numbers2 = self.device.read()
			
			measurement = {	"pot_meter": {"currentValue": np.mean(numbers1), "UNIT": "Ohm"},
							"light_resistor": {"currentValue": np.mean(numbers2), "UNIT": "Ohm"}}
			
			self.systemState["arduino"] = {	"baud": self.baud,
											"measurement": measurement}
			
			if not plotsShown:
				self.GUI.addRealTimePlot(showArduino)
				plotsShown = True
		
		s.close()
		
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


class startProcess_camera(BiotixCommand):
    def worker(self):

        import pydc1394
        import Image

        def acquireFrame(saveImage=False, imageFileName="image-{timeStamp}.png"):

            imageData = camera.current_image

            d = self.systemState["camera"]
            d["imageData"] = imageData
            self.systemState["camera"] = d

            if saveImage:

                image = Image.fromarray(imageData)
                imageFileName = imageFileName.format(timeStamp=time.strftime("%Y%m%d-%H%M%S"))

                outFile = os.path.join(self.outputDirectory,imageFileName)
                image.save(outFile)

        def acquireIlluminatedBackground(camera):

            for cameraLight in [1,0]:

                DAQrequest = "DAQOUTPUT.cameraLight=%i" % cameraLight
                self.DAQServer.sendRequest(DAQrequest)

                if self.receiveStopMessage(3.0):  # sleep for 3 seconds
                    return

                if cameraLight:
                    camera.start(interactive=True)
                    acquireFrame(saveImage=True, imageFileName="image-background-{timeStamp}.png")
                    camera.stop()

        frameCaptureRate = self.args[0]  # how many times per second to we write a frame to an image file?
        # is not necessarily the same as the expose time

        dc1394Library = pydc1394.DC1394Library()
        cameraInfo = dc1394Library.enumerate_cameras()[0]
        shutterTimeInMicroSeconds = self.systemState["camera"]["shutterTimeInMicroSecond"]
        shutterTime = shutterTimeInMicroSeconds * 1E-6
        camera = pydc1394.Camera(dc1394Library, cameraInfo['guid'], shutter=shutterTimeInMicroSeconds)

        self.outputDirectory = os.path.join(self.outputDirectory, "images")

        if not os.path.exists(self.outputDirectory):
            os.mkdir(self.outputDirectory)

        showCameraImage = {"camera": {"plotType": ["image"],
                                      "imageDataSource": "self.systemState[\"camera\"][\"imageData\"]",
                                      "plotTitle": "Camera"}}

        imageShown = False
        timeSinceLastFrameCapture = time.time()

        # First acquire a single frame with the lights on
        acquireIlluminatedBackground(camera)

        # Restart the camera for the rest of the frames
        camera.start(interactive=True)

        print "info: Starting camera acquisition with shutter time %s us. Will capture %.1f frames per second" % \
              (shutterTimeInMicroSeconds, frameCaptureRate)

        while not self.receiveStopMessage(shutterTime):  # Do not change this to anything else (e.g. 1.0)

            now = time.time()

            if now - timeSinceLastFrameCapture >= 1.0/frameCaptureRate:
                acquireFrame(saveImage=True)
                timeSinceLastFrameCapture = now
            else:
                acquireFrame(saveImage=False)

            if not imageShown:
                self.GUI.addRealTimePlot(showCameraImage)
                imageShown = True

        camera.stop()

        return

    def hardwareChecker(self):

        import pydc1394

        dc1394Library = pydc1394.DC1394Library()
        cameraInfos = dc1394Library.enumerate_cameras()

        if not len(cameraInfos):
            return "Error: no camera found"

        if len(cameraInfos) > 1:
            return "Error: do not know how to handle more than one camera"

        return "OK"

    def inputChecker(self):

        if len(self.args) != 1:
            return "error: Need one input argument: frame capture rate"

        if type(self.args[0]) != float:
            return "error: frame capture rate needs to be float"

        if self.args[0] > 1.0:
            return "error: Will not capture more then one frame per second"

        return "OK"

    def reportGenerator(self):

        import h5py
        from reportGenerator import chapterCamera

        HVLogFile = os.path.join(self.outputDirectory, "highVoltageTracing.h5")

        if not os.path.exists(HVLogFile):
            return None

        imagesDir = os.path.join(self.outputDirectory, "images")

        HVLogData = h5py.File(HVLogFile)

        cameraChapter = chapterCamera.generateCameraChapter(imagesDir, HVLogData)

        return cameraChapter

################################################################################################################

class generateFinalReport(BiotixCommand):  # This is a special command which will not be present in recipe files
    #  but will be called directly by the software
    def worker(self):

        from reportGenerator import reportGenerator
        from CMTFunctions import uploadFileToCMT

        print "info: Generating PDF report"

        softwareVersion = self.args[0]

        reportChapters = []
        for step in self.args[1]:  # this is an execution sequence

            if self.receiveStopMessage():
                break

            try:
                chapter = step.reportGenerator()
                if chapter:
                    print "info: Generated %s section" % step.name
                    reportChapters.append(chapter)
            except Exception, e:
                tb = traceback.format_exc()
                print "warning: error generating report section of %s: %s" % (step.name, tb)

        if not len(reportChapters):
            return

        try:
            print "info: Please wait while the report is begin generated (for 8 hour measurement, can take ~30 minutes)"
            reportFileName = reportGenerator.generatePDFReport(self.outputDirectory,
                                                               reportChapters,
                                                               softwareVersion,
                                                               self.recipeInfo)

            if self.recipeInfo["upload to CMT"] == True:
                print "info: uploading report file to CMT"
                credentials = self.recipeInfo["CMT credentials"]

                attachments = [os.path.join(self.outputDirectory, fname) for fname in os.listdir(self.outputDirectory)
                               if fname.endswith(".h5")]
                # We do not attach the camera images in CMT.... just to much data we will probably not even look at

                reportFileName = os.path.join(self.outputDirectory, reportFileName)
                uploadFileToCMT(reportFileName, credentials, attachmentFiles=attachments)

        except Exception, e:
            tb = traceback.format_exc()
            print "warning: Error generating report: %s" % tb

    def inputChecker(self):  # Since this command is called from within the software, we can do away with
        # the formality of the input checker. If something goes wrong here... debug your code :-)
        return "OK"
