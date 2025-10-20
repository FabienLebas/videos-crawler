# videos-crawler
Search in all videos of a Youtube page to detect keywords in the audio

1- Create the Python virtual environment

python3 -m venv venv

source venv/bin/activate

2- Install packages

pip3 install streamlit pandas dotenv youtube_agent pytube pydub openai httpx yt-dlp torch openai-whisper

3- Launch the application locally

streamlit run app.py

You will search for a Youtube account and it will retrieve the list of videos. You can select those you want to transcript. 

4- Transcript with Whisper

Launch the process and it will go through all videos and record the text in a file.

caffeinate -i python3 youtube_worker.py


