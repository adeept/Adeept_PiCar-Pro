#!/usr/bin/env/python
# File name   : GUIServer.py
# Website     : www.Adeept.com
# Author      : Adeept
# Date		  : 2025/03/12

import time
import threading
import Move as move
import os
import Info as info
import RPIservo

import Functions as functions
import RobotLight as robotLight
import Switch as switch
import socket
import ast
import FPV
import VoiceIdentify
import json
import subprocess

Dv = -1 #Directional variable
OLED_connection = 1
try:
    import OLED
    screen = OLED.OLED_ctrl()
    screen.start()
    screen.screen_show(1, 'ADEEPT.COM')
except:
    OLED_connection = 0
    print('OLED disconnected')
    pass

mark_test = 0

functionMode = 0
speed_set = 25
rad = 0.5
turnWiggle = 60

direction_command = 'no'
turn_command = 'no'


scGear = RPIservo.ServoCtrl()
scGear.moveInit()

P_sc = RPIservo.ServoCtrl()
P_sc.start()

T_sc = RPIservo.ServoCtrl()
T_sc.start()

H_sc = RPIservo.ServoCtrl()
H_sc.start()

G_sc = RPIservo.ServoCtrl()
G_sc.start()

init_pwm = []
for i in range(8):
    init_pwm.append(scGear.initPos[i])
init_pwm0 = scGear.initPos[0]
init_pwm1 = scGear.initPos[1]
init_pwm2 = scGear.initPos[2]
init_pwm3 = scGear.initPos[3]
init_pwm4 = scGear.initPos[4]

fuc = functions.Functions()
fuc.setup()
fuc.start()
 
curpath = os.path.realpath(__file__)
thisPath = "/" + os.path.dirname(curpath)

def servoPosInit():
    scGear.initConfig(0,init_pwm[0],1)
    P_sc.initConfig(1,init_pwm[1],1)
    T_sc.initConfig(2,init_pwm[2],1)
    H_sc.initConfig(3,init_pwm[3],1)
    G_sc.initConfig(4,init_pwm[4],1)


def replace_num(initial,new_num):   #Call this function to replace data in '.txt' file
    global r
    newline=""
    str_num=str(new_num)
    with open(thisPath+"/RPIservo.py","r") as f:
        for line in f.readlines():
            if(line.find(initial) == 0):
                line = initial+"%s" %(str_num+"\n")
            newline += line
    with open(thisPath+"/RPIservo.py","w") as f:
        f.writelines(newline)


def FPV_thread():
    global fpv
    fpv=FPV.FPV()
    fpv.capture_thread(addr[0])


def functionSelect(command_input, response):
    global functionMode
    if 'scan' == command_input:
        if OLED_connection:
            screen.screen_show(5,'SCANNING')
        radar_send = fuc.radarScan()
        radar_array = []
        for i in range(len(radar_send)):
            radar_array.append(radar_send[i][0])
        response['title'] = 'scanResult'
        response['data'] = radar_array
        time.sleep(0.3)

    elif 'findColor' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FindColor')
        functionMode = 2
        fpv.FindColor(1)
        tcpCliSock.send(('FindColor').encode())

    elif 'motionGet' == command_input:
        if OLED_connection:
            screen.screen_show(5,'MotionGet')
        functionMode = 3
        fpv.WatchDog(1)
        tcpCliSock.send(('WatchDog').encode())

    elif 'stopCV' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        fpv.FindColor(0)
        fpv.WatchDog(0)
        FPV.FindLineMode = 0
        move.motorStop()
        switch.switch(1,0)
        switch.switch(2,0)
        switch.switch(3,0)

    elif 'police' == command_input:
        if OLED_connection:
            screen.screen_show(5,'POLICE')
        ws2812.police()

    elif 'policeOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        ws2812.pause()

    elif 'automatic' == command_input:
        if OLED_connection:
            screen.screen_show(5,'Automatic')
        fuc.automatic()

    elif 'automaticOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        fuc.pause()

    elif 'trackLine' == command_input:
        functions.last_status = None
        fuc.trackLine()
        if OLED_connection:
            screen.screen_show(5,'TrackLine')

    elif 'trackLineOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        fuc.pause()

    elif 'speech' == command_input:
        if OLED_connection:
            screen.screen_show(5,'Speed')
        speech.speech()
        pass

    elif 'speechOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        speech.pause()
        pass
    
    elif 'keepDistance' == command_input:
        functions.last_status = 25
        fuc.keepDistance()
        if OLED_connection:
            screen.screen_show(5,'KeepDistance')

    elif 'keepDistanceOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        fuc.pause()
        move.motorStop()
        time.sleep(0.5)
        move.motorStop()

