FROM python:3.10

RUN mkdir /.pathfinder && chmod a+rw /.pathfinder

WORKDIR /src

COPY . .

RUN pip install torch==1.13.1+cu117 torchvision==0.14.1+cu117 -f https://download.pytorch.org/whl/torch_stable.html && cd src/python && pip install .

WORKDIR /docs
