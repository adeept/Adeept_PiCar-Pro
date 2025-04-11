#!/usr/bin/env/python
# File name   : TalkToAI.py
# Website     : www.Adeept.com
# Author      : Adeept
# Date        : 2025/03/13

import pyttsx3
import os
from openai import OpenAI
import time

audio_file = "./response_audio.wav"

# Assume you've completed local speech recognition and obtained the recognized text
local_recognition_text = "hello"

# DeepSeek API settings, replace with your own information    
DEEPSEEK_API_URL = "https://api.deepseek.com"
DEEPSEEK_API_KEY = "sk-cb3625243e214fea872c815d41624201"

# Function to send a request to the DeepSeek cloud service and get the response
def get_deepseek_response(text):
    """
    Send a request to the DeepSeek cloud service and return the response.
    :param text: The input text for the DeepSeek service.
    :return: The output text from the DeepSeek service, or an empty string if an error occurs.
    """
    try:
        
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_API_URL)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": text},
            ],
            stream=False
        )
        # print("response: " +str(response))
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error occurred when requesting the DeepSeek service: {e}")
        return ""


def text_to_speech(text, output_file):
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)    # Speed adjustment（50-200）
    engine.setProperty('volume', 0.8)  # Volume control（0.0-1.0）
    
    voices = engine.getProperty('voices')
    engine.setProperty('voice', voices[29].id)   #29: English (America, New York City) (['en-us-nyc'])
    # If you want to change the language, you can run the following code to get the list of languages, and then select the appropriate language. 
    # voices = engine.getProperty('voices')
    # for i, voice in enumerate(voices):
    #     print(f"{i}: {voice.name} ({voice.languages})")
        
    engine.save_to_file(text, output_file)
    engine.runAndWait()


# Function to play the audio file
def play_audio(audio_file):
    """
    Play the audio file using the system's default media player.
    :param audio_file: The path to the audio file.  
    """
    try:
        os.system('aplay -D "plughw:2,0" ' + audio_file)    #In the example, the playback device is card 2, so "plughw:2,0" is used. You can use the command "aplay -l" to check your own playback device.  
    except Exception as e:
        print(f"Error occurred when playing the audio file: {e}")

file_position = 0
while True:
    with open("output.txt", "r") as file: # Read the file named “output.txt”
        file.seek(file_position)
        new_lines = file.readlines() # Read all lines from the current file pointer position to the end of the file
        if new_lines:
            for line in new_lines:
                if "Started" in line:
                    local_recognition_text = line.split("Started")[-1].strip()
                elif file_position > 0:  # Ensure we print lines after the first "Started"
                    local_recognition_text = line.strip()
    
            file_position = file.tell()
            print("I： " + local_recognition_text)

            if local_recognition_text:
                deepseek_response = get_deepseek_response(local_recognition_text)
                if deepseek_response:
                    print("deepseek: " + deepseek_response)
                    text_to_speech(deepseek_response, audio_file)
                    play_audio(audio_file)
                    if os.path.exists(audio_file):
                        os.remove(audio_file)
    time.sleep(5)  # Read every 5 second

    