def switchCtrl(command_input):
    if 'Switch_1_on' in command_input:
        switch.switch(1,1)

    elif 'Switch_1_off' in command_input:
        switch.switch(1,0)

    elif 'Switch_2_on' in command_input:
        switch.switch(2,1)
        switch.switch(1,1)

    elif 'Switch_2_off' in command_input:
        switch.switch(2,0)

    elif 'Switch_3_on' in command_input:
        switch.switch(3,1)

    elif 'Switch_3_off' in command_input:
        switch.switch(3,0) 


def robotCtrl(command_input):
    global direction_command, turn_command
    if 'forward' == command_input:
        direction_command = 'forward'
        move.move(speed_set, 1, "mid")
    
    elif 'backward' == command_input:
        direction_command = 'backward'
        move.move(speed_set, -1, "mid")

    elif 'DS' in command_input:
        direction_command = 'no'
        move.motorStop()

    elif 'left' == command_input:
        turn_command = 'left'
        scGear.moveAngle(0, 30  * Dv)
        time.sleep(0.15)
        move.move(30, 1, "mid")
        switch.switch(1,1)
        time.sleep(0.15)

    elif 'right' == command_input:
        turn_command = 'right'
        scGear.moveAngle(0,-30  * Dv)
        time.sleep(0.15)
        move.move(30, 1, "mid")
        switch.switch(2,1)
        time.sleep(0.15)

    elif 'TS' in command_input:
        turn_command = 'no'
        scGear.moveAngle(0, 0)
        move.motorStop()
        switch.switch(2,0)
        switch.switch(1,0)

    elif 'lookleft' == command_input:
        P_sc.singleServo(1, 1, 5)

    elif 'lookright' == command_input:
        P_sc.singleServo(1, -1, 5)

    elif 'LRstop' in command_input:
        P_sc.stopWiggle()

    elif 'armup' == command_input:
        T_sc.singleServo(2, -1, 5)

    elif 'armdown' == command_input:
        T_sc.singleServo(2,  1, 5)

    elif 'armstop' in command_input:
        T_sc.stopWiggle()

    elif 'handup' == command_input:
        H_sc.singleServo(3, 1, 5)

    elif 'handdown' == command_input:
        H_sc.singleServo(3, -1, 5)

    elif 'HAstop' in command_input:
        H_sc.stopWiggle()

    elif 'grab' == command_input:
        G_sc.singleServo(4, -1, 5)

    elif 'loose' == command_input:
        G_sc.singleServo(4, 1, 5)

    elif 'stop' == command_input:
        G_sc.stopWiggle()

    elif 'home' == command_input:
        P_sc.moveServoInit([1])
        T_sc.moveServoInit([2])
        H_sc.moveServoInit([3])
        G_sc.moveServoInit([4])

def robotCtrl_speech(command_input, response):
    if 'stop' in command_input:
        scGear.stopWiggle()
    elif 'lookleft' == command_input:
        P_sc.singleServo(1, 1, 7)

    elif 'lookright' == command_input:
        P_sc.singleServo(1,-1, 7)

    elif 'armup' == command_input:
        T_sc.singleServo(2, -1, 7)

    elif 'armdown' == command_input:
        T_sc.singleServo(2, 1, 7)

    elif 'handup' == command_input:
        H_sc.singleServo(3, 1, 7)

    elif 'handdown' == command_input:
        H_sc.singleServo(3, -1, 7)

    elif 'grab' == command_input:
        G_sc.singleServo(4, -1, 7)

    elif 'loose' == command_input:
        G_sc.singleServo(4, 1, 7)
        
    elif 'home' == command_input:
        scGear.moveServoInit([0])
        P_sc.moveServoInit([1])
        T_sc.moveServoInit([2])
        H_sc.moveServoInit([3])


def configPWM(command_input):
    global init_pwm0, init_pwm1, init_pwm2, init_pwm3, init_pwm4

    if 'SiLeft' in command_input:
        numServo = int(command_input[7:])
        if numServo == 0:
            init_pwm0 -= 5
            T_sc.setPWM(0,init_pwm0)
        elif numServo == 1:
            init_pwm1 -= 5
            P_sc.setPWM(1,init_pwm1)
        elif numServo == 2:
            init_pwm2 -= 5
            scGear.setPWM(2,init_pwm2)
        elif numServo == 3:
            init_pwm3 -= 5
            P_sc.setPWM(1,init_pwm3)
        elif numServo == 4:
            init_pwm4 -= 5
            scGear.setPWM(2,init_pwm4)

    if 'SiRight' in command_input:
        numServo = int(command_input[8:])
        if numServo == 0:
            init_pwm0 += 5
            T_sc.setPWM(0,init_pwm0)
        elif numServo == 1:
            init_pwm1 += 5
            P_sc.setPWM(1,init_pwm1)
        elif numServo == 2:
            init_pwm2 += 5
            scGear.setPWM(2,init_pwm2)
        elif numServo == 3:
            init_pwm3 += 5
            P_sc.setPWM(1,init_pwm3)
        elif numServo == 2:
            init_pwm4 += 5
            scGear.setPWM(2,init_pwm4)

    if 'PWMMS' in command_input:
        numServo = int(command_input[6:])
        scGear.moveAngle(numServo, 0)

    if 'PWMINIT' == command_input:
        servoPosInit()
    elif 'PWMD' in command_input:
        init_pwm0 = 90 
        init_pwm1 = 90 
        init_pwm2 = 90 
        init_pwm3 = 90 
        init_pwm4 = 90
        for i in range(5):
            scGear.moveAngle(i, 0)

