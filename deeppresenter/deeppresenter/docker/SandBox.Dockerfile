# Partly copied from wonderwhy-er/DesktopCommanderMCP
# ? global dependency
FROM node:lts-bullseye-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.tuna.tsinghua.edu.cn/debian|g' /etc/apt/sources.list && \
    sed -i 's|http://deb.debian.org/debian-security|http://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org/debian-security|http://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list

# Install ca-certificates first to avoid GPG signature issues, then other packages
RUN apt-get update --allow-insecure-repositories && \
    apt-get install -y --fix-missing  --no-install-recommends --allow-unauthenticated ca-certificates && \
    update-ca-certificates && \
    apt-get install -y --no-install-recommends git bash curl wget unzip ripgrep vim sudo g++ locales

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen

# Install Chromium and dependencies
RUN apt-get update && apt-get install -y --fix-missing --no-install-recommends \
        chromium \
        fonts-liberation \
        libappindicator3-1 \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        xdg-utils \
        fonts-dejavu \
        fonts-noto \
        fonts-noto-cjk \
        fonts-noto-cjk-extra \
        fonts-noto-color-emoji \
        fonts-freefont-ttf \
        fonts-urw-base35 \
        fonts-roboto \
        fonts-wqy-zenhei \
        fonts-wqy-microhei \
        fonts-arphic-ukai \
        fonts-arphic-uming \
        fonts-ipafont \
        fonts-ipaexfont \
        fonts-comic-neue \
        imagemagick

RUN mkdir -p /usr/src/pptagent&& \
    cd /usr/src/pptagent && \
    git clone https://gitclone.com/github.com/icip-cas/PPTAgent.git . && \
    npm install --ignore-scripts && \
    npx playwright install chromium

# ? project dependency

WORKDIR /usr/src/app

# Puppeteer config for mermaid-cli
RUN echo '{"args":["--no-sandbox","--disable-setuid-sandbox"]}' > /root/.puppeteerrc.json

# Set environment variables (for CMD and non-shell contexts)
ENV PATH="/opt/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV="/opt/.venv" \
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    MPLCONFIGDIR=/etc/matplotlib \
    MCP_CLIENT_DOCKER=true

# Export ENV to /etc/profile.d/ for bash -lc and interactive shells
RUN printenv | grep -E '^(PATH|PYTHONUNBUFFERED|VIRTUAL_ENV|PUPPETEER_|LANG|LC_ALL|MPLCONFIGDIR|MCP_CLIENT_DOCKER)=' | sed 's/^/export /' > /etc/profile.d/docker-env.sh && \
    echo 'source /etc/profile.d/docker-env.sh' >> /etc/bash.bashrc

# Clone the repository at specific commit
RUN git clone https://gitclone.com/github.com/wonderwhy-er/DesktopCommanderMCP.git . && \
    git checkout 252a00d624c2adc5707fa743c57a1b68bc223689 && \
    rm -rf .git
RUN npm install --ignore-scripts && npm install -g @mermaid-js/mermaid-cli pptxgenjs playwright sharp

# Create Python virtual environment and install packages
RUN uv venv --python 3.13 $VIRTUAL_ENV && \
    uv pip install pip python-pptx matplotlib seaborn plotly numpy pandas opencv-python-headless pillow

# Copying config and tailored server files
COPY config.json /root/.claude-server-commander/config.json
COPY server.ts src/server.ts
COPY improved-process-tools.ts src/tools/improved-process-tools.ts

# Configure matplotlib for CJK fonts
RUN fc-cache -f && \
    mkdir -p /etc/matplotlib && \
    printf '%s\n' \
      'font.family: sans-serif' \
      'font.sans-serif: Noto Sans CJK SC, WenQuanYi Zen Hei, DejaVu Sans' \
      > /etc/matplotlib/matplotlibrc

# Rebuild the package
RUN npm run build

CMD ["node",  "/usr/src/app/dist/index.js", "--no-onboarding"]
