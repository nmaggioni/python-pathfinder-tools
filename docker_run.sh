#!/bin/bash

if [[ -n "$XAUTHORITY" ]]; then
    XARGS="-e DISPLAY --net=host -v $XAUTHORITY:/root/.Xauthority -v /tmp/.X11-unix:/tmp/.X11-unix"
else
    XARGS="-v /tmp:/tmp"
fi

if [[ -n "$(docker images -q python-pathfinder-tools:latest 2> /dev/null)" ]]; then
  IMAGE="python-pathfinder-tools"
else
  IMAGE="ghcr.io/nmaggioni/python-pathfinder-tools"
fi

# shellcheck disable=SC2068
# shellcheck disable=SC2086
docker run --rm -it -v "$(pwd):/docs" -u="$(id -u $USER):$(id -g $USER)" $XARGS "$IMAGE:latest" $@