def recv_msg(tcpCliSock):
    global speed_set
    move.setup()

    while True: 
        response = {
            'status' : 'ok',
            'title' : '',
            'data' : None
        }


        data = tcpCliSock.recv(BUFSIZ).decode()
        print(data)

        if not data:
            continue


        if isinstance(data,str):
            robotCtrl(data)

            switchCtrl(data)

            functionSelect(data, response)

            configPWM(data)

            if 'get_info' == data:
                response['title'] = 'get_info'
                response['data'] = [info.get_cpu_tempfunc(), info.get_cpu_use(), info.get_ram_info()]

            if 'wsB' in data:
                try:
                    set_B=data.split()
                    speed_set = int(set_B[1])
                except:
                    pass

            #CVFL
            elif 'CVFL' == data:
                FPV.FindLineMode = 1
                tcpCliSock.send(('CVFL_on').encode())


            elif 'CVFLColorSet' in data:
                color = int(data.split()[1])
                FPV.lineColorSet = color

            elif 'CVFLL1' in data:
                try:
                    set_lip1=data.split()
                    lip1_set = int(set_lip1[1])
                    FPV.linePos_1 = lip1_set
                except:
                    pass

            elif 'CVFLL2' in data:
                try:
                    set_lip2=data.split()
                    lip2_set = int(set_lip1[1])
                    FPV.linePos_2 = lip2_set
                except:
                    pass

            elif 'CVFLSP' in data:
                try:
                    set_err=data.split()
                    err_set = int(set_lip1[1])
                    FPV.findLineError = err_set
                except:
                    pass

            elif 'defEC' in data:#Z
                fpv.defaultExpCom()

            elif 'findColorSet' in data:
                try:
                    command_dict = ast.literal_eval(data)
                    if 'data' in command_dict and len(command_dict['data']) == 3:
                        r, g, b = command_dict['data']
                        fpv.colorFindSet(b, g, r)
                        print(f"color: r={r}, g={g}, b={b}")
                except (SyntaxError, ValueError):
                    print("The received string format is incorrect and cannot be parsed.")

        else:
            pass
        response = json.dumps(response)
        tcpCliSock.sendall(response.encode())

def show_wlan0_ip():
    try:
        if OLED_connection:
            result = subprocess.run(
                "ifconfig wlan0 | grep 'inet ' | awk '{print $2}'",
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8'
            ) 
            screen.screen_show(2, "IP:" + result.stdout.strip())
    except Exception as e:
        pass

def show_network_mode():
    try:
        if OLED_connection:
            result = subprocess.run(
                "if iw dev wlan0 link | grep -q 'Connected'; then echo 'Station Mode'; else echo 'AP Mode'; fi",
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8'
            )
            screen.screen_show(3, result.stdout.strip())
    except Exception as e:
        pass

if __name__ == '__main__':
    global speech
    try:
        switch.switchSetup()
        switch.set_all_switch_off()                                  
        show_wlan0_ip()
        time.sleep(0.5)
        show_network_mode()
        ws2812=robotLight.Adeept_SPI_LedPixel(16, 255)
        if ws2812.check_spi_state() != 0:
            ws2812.start()
            ws2812.breath(70,70,255)                       # Set the brightness of lights.
    except:
        ws2812.led_close()
        pass

    try:
        speech = VoiceIdentify.Speech(control_callback = robotCtrl_speech)
        speech.daemon = True
        speech.start()
    except Exception as e:
        pass

    HOST = ''
    PORT = 10223                              #Define port serial 
    BUFSIZ = 1024                             #Define buffer size
    ADDR = (HOST, PORT)
   
    try:                  #Start server,waiting for client
        tcpSerSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcpSerSock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        tcpSerSock.bind(ADDR)
        tcpSerSock.listen(5)                   
        print("Waiting for client connection")
        tcpCliSock, addr = tcpSerSock.accept()
        print("Connected to the client :" + str(addr))
        fps_threading=threading.Thread(target=FPV_thread)         #Define a thread for FPV and OpenCV
        fps_threading.daemon = True                         #'True' means it is a front thread,it would close when the mainloop() closes
        fps_threading.start()   
        recv_msg(tcpCliSock)  
    except Exception as e:
        print(e)


