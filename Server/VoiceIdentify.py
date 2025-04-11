#!/usr/bin/env python3
# File name   : VoiceIdentify.py
# Author      : Adeept
# Date        : 2025/03/12
import os

def main():
    # cmd = "sudo  /home/pi/sherpa-ncnn/build/bin/sherpa-ncnn-microphone \
    #       /home/pi/sherpa-ncnn/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/tokens.txt \
    #       /home/pi/sherpa-ncnn/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/encoder_jit_trace-pnnx.ncnn.param \
    #       /home/pi/sherpa-ncnn/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/encoder_jit_trace-pnnx.ncnn.bin \
    #       /home/pi/sherpa-ncnn/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/decoder_jit_trace-pnnx.ncnn.param \
    #       /home/pi/sherpa-ncnn/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/decoder_jit_trace-pnnx.ncnn.bin \
    #       /home/pi/sherpa-ncnn/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/joiner_jit_trace-pnnx.ncnn.param \
    #       /home/pi/sherpa-ncnn/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/joiner_jit_trace-pnnx.ncnn.bin "

    # If the above commands cannot be used, please use the following command. Use "arecord -l" to check the local audio input devices, and then replace the parameter "2" in "plughw:2,0". 
    cmd = "sudo /home/pi/sherpa-ncnn/build/bin/sherpa-ncnn-alsa \
            /home/pi/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/tokens.txt \
            /home/pi/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/encoder_jit_trace-pnnx.ncnn.param \
            /home/pi/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/encoder_jit_trace-pnnx.ncnn.bin \
            /home/pi/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/decoder_jit_trace-pnnx.ncnn.param \
            /home/pi/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/decoder_jit_trace-pnnx.ncnn.bin \
            /home/pi/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/joiner_jit_trace-pnnx.ncnn.param \
            /home/pi/sherpa-ncnn-streaming-zipformer-bilingual-zh-en-2023-02-13/joiner_jit_trace-pnnx.ncnn.bin \
            plughw:2,0 \
            4 \
            greedy_search"
    os.system(f"{cmd} > output.txt 2>&1")
if __name__ == "__main__":
    main()

