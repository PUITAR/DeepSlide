FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

RUN apt update

# Core development tools and build essentials
RUN apt install -y --no-install-recommends \
    autoconf \
    automake \
    autotools-dev \
    build-essential \
    cmake \
    g++ \
    make \
    ninja-build \
    pkg-config

# Version control and package management
RUN apt install -y --no-install-recommends \
    git \
    git-lfs \
    wget \
    curl \
    aria2

# System utilities and security
RUN apt install -y --no-install-recommends \
    ca-certificates \
    sudo \
    unattended-upgrades \
    tmux \
    vim \
    zip \
    unzip \
    tree \
    daemontools

# Networking and distributed systems
RUN apt install -y --no-install-recommends \
    openssh-client \
    openssh-server \
    nfs-common \
    krb5-user \
    libkrb5-dev

# Libraries for parallel computing and hardware
RUN apt install -y --no-install-recommends \
    libnuma1 \
    libnuma-dev \
    libpmi2-0-dev \
    libibverbs1 \
    librdmacm1 \
    libaio1

# Cryptography and database libraries
RUN apt install -y --no-install-recommends \
    libssl-dev \
    libsqlite3-dev \
    sqlite3

# Document and graphics processing
RUN apt install -y --no-install-recommends \
    dvipng \
    poppler-utils \
    imagemagick

# Miscellaneous development and system libraries
RUN apt install -y --no-install-recommends \
    libtool \
    libncurses-dev \
    locales \
    mesa-utils

RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
RUN apt install -y ./google-chrome-stable_current_amd64.deb

RUN apt install -y --no-install-recommends libreoffice

RUN apt install -y software-properties-common
RUN add-apt-repository -y ppa:deadsnakes/ppa
RUN apt install -y python3.13-full python3-pip python3-distutils python3.13-dev
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 100
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.13 100

RUN locale-gen en_US.UTF-8 && update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
RUN apt install -y nodejs fish npm

# model cache
RUN uv pip install --system huggingface_hub
RUN huggingface-cli download google/vit-base-patch16-224-in21k
RUN huggingface-cli download julien-c/fasttext-language-id

ARG CACHE_DATE=UNKNOWN
RUN git clone https://github.com/icip-cas/PPTAgent
RUN uv pip install --system "pptagent[full]"
RUN npm install --prefix /PPTAgent/pptagent_ui

WORKDIR /PPTAgent

CMD ["/bin/bash", "docker/launch.sh"]
