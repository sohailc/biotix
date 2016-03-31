# Introduction Biotix - A python measurement framework

This project implements a Python based measurement framework. At the moment this software works on Linux only with Python 2.7. 

The plug-in architecture of the software makes adding support for new hardware easy. A programmer can develop a plug-in for hardware and call the plug-in from a recipe file. A recipe file is a text file specifying which plug-in needs to be called and what parameters need to be used.

To program a plug-in one creates a sub-class which inherits from an plug-in base class. Each plug-in sub-class implements specific methods which were left as a stub in the base class. These methods check for the availability of hardware, determine if the correct number and type of arguments have been defined in the recipe file, execute the functionality of the plug-in and finally make a chapter in a PDF measurement report.

# Dependencies

The software has few dependencies beyond standard Python modules. However, the following needs to be installed:
1. Gtk3 bindings for Python 2.7
2. h5py for HDF5 support. This is needed for logging measurement data

# Arduino example

To get started with the measurement framework, a small example using an Arduino board has been provided. The sketch file for this example can be found under “arduino_sketches” in this repository.  The Arduino board needs to be hooked-up in the following way for this example to work. 

![alt text](https://github.com/sohailc/biotix/docs/biotix_example_bb.png)

Before the software can run the Arduino recipe, the sketch file needs to be uploaded to the Arduino board. Consult the Arduino manual for guidelines. 

A screen recording showing the software at work with the Arduino device can be seen [here](http://sohailchatoor.com/measurement-automation/). 

