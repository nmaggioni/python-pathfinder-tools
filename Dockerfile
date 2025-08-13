FROM python:3.13.6-trixie

RUN mkdir /.pathfinder && chmod a+rw /.pathfinder

WORKDIR /src

RUN pip install torch==2.8.0+cpu torchvision==0.23.0+cpu --index-url https://download.pytorch.org/whl/cpu

COPY . .

WORKDIR /src/src/python

RUN pip install .

WORKDIR /docs
