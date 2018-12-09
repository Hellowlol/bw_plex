FROM ubuntu:18.04

# This images is much bigger then i want, ill try to reduce it
# but im such a docker noob, send a PR if you know how to fix it.

MAINTAINER hellowlol1@gmail.com

ENV DEBIAN_FRONTEND="noninteractive"
ENV LC_ALL C.UTF-8
ENV lang C.UTF-8

RUN apt-get update
RUN apt-get -y install git
RUN apt-get -y install swig
RUN apt-get -y install libpulse-dev
RUN apt-get -y install libasound2-dev
RUN apt-get -y install ffmpeg
RUN apt-get -y install tesseract-ocr
RUN apt-get -y install python3-pip
RUN apt-get -y install pandoc
RUN apt-get -y install python3.6-tk

# for tests
RUN pip3 install pytest pytest-cov pytest-mock pytest_click pypandoc codecov

# for credits
RUN pip3 install opencv-contrib-python-headless

# Find phrase in audio
RUN pip3 install SpeechRecognition
RUN pip3 install pocketsphinx

# For ocr.
RUN pip3 install pytesseract

RUN git clone https://github.com/Hellowlol/bw_plex.git /app/bw_plex

# This is needed for the the manual install of bw_plex
WORKDIR /app/bw_plex

RUN pip3 install -e .

# COPY root/ /
VOLUME /config


CMD ["sh", "-c", "bw_plex --url ${url} -t ${token} -df /config watch"]


# docker build -t bw_plex:latest .
# docker run -it bw_plex
# then just do the normal bw_plex commands.
