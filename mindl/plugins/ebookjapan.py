# mindl - A plugin-based downloading tool.
# Copyright (C) 2016 Mino <mino@minomino.org>

# This file is part of mindl.

# mindl is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# mindl is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with mindl. If not, see <http://www.gnu.org/licenses/>.

import functools
import requests
import base64
import sys
import re

from selenium.webdriver.common.desired_capabilities import DesiredCapabilities as DC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium import webdriver
from re import match

from mindl import BasePlugin

__version__ = "0.1"

API_LOGIN = "https://api.ebookjapan.jp/ebj/api/EbiService.svc/user/login"
USER_AGENT = "Mozilla/5.0 (Windows NT 6.3; rv:36.0) Gecko/20100101 Firefox/36.0"

class ebookjapan(BasePlugin):
    name = "eBookJapan"
    options = ( ("@email", ""),
                ("@password", "") )

    def __init__(self, url):
        self.url = url
        self.book_name = "N/A"
        self.book_volume = None

        # Set the user agent to something generic.
        dc = dict(DC.PHANTOMJS)
        dc["phantomjs.page.settings.userAgent"] = USER_AGENT

        self.d = webdriver.PhantomJS(desired_capabilities=dc,
            service_args=["--ignore-ssl-errors=true", "--ssl-protocol=any", "--web-security=false", "--ssl-protocol=TLSv1"])
        # Set cookies that makes it think we previously agreed to the ToS.
        self.d.add_cookie({"name": "tachiyomi_auto_reader", "value": "Browser", "domain": ".ebookjapan.jp", "path": "/"})
        self.d.add_cookie({"name": "tachiyomi_user_policy", "value": "on", "domain": ".ebookjapan.jp", "path": "/"})
        self.d.set_window_size(1120, 550)
        # Generic waiter.
        self.wait = WebDriverWait(self.d, 60)

    def _rewrite_alert(self):
        # Apparently PhantomJS doesn't directly deal with alerts yet, so we rewrite
        # the alert function to put the message on a variable. Thanks, StackOverflow.
        js = """
        window.alert = function(message) {
        lastAlert = message;
        }
        """
        self.d.execute_script(js)

    @staticmethod
    def can_handle(url):
        if match(r"^https?://(?:www.)?ebookjapan.jp/ebj/\d+?/?.+$", url):
            return True
        elif match(r"^https?://br.ebookjapan.jp/br/reader/viewer/view.html\?.+$", url):
            return True

        return False

    def directory(self):
        # This will be called after the first iteration of downloader(), which will gather
        # the title and book name for us.
        if self.book_volume is None:
            return "{}".format(self.book_name)
        else:
            return "{} 第{}巻".format(self.book_name, self.book_volume)

    def login(self):
        # We use requests to login, since it's a lot faster. We then copy the
        # resulting cookies to PhantomJS.
        r = requests.post(API_LOGIN,
            json={"email": self["email"], "password": self["password"], "spoofing": 0},
            headers={"user-agent": USER_AGENT})
        if r.status_code != 200:
            raise RuntimeError("Login failed with status code {}: {}".format(r.status_code, r.text))

        for c in r.cookies:
            # PhantomJS is weird and refuses to take domains without the dot in front.
            domain = c.domain if c.domain.startswith(".") else "." + c.domain
            self.d.add_cookie({"name": c.name, "value": c.value, "domain": domain, "path": c.path})

    def downloader(self):
        self.logger.debug("Logging in as '{}'...".format(self["email"]))
        self.login()

        if "br.ebookjapan.jp" not in self.url:
            # Going through the comic page using tachiyomi.
            self.logger.debug("Opening comic page...")
            self.d.get(self.url)
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@class='bookBtnListTachiyomi']/a"))).click()
            self.logger.debug("Clicked on reader. Waiting for popup window...")
            self.wait.until(lambda d: len(d.window_handles) > 1)
            self.d.switch_to_window(self.d.window_handles[-1])
        else:
            # We're using a reader link directly. This assumes cookies are correctly set.
            self.d.get(self.url)

        # We use a window size that makes the reader display one page at a time.
        self.d.set_window_size(700, 500)
        self._rewrite_alert()

        try:
            self.logger.debug("Waiting for reader to load...")
            self.wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@id='controller']")))
        except TimeoutException as e:
            self.logger.critical("Failed to find the controller. Checking for an alert...")
            # Check if we have an alert.
            alert_text = self.d.execute_script("return lastAlert")
            if alert_text:
                self.logger.critical("The reader threw the following error:\n" + alert_text)
                exit(1)
            else:
                self.logger.critical("No alert was present. Unknown error. Check the exception_state.png"
                    "image for a screenshot of the page when it failed.")
            raise e

        self.logger.debug("Checking if page 0 is being displayed...")
        current_page = self.wait.until(EC.visibility_of_element_located((By.XPATH, "//canvas[@class='current']")))
        if current_page.get_attribute("page") != "0":
            # We did not find outselves on page 0, so we need to
            # check if the popup about previously read pages appeared.
            cancel = self.wait.until(EC.visibility_of_element_located((By.XPATH, "//span[@id='btn_cancel']")))
            self.logger.debug("Popup about returning to last page previously read detected. Clicking cancel...")
            # Tell it to go to the start of the comic.
            cancel.click()
            # Wait for page 0 to load.
            self.logger.debug("Waiting for page 0 to be the current page...")
            self.wait.until(EC.visibility_of_element_located((By.XPATH, "//canvas[@page='0' and @class='current']")))

        self.logger.debug("Waiting for the total pages to appear...")
        # The reader doesn't count covers and whatnot as actual pages, so we'll get more images
        # than this number, but we use it to determine when we've hit the last page.
        total_pages = int(self.wait.until(EC.presence_of_element_located((By.XPATH,
            "//span[@id='sliderMaxNum']"))).get_attribute('innerHTML'))
        self.logger.debug("Comic has about {} pages.".format(total_pages + 3))
        # The element we send keystrokes to, making it flip pages.
        body = self.d.find_element_by_tag_name("body")

        # Before we start ripping, we get the book name, and the volume number if it has one.
        self.book_name = (self.d.find_element_by_xpath("//div[@class='bookProperty']/span[@class='name']")
            .get_attribute('innerHTML').strip().replace("/", "／").replace("\\", "＼")).replace("（", "(").replace("）", ")")
        # For stuff like time limited free books, the title might have 特別無料版 prepended, so remove it.
        self.book_name = self.book_name.split("<br>")[-1]
        res = re.match(r".+\((\d+)\)$", self.book_name) #downloads/特別無料版<br>きみはペット　（1）)'
        if res: # Is it a series?
            self.book_volume = int(res.group(1))
            self.book_name = self.book_name[:-(2+len(res.group(1)))]

        def is_page_ready(driver, page):
            # No actual way to check if a canvas is empty is JS for whatever reason, so we
            # check if (10, 10) has an alpha of 0 to determine if it's empty or not.
            # The canvas has borders that could have an alpha of 0, which is we don't just use (0, 0).
            return self.d.execute_script("return arguments[0].getContext(\"2d\").getImageData(10, 10, 10, 10).data[3] == 255;", page)

        canvas_wait = WebDriverWait(self.d, 120)
        i = 0
        self.logger.info("Starting the ripping process...")

        while True:
            current = self.wait.until(EC.visibility_of_element_located((By.XPATH,
                "//canvas[@class='current' and @page='{}']".format(i))))
            canvas_wait.until(functools.partial(is_page_ready, page=current))

            # We always start by checking if we're on the last page. We skip it because on paid books
            # it has a serial number on it, which can presumably be used to trace who ripped it.
            # Not to mention it's just a generic page added automatically for all books.
            slider_page = int(self.d.find_element_by_xpath("//span[@id='sliderSelectNum']").get_attribute('innerHTML'))
            if total_pages == slider_page:
                break

            self.logger.debug("Ripping page: {}".format(int(current.get_attribute("page")) + 1))
            # Remove the "data:image/png;base64," part, then decode it.
            data = base64.b64decode(self.d.execute_script('return arguments[0].toDataURL("image/png");', current)[22:])
            yield "{:04d}.png".format(i + 1), data
            
            body.send_keys(Keys.ARROW_LEFT)
            i += 1

    def handle_exception(self, e):
        with open("exception_state.png", "wb") as f:
            f.write(self.d.get_screenshot_as_png())

        for elem in self.d.find_elements_by_tag_name("canvas"):
            print(elem.get_attribute("id"), elem.get_attribute("class"), elem.get_attribute("page"))

        return False

    def finalize(self):
        self.d.quit()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: {} <book_url>".format(sys.argv[0]))
        exit()

    ebj = ebookjapan(sys.argv[1])

    try:
        dler = ebj.downloader()
        for filename, data in dler:
            with open(filename, "wb") as f:
                f.write(data)
    except Exception as e:
        with open("exception_state.png", "wb") as f:
            f.write(ebj.d.get_screenshot_as_png())

        for elem in ebj.d.find_elements_by_tag_name("canvas"):
            print(elem.get_attribute("id"), elem.get_attribute("class"), elem.get_attribute("page"))
        ebj.finalize()
        raise e

    ebj.finalize()