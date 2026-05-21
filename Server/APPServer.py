#!/usr/bin/env/python
# File name   : WebServer.py
# Website     : www.Adeept.com
# Author      : Adeept
# Date        : 2025/03/11
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
import asyncio
import websockets
import Voice_Command
import json
import app
import Voltage
import Buzzer
import subprocess


Angular_deviation = -3
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


functionMode = 0
speed_set = 50
rad = 0.5


scGear = RPIservo.ServoCtrl()
scGear.moveInit()
scGear.start()

modeSelect = 'PT'

init_pwm0 = scGear.initPos[0]
init_pwm1 = scGear.initPos[1]
init_pwm2 = scGear.initPos[2]
init_pwm3 = scGear.initPos[3]
init_pwm4 = scGear.initPos[4]

fuc = functions.Functions()
fuc.setup()
fuc.start()

try:
    ncnn = Voice_Command.Sherpa_ncnn()
    ncnn.start()
    SR = Voice_Command.Speech()
    SR.start()
except:
    pass


player = Buzzer.Player()
player.start()

batteryMonitor = Voltage.BatteryLevelMonitor()
batteryMonitor.start()

curpath = os.path.realpath(__file__)
thisPath = "/" + os.path.dirname(curpath)


def servoPosInit():
    scGear.initConfig(0,init_pwm0,1)
    scGear.initConfig(1,init_pwm1,1)
    scGear.initConfig(2,init_pwm2,1)
    scGear.initConfig(3,init_pwm3,1)
    scGear.initConfig(4,init_pwm4,1)


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

def functionSelect(command_input, response):
    global functionMode
    if 'scan' == command_input:
        functionMode = 1
        if OLED_connection:
            screen.screen_show(5,'SCANNING')
        if modeSelect == 'PT':
            radar_send = fuc.radarScan()
            response['title'] = 'scanResult'
            response['data'] = radar_send
            time.sleep(0.3)

    elif 'findColor' == command_input:
        functionMode = 1
        if OLED_connection:
            screen.screen_show(5,'FindColor')
        if modeSelect == 'PT':
            flask_app.modeselect('findColor')
            flask_app.modeselectApp('APP')

    elif 'motionGet' == command_input:
        functionMode = 1
        if OLED_connection:
            screen.screen_show(5,'MotionGet')
        flask_app.modeselect('watchDog')

    elif 'stopCV' == command_input:
        functionMode = 0
        flask_app.modeselect('none')
        switch.switch(1,0)
        switch.switch(2,0)
        switch.switch(3,0)
        move.motorStop()

    elif 'automatic' == command_input:
        functionMode = 1
        if OLED_connection:
            screen.screen_show(5,'Automatic')
        if modeSelect == 'PT':
            fuc.automatic()
        else:
            fuc.pause()

    elif 'automaticOff' == command_input:
        functionMode = 0
        ws2812.pause()
        fuc.pause()
        move.motorStop()
        time.sleep(0.2)
        move.motorStop()

    elif 'trackLine' == command_input:
        functionMode = 1
        fuc.trackLine()
        if OLED_connection:
            screen.screen_show(5,'TrackLine')

    elif 'trackLineOff' == command_input:
        functionMode = 0
        fuc.pause()
        move.motorStop()
        time.sleep(0.2)
        move.motorStop()

    elif 'police' == command_input:
        functionMode = 1
        if OLED_connection:
            screen.screen_show(5,'Police')
        ws2812.police()
        pass

    elif 'policeOff' == command_input:
        functionMode = 0
        ws2812.breath(75,85,90)
        pass

    elif 'speech' == command_input:
        functionMode = 1
        if OLED_connection:
            screen.screen_show(5,'Speech')
        SR.speech()
        pass

    elif 'speechOff' == command_input:
        functionMode = 0
        SR.pause()
        pass

    elif 'Buzzer_Music' == command_input:
        functionMode = 1
        screen.screen_show(5,'BuzzerMusic')
        player.start_playing()

    elif 'Buzzer_Music_Off' == command_input:
        functionMode = 0
        player.pause()

