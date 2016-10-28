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

import requests
import datetime
import logging
import base64
import random
import math
import json
import re

from urllib.parse import urlencode
from io import BytesIO

try:
    from .descramble import BinBDescrambler
except ImportError:
    # Allow this file to be ran as __main__.
    from descramble import BinBDescrambler

"""
A helper module that makes requests to BinB Reader's HTML5 e-book reader API.

Since this is a private API, these calls are all based on reverse engineering.
I got several directory listings of servers serving the API, so the methods
are all here, but not all of the parameters are known to me, and some of them
just aren't really of interest (e.g. settings and memo stuff).

Note that while this class has methods for each of the API methods, this class
is higher level. This means that signatures don't match at all, and a lot of
stuff (e.g. k value, p value, dealing with ServerType) is taken care of behind
the scenes. You can however set those manually, as those properties have setters.

"""

USER_AGENT = "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)"
RE_IMAGE_PATH = re.compile(r"t-img src=\"(.+?)\"")
RE_DATA_URI = re.compile(r"^(?:data:)?(?P<mime>[\w/\-\.]+);(?P<encoding>\w+),(?P<data>.*)$")
RE_CONTENT_JS = re.compile(r"^\w+?\((?P<data>.+)\)$")

# For k generation. Doesn't really need to be implemented like the JS, but we don't
# want to stand out, so we implement it like the JS code does.
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# API methods for easy formatting of the URL. we could theoretically use the params
# keyword when doing requests with a requests.Session, but then the URL would only
# be properly formatted *after* the request.
BIB_API_METHODS = {
    "get_content_info": "{bib}bibGetCntntInfo.php?{params}",
    "get_bibliography": "{bib}bibGetBibliography.php?{params}",
    "get_content_settings": "{bib}bibGetCntSetting.php?{params}",
    "set_content_settings": "{bib}bibUdtCntSetting.php?{params}",
    "get_memo": "{bib}bibGetMemo.php?{params}",
    "set_memo": "{bib}bibRegMemo.php?{params}"
}
SBC_API_METHODS = {
    "check_login": "{sbc}sbcChkLogin.php?{params}",
    "check_p": "{sbc}sbcPCheck.php?{params}",
    "content_check": "{sbc}sbcContentCheck.php?{params}",
    "get_content": "{sbc}sbcGetCntnt.php?{params}",
    "get_image": "{sbc}sbcGetImg.php?{params}",
    "get_image_base64": "{sbc}sbcGetImgB64.php?{params}",
    "get_nec_image": "{sbc}sbcGetNecImg.php?{params}",
    "get_nec_image_list": "{sbc}sbcGetNecImgList.php?{params}",
    "get_request_info": "{sbc}sbcGetRequestInfo.php?{params}",
    "get_small_image": "{sbc}sbcGetSmlImg.php?{params}",
    "get_small_image_list": "{sbc}sbcGetSmlImgList.php?{params}",
    "text_to_speech": "{sbc}sbcTextToSpeech.php?{params}",
    "user_login": "{sbc}sbcUserLogin.php?{params}"
}

# bib's get_content_info returns ServerType.
# ServerType == 0 means the images should be downloaded through the provided sbc API.
# ServerType == 1 means the images should be downloaded directly from the provided CDN.
# The former tends to be used for paid books, the latter for trials.
SERVERTYPE_UNSET = None
SERVERTYPE_SBC = 0
SERVERTYPE_STATIC = 1

class BinBApiError(Exception):
    """Generic exception raised when the API returns <=0, meaning something went wrong."""
    pass

