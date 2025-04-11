#!/usr/bin/env/python
# File name   : Speech_Recognition.py
# Website     : www.Adeept.com
# Author      : Adeept
# Date        : 2025/03/13
import subprocess
import time
#  Define the paths to two Python programs to run
program1_path = "./Speech.py"
program2_path = "./Text.py"

# Create two sub processes and run two Python programs separately
process1 = subprocess.Popen(["python3", program1_path])
time.sleep(3)           # Waiting for speech recognition to start
process2 = subprocess.Popen(["python3", program2_path])

# Waiting for two child processes to complete
process1.wait()
process2.wait()