def switchCtrl(command_input, response):
    if 'Switch_1_on' in command_input:
        switch.switch(1,1)

    elif 'Switch_1_off' in command_input:
        switch.switch(1,0)

    elif 'Switch_2_on' in command_input:
        switch.switch(2,1)

    elif 'Switch_2_off' in command_input:
        switch.switch(2,0)

    elif 'Switch_3_on' in command_input:
        switch.switch(3,1)

    elif 'Switch_3_off' in command_input:
        switch.switch(3,0) 


def robotCtrl(command_input, response):
    clen = len(command_input.split())
    if 'forward' in command_input and clen == 2:
        scGear.moveAngle(0, Angular_deviation)
        move.move(speed_set, 1, "mid")
    
    elif 'backward' in command_input and clen == 2:
        scGear.moveAngle(0, Angular_deviation)
        move.move(speed_set, -1, "mid")

    elif 'left' in command_input and clen == 2:
        scGear.moveAngle(0, 30  * Dv)
        time.sleep(0.15)
        move.move(speed_set, 1, "mid")
        switch.switch(3,1)
        time.sleep(0.15)

    elif 'right' in command_input and clen == 2:
        scGear.moveAngle(0,-30  * Dv)
        time.sleep(0.15)
        move.move(speed_set, 1, "mid")
        switch.switch(2,1)
        time.sleep(0.15)

    elif 'DTS' in command_input:
        scGear.moveAngle(0, 0)
        move.motorStop()
        switch.switch(2,0)
        switch.switch(3,0)

    elif 'lookleft' == command_input.lower():
        scGear.singleServo(1, 1, 7)

    elif 'lookright' == command_input.lower():
        scGear.singleServo(1,-1, 7)

    elif 'LRstop' in command_input:
        scGear.stopWiggle()


    elif 'armup' == command_input.lower():
        scGear.singleServo(2, -1, 7)

    elif 'armdown' == command_input.lower():
        scGear.singleServo(2, 1, 7)

    elif 'armstop' in command_input.lower():
        scGear.stopWiggle()



    elif 'handup' == command_input.lower():
        scGear.singleServo(3, 1, 7)

    elif 'handdown' == command_input.lower():
        scGear.singleServo(3, -1, 7)

    elif 'handstop' in command_input.lower():
        scGear.stopWiggle()

    elif 'grab' == command_input.lower():
        scGear.singleServo(4, -1, 7)

    elif 'loose' == command_input.lower():
        scGear.singleServo(4, 1, 7)

    elif 'glstop' == command_input.lower():
        scGear.stopWiggle()

    elif 'home' == command_input.lower():
        scGear.moveServoInit([0])
        scGear.moveServoInit([1])
        scGear.moveServoInit([2])
        scGear.moveServoInit([3])
        scGear.moveServoInit([4])

def configPWM(command_input, response):
    global init_pwm0, init_pwm1, init_pwm2, init_pwm3, init_pwm4

    if 'SiLeft' in command_input:
        numServo = int(command_input[7:])
        if numServo == 0:
            init_pwm0 -= 2
            scGear.setPWM(0,init_pwm0)
        elif numServo == 1:
            init_pwm1 -= 2
            scGear.setPWM(1,init_pwm1)
        elif numServo == 2:
            init_pwm2 -= 2
            scGear.setPWM(2,init_pwm2)
        elif numServo == 3:
            init_pwm3 -= 2
            scGear.setPWM(3,init_pwm3)
        elif numServo == 4:
            init_pwm4 -= 2
            scGear.setPWM(4,init_pwm4)

    if 'SiRight' in command_input:
        numServo = int(command_input[8:])
        if numServo == 0:
            init_pwm0 += 2
            scGear.setPWM(0,init_pwm0)
        elif numServo == 1:
            init_pwm1 += 2
            scGear.setPWM(1,init_pwm1)
        elif numServo == 2:
            init_pwm2 += 2
            scGear.setPWM(2,init_pwm2)
        elif numServo == 3:
            init_pwm3 += 2
            scGear.setPWM(3,init_pwm3)
        elif numServo == 4:
            init_pwm4 += 2
            scGear.setPWM(4,init_pwm4)

    if 'PWMMS' in command_input:
        numServo = int(command_input[6:])
        scGear.moveAngle(numServo, 0)


    if 'PWMINIT' == command_input:
        print(init_pwm1)
        servoPosInit()
    elif 'PWMD' in command_input:
        init_pwm0 = 90 
        init_pwm1 = 90 
        init_pwm2 = 90 
        init_pwm3 = 90 
        init_pwm4 = 90
        for i in range(5):
            scGear.moveAngle(i, 0)

