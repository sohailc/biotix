#include <stdlib.h>
#include "array.h" 

#ifndef SERIAL_RATE
#define SERIAL_RATE         115200
#endif

#ifndef SERIAL_TIMEOUT
#define SERIAL_TIMEOUT      5
#endif

#ifndef NUMBER_OF_CHANNELS
#define NUMBER_OF_CHANNELS  2
#endif

Array input_buffers[NUMBER_OF_CHANNELS];

void add_to_array(Array *n, int value){
  
  if (n->length < MAX_ARRAY_LENGTH)
    n->length++;
  
  memmove(n->data+1, n->data, sizeof(int)*(MAX_ARRAY_LENGTH-1));
  n->data[0] = value;
  
}

void print_array_to_serial(Array *n)
{
  int i;
  for (i=0; i<n->length; i++)
  {
    Serial.print(n->data[i]);
    Serial.print(",");
  }
    
  Serial.print("\r\n");
  n->length = 0;
}

void parse_command(String command)
{
  char cmd = command.charAt(0);
  String value_str = command.substring(1);
  int value = value_str.toInt();
      
  switch(cmd)
  {
    case 'r': // read the input buffer
      print_array_to_serial(&input_buffers[0]);
      print_array_to_serial(&input_buffers[1]);
      break;
    case 'n': // get the name of the device
      Serial.println("Arduino Uno");
      break;
  }
}

void setup() {
  // put your setup code here, to run once:
  Serial.begin(SERIAL_RATE);
  Serial.setTimeout(SERIAL_TIMEOUT);
  
  pinMode(0, INPUT);
  pinMode(1, INPUT);
  
}

void loop() {
  
  if (Serial.available())
  {
      String command = Serial.readString();
      parse_command(command);
  }
  
  int i;
  int sensor_value;
  for (i=0;i<2;i++)
  {
    sensor_value = analogRead(i);
    add_to_array(&input_buffers[i], sensor_value);
  }
  
}


