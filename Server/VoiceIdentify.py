#!/usr/bin/env python3

# Real-time speech recognition from a microphone with sherpa-onnx Python API
# with endpoint detection.
#
# Please refer to
# https://k2-fsa.github.io/sherpa/onnx/pretrained_models/index.html
# to download pre-trained models
import sys
import os
import time
import subprocess
import threading
import numpy as np

try:
    import sherpa_onnx
    HAS_SHERPA = True
except ImportError:
    HAS_SHERPA = False
    print("Speech function is disabled, Please install sherpa-onnx by 'sudo pip3 install sherpa-onnx sherpa-onnx-bin --break-system-packages'")

# username = os.popen("echo ${SUDO_USER:-$(who -m | awk '{ print $1 }')}").readline().strip() # pi
# user_home = os.popen(f'getent passwd {username} | cut -d: -f 6').readline().strip()        # home

def get_cur_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.abspath(os.path.join(script_dir, "../.."))
    print(f"Base directory: {base_dir}")
    return base_dir
user_home = get_cur_path()

dic_map = {
    "停止": "stop",
    "向左转": "lookleft",
    "向右转": "lookright",
    "抬起大臂": "armup",
    "落下大臂": "armdown",
    "抬起小臂": "handup",
    "落下小臂": "handdown",
    "抓取": "grab",
    "松开": "loose",
    "重置": "home",

    "STOP": "stop",
    "LOOK LEFT": "lookleft",
    "LOOK RIGHT": "lookright",
    "ARM UP": "armup",
    "ARM DOWN": "armdown", 
    "HAND UP": "handup",
    "HAND DOWN": "handdown",
    "GRAB": "grab",
    "LOOSE": "loose",
    "RESET":"home",
}

class Speech(threading.Thread):
    def __init__(self, control_callback, *args, **kwargs):
        self.SpeechMode = 'none'
        self.command = ''
        self.control_callback = control_callback
        if HAS_SHERPA:
            self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=f"{user_home}/sherpa-onnx/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/tokens.txt",
                encoder=f"{user_home}/sherpa-onnx/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/encoder-epoch-99-avg-1.onnx",
                decoder=f"{user_home}/sherpa-onnx/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/decoder-epoch-99-avg-1.onnx",
                joiner=f"{user_home}/sherpa-onnx/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/joiner-epoch-99-avg-1.onnx",
                num_threads=1,
                sample_rate=16000,
                feature_dim=80,
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=2.4,
                rule2_min_trailing_silence=1.2,
                rule3_min_utterance_length=300,  # it essentially disables this rule
                provider="cpu"
            )
        self.cmd = [
            "arecord",
            "-D", "plughw:2,0",   # device card 2, subdevice 0, command: arecord -l
            "-f", "S16_LE",       # format
            "-r", "16000",        # supported sample rate
            "-c", "1",            # mono
            "-t", "raw", 
            "-q",                 # output raw audio
            "-"                   # output to stdout
        ]
        super(Speech, self).__init__(*args, **kwargs)
        self.__flag = threading.Event()
        self.__flag.clear()
        self.p = None

    def pause(self):
        self.SpeechMode = 'none'
        self.__flag.clear()
        # 关闭录音
        if self.p:
            try:
                self.p.terminate()
            except:
                pass
            self.p = None


    def resume(self):
        self.__flag.set()

    def speech(self):
        self.SpeechMode = 'speech'
        self.resume()

    def run(self):
        while True:
            self.__flag.wait()
            if self.SpeechMode == 'speech':
                self.SpeechProcessing()
            time.sleep(0.1)

    def SpeechProcessing(self):
        if not HAS_SHERPA:
            return
        # The model is using 16 kHz, we use 48 kHz here to demonstrate that
        # sherpa-onnx will do resampling inside.
        sample_rate = 16000
        chunk_seconds = 0.2
        chunk_size = int(sample_rate * chunk_seconds)
        stream = self.recognizer.create_stream()
        # display = sherpa_onnx.Display()

        if self.p == None:
            self.p = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=chunk_size * 2)

        while self.SpeechMode == 'speech':
            data = self.p.stdout.read(chunk_size * 2)
            if not data:
                return 
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            stream.accept_waveform(sample_rate, samples)
            while self.recognizer.is_ready(stream):
                self.recognizer.decode_stream(stream)

            # display.update_text(result)
            # display.display()

            if self.recognizer.is_endpoint(stream):
                result = self.recognizer.get_result(stream)
                if result:
                    self.command = dic_map.get(result, result)
                    print(f"{result} ==> {self.command}")


                    self.control_callback(self.command, None)
                    self.command = ''
                    # display.finalize_current_sentence()
                    # display.display()
                self.recognizer.reset(stream)


if __name__ == "__main__":

    speech = Speech()
    speech.daemon = True 
    speech.start() 
    speech.speech()  
    while 1:
        time.sleep(1)
