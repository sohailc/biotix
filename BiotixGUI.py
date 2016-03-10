import os
import re
import time
import multiprocessing
from multiprocessing.queues import Queue
import sys
import numpy as np

from readRecipe import BiotixRecipe
from writeLog import logPrintMessages

class StdOutQueue(Queue):
    def __init__(self,*args,**kwargs):
        Queue.__init__(self,*args,**kwargs)

    def write(self,msg):
        self.put(msg)

    def flush(self):
        sys.__stdout__.flush()

class BiotixGUI(object):
    def __init__(self, BiotixProgram):

        self.win = None
        self.BiotixProgram = BiotixProgram
        self.systemState = BiotixProgram.systemState
        self.softwareVersion = BiotixProgram.softwareVersion
        self.recipeFolder = self.systemState["recipeFolder"]
        self.outputDirRoot = self.systemState["outputDir"]
        self.logFile = self.systemState["logFile"]

        self.recipeList = dict()

        self.time0 = None
        self.plots = dict()
        self.maxNumberOfPlots = 9
        self.axesAvailable = None
        self.timeResolution = 0.5 # [s]
        self.maxTimePlot = 1000.0 #[s]  In the real time plots, we see data going back to 1000 seconds in the past

        self.stdOut = StdOutQueue()
        sys.stdout = self.stdOut

        self.logWindow = None
        self.scrolledWindow = None
        self.parentConnection, self.childConnection = multiprocessing.Pipe()
        self.proc = multiprocessing.Process(target=self._start)

######################################## Public interface ########################################

    def start(self):
        self.proc.start()

    def quit(self):
        self.sendSignal({"type": "quit"})
        self.proc.join()

    def sendSignal(self, message):
        self.parentConnection.send(message)

    def receiveSignal(self):

        msg = None
        if self.parentConnection.poll():
            msg = self.parentConnection.recv()

        return msg

    def addRealTimePlot(self, dataSource):

        requesterPid = os.getpid()  # If we see that the process asking to include this real time plot
        # does not exists any more, we will remove the real time plot

        self.sendSignal({"type":"plot", "data":dataSource, "requesterPid":requesterPid})

