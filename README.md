# Introduction Measurix - A python measurement framework

This project implements a Python based measurement framework which is able to take measurements from heterogeneous devices to combine everything in one visualization, logging, queuing and management platform. A brief schematic overview is given below:

<img src="https://github.com/sohailc/measurix/blob/master/overview.png" height="400" /> 

The plug-in architecture of the software makes adding support for new hardware easy. A programmer can develop a plug-in for hardware and call the plug-in from a recipe file. A recipe file is a text file specifying which plug-in needs to be called and what parameters need to be used.

# Arduino example

To get started with the measurement framework, a small example using an Arduino board has been provided. The sketch file for this example can be found under “arduino_sketches” in this repository.  The Arduino board needs to be hooked-up in the following way for this example to work. 

<img src="https://github.com/sohailc/biotix/blob/master/docs/biotix_example_bb.png" height="400" />

Before the software can run the Arduino recipe, the sketch file needs to be uploaded to the Arduino board. Consult the Arduino manual for guidelines. 

Click on the picture below to view a screen recording showing the software at work with the Arduino device. 
[![ScreenShot](http://sohailchatoor.com/wp-content/uploads/2016/07/vlcsnap-2016-07-17-20h06m09s175.png)](http://sohailchatoor.com/wp-content/uploads/2016/03/recording-020416.mp4?_=1)

In the video we see a recipe running which activated the webcam on my laptop as well as the Arduino. The webcam plugin sends frames to the graphical user interface and the Arduino sends data to be plotted. We see that when I shine light with and LED torch on the light sensitive resistor its resistance goes down as we see in the plots. Similarly, when I turn the knob of the potentiometer its resistance fluctuates accordingly. 

# Recipe Files

Recipe files are zip files which contain two text files: recipeInfo.txt and sequence.txt. Among other things the former file tells the software where the output of the recipe needs to be stored. The sequence file contains recipe execution instructions. The recipe "camera_and_arduino" which we see being run in the video contains the instructions: 

<br>startProcess_webcam(640, 480)</br>
<br>startProcess_arduino()</br>
<br>execute_sleep(30.0)</br>
<br>stopProcess_arduino()</br>
<br>stopProcess_webcam()</br>