class BinBApi:
    # The various image sizes. Presumably:
    #   M/S = Medium/Small resolution
    #   H/L = High/Low quality
    # There's also SS, but it's unscrambled and extremely low resoution and quality.
    # If you really want SS, use get_nec_image with regular filenames.
    # L has pretty bad artifacting, so most of the time S_H > M_L.
    # I've never seen anything over M, so for now I'm assuming it doesn't exist.
    image_size_priorities = ("M_H", "S_H", "M_L", "S_L") # SS omitted.
    
    def __init__(self, bib_url, cid, logger=None, **kwargs):
        self._bib = bib_url if bib_url.endswith("/") else bib_url + "/"
        self._kwargs = kwargs
        self._sbc = None
        self._cid = cid
        self._k = None
        self._p = None
        self._content_info = None
        self.content = None
        self._server_type = SERVERTYPE_UNSET
        self._pages = None # Only the filenames of the pages.
        self._page_paths = None # Pages with the full "pages/" prefix.
        # No idea what "nec" pages are, as no sample has yet had them. Still implementing it, though.
        self._nec_pages = None # Only the filenames of the pages.
        self._nec_page_paths = None # Pages with the full "pages/" prefix.
        self._logger = logger or logging.getLogger()
        # Descrambling data and descrambler instance.
        self._descrambling_data = None
        self._descrambler = None

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

        # If set to True, allow SBC methods while in SERVERTYPE_STATIC if we have 'p'.
        # On BookLive, for instance, you can still proxy images through SBC even if
        # the API tells you to use static content. Note that you need to manually
        # set SBC to point to the API after a call to get_content_info for it to work.
        # Getting static content is faster in any case, so don't worry about that.
        self.allow_sbc_on_static = False

    @staticmethod
    def generate_k():
        """
        For k generation. Doesn't really need to be implemented like the JS,
        but we don't want to stand out, so we implement it like the JS code does.

        """
        now = datetime.datetime.now()
        source = now.strftime("%Y%m%d%H%M%S") + str(int(now.strftime("%f"))//1000) + ALPHABET
        res = ""
        for i in range(32):
            res += source[math.floor(random.random() * len(source))]

        return res

    @property
    def cid(self):
        if self._cid is None:
            raise RuntimeError("Attempted to use 'cid' without being set.")
        
        return self._cid

    @cid.setter
    def cid(self, value):
        self._cid = value
        self._logger.debug("'cid' was set to: " + str(value))

    @property
    def sbc(self):
        if self._sbc is None:
            self.get_content_info()
        
        return self._sbc

    @sbc.setter
    def sbc(self, value):
        self._sbc = value
        self._logger.debug("'sbc' was set to: " + str(value))

    @property
    def bib(self):
        return self._bib

    @bib.setter
    def bib(self, value):
        self._bib = value
        self._logger.debug("'bib' was set to: " + str(value))

    @property
    def k(self):
        if self._k is None:
            self._k = self.generate_k()

        return self._k

    @k.setter
    def k(self, value):
        self._k = value
        self._logger.debug("'k' was set to: " + str(value))

    @property
    def p(self):
        if self._p is None:
            self.get_content_info()
        
        return self._p

    @p.setter
    def p(self, value):
        self._p = value
        self._logger.debug("'p' was set to: " + str(value))

    @property
    def content_info(self):
        if self._content_info is None:
            self.get_content_info()

        return self._content_info

    @content_info.setter
    def content_info(self, value):
        self._content_info = value

    @property
    def pages(self):
        if self._pages is None:
            self.get_content()

        return self._pages

    @pages.setter
    def pages(self, value):
        self._pages = value

    @property
    def page_paths(self):
        if self._page_paths is None:
            self.get_content()

        return self._page_paths

    @page_paths.setter
    def page_paths(self, value):
        self._page_paths = value

    @property
    def nec_pages(self):
        if self._nec_pages is None:
            self.get_nec_image_list()

        return self._nec_pages

    @nec_pages.setter
    def nec_pages(self, value):
        self._nec_pages = value

    @property
    def nec_page_paths(self):
        if self._nec_page_paths is None:
            self.get_nec_image_list()

        return self._nec_page_paths

    @nec_page_paths.setter
    def nec_page_paths(self, value):
        self._nec_page_paths = value

    @property
    def server_type(self):
        if self._server_type is SERVERTYPE_UNSET:
            self.get_content_info()

        return self._server_type

    @server_type.setter
    def server_type(self, value):
        self._server_type = value
        self._logger.debug("'server_type' was set to: " + str(value))

    @property
    def descrambling_data(self):
        if self._descrambling_data is None:
            self.get_content_info()

        return self._descrambling_data

    @descrambling_data.setter
    def descrambling_data(self, value):
        self._descrambling_data = value
        self._descrambler = BinBDescrambler(self._descrambling_data)
        #self._logger.debug("'descrambling_data' was set to: " + str(value))

    # ====================================================================
    #                             BIB METHODS
    # ====================================================================

    def get_content_info(self, **kwargs):
        """Get the content info, including the 'p' parameter to later get content."""
        params = dict(cid=self.cid, k=self.k, **self._kwargs, **kwargs)
        url = BIB_API_METHODS["get_content_info"].format(bib=self.bib,
            params=urlencode(params))
        self._logger.debug("Calling get_content_info: {}".format(url))
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()
        
        self._content_info = r.json()
        result = self._content_info["result"]
        if result != 1:
            raise BinBApiError("get_content_info returned result: " + str(result))
        
        self._content_info = self._content_info["items"][0]
        # Extract and decrypt descrambling data.
        ctbl = self._decrypt_descramble_data(self._content_info["ctbl"])
        ptbl = self._decrypt_descramble_data(self._content_info["ptbl"])
        self.descrambling_data = (ctbl, ptbl)

        self.server_type = self._content_info["ServerType"]
        if self.server_type != SERVERTYPE_STATIC and "p" in self._content_info:
            self.p = self._content_info["p"]
        sbc = self._content_info["ContentsServer"]
        self.sbc = sbc if sbc.endswith("/") else sbc + "/"

        return self._content_info

    def get_bibliography(self, **kwargs):
        """Gets metadata about the book. Much, if not all of it, is already included in get_content_info."""
        params = dict(cid=self.cid, k=self.k, **self._kwargs, **kwargs)
        url = BIB_API_METHODS["get_bibliography"].format(bib=self.bib,
            params=urlencode(params))
        self._logger.debug("Calling get_bibliography: {}".format(url))
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()
        
        res = r.json()
        ret_code = res["result"]
        if ret_code != 1:
            raise BinBApiError("get_bibliography returned result: " + str(ret_code))

        return res["items"][0]

    def get_content_settings(self, **kwargs):
        raise NotImplementedError("This API method has not been implemented, "
            "likely due to it not being important or having unknown parameters.")

    def set_content_settings(self, **kwargs):
       raise NotImplementedError("This API method has not been implemented, "
            "likely due to it not being important or having unknown parameters.")
       
    def get_memo(self, **kwargs):
       raise NotImplementedError("This API method has not been implemented, "
           "likely due to it not being important or having unknown parameters.")

    def set_memo(self, **kwargs):
       raise NotImplementedError("This API method has not been implemented, "
           "likely due to it not being important or having unknown parameters.")

    # ====================================================================
    #                             SBC METHODS
    # ====================================================================

    def check_login(self, **kwargs):
        """Check whether or not the API recognizes us as being logged in."""
        params = dict(cid=self.cid, p=self.p, **self._kwargs, **kwargs)
        url = SBC_API_METHODS["check_login"].format(bib=self.bib, params=urlencode(params))
        self._logger.debug("Calling get_content: {}".format(url))
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()
        elif r.json()["result"] != 1:
            return False

        return True

    def check_p(self, **kwargs):
        """Check whether or not the 'p' is valid. If it's not, downloads will not work."""
        params = dict(cid=self.cid, p=self.p, **self._kwargs, **kwargs)
        url = SBC_API_METHODS["check_p"].format(sbc=self.sbc, params=urlencode(params))
        self._logger.debug("Calling check_p: {}".format(url))
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()
        elif r.json()["result"] != 1:
            return False

        return True

    def get_content(self, **kwargs):
        """
        Get the list of pages and a bunch of other data mostly used by the reader.
        Using get_small_image_list is more preferable if you only need to get the pages.

        Whenever server type is SERVERTYPE_STATIC, this method will fall back to using
        content.js unless allow_sbc_on_static is True and we have 'p'.

        """
        if self.server_type == SERVERTYPE_STATIC and not self.allow_sbc_on_static:
            url = self.sbc + "content.js"
            r = self.session.get(url)
            if r.status_code != requests.codes.ok:
                r.raise_for_status()
            self._content = json.loads(RE_CONTENT_JS.match(r.text).group("data"))
        else:
            self._assert_sbc_server_type()
            params = dict(cid=self.cid, p=self.p, **self._kwargs, **kwargs)
            url = SBC_API_METHODS["get_content"].format(sbc=self.sbc, params=urlencode(params))
            self._logger.debug("Calling get_content: {}".format(url))
            r = self.session.get(url)
            if r.status_code != requests.codes.ok:
                r.raise_for_status()
            
            self._content = r.json()
            result = self._content["result"]
            if result != 1:
                raise BinBApiError("get_content returned result: " + str(result))

        # Repeats twice, so we only include first half.
        page_paths = RE_IMAGE_PATH.findall(self._content["ttx"])
        self.page_paths = page_paths[:len(page_paths) // 2]
        # Strip the "pages/" prefix and only keep filenames. Useful for descrambling later.
        self.pages = tuple([s[s.index("/")+1:] for s in self.page_paths])

        return self._content

    def get_image(self, page_number, descramble=True, **kwargs):
        """
        Try to download a page from the content server. Returns bytes.

        Whenever server type is SERVERTYPE_STATIC, this method will fall back to using
        static content unless allow_sbc_on_static is True and we have 'p'.

        """
        if self.server_type == SERVERTYPE_STATIC and not self.allow_sbc_on_static:
            for size in self.image_size_priorities:
                url = self.sbc + self.page_paths[page_number] + "/{}.jpg".format(size)
                r = self.session.get(url)
                if r.status_code != requests.codes.ok:
                    continue
                else:
                    break
            
            if r.status_code != requests.codes.ok:
                r.raise_for_status()
        else:
            self._assert_sbc_server_type()
            params = dict(cid=self.cid, p=self.p, src=self.page_paths[page_number], h=9999, q=0, **self._kwargs, **kwargs)
            url = SBC_API_METHODS["get_image"].format(sbc=self.sbc, params=urlencode(params))
            r = self.session.get(url)
            if r.status_code != requests.codes.ok:
                r.raise_for_status()

        return r.content

    def get_image_base64(self, page_number, descramble=True, **kwargs):
        """
        Try to download a page from the content server as a data URI, then decode and return as bytes.
        The name of the method refers to which API method is called, not what it returns.
        """
        self._assert_sbc_server_type()
        params = dict(cid=self.cid, p=self.p, src=self.page_paths[page_number], h=9999, q=0, **self._kwargs, **kwargs)
        url = SBC_API_METHODS["get_image_base64"].format(sbc=self.sbc, params=urlencode(params))
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()

        res = r.json()
        ret_code = res["result"]
        if ret_code != 1:
            raise BinBApiError("get_image_base64 returned result: " + str(ret_code))

        re_data = RE_DATA_URI.match(res["Data"])
        if re_data is None:
            raise RuntimeError("Unexpected data in get_image_base64: " + res["Data"])

        return base64.b64decode(re_data.group("data"))

    def get_nec_image(self, page_number, **kwargs):
        """
        I honestly have no idea what a "nec" image is, as none of the samples I've worked on
        have had returned them when I use get_nec_image_list. You can however pass it regular
        file paths and it'll return the smallest sized one usually, base64 encoded.

        Similar to get_image_base64, images also come encoded in base64, but the JSON
        structure is a bit different.

        """
        self._assert_sbc_server_type()
        # Allow overwriting of src here in case you want to call this API method with a regular file path.
        if "src" in kwargs:
            params = dict(cid=self.cid, p=self.p, h=9999, q=0, **self._kwargs, **kwargs)
        else:
            params = dict(cid=self.cid, p=self.p, src=self.nec_page_paths[page_number], h=9999, q=0, **self._kwargs, **kwargs)
        
        url = SBC_API_METHODS["get_nec_image"].format(sbc=self.sbc, params=urlencode(params))
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()

        res = r.json()
        ret_code = res["result"]
        if ret_code != 1:
            raise BinBApiError("get_nec_image returned result: " + str(ret_code))

        res = res["items"][0]
        re_data = RE_DATA_URI.match(res["Data"])
        if re_data is None:
            raise RuntimeError("Unexpected data in get_nec_image: " + res["Data"])

        return base64.b64decode(re_data.group("data"))

    def get_nec_image_list(self, **kwargs):
        """Returns a list of "nec" page paths. Whatever that is."""
        self._assert_sbc_server_type()
        params = dict(cid=self.cid, p=self.p, h=9999, q=0, **self._kwargs, **kwargs)
        url = SBC_API_METHODS["get_nec_image_list"].format(sbc=self.sbc, params=urlencode(params))
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()

        res = r.json()
        ret_code = res["result"]
        if ret_code != 1:
            raise BinBApiError("get_nec_image_list returned result: " + str(ret_code))

        self.nec_page_paths = tuple(res["ImageName"])
        self.pages = tuple([s[s.index("/")+1:] for s in self.nec_page_paths])
        
        return self.nec_page_paths

    def get_small_image(self, page_number, descramble=True, **kwargs):
        """
        Try to download a page from the content server as a data URI. Other than the
        JSON structure, it doesn't seem to differ much from get_image_base64. The image
        is decoded before returning, so it'll return bytes.

        Whenever server type is SERVERTYPE_STATIC, this method will fall back to using
        static content unless allow_sbc_on_static is True and we have 'p'.

        """
        if self.server_type == SERVERTYPE_STATIC and not self.allow_sbc_on_static:
            return self.get_image(page_number, **kwargs)

        self._assert_sbc_server_type()
        params = dict(cid=self.cid, p=self.p, src=self.page_paths[page_number], h=9999, q=0, **self._kwargs, **kwargs)
        url = SBC_API_METHODS["get_small_image"].format(sbc=self.sbc, params=urlencode(params))
        r = self.session.get(url)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()

        res = r.json()
        ret_code = res["result"]
        if ret_code != 1:
            raise BinBApiError("get_small_image returned result: " + str(ret_code))

        res = res["items"][0]
        re_data = RE_DATA_URI.match(res["Data"])
        if re_data is None:
            raise RuntimeError("Unexpected data in get_small_image: " + res["Data"])

        return base64.b64decode(re_data.group("data"))

    def get_small_image_list(self, **kwargs):
        """
        Returns a list of page paths. It's way neater and more reliable than using get_content
        if you only need the page list.

        Whenever server type is SERVERTYPE_STATIC, this method will fall back to using
        content.js unless allow_sbc_on_static is True and we have 'p'.

        """
        if self.server_type == SERVERTYPE_STATIC and not self.allow_sbc_on_static:
            self.get_content(**kwargs)
        else:
            self._assert_sbc_server_type()
            params = dict(cid=self.cid, p=self.p, h=9999, q=0, **self._kwargs, **kwargs)
            url = SBC_API_METHODS["get_small_image_list"].format(sbc=self.sbc, params=urlencode(params))
            r = self.session.get(url)
            if r.status_code != requests.codes.ok:
                r.raise_for_status()

            res = r.json()
            ret_code = res["result"]
            if ret_code != 1:
                raise BinBApiError("get_small_image_list returned result: " + str(ret_code))

            self.page_paths = tuple(res["ImageName"])
            self.pages = tuple([s[s.index("/")+1:] for s in self.page_paths])
        
        return self.page_paths

    def get_request_info(self):
        """
        With the help of some leaked PHP source I found, this method seems to be the
        juiciest, as it's the one that gives out a 'p' for the 'cid' requested, but
        it's set up so that it only responds to the server hosting the BIB API.

        """
        raise NotImplementedError("This API method has not been implemented, "
            "likely due to it not being important or having unknown parameters.")

    def text_to_speech(self):
      raise NotImplementedError("This API method has not been implemented, "
           "likely due to it not being important or having unknown parameters.")

    def user_login(self):
        """
        Could be interesting to poke at, but I don't know the parameters it takes.
        All sites I've dealt with deal with authentication using cookies not set by
        BinB, but by the site itself.

        """
        raise NotImplementedError("This API method has not been implemented, "
            "likely due to it not being important or having unknown parameters.")

    # ====================================================================
    #                               HELPERS
    # ====================================================================

    def _assert_sbc_server_type(self):
        """
        Raises an exception if an SBC exclusive method is used while server
        type is SERVERTYPE_STATIC.

        """
        if self.server_type != SERVERTYPE_SBC:
            if not self.allow_sbc_on_static:
                raise RuntimeError("Attempted an SBC method while server type is SERVERTYPE_STATIC.")
            elif not self.p:
                # We can't proxy through SBC even if we wanted to.
                raise RuntimeError("allow_sbc_on_static is True, but no 'p' was received.")

    def _decrypt_descramble_data(self, ciphertext):
        def generate_key(cid, k):
            s = cid + ":" + k
            res = 0
            for i, char in enumerate(s):
                res += ord(char) << (i % 16)
            res &= 0x7FFFFFFF

            return res or 0x12345678

        key = generate_key(self.cid, self.k)
        res = ""
        for i, char in enumerate(ciphertext):
            key = (key >> 1) ^ (-(key & 1) & 0x48200004)
            c = ord(char) - 0x20
            n = ((c + key) % 0x5E) + 0x20
            res += chr(n)

        return json.loads(res)

    # ====================================================================
    #                               HELPERS
    # ====================================================================

    def descramble(self, page_number, image_data, **kwargs):
        """
        Convenience method for descrambling images. Page number is needed
        because of the fact that the filename of the image is used to
        determine which key should be used to descramble.

        Keyword arguments are forwarded to PIL to control the output format
        (e.g. PNG, JPEG) and whatnot. Default is JPEG with 95 quality.

        """
        return self._descrambler.descramble(self.pages[page_number], BytesIO(image_data), **kwargs)

if __name__ == "__main__":
    import sys
    logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.DEBUG)
    if len(sys.argv) < 2:
        print("Usage: {} <site_name>".format(sys.argv[0]))
        exit(0)

    from PIL import Image
    name = " ".join(sys.argv[1:])
    if name.lower() == "cmoa":
        # u0=0, u1=0 are cmoa specific values, so we tell it to always use it with requests.
        binb = BinBApi("http://www.cmoa.jp/bib/sws/", "0000087508_jp_0004", u0=0, u1=0)

        # get_image
        data = binb.descramble(0, binb.get_image(0))
        img = Image.open(BytesIO(data))
        img.show()
        img.close()

        # get_image_base64
        data = binb.descramble(0, binb.get_image_base64(0))
        img = Image.open(BytesIO(data))
        img.show()
        img.close()

        # get_nec_image
        # Probably doesn't have any nec images, so we overwrite src with a regular image path.
        data = binb.get_nec_image(0, src=binb.page_paths[0])
        img = Image.open(BytesIO(data))
        img.show()
        img.close()

        # get_small_image
        data = binb.descramble(0, binb.get_small_image(0))
        img = Image.open(BytesIO(data))
        img.show()
        img.close()
    elif name.lower() == "animate":
        binb = BinBApi("http://www.animatebookstore.com/sws/apis/", "662011", u0="280326")

        # get_image
        for i in range(min(len(binb.pages), 3)):
            data = binb.descramble(i, binb.get_image(i))
            img = Image.open(BytesIO(data))
            img.show()
            img.close()

        # get_small_image
        data = binb.descramble(0, binb.get_small_image(0))
        img = Image.open(BytesIO(data))
        img.show()
        img.close()
    elif name.lower() == "booklive":
        binb = BinBApi("http://booklive.jp/bib-api/", "378252_001")
        for i in range(min(len(binb.pages), 3)):
            data = binb.descramble(i, binb.get_image(i))
            img = Image.open(BytesIO(data))
            img.show()
            img.close()
    else:
        print("'{}' is an unknown site.".format(name))
