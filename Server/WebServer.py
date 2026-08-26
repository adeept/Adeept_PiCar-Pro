#!/usr/bin/env/python
# File name   : WebServer.py
# Website     : www.Adeept.com
# Author      : Adeept
import time
import Move as move
import os
import Info as info
import RPIservo
import Functions as functions
import RobotLight as robotLight
import Switch as switch
import asyncio
from websockets.asyncio.server import serve
import VoiceIdentify
import json
import app
import Voltage
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


functionMode = 0
speed_set = 50
rad = 0.5


scGear = RPIservo.ServoCtrl()
scGear.moveInit()
scGear.start()

init_pwm0 = scGear.initPos[0]
init_pwm1 = scGear.initPos[1]
init_pwm2 = scGear.initPos[2]
init_pwm3 = scGear.initPos[3]
init_pwm4 = scGear.initPos[4]

fuc = functions.Functions()
fuc.setup()
fuc.start()

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

def functionSelect(command_input, response):
    if 'scan' == command_input:
        if OLED_connection:
            screen.screen_show(5,'SCANNING')
        radar_send = fuc.radarScan()
        response['title'] = 'scanResult'
        response['data'] = radar_send
        time.sleep(0.3)

    elif 'findColor' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FindColor')
        flask_app.modeselect('findColor')

    elif 'motionGet' == command_input:
        if OLED_connection:
            screen.screen_show(5,'MotionGet')
        flask_app.modeselect('watchDog')

    elif 'stopCV' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        flask_app.modeselect('none')
        switch.switch(1,0)
        switch.switch(2,0)
        switch.switch(3,0)
        move.motorStop()

    elif 'automaticOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        ws2812.pause()
        fuc.pause()
        move.motorStop()
        time.sleep(0.3)
        move.motorStop()

    elif 'automatic' == command_input:
        if OLED_connection:
            screen.screen_show(5,'Automatic')
        fuc.automatic()


    elif 'trackLine' == command_input:
        functions.last_status = None
        fuc.trackLine()
        if OLED_connection:
            screen.screen_show(5,'TrackLine')

    elif 'trackLineOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        fuc.pause()
        move.motorStop()

    elif 'steadyCamera' == command_input:
        if OLED_connection:
            screen.screen_show(5,'SteadyCamera')
        fuc.steady(scGear.lastPos[2])

    elif 'steadyCameraOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        fuc.pause()
        move.motorStop()

    elif 'police' == command_input:
        if OLED_connection:
            screen.screen_show(5,'POLICE')
        ws2812.police()

    elif 'policeOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        ws2812.breath(75,85,90)
    
    elif 'speech' == command_input:
        if OLED_connection:
            screen.screen_show(5,'SPEECH')
        speech.speech()

    elif 'speechOff' == command_input:
        if OLED_connection:
            screen.screen_show(5,'FUNCTION OFF')
        speech.pause()
    
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
    if 'forward' == command_input:
        move.move(speed_set, 1, "mid")
    
    elif 'backward' == command_input:
        move.move(speed_set, -1, "mid")

    elif 'DS' in command_input:
        move.motorStop()

    elif 'left' == command_input:
        scGear.moveAngle(0, 30  * Dv)
        time.sleep(0.15)
        move.move(30, 1, "mid")
        switch.switch(3,1)
        time.sleep(0.15)

    elif 'right' == command_input:
        scGear.moveAngle(0,-30  * Dv)
        time.sleep(0.15)
        move.move(30, 1, "mid")
        switch.switch(2,1)
        time.sleep(0.15)
    elif 'TS' in command_input:
        scGear.moveAngle(0, 0)
        move.motorStop()
        switch.switch(2,0)
        switch.switch(3,0)

    elif 'lookleft' == command_input:
        scGear.singleServo(1, 1, 7)

    elif 'lookright' == command_input:
        scGear.singleServo(1,-1, 7)

    elif 'LRstop' in command_input:
        scGear.stopWiggle()


    elif 'armup' == command_input:
        scGear.singleServo(2, -1, 7)

    elif 'armdown' == command_input:
        scGear.singleServo(2, 1, 7)

    elif 'armstop' in command_input:
        scGear.stopWiggle()



    elif 'handup' == command_input:
        scGear.singleServo(3, 1, 7)

    elif 'handdown' == command_input:
        scGear.singleServo(3, -1, 7)

    elif 'HAstop' in command_input:
        scGear.stopWiggle()

    elif 'grab' == command_input:
        scGear.singleServo(4, -1, 7)

    elif 'loose' == command_input:
        scGear.singleServo(4, 1, 7)

    elif 'stop' == command_input:
        scGear.stopWiggle()
    elif 'home' == command_input:
        scGear.moveServoInit([0])
        scGear.moveServoInit([1])
        scGear.moveServoInit([2])
        scGear.moveServoInit([3])

