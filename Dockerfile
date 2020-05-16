FROM ubuntu:18.04 AS builder
ENV DEBIAN_FRONTEND="noninteractive"
ENV LC_ALL C.UTF-8
ENV lang C.UTF-8
RUN apt-get update && apt-get -y install \
  git-core swig libpulse-dev libasound2-dev ffmpeg tesseract-ocr python3-pip pandoc python3.6-tk \
  python3-setuptools python3-venv && apt-get clean \
  && rm -rf /var/lib/apt/lists/* && \
  python3 -m venv /app/bw_plex

ENV PATH="/app/bw_plex/bin:$PATH"
WORKDIR /src

# Python requirements from pip
RUN pip3 --no-cache-dir install pytest pytest-cov pytest-mock pytest_click pypandoc codecov \
  opencv-contrib-python-headless SpeechRecognition pocketsphinx pytesseract

ADD . /src
RUN pip3 --no-cache-dir wheel -e . && pip3 --no-cache-dir install bw_plex*.whl

FROM ubuntu:18.04
LABEL maintainer="hellowlol1@gmail.com"

ENV DEBIAN_FRONTEND="noninteractive"
ENV LC_ALL C.UTF-8
ENV lang C.UTF-8

# Package requirements
RUN apt-get update && apt-get -y install \
  libpulse0 libasound2 ffmpeg tesseract-ocr python3-pip pandoc python3.6-tk \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/bw_plex /app/bw_plex
ENV PATH="/app/bw_plex/bin:$PATH"

# COPY root/ /
VOLUME /config


CMD ["bw_plex", "-df", "/config", "watch"]


# To build (Docker image):
# docker build -t bw_plex:latest .

# To run:
# docker run -it bw_plex
# then just do the normal bw_plex commands.
