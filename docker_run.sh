#!/bin/bash

docker run --rm -it -v "$(pwd):/docs" -u=$(id -u $USER):$(id -g $USER) -e DISPLAY --net=host -v $XAUTHORITY:/root/.Xauthority -v /tmp/.X11-unix:/tmp/.X11-unix python-pathfinder-tools $@
