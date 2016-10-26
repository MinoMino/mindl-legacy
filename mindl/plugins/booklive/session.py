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

import urllib.parse
import urllib.request
import urllib.error
import http.cookiejar
import logging
import json
import re
import datetime
import math
import random

"""
Class to get a session with Booklive and utilize it's API to get content info/listings and download it.

A lot of it could be simplified into just a couple of "public" methods instead of letting the user call
all the stuff, but it's useful to have it all split up when I want to poke around the API. Some thing
applies for the fact that you have to pass 'cid' for most methods.
"""

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
USER_AGENT = "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)"

CONTENT_INFO_URL = "http://booklive.jp/bib-api/bibGetCntntInfo"
CONTENT_URL = "http://bib.booklive.jp/bib-deliv/sbcGetCntnt.php"
IMAGE_URL = "http://bib.booklive.jp/bib-deliv/sbcGetImg.php"
LOGIN_SCREEN_URL = "https://booklive.jp/login"
LOGIN_URL = "https://booklive.jp/login/index"
PURCHASE_URL = "https://booklive.jp/purchase/product/title_id/{}/vol_no/{}/direct/1"
RE_IMAGE_PATH = re.compile(r"t-img src=\"(.+?)\"")

class BookliveSession():
    def __init__(self, username="", password=""):
        self.cookies = http.cookiejar.CookieJar(http.cookiejar.DefaultCookiePolicy())

        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self._logged_in = False
        self._username = username
        self._password = password
        self._session = ""
        self._pages = None
        self.filenames = None
        self.k = self.generate_k()

    def generate_k(self):
        """It accepts anything that's alphanumerical and 32 characters long,
        but fuck it, I'm implementing it like they did."""
        now = datetime.datetime.now()
        source = now.strftime("%Y%m%d%H%M%S") + str(int(now.strftime("%f"))//1000) + ALPHABET
        out = ""
        for i in range(32):
            out += source[math.floor(random.random() * len(source))]

        return out

    def get_content_info(self, cid):
        """Get the content info, including the 'p' parameter to later get content."""
        url = CONTENT_INFO_URL + "?" + urllib.parse.urlencode({"cid":cid, "k":self.k})
        logging.debug("Opening URL to get content info: {}".format(url))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            data = self.opener.open(request).read().decode()
        except urllib.error.HTTPError as e:
            logging.error("The server return HTTP error {} while getting content info.".format(e.code))
            return None
        
        self._content_info = json.loads(data)
        if self._content_info["result"] != 1:
            raise RuntimeError("get_content() got result {}.".format(self._content_info["result"]))
        
        self._content_info = self._content_info["items"][0]
        self._p = self._content_info["p"]
        self._cid = cid

        return self._content_info

    def get_content(self, cid):
        """Get the list of pages and metadata."""
        url = CONTENT_URL + "?" + urllib.parse.urlencode({"cid":cid, "p":self._p})
        logging.debug("Opening content URL: {}".format(url))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        
        try:
            data = self.opener.open(request).read().decode()
        except urllib.error.HTTPError as e:
            logging.error("The server return HTTP error {} while getting content.".format(e.code))
            return None
        
        self._content = json.loads(data)
        if self._content["result"] != 1:
            raise RuntimeError("get_content() got result {}.".format(self._content["result"]))

        self._pages = RE_IMAGE_PATH.findall(self._content["ttx"])
        # Repeats twice, so we only include first half.
        self._pages = self._pages[:len(self._pages) // 2]
        self.filenames = [s[s.index("/")+1:] for s in self._pages]

        return self._content

    def download_page(self, cid, page):
        """Try to download a page from the content server."""
        url = IMAGE_URL + "?" + urllib.parse.urlencode({"cid":cid, "p":self._p, "src":self._pages[page]})
        logging.debug("Opening image URL: {}".format(url))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        
        try:
            data = self.opener.open(request).read()
        except urllib.error.HTTPError as e:
            logging.error("The server return HTTP error {} while downloading a page.".format(e.code))
            return None

        return data
    
    def login(self, username, password):
        if not username or not password:
            raise RuntimeError("Log in attempted with a missing username or password.")
        else:
            self._username = username
            self._password = password
        
        # Get a token first.
        logging.debug("Getting a login token...")
        request = urllib.request.Request(LOGIN_SCREEN_URL, headers={"User-Agent": USER_AGENT})
        data = self.opener.open(request).read().decode()
        res = re.search("input type=\"hidden\" name=\"token\" value=\"(.+?)\">", data)
        if res:
            token = res.group(1)
        else:
            raise RuntimeError("Failed to get a login token.")

        # Log in.
        logging.debug("Logging in as '{}'...".format(self._username))
        params = urllib.parse.urlencode({"mail_addr": self._username, "pswd": self._password,
                                        "token": token }).encode("utf-8")
        request = urllib.request.Request(LOGIN_URL, params, {"User-Agent": USER_AGENT})
        self.opener.open(request)

        for cookie in self.cookies:
            if cookie.name == "BL_LI":
                logging.debug("Got session ID: {}".format(cookie.value))
                self._logged_in = True

        return self._logged_in

    def _decrypt_scramble_data(self, ciphertext, cid):
        def generate_key(cid, k):
            s = cid + ":" + k
            res = 0
            for i, char in enumerate(s):
                res += ord(char) << (i % 16)
            res &= 0x7FFFFFFF

            return res or 0x12345678

        key = generate_key(cid, self.k)
        res = ""
        for i, char in enumerate(ciphertext):
            key = (key >> 1) ^ (-(key & 1) & 0x48200004)
            c = ord(char) - 0x20
            n = ((c + key) % 0x5E) + 0x20
            res += chr(n)

        return json.loads(res)

    def get_descrambling_data(self, cid):
        if self._content_info is None:
            raise RuntimeError("Cannot decrypt descramble data before a call to get_content_info().")
        ctbl = self._decrypt_scramble_data(self._content_info["ctbl"], cid)
        ptbl = self._decrypt_scramble_data(self._content_info["ptbl"], cid)

        return ctbl, ptbl
