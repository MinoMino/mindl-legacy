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
import threading
import os.path
import json
import time
import sys
import os
import re

import mindl.plugins.binb as binbapi
from mindl import BasePlugin, download_directory

__version__ = "0.1"

# BIB API URL
URL_BOOKLIVE_API = "http://booklive.jp/bib-api/"
URL_LOGIN_SCREEN = "https://booklive.jp/login"
URL_LOGIN = "https://booklive.jp/login/index"

# Number of errors before it gives up if another error were to happen.
MAX_ERRORS = 20

RE_BOOK = re.compile(r"^https?://booklive.jp/product/index/title_id/(?P<title_id>[0-9]+?)/vol_no/(?P<volume>[0-9]+?)$")
RE_TITLE_CLEANUP = re.compile(r".+?( ?\([0-9]+\)| ?[0-9]+巻)$")

# Data we should take from the content info response and pull it into our metadata.
METADATA = ("Authors", "Publisher", "PublisherRuby", "Title", "TitleRuby", "Categories", "Publisher",
            "PublisherRuby", "Abstract")

class booklive(BasePlugin):
    name = "BookLive"
    options = ( ("page_start", "1"),
                ("page_end", "end"),
                ("lossless", "0"),
                ("metadata", "1"),
                ("zip_it", "1"),
                ("threads", "10"),
                ("username", ""),
                ("password", ""),
                ("additional_zip_content", "") )

    def __init__(self, url):
        self._url = url

        r = RE_BOOK.match(url)
        self._cid = "{}_{}".format(*r.groups())
        self._binb = binbapi.BinBApi(URL_BOOKLIVE_API, self._cid)
        # Check if we need to login.
        self._logged_in = False
        if self["username"] and self["password"]:
            self._username = self["username"]
            self._password = self["password"]
            self.login()
        elif self["username"] or self["password"]:
            self.logger.critical("Both username and password needs to be supplied, not just one of them.")
            sys.exit(1)

        # A dictionary with info we can use for naming and to include in the zipped file if desired.
        self.metadata = {}
        self.metadata["Volume"] = int(r.group("volume"))
        # Extract info into metadata dictionary.
        for md in METADATA:
            if md in self._binb.content_info:
                self.metadata[md] = self._binb.content_info[md]

        # Clean up the title a bit by removing the full-width stuff at the end of the title
        # (e.g. （４） for volume 4) and instead use the "Volume" entry later.
        if "Title" in self.metadata:
            r = RE_TITLE_CLEANUP.match(unicodedata.normalize("NFKC", self.metadata["Title"]))
            if r:
                self.metadata["Title"] = self.metadata["Title"][:-len(r.group(1))]

        # If it's a trial, the response will point us directly towards their CDN instead of through
        # sbcGetImg.php API acting as a proxy.
        trial = True if self._binb.server_type == binbapi.SERVERTYPE_STATIC else False
        self.metadata["Trial"] = trial
        if trial:
            if self["username"] and self["password"]:
                self.logger.warning("Username and password was supplied, but the server is responding with "
                    "a trial. You do not seem to own the book, meaning the book will NOT contain all pages.")
            else:
                self.logger.warning("The server responded with a trial. This means the book does NOT contain all pages.")

        # Use above metadata to name our target directory.
        if "Title" in self.metadata:
            if "Volume" in self.metadata:
                self._directory = self.metadata["Title"] + " 第{}巻".format(self.metadata["Volume"])
            else:
                self._directory = self.metadata["Title"]
            # We only add the author(s) if they're 3 or fewer. Don't want the filename to get out of hand.
            if "Authors" in self.metadata and len(self.metadata["Authors"]) <= 3:
                names = [a["Name"] for a in self.metadata["Authors"]]
                self._directory += " 【{}】".format("×".join(names))
        else:
            self._directory = super().directory()

        # To avoid confusion, tag the directory whenever it's a trial.
        if trial:
            self._directory = "［立ち読み版］" + self._directory
        
        # Threading stuff.
        self._thread_count = int(self["threads"])
        self._threads = []
        self._stop_event = threading.Event()
        self._require_processing = []
        self._processed = []
        self._errors = 0 # Number of errors while downloading files.
        self._errors_lock = threading.Lock()

    def login(self):
        # Get a token first.
        self.logger.debug("Getting a login token...")
        r = self._binb.session.get(URL_LOGIN_SCREEN)
        res = re.search("input type=\"hidden\" name=\"token\" value=\"(.+?)\">", r.text)
        if res:
            token = res.group(1)
        else:
            raise RuntimeError("Failed to get a login token.")

        # Log in.
        self.logger.debug("Logging in as '{}'...".format(self._username))
        params = {"mail_addr": self._username, "pswd": self._password, "token": token}
        r = self._binb.session.post(URL_LOGIN, data=params)

        for cookie in self._binb.session.cookies:
            if cookie.name == "BL_LI":
                self.logger.debug("Got session ID: {}".format(cookie.value))
                self._logged_in = True

        return self._logged_in

    @staticmethod
    def can_handle(url):
        if RE_BOOK.match(url):
            return True

        return False

    def directory(self):
        return self._directory

    def progress(self):
        end_page = len(self._binb.pages) if self["page_end"] == "end" else int(self["page_end"])
        
        return len(self._processed), int(end_page + 1 - int(self["page_start"]))

    def done(self):
        current, total = self.progress()
        return not bool(total - current)

    def downloader(self):
        # Start all the threads and start downloading immediately.
        self._start_threads()
        
        try:
            while not self.done():
                while not len(self._require_processing) and self._are_threads_alive():
                    time.sleep(0.1)

                if not len(self._require_processing):
                    # Threads are dead. We're done.
                    break

                filename, data = self._require_processing.pop()
                self._processed.append(filename)
                yield filename, data
        except KeyboardInterrupt:
            self.logger.info("Download interrupted! Waiting for threads to stop...")
            self._stop_event.set()
            while self._are_threads_alive():
                time.sleep(0.1)

    def finalize(self):
        mydir = os.path.join(download_directory(), self.directory())

        if bool(int(self["zip_it"])):
            from shutil import rmtree
            self.logger.debug("Zipping files...")
            items = os.listdir(mydir)
            from zipfile import ZipFile
            zipf = ZipFile(mydir + ".zip" , mode="w")
            for item in items:
                zipf.write(os.path.join(mydir, item), "content/" + item)
            if self["additional_zip_content"]:
                for extra_file in [f.strip() for f in self["additional_zip_content"].split(",")]:
                    zipf.write(extra_file, os.path.basename(extra_file))
            if bool(int(self["metadata"])):
                zipf.writestr("metadata.json", self._serialize_metadata())
            zipf.close()
            self.logger.info("Collection zipped to '{}'!".format(mydir + ".zip"))
            self.logger.info("Deleting directory '{}'...".format(mydir))
            rmtree(mydir)
        elif bool(int(self["metadata"])):
            with open(os.path.join(mydir, "metadata.json"), "w", encoding="utf-8") as f:
                f.write(self._serialize_metadata())

    def _serialize_metadata(self):
        return json.dumps(self.metadata, indent=4, sort_keys=True, ensure_ascii=False)

    def _download_and_descramble_many(self, pages):
        #self.logger.debug("Thread #{} started!".format(self._threads.index(threading.current_thread())))
        while len(pages):
            # Check if we need to stop.
            if self._stop_event.is_set():
                return

            page = pages.pop(0)
            try:
                data = self._binb.get_image(page)
            except:
                self.logger.exception("Failed to get an image from the API. Trying again...")
                data = None
            
            if data is None:
                if self._errors >= MAX_ERRORS:
                    self.logger.critical("The number of errors has exceeded the maximum allowed. Aborting!")
                    self._stop_event.set()
                    return
                else:
                    with self._errors_lock:
                        self._errors += 1
                    continue

            keywords = {"format":"PNG", "optimize":True} if bool(int(self["lossless"])) else {"format":"JPEG", "quality":95, "optimize":True}
            data = self._binb.descramble(page, data, **keywords)

            # Add (filename, data) to list for further processing.
            ext = "jpg" if keywords["format"] == "JPEG" else "png"
            self._require_processing.append(("{:04d}.{}".format(page + 1, ext), data))

        #self.logger.debug("Thread #{} stopped!".format(self._threads.index(threading.current_thread())))

    def _split_pages(self, pages):
        thread_pages = [[] for i in range(self._thread_count)]
        for i, page in enumerate(pages):
            thread_pages[i % self._thread_count].append(page)

        return thread_pages

    def _are_threads_alive(self):
        for thread in self._threads:
            if thread.is_alive():
                return True

        return False

    def _start_threads(self):
        # Distribute pages.
        total = len(self._binb.pages)
        end_page = total if self["page_end"] == "end" else min(total, int(self["page_end"]))
        thread_pages = self._split_pages([i for i in range(end_page)])
        
        # Start threads.
        for i in range(self._thread_count):
            self._threads.append(threading.Thread(target=self._download_and_descramble_many, args=(thread_pages[i],)))
            self._threads[i].start()
            time.sleep(0.2)
