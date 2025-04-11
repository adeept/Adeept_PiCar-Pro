#!/usr/bin/env python3
# File name   : Voice_Command.py
# Author      : Adeept
# Date        : 2025/03/12
import time
import os

import threading
import Move as move
import RPIservo
import subprocess

scGear = RPIservo.ServoCtrl()
scGear.start()
scGear.moveInit()

move.setup()
posUD = 0

class Sherpa_ncnn(threading.Thread):
    def __init__(self, *args, **kwargs):
        super(Sherpa_ncnn, self).__init__(*args, **kwargs)

    def run(self):
        try:
            result = subprocess.run(['sudo', 'python', '/home/pi/Adeept_PiCar-Pro/Server/VoiceIdentify.py'], capture_output=True, text=True)
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
        except Exception as e:
            print(f"Error executing command: {e}")

class Speech(threading.Thread):
    def __init__(self, *args, **kwargs):
        self.SpeechMode = 'none'
        self.file_position = 0
        super(Speech, self).__init__(*args, **kwargs)
        self.__flag = threading.Event()
        self.__flag.clear()

    def pause(self):
        self.SpeechMode = 'none'
        self.file_position = 0
        scGear.moveInit()
        self.__flag.clear()

    def resume(self):
        self.__flag.set()

    def speech(self):
        self.clear_output()
        self.SpeechMode = 'speech'
        self.resume()

    def functionGoing(self):
        if self.SpeechMode == 'none':
            self.pause()
        elif self.SpeechMode == 'speech':
            self.SpeechProcessing()

    def clear_output(self):
        try:
            with open("output.txt", "w") as file:
                file.write("")
            print("Output file cleared.")
        except Exception as e:
            print(f"Error clearing output file: {e}")

    def run(self):
        while True:
            self.__flag.wait()
            self.functionGoing()
            time.sleep(2)

    def SpeechProcessing(self):

        try:
            with open("output.txt", "r") as file:
                file.seek(self.file_position)
                new_lines = file.readlines()
                if new_lines:
                    #String processing: remove spaces, convert to lowercase letters, and finally match the commands.
                    line = new_lines[len(new_lines) - 1].replace(" ", "").lower()
                    if ':' in line:
                        line = line[line.index(':') + 1:]
                    print(f"The information recognized by the speech recognition is: {str(line)}")
                    for keyword in ["lookleft", "lookright", "armup", "armdown", "handup", "handdown",
                                        "grab", "loose", "stop"]:
                        if keyword in line:
                            if keyword == 'lookleft':
                                scGear.singleServo(1, 1, 30)
                                time.sleep(0.1)
                                print('Your command is "lookleft" ')
                                break
                            elif keyword == 'lookright':
                                scGear.singleServo(1, -1, 30)
                                time.sleep(0.1)
                                print('Your command is "lookright" ')
                                break
                            elif keyword == 'armup':
                                scGear.singleServo(2, -1, 30)
                                time.sleep(0.1)
                                print('Your command is "armup" ')
                                break
                            elif keyword == 'armdown':
                                scGear.singleServo(2, 1, 30)
                                time.sleep(0.1)
                                print('Your command is "armdown" ')
                                break
                            elif keyword == 'handup':
                                scGear.singleServo(3, 1, 30)
                                time.sleep(0.1)
                                print('Your command is "handup" ')
                                break
                            elif keyword == 'handdown':
                                scGear.singleServo(3, -1, 30)
                                time.sleep(0.1)
                                print('Your command is "handdown" ')
                                break
                            elif keyword == 'grab':
                                scGear.singleServo(4, -1, 30)
                                time.sleep(0.1)
                                print('Your command is "grab" ')
                                break
                            elif keyword == 'loose':
                                scGear.singleServo(4, 1, 30)
                                time.sleep(0.1)
                                print('Your command is "loose" ')
                                break
                            elif keyword == 'stop':
                                scGear.moveInit()
                                time.sleep(0.3)
                                print('Your command is "stop" ')
                                break
                    self.file_position = file.tell()
        except Exception as e:
            print(f"Error reading output file: {e}")
        time.sleep(0.5)


if __name__ == '__main__':
    try:
        ncnn = Sherpa_ncnn()
        ncnn.start()

        fuc = Speech()
        fuc.start()  
        fuc.speech()  
        while True:
            pass
    except KeyboardInterrupt:
        move.motorStop()
