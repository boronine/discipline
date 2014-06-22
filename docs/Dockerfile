FROM debian:7.4
RUN echo "deb http://http.debian.net/debian/ wheezy-backports main" >> /etc/apt/sources.list
RUN apt-get update

RUN apt-get install -y python-sphinx
RUN apt-get install -y make

WORKDIR /disciplinedocs