######################################## Private functions ########################################

    def _start(self):
        
        from gi.repository import Gtk, GObject, Gdk, GLib
        from GUIDialogs import BiotixMessage, BiotixDialog, BiotixGetUserInput, BiotixGetCMTCredentials
        
        self.Gtk = Gtk
        self.GObject = GObject
        self.Gdk = Gdk
        self.GLib = GLib

        self.BiotixDialog = BiotixDialog
        self.BiotixGetUserInput = BiotixGetUserInput
        self.BiotixGetCMTCredentials = BiotixGetCMTCredentials
        self.BiotixMessage = BiotixMessage

        if not self._checkHarddriveSpace():
            self._sendSignal({"type": "quit"})
            self._quit()

        self.win = self.Gtk.Window()

        self.win.maximize()
        self.win.set_border_width(10)
        self.win.connect("delete-event",self._onDeleteEvent)

        vbox1 = self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL, spacing=1)
        hbox1 = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL, spacing=1)
        hbox1.pack_start(self._makeControlElements(), False, True, 0)
        hbox1.pack_start(self._makeGraphics(), True, True, 0)

        vbox1.pack_start(hbox1, True, True, 0)
        vbox1.pack_start(self._makeLogWindow(), False, True, 0)

        self.win.add(vbox1)
        self.win.show_all()

        self._getRecipeListFromLocalFolder()

        self.GObject.io_add_watch(self.childConnection, self.GObject.IO_IN, self._handleMessagesFromPublicInterface)
        self.GObject.io_add_watch(self.stdOut._reader.fileno(), self.GObject.IO_IN|self.GObject.IO_HUP, self._print)

        self.Gtk.main()

    def _checkHarddriveSpace(self):

        s = os.statvfs(self.systemState["outputDir"])

        freeDiskSpaceInBytes = s.f_bsize * s.f_bavail
        minimumFreeDiskSpaceInGB = self.systemState["minimumFreeDiskSpaceInGB"]

        if freeDiskSpaceInBytes < minimumFreeDiskSpaceInGB*1024**3:

            dialog= self.BiotixDialog(self.win, "The amount of disk space %.1f GB is less then %.1f GB. "
                                                "Are you sure you want to continue?" % (freeDiskSpaceInBytes/(1024**3),
                                                                                        minimumFreeDiskSpaceInGB))

            response = dialog.run()
            dialog.destroy()

            if response == self.Gtk.ResponseType.CANCEL:
                return None

        return 1


    def _handleMessagesFromPublicInterface(self, stream, condition):

        while stream.poll():

            msg = stream.recv()

            if msg["type"] == "quit":
                self._quit()
            elif msg["type"] == "plot":
                self._addPlot(msg["data"], msg["requesterPid"])

        return 1    # This is really necessary! If 0 or None is returned, this function will be removed from the
                    # list of call back functions, which will hang our application!

    def _sendSignal(self, message):
        self.childConnection.send(message)

    def _makeControlElements(self):

        grid = self.Gtk.Grid()

        versionMessage = self.softwareVersion

        if versionMessage.startswith("Development"):
            warningMessage = "\nThis is a development version of the software and should\n only be used by developers!"
            versionMessage += "<span color=\"red\">%s</span>" % warningMessage

        labelSoftwareVersion = self.Gtk.Label(xalign=0)
        labelSoftwareVersion.set_line_wrap(True)
        labelSoftwareVersion.set_markup(versionMessage)

        labelRecipe = self.Gtk.Label("Please select recipe", xalign=0)
        self.comboRecipe = self.Gtk.ComboBoxText()

        executeButton = self.Gtk.Button(label="execute")
        executeButton.connect("clicked", self._onExecuteButtonClick)

        quitButton = self.Gtk.Button(label="quit")
        quitButton.connect("clicked", self._onQuitButtonClick)

        abortButton = self.Gtk.Button(label="abort")
        abortButton.connect("clicked", self._onAbortButtonClick)

        ventButton = self.Gtk.Button(label="vent")
        ventButton.connect("clicked", self._onVentButtonClick)

        evacuateButton = self.Gtk.Button(label="evacuate")
        evacuateButton.connect("clicked", self._onEvacuateButtonClick)

        checkRecipeButton = self.Gtk.Button(label="check recipe")
        checkRecipeButton.connect("clicked", self._onCheckRecipeButtonClick)

        regenerateReportButton = self.Gtk.Button(label="regenerate a measurement report")
        regenerateReportButton.connect("clicked", self._onRegenerateReportButtonClick)

        refreshRecipeListButton = self.Gtk.Button(label="refresh recipe list")
        refreshRecipeListButton.connect("clicked", self._onRefreshRecipeListButtonClick)

        grid.attach(labelSoftwareVersion, 0, 0, 2, 1)

        grid.attach_next_to(labelRecipe, labelSoftwareVersion, self.Gtk.PositionType.BOTTOM, 1, 1)
        grid.attach_next_to(self.comboRecipe,labelRecipe, self.Gtk.PositionType.BOTTOM, 1, 1)

        hboxButtons = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL, spacing=1)

        hboxButtons.pack_start(executeButton, True, True, 0)
        hboxButtons.pack_start(quitButton, True, True, 0)
        hboxButtons.pack_start(abortButton, True, True, 0)

        grid.attach_next_to(hboxButtons, self.comboRecipe, self.Gtk.PositionType.BOTTOM, 1, 1)

        hboxButtons2 = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL, spacing=1)
        hboxButtons2.pack_start(ventButton, True, True, 0)
        hboxButtons2.pack_start(evacuateButton, True, True, 0)

        grid.attach_next_to(hboxButtons2, hboxButtons, self.Gtk.PositionType.BOTTOM, 1, 1)

        hboxButtons3 = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL, spacing=1)
        hboxButtons3.pack_start(checkRecipeButton, True, True, 0)
        hboxButtons3.pack_start(refreshRecipeListButton, True, True, 0)

        grid.attach_next_to(hboxButtons3, hboxButtons2, self.Gtk.PositionType.BOTTOM, 1, 1)

        hboxButtons4 = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL, spacing=1)
        hboxButtons4.pack_start(regenerateReportButton, True, True, 0)
        grid.attach_next_to(hboxButtons4, hboxButtons3, self.Gtk.PositionType.BOTTOM, 1, 1)

        return grid

    def removeGraphicFromRealTimePlot(self, plotName):

        for count, (axis, available) in enumerate(self.axesAvailable):

            if axis == self.plots[plotName]["axis"]:
                self.axesAvailable[count][1] = True
                axis.set_xlim([0,1])
                axis.set_ylim([0,1])
                axis.set_aspect('equal', 'datalim')
                break

        self.plots = {key: self.plots[key] for key in self.plots if key != plotName}

    def _makeGraphics(self):

        import matplotlib.pyplot as plt
        import matplotlib.animation as animation
        from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas

        nPlots = self.maxNumberOfPlots
        nPlotsHorizontal = 3 if (nPlots >= 3) else nPlots
        nPlotsVertical = nPlots/4+1
        self.time0 = self.systemState["time"]["currentValue"]

        figure, axes = plt.subplots(nPlotsVertical, nPlotsHorizontal)
        axes = axes.flatten()
        self.axesAvailable = [[axis, True] for axis in axes]

        canvas = FigureCanvas(figure)
        plt.rcParams.update({'font.size': 10})

        def _updateGraphics(_):  # update needs one argument or else "animation.FuncAnimation" will fail

            for plotName in self.plots.keys():

                ax = self.plots[plotName]["axis"]
                ax.clear()

                if not os.path.exists("/proc/%i" % self.plots[plotName]["requesterPID"]):
                    self.removeGraphicFromRealTimePlot(plotName)
                    continue

                if not self.plots[plotName]:
                    self.removeGraphicFromRealTimePlot(plotName)
                    continue

                if "xDataSource" in self.plots[plotName].keys():

                    if self.plots[plotName]["xDataSource"] == "time":

                        if not "xData" in self.plots[plotName].keys():
                            # We are starting a real time plot
                            # instead of just updating an existing one.
                            self.plots[plotName]["xData"] = np.array([])
                            self.plots[plotName]["yData"] = np.array([])

                        unit = eval(self.plots[plotName]["yDataSource"]+"[\"UNIT\"]")
                        currentValue = eval(self.plots[plotName]["yDataSource"]+"[\"currentValue\"]")
                        self.plots[plotName]["yData"] = np.append(self.plots[plotName]["yData"], currentValue)

                        if len(self.plots[plotName]["xData"]) > self.maxTimePlot:
                            lenXData = len(self.plots[plotName]["xData"])
                            self.plots[plotName]["yData"] = self.plots[plotName]["yData"][-lenXData:]
                        else:
                            self.plots[plotName]["xData"] -= self.timeResolution
                            self.plots[plotName]["xData"] = np.append(self.plots[plotName]["xData"], 0)

                        ax.set_title("%s = %.4e %s" % (plotName, currentValue, unit))
                        ax.set_xlabel("time [s]")
                        ax.set_ylabel(unit)

                    else:

                        xData = eval(self.plots[plotName]["xDataSource"])
                        self.plots[plotName]["xData"] = xData

                        if "xDataLabel" in self.plots[plotName].keys():
                            xDataLabel = self.plots[plotName]["xDataLabel"]
                            ax.set_xlabel(xDataLabel)

                        if "yDataLabel" in self.plots[plotName].keys():
                            yDataLabel = self.plots[plotName]["yDataLabel"]
                            ax.set_ylabel(yDataLabel)

                        if "yDataSource" in self.plots[plotName].keys():
                            yData = eval(self.plots[plotName]["yDataSource"])
                            self.plots[plotName]["yData"] = yData

                        if "xlim" in self.plots[plotName].keys():
                            ax.set_xlim(self.plots[plotName]["xlim"])

                        if "ylim" in self.plots[plotName].keys():
                            ax.set_ylim(self.plots[plotName]["ylim"])

                if "imageDataSource" in self.plots[plotName].keys():
                    imageData = eval(self.plots[plotName]["imageDataSource"])
                    self.plots[plotName]["imageData"] = imageData

                if "plotTitle" in self.plots[plotName].keys():
                    plotTitle = self.plots[plotName]["plotTitle"]
                    ax.set_title(plotTitle)

                plotType = self.plots[plotName]["plotType"]

                if "bar" in plotType:

                    if "semiLogY" in plotType:

                        # Make sure the x data and y data arrays are not empty or log plotting
                        # will crash our software

                        if len(xData) and len(yData):
                            ax.bar(xData, yData, 1, log=True)
                    else:

                        ax.bar(xData, yData, 1)

                elif "image" in plotType:
                    ax.imshow(self.plots[plotName]["imageData"], cmap=plt.cm.gray,
                                    origin="lower",interpolation='nearest')
                else:

                    ax.plot(self.plots[plotName]["xData"],self.plots[plotName]["yData"])

                    if "semiLogY" in plotType:
                        ax.set_yscale('log')

                    if "semiLogX" in plotType:
                         ax.set_xscale('log')

            plt.tight_layout()

        self.ani = animation.FuncAnimation(figure, _updateGraphics, interval=self.timeResolution*1E3, blit=False)  # don't set blit to true
        sw = self.Gtk.ScrolledWindow()
        sw.add_with_viewport (canvas)
        sw.set_shadow_type(self.Gtk.ShadowType.ETCHED_IN)

        return sw

    def _getRecipeListFromLocalFolder(self):

        listOfFiles = os.listdir(self.recipeFolder)
        recipeNamePattern = "biotixRecipe_(.*)-|_(v\d*-\d*).zip"
        self.recipeList = dict()

        for fileName in listOfFiles:

            m = re.search(recipeNamePattern, fileName)

            if not m:
                continue

            key = m.groups()[0]
            versionInfo = m.groups()[1]

            if key in self.recipeList.keys():
                print "detected two recipes with same name but different revisions: %s, %s" % (fileName, self.recipeList[key])
                print "using recipe %s" % self.recipeList[key]
                continue

            self.recipeList[m.groups()[0]] = {"file": fileName, "version": versionInfo}

        self.comboRecipe.remove_all()

        for count, item in enumerate(self.recipeList.keys()):
            self.comboRecipe.insert(count, str(count), item)

    def _addPlot(self, plotData, requesterPid):

        for plotDataKey in plotData.keys():

            numberOfPlotsAvailable = sum(v[1] for v in self.axesAvailable)

            if numberOfPlotsAvailable == 0:
                print "error: Can't add additional plot, maximum received"
                return

            if "xDataSource" in plotData[plotDataKey].keys():
                try:
                    eval(plotData[plotDataKey]["xDataSource"])
                except KeyError:
                    print "error: Plot command %s is erroneous" % plotData[plotDataKey]
                    return

            if "yDataSource" in plotData[plotDataKey].keys():
                try:
                    eval(plotData[plotDataKey]["yDataSource"])
                except KeyError:
                    print "error: Plot command %s is erroneous" % plotData[plotDataKey]
                    return

            if "imageDataSource" in plotData[plotDataKey].keys():
                try:
                    eval(plotData[plotDataKey]["imageDataSource"])
                except KeyError:
                    print "Plot command %s is erroneous" % plotData[plotDataKey]
                    return

            newAxis = None
            for count, (newAxis, available) in enumerate(self.axesAvailable):

                if available:
                    self.axesAvailable[count][1] = False
                    break

            plotData[plotDataKey]["axis"] = newAxis
            plotData[plotDataKey]["requesterPID"] = requesterPid
            self.plots[plotDataKey] = plotData[plotDataKey]

    def _makeLogWindow(self):

        self.scrolledWindow = self.Gtk.ScrolledWindow()
        self.scrolledWindow.set_min_content_height(120)
        self.logWindow = self.Gtk.Label(xalign=0)
        self.logWindow.override_background_color(self.Gtk.StateFlags.NORMAL, self.Gdk.RGBA(255, 255, 255, 1))
        self.logWindow.set_line_wrap(True)
        self.logWindow.set_selectable(True)
        self.logWindow.connect("size-allocate", self._autoScrollLogView)
        self.scrolledWindow.add(self.logWindow)
        self.scrolledWindow.set_border_width(3)
        self.scrolledWindow.set_shadow_type(self.Gtk.ShadowType.ETCHED_IN)

        return self.scrolledWindow

    def _print(self, stream, condition):

        while self.stdOut.qsize():
            data = self.stdOut.get()
            data = data.strip()
            if data != "":
                self._addLogLine(data)
                logPrintMessages(data, self.systemState["logFile"])

        return True

    def _addLogLine(self, logTxt):

        text = self.logWindow.get_text()
        text += "{timeStamp}: {logTxt}\n".format(timeStamp=time.strftime("%Y%m%d-%H%M%S"),logTxt=logTxt)

        text = text.replace("info", "<span color=\"green\">info</span>")
        text = text.replace("warning", "<span color=\"orange\">warning</span>")
        text = text.replace("error", "<span color=\"red\">error</span>")

        self.logWindow.set_markup(text)

    def _autoScrollLogView(self, *args):
        adj = self.scrolledWindow.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())

    def _getUnknowns(self, string):

        regex = ur"{(.+?)}+?"  # for example, if outputDir = /home/{object type}/{serial number}/RGA/
        # then the parts within the curly brackets are unknown. Ask the user to give these as input
        unknowns = re.findall(regex, string)

        if not len(unknowns):
            return "no unknowns"

        answers = dict()

        if len(unknowns):
            userInputBox = self.BiotixGetUserInput(self.win, unknowns, "please give the following information")
            answers = userInputBox.getAnswers()

        return answers

    def _fillInAnswers(self, string, answers):

        regex = ur"{(.+?)}+?"
        unknowns = re.findall(regex, string)

        for unknown in unknowns:

            if ";" in unknown:
                unknownNew = unknown.split(";")[0]  # e.g. if unknown = "object type; PL, PLWPPF",
                #  make into "object type"
                string = string.replace("{"+unknown+"}", "{"+unknownNew+"}")

        return string.format(**answers)

    def _onExecuteButtonClick(self, widget):

        tree_iter = self.comboRecipe.get_active_iter()

        if tree_iter:
                model = self.comboRecipe.get_model()
                recipeSelected = model[tree_iter][0]
        else:
                print "error: no recipe selected"
                return

        recipeFileBaseName = self.recipeList[recipeSelected]["file"]
        recipeVersion = self.recipeList[recipeSelected]["version"]
        recipeFileName = os.path.join(self.recipeFolder, recipeFileBaseName)

        print "info: starting recipe %s, version %s" % (recipeSelected, recipeVersion)
        self._sendExecuteMessage(recipeFileName)

    def _sendExecuteMessage(self, recipeFileName):

        recipe = BiotixRecipe(recipeFileName, self.systemState)

        if recipe.init != "OK":
            print recipe.init
            return

        if not "outputDir" in recipe.recipeInfo.keys():
            print "error: no output directory given in recipe information file!"
            return

        outputDir = recipe.recipeInfo["outputDir"]
        answers = self._getUnknowns(outputDir)

        if not answers:
            print "error: did not get any answers. Can't run recipe"
            return

        if answers != "no unknowns":
            outputDir = self._fillInAnswers(outputDir, answers)
            recipe.setOutputDirectory(outputDir)
            recipe.addInfoToRecipe(answers)

        recipe.addInfoToRecipe({"recipeFileName":recipeFileName})

        if "time stamp" not in recipe.recipeInfo.keys():
            recipe.addInfoToRecipe({"time stamp":time.strftime("%Y%m%d-%H%M%S")})

        msg = {"type": "execute", "recipe": recipe}

        self._sendSignal(msg)

    def _onQuitButtonClick(self, widget):
        self._onDeleteEvent(widget)

    def _onAbortButtonClick(self, widget):
        self._sendSignal({"type": "abort"})

    def _onVentButtonClick(self, widget):

        recipeFileName = None

        for key in self.recipeList.keys():
            if "vent" in key:
                recipeFileName = self.recipeList[key]["file"]

        if not recipeFileName:
            print "error: No vent recipe found!"
            return

        recipeFileName = os.path.join(self.recipeFolder, recipeFileName)

        dialog = self.BiotixDialog(self.win, "Are you sure you want to vent the vacuum chamber?")
        response = dialog.run()

        if response == self.Gtk.ResponseType.OK:
            self._sendExecuteMessage(recipeFileName)

        dialog.destroy()

    def _onEvacuateButtonClick(self, widget):

        recipeFileName = None

        for key in self.recipeList.keys():
            if "evacuate" in key:
                recipeFileName = self.recipeList[key]["file"]

        if not recipeFileName:
            print "No evacuate recipe found!"
            return

        recipeFileName = os.path.join(self.recipeFolder, recipeFileName)

        dialog = self.BiotixDialog(self.win, "Are you sure you want to evacuate the vacuum chamber?")
        response = dialog.run()

        if response == self.Gtk.ResponseType.OK:
            self._sendExecuteMessage(recipeFileName)

        dialog.destroy()

    def _onCheckRecipeButtonClick(self, widget):

        dialog = self.Gtk.FileChooserDialog(title = "Please select the recipe to check",
                                            parent = self.win,
                                            action = self.Gtk.FileChooserAction.OPEN,
                                            buttons=["Open", self.Gtk.ResponseType.OK, "Cancel", self.Gtk.ResponseType.CANCEL])

        filter = self.Gtk.FileFilter()
        filter.set_name('zip files')
        filter.add_pattern('biotixRecipe_*.zip')
        dialog.add_filter(filter)

        response = dialog.run()

        recipeFileName = dialog.get_filename()
        dialog.destroy()

        if response == self.Gtk.ResponseType.CANCEL:
            return

        if not os.path.exists(recipeFileName):
            print "error: file does not exist"
            return

        if os.path.isdir(recipeFileName):
            return

        recipe = BiotixRecipe(recipeFileName, self.systemState)
        print "info: checking recipe %s" % recipeFileName

        self._sendSignal({"type": "check", "recipe": recipe})

        return

    def _onRefreshRecipeListButtonClick(self, widget):
        self.getRecipeList()

    def _onRegenerateReportButtonClick(self, widget):

        def extractUnknowns(s, pattern):

            regex = ur"{(.+?)}+?"
            unknowns = re.findall(regex, pattern)

            for unknown in unknowns:
                pattern = pattern.replace("{"+unknown+"}", "(.*)")

            m = re.search(pattern,s)

            if m:
                answers = m.groups()
                return dict(zip([i.split(";")[0] for i in unknowns], answers))
            else:
                return None

        dialog = self.Gtk.FileChooserDialog(title = "Open file",
                                            parent = self.win,
                                            action = self.Gtk.FileChooserAction.OPEN,
                                            buttons=["Open", self.Gtk.ResponseType.OK, "Cancel", self.Gtk.ResponseType.CANCEL])

        dialog.set_current_folder(self.systemState["outputDir"])

        filter = self.Gtk.FileFilter()
        filter.set_name('zip files')
        filter.add_pattern('*.zip')
        dialog.add_filter(filter)

        response = dialog.run()

        recipeFileName = dialog.get_filename()
        dialog.destroy()

        if response == self.Gtk.ResponseType.CANCEL:
            return

        if not os.path.exists(recipeFileName):
            print "error: file does not exist"
            return

        recipe = BiotixRecipe(recipeFileName, self.systemState, ignoreTimeStampInRecipeInfo=True)
        outputDirInRecipe = recipe.recipeInfo["outputDir"]

        if recipe.init != "OK":
            print "error: %s" % recipe.init
            return

        outputDir = os.path.dirname(recipeFileName)

        if outputDirInRecipe.endswith("/"):
            outputDir += "/"

        unknowns = extractUnknowns(outputDir, outputDirInRecipe)

        if unknowns:
            recipe.addInfoToRecipe(unknowns)

        recipe.setOutputDirectory(outputDir)
        recipe.addInfoToRecipe({"recipeFileName":os.path.basename(recipeFileName)})

        self._sendSignal({"type": "regenerateFinalReport", "recipe": recipe})

    def _onDeleteEvent(self, widget, event=None):
        self._sendSignal({"type": "quit"})

        return 1 # We do not want the delete event to propagate any further
        # see https://developer.gnome.org/gtk3/stable/GtkWidget.html#GtkWidget-delete-event
        # for details.

    def _quit(self):
        self.Gtk.main_quit()

    def log(self, logText, errorLevel):
        self._addLogLine(logText)
