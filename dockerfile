FROM texlive/texlive:latest

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# 安装必要的工具
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        netcat-traditional \
        gnupg \
        curl \
        unzip \
        zip \
        xvfb \
        libxss1 \
        libnss3 \
        libnspr4 \
        libasound2t64 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        build-essential \
        libssl-dev \
        zlib1g-dev \
        libffi-dev \
        libreadline-dev \
        libsqlite3-dev \
        libbz2-dev \
        libncurses5-dev \
        liblzma-dev \
        uuid-dev \
        xdg-utils \
        fonts-liberation \
        dbus \
        xauth \
        x11vnc \
        tigervnc-tools \
        supervisor \
        net-tools \
        procps \
        git \
        python3-numpy \
        fontconfig \
        fonts-dejavu \
        fonts-dejavu-core \
        fonts-dejavu-extra \
        tmux \
        poppler-utils \
        antiword \
        unrtf \
        catdoc \
        grep \
        gawk \
        sed \
        file \
        jq \
        csvkit \
        xmlstarlet \
        less \
        vim \
        tree \
        rsync \
        lsof \
        iputils-ping \
        dnsutils \
        make \
        sudo && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 3.12.5
RUN wget https://www.python.org/ftp/python/3.12.5/Python-3.12.5.tgz && \
    tar -xzf Python-3.12.5.tgz && \
    cd Python-3.12.5 && \
    ./configure --prefix=/opt/python312 --enable-optimizations && \
    make -j$(nproc) && \
    make install && \
    cd .. && \
    rm -rf Python-3.12.5 Python-3.12.5.tgz

# 链接 Python3.12 到 /usr/local/bin
RUN ln -sf /opt/python312/bin/python3.12 /usr/local/bin/python && \
    ln -sf /opt/python312/bin/python3.12 /usr/local/bin/python3 && \
    ln -sf /opt/python312/bin/pip3 /usr/local/bin/pip

# 创建虚拟环境（禁止在容器内直接 pip）
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# 复制并安装 Python 依赖
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt \
        -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . /app

CMD ["bash"]
