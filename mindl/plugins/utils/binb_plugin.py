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

import os.path
import json
import sys
import os

import mindl.plugins.binb as binbapi
from mindl import download_directory
from mindl.plugins.utils.threaded_downloader import ThreadedDownloaderPlugin

# Data we should take from the content info response and pull it into our metadata.
METADATA = ["Authors", "Publisher", "PublisherRuby", "Title", "TitleRuby", "Categories", "Publisher",
            "PublisherRuby", "Abstract"]

VOLUME_UNSET = -999

# Number of errors before it gives up if another error were to happen.
MAX_ERRORS = 20

class BinBPlugin(ThreadedDownloaderPlugin):
    name = "BinBPlugin"
    options = [ ("page_start", "1"),
                ("page_end", "end"),
                ("lossless", "0"),
                ("metadata", "1"),
                ("zip_it", "1"),
                ("threads", "10"),
                ("additional_zip_content", "") ]

    # Data we should take from the content info response and pull it into our metadata.
    extract_metadata = ["Authors", "Publisher", "PublisherRuby", "Title", "TitleRuby",
        "Categories", "Publisher", "PublisherRuby", "Abstract"]

    def __init__(self, bib, cid, login=True):
        # A dictionary with info we can use for naming and to include in the zipped file if desired.
        self.metadata = {}

        self._cid = cid
        self.binb = binbapi.BinBApi(bib, self._cid, logger=self.logger)

        if login:
            self.login(self.binb.session)

        # Extract info into metadata dictionary.
        for md in METADATA:
            if md in self.binb.content_info:
                self.metadata[md] = self.binb.content_info[md]
        # Further processing is done to the metadata, but we wait until the first download,
        # so that any subclass can change stuff and/or process stuff before it's changed by us.

        # Initialize the threading stuff.
        try:
            threads = int(self["threads"])
        except:
            self.logger.critical("Unintelligible number of threads. Please use integers.")
            sys.exit(1)
        
        super().__init__(threads)
        # Distribute page numbers for the threads.
        self.distribute_items(range(len(self.binb.pages)), expected_downloads=len(self.binb.pages))

    def get_volume(self, content_info):
        return VOLUME_UNSET

    def login(self):
        raise NotImplementedError("Login method needs to be implemented if login=True.")
    
    def directory(self):
        return self._directory

    def progress(self):
        end_page = len(self.binb.pages) if self["page_end"] == "end" else int(self["page_end"])
        
        return self.download_counter, int(end_page + 1 - int(self["page_start"]))

    def downloader(self):
        # Since BinB doesn't keep track of volume, we'll need to get it ourselves.
        # If it's VOLUME_UNSET, assume it's not set and ignore it instead.
        self.metadata["Volume"] = self.get_volume(self.binb.content_info)

        # Use above metadata to name our target directory.
        if "Title" in self.metadata:
            if "Volume" in self.metadata and self.metadata["Volume"] != VOLUME_UNSET:
                self._directory = self.metadata["Title"] + " 第{}巻".format(self.metadata["Volume"])
            else:
                self._directory = self.metadata["Title"]
            # We only add the author(s) if they're 3 or fewer. Don't want the filename to get out of hand.
            if "Authors" in self.metadata and len(self.metadata["Authors"]) <= 3:
                names = [a["Name"] for a in self.metadata["Authors"]]
                self._directory += " 【{}】".format("×".join(names))
        else:
            self._directory = super().directory()

        dler = super().downloader()
        for dl in dler:
            yield dl

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

    def download_many(self, pages):
        while len(pages):
            # Check if we need to stop.
            if self.stop_event.is_set():
                return

            page = pages.pop(0)
            try:
                data = self.binb.get_image(page)
            except:
                self.logger.exception("Failed to get an image from the API. Trying again...")
                data = None
            
            if data is None:
                if self._errors >= MAX_ERRORS:
                    self.logger.critical("The number of errors has exceeded the maximum allowed. Aborting!")
                    self.stop_event.set()
                    return
                else:
                    with self._errors_lock:
                        self._errors += 1
                    continue

            keywords = {"format":"PNG", "optimize":True} if bool(int(self["lossless"])) else {"format":"JPEG", "quality":95, "optimize":True}
            data = self.binb.descramble(page, data, **keywords)

            # Add (filename, data) to list for further processing.
            ext = "jpg" if keywords["format"] == "JPEG" else "png"
            self.got_download(("{:04d}.{}".format(page + 1, ext), data))
