#!/usr/bin/env/python
# File name   : Text.py
# Website     : www.Adeept.com
# Author      : Adeept
# Date        : 2025/03/13
import time

file_position = 0
while True:
    with open("output.txt", "r") as file: # Read the file named “output.txt”
        file.seek(file_position)
        new_lines = file.readlines() # Read all lines from the current file pointer position to the end of the file
        if new_lines:
            for line in new_lines:
                if "Started" in line:
                    print(line.split("Started")[-1].strip() + "\n")
                elif file_position > 0:  # Ensure we print lines after the first "Started"
                    print(line.strip())
            file_position = file.tell()
    time.sleep(3)  # Read every 3 second