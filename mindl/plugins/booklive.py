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
import sys
import re

import mindl.plugins.binb as binbapi
from mindl.plugins.utils.binb_plugin import BinBPlugin

__version__ = "0.1"

# BIB API URL
URL_BOOKLIVE_API = "https://booklive.jp/bib-api/"
URL_LOGIN_SCREEN = "https://booklive.jp/login"
URL_LOGIN = "https://booklive.jp/login/index"

RE_BOOK = re.compile(r"^https?://booklive.jp/product/index/title_id/(?P<title_id>[0-9]+?)/vol_no/(?P<volume>[0-9]+?)$")
RE_TITLE_CLEANUP = re.compile(r".+?( ?\([0-9]+\)| ?[0-9]+巻)$")

class booklive(BinBPlugin):
    name = "BookLive"
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

        r = RE_BOOK.match(url)
        cid = "{}_{}".format(*r.groups())
        self._volume = int(r.group("volume"))
        super().__init__(URL_BOOKLIVE_API, cid, login=need_login)

        # Clean up the title a bit by removing the full-width stuff at the end of the title
        # (e.g. （４） for volume 4) and instead use the "Volume" entry later.
        if "Title" in self.metadata:
            r = RE_TITLE_CLEANUP.match(unicodedata.normalize("NFKC", self.metadata["Title"]))
            if r:
                self.metadata["Title"] = self.metadata["Title"][:-len(r.group(1))]

        # If it's a trial, the response will point us directly towards their CDN instead of through
        # sbcGetImg.php API acting as a proxy.
        trial = True if self.binb.server_type == binbapi.SERVERTYPE_STATIC else False
        self.metadata["Trial"] = trial
        if trial:
            if self["username"] and self["password"]:
                self.logger.warning("Username and password was supplied, but the server is responding with "
                    "a trial. You do not seem to own the book, meaning the book will NOT contain all pages.")
            else:
                self.logger.warning("The server responded with a trial. This means the book does NOT contain all pages.")

        # To avoid confusion, tag the directory whenever it's a trial.
        if trial:
            self._directory = "［立ち読み版］" + self._directory

    def get_volume(self, content_info):
        return self._volume

    def login(self, session):
        # Get a token first.
        self.logger.debug("Getting a login token...")
        r = session.get(URL_LOGIN_SCREEN)
        res = re.search("input type=\"hidden\" name=\"token\" value=\"(.+?)\">", r.text)
        if res:
            token = res.group(1)
        else:
            raise RuntimeError("Failed to get a login token.")

        # Log in.
        self.logger.debug("Logging in as '{}'...".format(self._username))
        params = {"mail_addr": self._username, "pswd": self._password, "token": token}
        r = session.post(URL_LOGIN, data=params)

        for cookie in session.cookies:
            if cookie.name == "BL_LI":
                self.logger.debug("Got session ID: {}".format(cookie.value))
                self._logged_in = True

        return self._logged_in

    @staticmethod
    def can_handle(url):
        if RE_BOOK.match(url):
            return True

        return False
