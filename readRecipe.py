import commandDefinitions
import re
import zipfile
import cPickle
import time
import multiprocessing
import traceback


class BiotixRecipe():
    def __init__(self, recipeFileName, systemState, ignoreTimeStampInRecipeInfo=False):

        self.ignoreTimeStampInRecipeInfo = ignoreTimeStampInRecipeInfo

        self.recipeFileName = recipeFileName
        self.messageQueue = None
        self.init, extraction = self._extractRecipeFile(recipeFileName)
        self.systemState = systemState

        if self.init != "OK":
            return

        self.sequenceText, infoText, self.inputs = extraction
        self.recipeInfo = self._parseRecipeInfoText(infoText, self.systemState)

        # All None values will be decided in due course
        self.executionSequence = None
        self.processesStarted = dict()
        self.currentStepInRecipe = 0
        self.done = False
        self.biotixProgram = None

    def _extractRecipeFile(self, recipeFile):
        try:
            zf = zipfile.ZipFile(recipeFile, "r")
        except:
            return "error reading recipe %s: Does not seem to be a valid zip file or file corrupted" % recipeFile, []

        listOfFiles = zf.namelist()

        if "sequence.txt" not in listOfFiles:
            return "error reading recipe file %s: no sequence file found" % recipeFile, []

        if "recipeInfo.txt" not in listOfFiles:
            return "error reading recipe file %s: no recipe information text file found" % recipeFile, []

        sequenceText = zf.read("sequence.txt")
        infoText = zf.read("recipeInfo.txt")

        inputsDict = dict()

        for f in listOfFiles:

            m = re.search("inputs/(.*)", f)

            if not m:
                continue

            objectName = m.groups()[0]

            if objectName.strip() == "":
                continue

            objectValuePickled = zf.read(f)
            objectValue = cPickle.loads(objectValuePickled)
            inputsDict[objectName] = objectValue

        zf.close()

        return "OK", [sequenceText, infoText, inputsDict]

    def _parseSequenceText(self, sequenceText, noHardwareCheck=False):

        for name, value in zip(self.inputs.keys(), self.inputs.values()):
            exec ("{name}=value".format(name=name))

        sequence = []
        startedProcs = dict()

        for lineNo, line in enumerate(sequenceText.split("\n")):

            line = line.strip()

            if line == "":
                continue

            m = re.search("(.*)\((.*)\)", line)

            if not m:
                return "error: Line %i: %s is not in the format command(inp1, inp2,...)" % (lineNo, line), []
            else:

                commandName = m.groups()[0]

                if "stopProcess" in commandName:
                    procNameToStop = commandName.replace("stopProcess", "startProcess")

                    if procNameToStop not in startedProcs.keys():
                        return "error: process %s stopping without being started" % commandName, []

                    objToStop = startedProcs[procNameToStop]

                    if not objToStop:
                        return "error: process %s stopping without being started" % commandName, []

                    stub = commandDefinitions.stopProcessStub(objToStop)
                    sequence.append(stub)
                    startedProcs[procNameToStop] = None

                    continue

                argStringArray = m.groups()[1].split(",")
                argArray = []

                try:
                    commandObj = eval("commandDefinitions.{commandName}".format(commandName=commandName))
                except AttributeError:
                    return "error: Line %i: %s unknown" % (lineNo, commandName), []

                for argString in argStringArray:

                    if argString.strip() == "":
                        continue

                    try:
                        argArray.append(eval(argString))
                    except NameError:
                        return "error: Line %i: %s. Input %s not defined" % (lineNo, line, argString), []

                comObj = commandObj(argArray, self.messageQueue, self.biotixProgram, self.recipeInfo)

                try:
                    checkResult = comObj.checker(noHardwareCheck=noHardwareCheck)
                except Exception, e:

                    timeStamp = time.strftime("%Y%m%d-%H%M%S")
                    crashLog = self.systemState["crashLog"].format(timeStamp=timeStamp)

                    with open(crashLog, "w") as fh:
                        traceback.print_exc(None, fh)

                    return "error: Checker error. Please submit a TT to the developer. Please see crash log file %s" % \
                           crashLog, []

                if not checkResult.startswith("OK"):
                    return "error: Line %i: %s: %s" % (lineNo, line, checkResult), []

                sequence.append(comObj)

                if "startProcess" in commandName:

                    if commandName in startedProcs.keys():
                        if startedProcs[commandName]:
                            return "Error: process %s starting twice" % commandName, []

                    startedProcs[commandName] = comObj

        for startedProc in startedProcs.keys():

            if startedProcs[startedProc]:
                return "error: process %s started but not stopped" % startedProc, []

        return "OK", sequence

    def _parseRecipeInfoText(self, infoText, INI):

        regex = ur"{(.+?)}+?"
        infoDict = dict()
        timeStamp = time.strftime("%Y%m%d-%H%M%S")

        for line in infoText.split("\n"):

            parts = line.split("=")
            name = parts[0].strip()
            value = "=".join(parts[1:]).strip()

            elements = re.findall(regex, value)

            for element in elements:

                elementEvaluated = element

                if "INI" in element:

                    try:
                        elementEvaluated = eval(element)

                        if len(elementEvaluated) > 1 and type(elementEvaluated) != str:  # If there is more then one
                            # value in the INI file, we need to present the user with the options

                            regex2 = ur"\[(.+?)\]+?"
                            elementName = "\\".join(re.findall(regex2, element))
                            elementName = elementName.strip("\"")

                            elementEvaluated = "{elementName}; {options}".format(elementName=elementName,
                                                                                 options=",".join(elementEvaluated))

                            elementEvaluated = "{" + elementEvaluated + "}"

                    except KeyError:
                        return "Error, %s not known in INI file" % element

                if element == "time stamp" and not self.ignoreTimeStampInRecipeInfo:
                    elementEvaluated = timeStamp

                if elementEvaluated != element:
                    value = value.replace("{%s}" % element, elementEvaluated)

            infoDict[name] = value

        return infoDict

    def _evaluateSequence(self, noHardwareCheck=False):

        parseResult, evacuatedSequence = self._parseSequenceText(self.sequenceText,
                                                                 noHardwareCheck=noHardwareCheck)

        if parseResult != "OK":
            return "Evacuated sequence: " + parseResult, []

        return "OK", evacuatedSequence

    def setOutputDirectory(self, directoryPath):
        self.recipeInfo["outputDir"] = directoryPath

    def addInfoToRecipe(self, additionalInfo):

        for key in additionalInfo:
            self.recipeInfo[key] = additionalInfo[key]

    def check(self, biotixProgram):
        self.biotixProgram = biotixProgram

        evaluateResult, sequence = self._evaluateSequence()

        return evaluateResult

    def start(self, biotixProgram):

        # from commandDefinitions import generateFinalReport
        from main import softwareVersion

        self.messageQueue = multiprocessing.Queue()
        self.biotixProgram = biotixProgram

        evaluateResult, self.executionSequence = self._evaluateSequence()

        if not evaluateResult.startswith("OK"):
            return evaluateResult

        self.currentStepInRecipe = 0

        args = ([softwareVersion, self.executionSequence],
                self.messageQueue, self.biotixProgram, self.recipeInfo)

        # reportGeneratingStep = generateFinalReport(*args)
        # self.executionSequence.append(reportGeneratingStep)

        pid = self.executionSequence[0].start()
        self.processesStarted[pid] = self.executionSequence[0]

        return "OK"

    def regenerateFinalReport(self, biotixProgram):

        # from commandDefinitions import generateFinalReport
        from main import softwareVersion

        self.biotixProgram = biotixProgram

        self.messageQueue = multiprocessing.Queue()

        evaluateResult, executionSequence = self._evaluateSequence(noHardwareCheck=True)

        if not evaluateResult.startswith("OK"):
            return evaluateResult

        self.currentStepInRecipe = 0

        args = ([softwareVersion, executionSequence],
                self.messageQueue, biotixProgram, self.recipeInfo)

        # reportGeneratingStep = generateFinalReport(*args)
        # self.executionSequence = [reportGeneratingStep]
        # pid = reportGeneratingStep.start()
        # self.processesStarted[pid] = reportGeneratingStep

        return "OK"

    def process(self):

        if self.messageQueue.empty():
            return

        message = self.messageQueue.get()

        if message["type"] in ["continue", "done"]:

            if message["type"] == "done":
                self.processesStarted[message["PID"]].cleanUp()

            self.currentStepInRecipe += 1
            if self.currentStepInRecipe == len(self.executionSequence):
                self.processRecipeDone()
            else:
                currentStepObject = self.executionSequence[self.currentStepInRecipe]
                pid = currentStepObject.start()
                if pid:
                    self.processesStarted[pid] = currentStepObject

        elif message["type"] in ["exception", "abort"]:

            name = self.processesStarted[message["PID"]].name

            if message["type"] == "exception":
                print "error: Exception occurred in %s: %s" % (name, message["exception"])
            else:
                print "info: Abort message received by process %s" % name

            self.processesStarted[message["PID"]].cleanUp()
            self.abort(exception=True)

            return

    def abort(self, exception=False):

        # Loop through all started processes and if they are alive, tell them to stop nicely.
        # If the process is unresponsive, kill it.
        for pid in self.processesStarted.keys():
            if self.processesStarted[pid].proc.is_alive():

                # Send a stop message to the running process and wait for it to acknowledge that it will stop
                self.processesStarted[pid].parentConnection.send("stop")

                # Lets calculate how much time a recipe cat need at maximum to close after receiving
                # an abort signal...
                # We can set a voltage of 6.5 kV on HV and the maximum ramp speed is 500.0 V/s. This means
                # that if a recipe puts the maximum voltage on output and it received a stop message it needs
                # at least 6500/500 = 15.0 seconds to close everything gracefully. We will allow a little
                # additional time just to make sure...
                acknowledgeTimeOut = 15.0  # A command should not take longer than this to shut down
                stopAcknowledgmentReceived = False
                t0 = time.time()

                while time.time() - t0 < acknowledgeTimeOut:

                    if self.messageQueue.empty():
                        continue

                    message = self.messageQueue.get()

                    if message["PID"] == pid:
                        stopAcknowledgmentReceived = True
                        break

                # If we do not receive an acknowledgment, kill it by force
                # If a plugin command is programmed correctly, this can never happen. IF THIS HAPPENS, THE
                # PROGRAMMER IF THE PLUGIN COMMAND NEEDS TO BE MADE AWARE
                if not stopAcknowledgmentReceived:
                    print "error: Killing %s by force. Please submit a TT to the programmer" % self.processesStarted[
                        pid]
                    self.processesStarted[pid].abort()

                self.processesStarted[pid].cleanUp()

        self.processRecipeDone(exception=exception, abort=True)

    def processRecipeDone(self, exception=False, abort=False):

        if exception or abort:
            print "info: Recipe aborted"

        self.done = True
        self.currentStepInRecipe = -1

        return
