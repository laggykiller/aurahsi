FROM debian:11

WORKDIR /app

RUN apt update && \
    apt install -y python3 python3-pip firefox-esr curl fonts-noto fonts-noto-cjk

ARG FIREFOX_VERSION="0.34.0"
RUN curl -O -L https://github.com/mozilla/geckodriver/releases/download/v${FIREFOX_VERSION}/geckodriver-v${FIREFOX_VERSION}-linux64.tar.gz && \
    tar -xf geckodriver-v${FIREFOX_VERSION}-linux64.tar.gz && \
    rm geckodriver-v${FIREFOX_VERSION}-linux64.tar.gz && \
    mv geckodriver /usr/local/bin

COPY ./requirements.txt /app/requirements.txt
COPY ./assets /app/assets
COPY ./app.py /app/app.py
RUN pip3 install -r /app/requirements.txt

RUN apt clean autoclean && \
    apt autoremove --yes && \
    rm -rf /var/lib/{apt,dpkg,cache,log}/

CMD ["python3", "app.py"]
