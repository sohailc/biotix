
import re
import os
import time

def isStringLiteral(string):

    for c in ["\"", "\'"]:

        if string.startswith(c) and string.endswith(c):
            return True

    return False

def loadInitialSystemState(fname, settings):

    if not os.path.exists(fname):
        return "File %s does not exist" % fname, settings

    fh = open(fname, "r")

    sectionName = ""
    sectionDict = dict()

    msg = "OK"
    for line in fh.readlines():

        if line.strip() == "":
            continue

        m = re.search("\[(.*)\]", line)

        if m:

            if sectionName != "":
                settings[sectionName] = sectionDict

            sectionName = m.groups()[0]
            if sectionName != "General":
                sectionDict = dict()
            continue

        if not ":" in line:
            msg = "NOK: line %s not in format 'setting: value'"%line
            break

        parts = line.split(":")
        setting = parts[0].strip()
        valueStr = ":".join(parts[1:]).strip()

        if not isStringLiteral(valueStr):
            valuesStr = valueStr.split(",")
        else:
            valuesStr = [valueStr]

        values = []

        for s in valuesStr:

            if "." in s or "E" in s.upper():
                tp = float
            else:
                tp = int

            try:
                v = tp(s)
            except:
                v = s.strip().strip("\"").strip("\'")

            values.append(v)

        if len(values) == 1:
            values = values[0]

        if sectionName == "":
            msg = "NOK: line %s not in any section"%line
            break

        if sectionName == "General":
            settings[setting] = values
        else:
            sectionDict[setting] = values

    fh.close()

    settings["time"] = {"currentValue": time.time(), "unit":"unix time"}

    return msg