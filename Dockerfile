FROM ubuntu:18.04

# This images is much bigger then i want, ill try to reduce it
# but im such a docker noob, send a PR if you know how to fix it.

LABEL maintainer="hellowlol1@gmail.com"

ENV DEBIAN_FRONTEND="noninteractive"
ENV LC_ALL C.UTF-8
ENV lang C.UTF-8

# Package requirements
RUN apt-get update && apt-get -y install \
  git swig libpulse-dev libasound2-dev ffmpeg tesseract-ocr python3-pip pandoc python3.6-tk \
  python3-setuptools && apt-get clean \
  && rm -rf /var/lib/apt/lists/* && \
  mpdir -p /app/bw_plex

# Python requirements from pip
RUN pip3 install pytest pytest-cov pytest-mock pytest_click pypandoc codecov \
  opencv-contrib-python-headless SpeechRecognition pocketsphinx pytesseract

RUN git clone --depth=1 https://github.com/Hellowlol/bw_plex.git /app/bw_plex
#&& rm -rf /app/bw_plex/.git

# This is needed for the the manual install of bw_plex
WORKDIR /app/bw_plex

RUN pip3 install -e .

# COPY root/ /
VOLUME /config


CMD ["sh", "-c", "bw_plex --url ${url} -t ${token} -df /config watch"]


# To build (Docker image):
# docker build -t bw_plex:latest .

# To run:
# docker run -it bw_plex
# then just do the normal bw_plex commands.
