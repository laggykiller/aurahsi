#!/usr/bin/env python3
import os
import io
import time
from datetime import datetime
from multiprocessing import Lock
from typing import Optional
import logging

from flask import Flask, send_file, request
from waitress import serve
import av
from PIL import Image, ImageFont, ImageDraw
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

logging.basicConfig(level=logging.INFO)

UP_MESSAGE = "恆指唔係越高越巴閉"
DOWN_MESSAGE = "恒指又跌啦"
MULTI_TABS = True # Open one tab for each valid_windows
REGEN_TIME = 300 # At least wait x seconds before regenerating gif
REFRESH_TIME = 7200 # At least wait x seconds before refreshing tab
GIF_WIDTH = 424
GIF_HEIGHT = 240
# FULL_WIDTH = 848
# FULL_HEIGHT = 480
DEFAULT_WINDOW = "1Y"
VALID_WINDOWS = ["MAX", "5Y", "1Y", "YTD", "6M", "1M", "5D", "1D"]

app = Flask(__name__)

def check_timestamp_in_trading_time(timestamp: float):
    dt = datetime.fromtimestamp(timestamp)
    if dt.weekday() >= 5:
        return False
    elif dt.hour < 9 or dt.hour >= 16:
        return False
    
    return True

class Browser:
    def __init__(self):
        logging.info("Launching firefox")
        options = Options()
        options.add_argument("-headless")
        options.add_argument("--disable-extensions")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-application-cache")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.set_preference("intl.accept_languages", "zh-HK")
        service = Service(log_output=os.devnull)
        self.driver = webdriver.Firefox(options=options, service=service)
        logging.info("Launched firefox")

        self.driver_lock = Lock()
        self.window_handles = {}
        for window in VALID_WINDOWS:
            self.window_handles[window] = {"window_handle": None, "timestamp": time.time()}
            if MULTI_TABS:
                self._open_tab(window)
                time.sleep(1)
        
    def _open_tab(self, window: Optional[str] = None):
        if not window or window not in VALID_WINDOWS:
            window = DEFAULT_WINDOW
        logging.info(f"Open tab: {window}")
        
        if MULTI_TABS:
            self.driver.switch_to.new_window("tab")
        url = f"https://www.google.com/finance/quote/HSI:INDEXHANGSENG?window={window}"
        if url != self.driver.current_url:
            self.driver.get(url)

        self.window_handles[window]["window_handle"] = self.driver.current_window_handle
        self.window_handles[window]["timestamp"] = time.time()

    def _switch_tab(self, window: Optional[str] = None):
        if not window or window not in VALID_WINDOWS:
            window = DEFAULT_WINDOW
        
        handle = self.window_handles[window]["window_handle"]
        self.driver.switch_to.window(handle)
    
    def _refresh_tab(self, window: Optional[str] = None):
        if not window or window not in VALID_WINDOWS:
            window = DEFAULT_WINDOW
        logging.info(f"Refresh tab")
        
        self.driver.refresh()

    def get_stock(self, window: Optional[str] = None) -> Image.Image:
        if not window or window not in VALID_WINDOWS:
            window = DEFAULT_WINDOW
        logging.info(f"Get stock: {window}")
        
        if time.time() - self.window_handles[window]["timestamp"] > REFRESH_TIME:
            refresh = True
        else:
            refresh = False
        
        with self.driver_lock:
            if MULTI_TABS:
                self._switch_tab(window)
            else:
                self._open_tab(window)

            if refresh:
                self._refresh_tab()
            image_data = self.driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(image_data))
        image = image.crop((160, 200, 860, 640))

        return image, window

    def cleanup(self):
        self.driver.quit()

