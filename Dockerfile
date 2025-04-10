FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    xfce4 \
    xfce4-terminal \
    xfce4-goodies \
    xrdp \
    dbus-x11 \
    x11-xserver-utils \
    sudo \
    nano \
    net-tools \
    firefox \
    locales \
    iputils-ping \
    xorgxrdp \
    pulseaudio

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN sed -i 's/port=3389/port=3390/g' /etc/xrdp/xrdp.ini && \
    sed -i 's/max_bpp=32/max_bpp=24/g' /etc/xrdp/xrdp.ini && \
    sed -i 's/xserverbpp=24/xserverbpp=24/g' /etc/xrdp/xrdp.ini

RUN echo "startxfce4" > /etc/xrdp/startwm.sh && \
    chmod +x /etc/xrdp/startwm.sh

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 3390

ENTRYPOINT ["/entrypoint.sh"]
