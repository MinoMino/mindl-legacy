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

import unicodedata
import requests
import sys
import re

import urllib.parse as urlparse

import mindl.plugins.binb as binbapi
from mindl.plugins.utils.binb_plugin import BinBPlugin

__version__ = "0.1"

# BIB API URL
URL_BOOKLIVE_API = "http://www.animatebookstore.com/sws/apis/"
URL_LOGIN_PAGE = "https://www.animatebookstore.com/mypage/"
URL_LOGIN = "https://www.animatebookstore.com/frontparts/login_check.php"

RE_BOOK = re.compile(r"^https?://(?:www.)?animatebookstore.com/products/detail.php\?product_id=(?P<product_id>\d+?)", flags=re.ASCII)
RE_BOOKVIEW = re.compile(r"https?://(?:www.)?animatebookstore.com/bookview/\?u0=(?P<product_id>\d+?)&amp;cid=(?P<cid>\d+)", flags=re.ASCII)
RE_TITLE_CLEANUP = re.compile(r".+?( ?(?P<volume>[0-9]+)巻)$")

class animatebookstore(BinBPlugin):
    name = "AnimateBookstore"
    options = BinBPlugin.options + [("username", ""), ("password", "")]

    def __init__(self, url):
        self._url = url

        if self["username"] and self["password"]:
            self._username = self["username"]
            self._password = self["password"]
            need_login = True
        elif self["username"] or self["password"]:
            self.logger.critical("Both username and password needs to be supplied, not just one of them.")
            sys.exit(1)
        else:
            need_login = False

        s = requests.Session()
        # Get product ID and content ID.
        regex = RE_BOOK.match(url)
        if regex:
            r = s.get(url)
            product_id, cid = RE_BOOKVIEW.search(r.text).groups()
        else:
            regex = RE_BOOKVIEW.match(url)
            product_id, cid = RE_BOOKVIEW.search(r.text).groups()

        # Login if we've been passed credentials.
        if need_login and not self.login(s):
            self.logger.critical("Login failed. Make sure credentials are correct.")
            sys.exit(1)
        
        super().__init__(URL_BOOKLIVE_API, cid, login=False, requests_session=s, u0=product_id)

        # Clean up the title a bit by removing the full-width stuff at the end of the title
        # (e.g. （４） for volume 4) and instead use the "Volume" entry later.
        if "Title" in self.metadata:
            r = RE_TITLE_CLEANUP.match(unicodedata.normalize("NFKC", self.metadata["Title"]))
            if r:
                self.metadata["Volume"] = r.group("volume")
                self.metadata["Title"] = self.metadata["Title"][:-len(r.group(1))]

        # As opposed to BookLive, not all trials are SERVERTYPE_STATIC, so for the time being
        # we have no definitive way of telling whether or not it's a trial unless I get a sample.
        trial = True if self.binb.server_type == binbapi.SERVERTYPE_STATIC else False
        self.metadata["Trial"] = trial
        if trial:
            if self["username"] and self["password"]:
                self.logger.warning("Username and password was supplied, but the images are hosted on "
                    "a CDN instead of through the API, meaning it could be a trial. Double check the "
                    "page count and make sure it's the full book if you own it.")
            else:
                self.logger.warning("The images are hosted on a CDN instead of through "
                    "the API, meaning it could be a trial. Double check the "
                    "page count and make sure it's the full book if you own it.")

        # To avoid confusion, tag the directory whenever it's a trial.
        #if trial:
        #    self.metadata["Title"] = "［立ち読み版］" + self.metadata["Title"]

    @staticmethod
    def can_handle(url):
        return any((RE_BOOK.match(url), RE_BOOKVIEW.match(url)))

    def login(self, session):
        # Get a token first.
        self.logger.debug("Getting a login token...")
        r = session.get(URL_LOGIN_PAGE)
        # When you open the login page, you get a 302 to a URL with a "transactionId",
        # which we need for the login POST.
        if not len(r.history):
            raise RuntimeError("No redirection after opening the login page.")
        query = urlparse.parse_qs(urlparse.urlparse(r.url).query)
        if "transactionid" not in query or not query["transactionid"]:
            raise RuntimeError("Got redirected, but found no transaction ID.")
        trans = query["transactionid"][-1]
        
        # Log in.
        self.logger.debug("Logging in as '{}'...".format(self._username))
        params = {
            "transactionid": trans,
            "mode": "login",
            "login_email": self._username,
            "login_pass": self._password,
            "login_memory": 0
            }
        r = session.post(URL_LOGIN, data=params)
        if r.status_code != requests.codes.ok:
            self.logger.critical("The server responded with status code {} while logging in."
                .format(r.status_code))
            sys.exit(1)

        try:
            j = r.json()
        except:
            self.logger.critical("Unexpected response from the server while logging in.")
            sys.exit(1)

        if "success" in j:
            return True

        return False
