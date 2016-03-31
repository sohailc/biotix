import multiprocessing
import time
import iniReader
from BiotixGUI import BiotixGUI
import os

softwareVersion = "V01-00"


class BiotixProgram():
    def __init__(self, iniFile):

        self.softwareVersion = softwareVersion

        self.initError = False

        mgr = multiprocessing.Manager()
        self.systemState = mgr.dict()

        readIniResult = iniReader.loadInitialSystemState(iniFile, self.systemState)

        if readIniResult.startswith("NOK"):
            print "Error: INI file not OK: %s" % readIniResult
            self.initError = True
            return

        self.logFile = self.systemState["logFile"]
        self.recipeFolder = self.systemState["recipeFolder"]
        self.outputDirRoot = self.systemState["outputDir"]

        self.GUI = BiotixGUI(self)
        self.GUI.start()

        self.quit = False
        self.recipe = None

        print "info: Started Biotix software"

    def mainLoop(self):

        import select

        while not self.quit:

            select.select([self.GUI.parentConnection], [], [], 1.0)

            self.handleUserInput()

            if self.recipe:
                self.recipe.process()

                if self.recipe.done:
                    print "info: Recipe successfully executed"
                    self.recipe = None

        self.GUI.quit()

        return

    def handleUserInput(self):

        msg = self.GUI.receiveSignal()

        if not msg:
            return

        if msg["type"] == "execute":

            if self.recipe:
                print "error: can't start recipe when one is already running"
                return

            self.recipe = msg["recipe"]

            if "outputDir" in self.recipe.recipeInfo.keys():
                outputDir = self.recipe.recipeInfo["outputDir"]
            else:
                outputDir = ""

            if not os.path.exists(outputDir) and outputDir != "":

                try:
                    os.mkdir(outputDir)
                    recipeFileName = self.recipe.recipeInfo["recipeFileName"]
                    recipeBaseName = os.path.basename(recipeFileName)
                    copyOfRecipe = os.path.join(outputDir, recipeBaseName)

                    os.system("cp \"{recipeFileName}\" \"{copyOfRecipe}\"".format(recipeFileName=recipeFileName,
                                                                                  copyOfRecipe=copyOfRecipe))

                except OSError:
                    print("error: Do not have permissions to create %s" % outputDir)
                    self.recipe = None
                    return

            msg = self.recipe.start(self)

            if msg != "OK":
                print "error: Recipe error: %s" % msg
                self.recipe = None

        elif msg["type"] == "check":

            checkResult = msg["recipe"].check(self)

            if checkResult == "OK":
                print"info: Recipe is ok"
            else:
                print "error: %s" % checkResult

        elif msg["type"] == "regenerateFinalReport":

            if self.recipe:
                print "error: can't regenerate a report while a recipe is running"
                return

            self.recipe = msg["recipe"]
            result = self.recipe.regenerateFinalReport(self)

            if result != "OK":
                print "error: %s" % result
                self.recipe = None

        elif msg["type"] == "abort":

            if not self.recipe:
                print "error: can't abort recipe when none is running"
            else:
                print "info: Aborting recipe"
                self.recipe.abort(exception=False)
                self.recipe = None

        elif msg["type"] == "quit":

            if not self.recipe:
                print "info: quitting Biotix software"
                self.quit = True
            else:
                print "error: can't quit while recipe is running"

        return


def main():
    thisFileName = os.path.realpath(__file__)

    iniFile = os.path.join(os.path.dirname(thisFileName), "biotix.ini")

    if not os.path.exists(iniFile):
        print "No INI file found!"
        time.sleep(10.0)
        return

    print "using INI file ", iniFile

    program = BiotixProgram(iniFile)

    if not program.initError:
        program.mainLoop()


if __name__ == "__main__":
    main()
