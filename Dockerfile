FROM python:3.9

WORKDIR /src

COPY . .

RUN pip install torch==1.7.1+cu110 torchvision==0.8.2+cu110 -f https://download.pytorch.org/whl/torch_stable.html && cd src/python && pip install .

WORKDIR /docs
