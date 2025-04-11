#!/usr/bin/env python3
# File name   : functions.py
# Description : Control Functions
# Author	  : Adeept
# Date		  : 2025/03/12
import time
from board import SCL, SDA
import busio
from adafruit_motor import servo
from adafruit_pca9685 import PCA9685

import threading
import os
import json
import Ultra as ultra
import Kalman_Filter as Kalman_filter
import Move as move
import RPIservo
from gpiozero import InputDevice

scGear = RPIservo.ServoCtrl()
scGear.start()
Angular_deviation = 5
Dv = -1 #Directional variable

move.setup()
kalman_filter_X =  Kalman_filter.Kalman_filter(0.01,0.1)


curpath = os.path.realpath(__file__)
thisPath = "/" + os.path.dirname(curpath)

def num_import_int(initial):
	global r
	with open(thisPath+"/RPIservo.py") as f:
		for line in f.readlines():
			if(line.find(initial) == 0):
				r=line
	begin=len(list(initial))
	snum=r[begin:]
	n=int(snum)
	return n

pwm0_direction = 1
pwm0_init = num_import_int('init_pwm0 = ')
pwm0_max  = 180
pwm0_min  = 0
pwm0_pos  = pwm0_init



line_pin_left = 22
line_pin_middle = 27
line_pin_right = 17



class Functions(threading.Thread):
	def __init__(self, *args, **kwargs):
		self.functionMode = 'none'
		self.steadyGoal = 0

		self.scanNum = 3
		self.scanList = [0,0,0]
		self.scanPos = 1
		self.scanDir = 1
		self.rangeKeep = 0.7
		self.scanRange = 100
		self.scanServo = 1
		self.turnServo = 2
		self.turnWiggle = 200


		super(Functions, self).__init__(*args, **kwargs)
		self.__flag = threading.Event()
		self.__flag.clear()


	def pwmGenOut(self, angleInput):
		return int(angleInput)

	def setup(self):
		global track_line_left, track_line_middle,track_line_right
		track_line_left = InputDevice(pin=line_pin_right)
		track_line_middle = InputDevice(pin=line_pin_middle)
		track_line_right = InputDevice(pin=line_pin_left)

	def radarScan(self):
		pwm0_min = -90
		pwm0_max =  90

		scan_speed = 2
		result = []

		pwm0_pos = pwm0_max
		scGear.moveAngle(1, 0)
		time.sleep(0.8)
		while pwm0_pos>pwm0_min:
			pwm0_pos-=scan_speed
			scGear.moveAngle(1, pwm0_pos)
			dist = ultra.checkdist()
			if dist > 200:
				continue
			theta = 90 + pwm0_pos 
			result.append([dist, theta])
			time.sleep(0.02)
	
		scGear.set_angle(1, 90)
		return result


	def pause(self):
		self.functionMode = 'none'
		move.motorStop()
		self.__flag.clear()


	def resume(self):
		self.__flag.set()


	def automatic(self):
		self.functionMode = 'Automatic'
		self.resume()


	def trackLine(self):
		self.functionMode = 'trackLine'
		self.resume()


	def keepDistance(self):
		self.functionMode = 'keepDistance'
		self.resume()


	def steady(self,goalPos):
		self.functionMode = 'Steady'
		self.steadyGoal = goalPos
		self.resume()

	def trackLineProcessing(self):
		status_right = track_line_right.value
		status_middle = track_line_middle.value
		status_left = track_line_left.value
		if status_middle == 0:
			if status_left == 0 and status_right == 1:

				scGear.set_angle(0, 30 * Dv - Angular_deviation + 90)
				move.move(25,1,"left")
			elif status_left == 1 and status_right == 0:
				scGear.set_angle(0, -30 * Dv - Angular_deviation + 90)
				move.move(25,1,"left")
			else:
				scGear.set_angle(0, 90 - Angular_deviation)
				move.move(25,1,"mid")
		elif status_left == 0:
			scGear.set_angle(0,30 * Dv - Angular_deviation + 90)
			move.move(25,1,"left")
		elif status_right == 0:
			scGear.set_angle(0, -30 * Dv - Angular_deviation + 90)
			move.move(25,1,"left")
		else:
			scGear.set_angle(0,90 - Angular_deviation)
			move.move(25,1,"no")
		print(status_left,status_middle,status_right)
		time.sleep(0.1)

	def distRedress(self): 
		mark = 0
		distValue = ultra.checkdist()
		while True:
			distValue = ultra.checkdist()
			if distValue > 900:
				mark +=  1
			elif mark > 5 or distValue < 900:
					break
			print(distValue)
		return round(distValue,2)

	def automaticProcessing(self):
		scGear.moveAngle(1, 0)
		dist = self.distRedress()
		time.sleep(0.2)
		if dist >= 40:
			scGear.moveAngle(0, 0)
			time.sleep(0.2)
			move.move(35, 1, "mid")
		elif dist > 20 and dist < 40:	
			scGear.moveAngle(1, 30)
			move.move(0, 1, "mid")
			time.sleep(0.3)
			distLeft = self.distRedress()
			self.scanList[0] = distLeft
			scGear.moveAngle(1, -30)
			time.sleep(0.3)
			distRight = self.distRedress()
			self.scanList[1] = distRight
			print(self.scanList)
			scGear.moveAngle(1, 0)
			if self.scanList[0] >= self.scanList[1]:
				scGear.moveAngle(0, -30  * Dv - Angular_deviation)
				time.sleep(0.3)
				move.move(35,1,"left")
				time.sleep(1)
			else:
				scGear.moveAngle(0, 30 * Dv - Angular_deviation)
				time.sleep(0.3)
				move.move(35, 1, "right")
				time.sleep(1)
		else:
			move.move(35, -1, "mid")
			time.sleep(1)

	def keepDisProcessing(self):
		distanceGet = ultra.checkdist()
		if distanceGet > (self.rangeKeep/2+0.1):
			move.move(80, 1, "mid")
		elif distanceGet < (self.rangeKeep/2-0.1):
			move.move(80, -1, "mid")
		else:
			move.motorStop()


	def functionGoing(self):
		if self.functionMode == 'none':
			self.pause()
		elif self.functionMode == 'Automatic':
			self.automaticProcessing()
		elif self.functionMode == 'trackLine':
			self.trackLineProcessing()
		elif self.functionMode == 'keepDistance':
			self.keepDisProcessing()


	def run(self):
		while 1:
			self.__flag.wait()
			self.functionGoing()
			pass


if __name__ == '__main__':
	pass
	try:
		fuc=Functions()
		fuc.setup()
		while True:
			fuc.radarScan()
	except KeyboardInterrupt:

			move.motorStop()