class ImageOperation:
    def __init__(self):
        logging.info(f"Preload hsi-before-base.webm")
        self.hsi_before_base_frames = []
        with av.open("assets/hsi-before-base.webm") as container:
            stream = container.streams.video[0]
            for frame in container.decode(stream):
                self.hsi_before_base_frames.append(frame.to_image().convert("RGBA").resize((GIF_WIDTH, GIF_HEIGHT)))

        logging.info(f"Preload hsi-original.webm")
        self.hsi_after_frames = []
        with av.open("assets/hsi-original.webm") as container:
            stream = container.streams.video[0]
            for i, frame in enumerate(container.decode(stream)):
                if i >= 72:
                    self.hsi_after_frames.append(frame.to_image().convert("P", palette=1, colors=128).resize((GIF_WIDTH, GIF_HEIGHT)))
        
        font_size = int(GIF_HEIGHT * 0.075)
        self.font = ImageFont.truetype("assets/AdobeFanHeitiStd-Bold.otf", font_size)

        self.browser = Browser()

        self.results = {}
        for window in VALID_WINDOWS:
            self.results[window] = {"gif": None, "timestamp": 0}
            self._generate(window=window)
    
    def _check_stock_is_up(self, stock_img: Image.Image, window: Optional[str] = None) -> bool:
        try:
            if window == "1D":
                previous_close_xpath = "/html/body/c-wiz[2]/div/div[4]/div/main/div[2]/div[2]/div/div[1]/div[2]/div"
                previous_close = float(self.browser.driver.find_element(By.XPATH, previous_close_xpath).text.replace(",", ""))

                current_xpath = "/html/body/c-wiz[2]/div/div[4]/div/main/div[2]/div[1]/div[1]/c-wiz/div/div[1]/div/div[1]/div/div[1]/div/span/div/div"
                current = float(self.browser.driver.find_element(By.XPATH, current_xpath).text.replace(",", ""))

                if current > previous_close:
                    return True
                else:
                    return False
            else:
                change_xpath = "/html/body/c-wiz[2]/div/div[4]/div/main/div[2]/div[1]/div[1]/c-wiz/div/div[1]/div/div[1]/div/div[2]/div/span[2]"
                change = self.browser.driver.find_element(By.XPATH, change_xpath).text

                if change.startswith("+"):
                    return True
                else:
                    return False
            
        except NoSuchElementException:
            logging.warning("NoSuchElementException occured when checking stock is up")
            
            r, g, b = stock_img.convert("RGB").getpixel((165, 70))
            if g > r:
                return True
            else:
                return False

    def _prepare_stock_img(self, window: Optional[str] = None) -> Image.Image:            
        stock_img, window = self.browser.get_stock(window)
        is_up = self._check_stock_is_up(stock_img, window)
        scale_factor = GIF_HEIGHT * 0.9 / stock_img.height
        stock_img = stock_img.resize((int(stock_img.width * scale_factor), int(stock_img.height * scale_factor)))
        stock_img.putalpha(150)

        return stock_img, window, is_up

    def _generate(self, window: Optional[str] = None):
        result_frames = []
        stock_img, window, is_up = self._prepare_stock_img(window)

        if is_up:
            message = UP_MESSAGE
        else:
            message = DOWN_MESSAGE

        text_width, text_height = None, None
        for frame in self.hsi_before_base_frames:
            frame = frame.copy()
            if not is_up:
                frame = frame.transpose(Image.FLIP_LEFT_RIGHT)
            x_pos = frame.width // 2 - stock_img.width // 2
            frame.paste(stock_img, (x_pos, 0), stock_img)

            draw = ImageDraw.Draw(frame)
            if not text_width and not text_height:
                _, _, text_width, text_height = draw.textbbox((0, 0), message, font=self.font)
                text_x_pos = frame.width // 2 - text_width // 2
                text_y_pos = frame.height - text_height - GIF_HEIGHT // 60

            draw.text(
                xy=(text_x_pos, text_y_pos),
                text=message,
                fill=(255, 255, 255),
                font=self.font,
                stroke_width=1,
                stroke_fill=(44, 44, 44)
            )

            result_frames.append(frame.convert("RGB").convert("P", palette=1, colors=128))
        
        for frame in self.hsi_after_frames:
            result_frames.append(frame)

        f = io.BytesIO()
        result_frames[0].save(
            f,
            format="GIF",
            save_all=True,
            append_images=result_frames[1:],
            duration=42,
            loop=0
        )

        f.seek(0)
        self.results[window]["gif"] = f.read()
        self.results[window]["timestamp"] = time.time()
    
    def get_img(self, window: Optional[str] = None) -> bytes:
        if not window or window not in VALID_WINDOWS:
            window = DEFAULT_WINDOW

        curr_time = time.time()
        prev_time = self.results[window]["timestamp"]
        curr_time_trading = check_timestamp_in_trading_time(curr_time)
        prev_time_trading = check_timestamp_in_trading_time(prev_time)

        if (not self.results[window]["gif"] or
            (curr_time - prev_time > REGEN_TIME and
            (curr_time_trading or
             curr_time_trading != prev_time_trading or
             curr_time - prev_time > 24 * 60 * 60))):

            self._generate(window=window)

        return self.results[window]["gif"]
    
    def cleanup(self):
        self.browser.cleanup()

@app.route("/hsi.gif")
def hsi_gif():
    window = request.args.get("window")
    img = im_op.get_img(window=window)

    return send_file(io.BytesIO(img), mimetype="image/gif")

@app.after_request
def add_header(r):
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    r.headers['Cache-Control'] = 'public, max-age=0'
    return r

if __name__ == "__main__":
    im_op = ImageOperation()
    try:
        serve(app, host="0.0.0.0", port=80)
    finally:
        im_op.cleanup()