async def recv_msg(websocket):
    global speed_set, modeSelect
    move.setup()

    while True: 
        response = {
            'status' : 'ok',
            'title' : '',
            'data' : None
        }

        data = ''
        data = await websocket.recv()
        try:
            data = json.loads(data)
        except Exception as e:
            print('not A JSON')

        if not data:
            continue

        if isinstance(data,str):
            robotCtrl(data, response)

            switchCtrl(data, response)

            functionSelect(data, response)

            configPWM(data, response)

            if 'get_info' == data:
                response['title'] = 'get_info'
                response['data'] = [info.get_cpu_tempfunc(), info.get_cpu_use(), info.get_ram_info(),batteryMonitor.get_battery_percentage()]

            if 'wsB' in data:
                try:
                    set_B=data.split()
                    speed_set = int(set_B[1])*10
                except:
                    pass

            #CVFL
            elif 'CVFL' == data:
                flask_app.modeselect('findlineCV')

            elif 'CVFLColorSet' in data:
                color = int(data.split()[1])
                flask_app.camera.colorSet(color)

            elif 'CVFLL1' in data:
                pos = int(data.split()[1]) / 100 * 480
                flask_app.camera.linePosSet_1(pos)

            elif 'CVFLL2' in data:
                pos = int(data.split()[1]) / 100 * 480
                flask_app.camera.linePosSet_2(pos)

        elif(isinstance(data,dict)):
            color = data['data']
            if "title" in data and data['title'] == "findColorSet":
                flask_app.colorFindSetApp(color[0],color[1],color[2])
            elif data['lightMode'] == "breath":  
                ws2812.breath(color[0],color[1],color[2])
            elif data['lightMode'] == "flowing":
                ws2812.flowing(color[0],color[1],color[2])
            elif data['lightMode'] == "rainbow":
                ws2812.rainbow(color[0],color[1],color[2])
            elif data['lightMode'] == "police":
                ws2812.police()

        if not functionMode:
            if OLED_connection:
                screen.screen_show(5,'Functions OFF')
        else:
            pass
        print(data)
        response = json.dumps(response)
        await websocket.send(response)

async def main_logic(websocket, path):
    await recv_msg(websocket)

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
    switch.switchSetup()
    switch.set_all_switch_off()

    show_wlan0_ip()
    time.sleep(0.5)
    show_network_mode()

    global flask_app
    flask_app = app.webapp()
    flask_app.startthread()
    ws2812 = robotLight.Adeept_SPI_LedPixel(16, 255)
    try:
        if ws2812.check_spi_state() != 0:
            ws2812.start()
            ws2812.breath(70,70,255)
    except:
        ws2812.led_close()
        pass

    while  1:
        try:                  #Start server,waiting for client
            start_server = websockets.serve(main_logic, '0.0.0.0', 8888)
            asyncio.get_event_loop().run_until_complete(start_server)
            print('waiting for connection...')
            break
        except Exception as e:
            print(e)
            ws2812.set_all_led_color_data(0,0,0)
            ws2812.show()

        try:
            ws2812.set_all_led_color_data(0,80,255)
            ws2812.show()
        except:
            pass
    try:
        asyncio.get_event_loop().run_forever()
    except Exception as e:
        print(e)
        ws2812.set_all_led_color_data(0,0,0)
        ws2812.show()
        move.destroy()