def robotCtrl_speech(command_input, response):
    if 'stop' in command_input:
        scGear.stopWiggle()
    elif 'lookleft' == command_input:
        scGear.singleServo(1, 1, 7)

    elif 'lookright' == command_input:
        scGear.singleServo(1,-1, 7)

    elif 'armup' == command_input:
        scGear.singleServo(2, -1, 7)

    elif 'armdown' == command_input:
        scGear.singleServo(2, 1, 7)

    elif 'handup' == command_input:
        scGear.singleServo(3, 1, 7)

    elif 'handdown' == command_input:
        scGear.singleServo(3, -1, 7)

    elif 'grab' == command_input:
        scGear.singleServo(4, -1, 7)

    elif 'loose' == command_input:
        scGear.singleServo(4, 1, 7)
        
    elif 'home' == command_input:
        scGear.moveServoInit([0])
        scGear.moveServoInit([1])
        scGear.moveServoInit([2])
        scGear.moveServoInit([3])

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

async def check_permit(websocket):
    while True:
        recv_str = await websocket.recv()
        cred_dict = recv_str.split(":")
        if cred_dict[0] == "admin" and cred_dict[1] == "123456":
            response_str = "congratulation, you have connect with server\r\nnow, you can do something else"
            await websocket.send(response_str)
            return True
        else:
            response_str = "sorry, the username or password is wrong, please submit again"
            await websocket.send(response_str)

async def recv_msg(websocket):
    global speed_set
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
                response['data'] = [info.get_cpu_tempfunc(), info.get_cpu_use(), info.get_ram_info()]

            if 'wsB' in data:
                try:
                    set_B=data.split()
                    speed_set = int(set_B[1])
                except:
                    pass

            #CVFL
            elif 'CVFL' == data:
                flask_app.modeselect('findlineCV')

            elif 'CVFLColorSet' in data:
                color = int(data.split()[1])
                flask_app.camera.colorSet(color)

            elif 'CVFLL1' in data:
                pos = int(data.split()[1])
                flask_app.camera.linePosSet_1(pos)

            elif 'CVFLL2' in data:
                pos = int(data.split()[1])
                flask_app.camera.linePosSet_2(pos)

            elif 'CVFLSP' in data:
                err = int(data.split()[1])
                flask_app.camera.errorSet(err)

        elif(isinstance(data,dict)):
            if data['title'] == "findColorSet":
                color = data['data']
                flask_app.colorFindSet(color[0],color[1],color[2])

        else:
            pass
        print(data)
        response = json.dumps(response)
        await websocket.send(response)

async def main_logic(websocket):
    await check_permit(websocket)
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

async def start_server():
    async with serve(main_logic, '0.0.0.0', 8888):
        await asyncio.Future()  # run forever

if __name__ == '__main__':
    global flask_app, speech
    try:
        switch.switchSetup()
        switch.set_all_switch_off()

        show_wlan0_ip()
        time.sleep(0.5)
        show_network_mode()

        flask_app = app.webapp()
        flask_app.startthread()
        ws2812 = robotLight.Adeept_SPI_LedPixel(16, 255)
        if ws2812.check_spi_state() != 0:
            ws2812.start()
            ws2812.breath(70,70,255)
    except:
        ws2812.led_close()
        pass

    try:
        speech = VoiceIdentify.Speech(control_callback = robotCtrl_speech)
        speech.daemon = True
        speech.start()
    except Exception as e:
        pass

    try:
        asyncio.run(start_server())
    except Exception as e:
        print(e)
