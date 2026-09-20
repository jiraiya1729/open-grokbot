FROM mcr.microsoft.com/playwright:v1.52.0-noble
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    git python3 python3-pip xvfb fluxbox x11vnc novnc websockify xdotool \
    && rm -rf /var/lib/apt/lists/*
RUN ln -s "$(find /ms-playwright -type f -path '*/chrome-linux/chrome' | head -1)" /usr/local/bin/chromium
RUN mkdir -p /workspace && chown -R pwuser:pwuser /workspace
USER pwuser
WORKDIR /workspace
ENV DISPLAY=:99 HOME=/home/pwuser
CMD ["bash", "-lc", "Xvfb :99 -screen 0 1440x900x24 -nolisten tcp & fluxbox >/tmp/fluxbox.log 2>&1 & chromium --no-sandbox --disable-dev-shm-usage --start-maximized about:blank >/tmp/chromium.log 2>&1 & x11vnc -display :99 -forever -shared -nopw -rfbport 5900 >/tmp/x11vnc.log 2>&1 & exec websockify --web=/usr/share/novnc 6080 localhost:5900"]
