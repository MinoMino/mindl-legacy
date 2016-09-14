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

import logging
import datetime

# If an option key starts with this, make it a required option.
REQUIRED_MAGIC = "@"

class BasePlugin():
    name = "N/A"
    options = tuple()
    _debug_logger = False

    def __iter__(self):
        if hasattr(self, "options"):
            return iter(self.options)

        return iter([])

    def __contains__(self, key):
        if hasattr(self, "options"):
            for opt in self.options:
                if key == opt.key:
                    return True

        return False

    def __getitem__(self, key):
        if hasattr(self, "options"):
            for opt in self.options:
                if key == opt.key:
                    return opt.value

        raise KeyError(key)

    @classmethod
    def process_options(cls):
        if not hasattr(cls, "_is_option_processed") and hasattr(cls, "options"):
            opts = []
            for k, v in cls.options:
                req = False
                if k.startswith(REQUIRED_MAGIC):
                    req = True
                    k = k[len(REQUIRED_MAGIC):]
                opts.append(Option(k, v, required=req))
            cls.options = opts
            cls._is_option_processed = True
            return True

        return False

    def progress(self):
        return None

    def directory(self):
        if not hasattr(self, "_directory"):
            self._directory = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S_") + self.name
        return self._directory

    def has_valid_options(self):
        is_valid = True
        for opt in self:
            if not opt.valid:
                self.logger.info("Option '{}' is a required option, but is not set.".format(opt.key))
                is_valid = False
        
        return is_valid

    @classmethod
    def input_options(cls, options, defaults=False):
        if not cls.options:
            return
        
        logger = logging.getLogger("mindl")
        unset_keys = [opt.key.lower() for opt in cls.options]
        for key, value in options.items():
            for opt in cls.options:
                if key.lower() == opt.key.lower():
                    logger.debug("The option '{}' was set to '{}'.".format(opt.key, value))
                    opt.value = value

                    # To know if we still have some options to set later, we keep track of
                    # what we've set so far by removing from unset_keys each time.
                    if key.lower() in unset_keys:
                        unset_keys.remove(key.lower())
        
        if defaults:
            for opt in cls.options:
                if opt.required and not opt.value:
                    logger.critical("The option '{}' has no default and is required to be set. "
                        "Run again with -o or without -d and input it manually.".format(opt.key))
                    exit(1)
        elif unset_keys:
            logger.info("Set this plugin's options:")
            for opt in cls.options:
                # If we set options through the command line, skip them.
                if opt.key.lower() not in unset_keys:
                    continue
                
                out = "  " + opt.key
                default = "" if opt.required else " [{}]".format(opt.value)
                out += default + ": "
                got = input(out).strip()
                if not got and not opt.required:
                    continue
                if not got:
                    logger.critical("The option '{}' is required!".format(opt.key))
                    exit(1)
                else:
                    opt.value = got
            
    def can_handle(url):
        raise NotImplementedError("The base plugin doesn't handle any URLs.")

    def downloader(self):
        raise NotImplementedError("'downloader' generator needs to be implemented.")

    def handle_exception(self, e):
        # Return False to tell the manager to raise it and let it go uncaught.
        # Return True to tell the manager to silently stop, assuming the plugin dealt with it.
        return False

    def finalize(self):
        pass

    @property
    def logger(self):
        if not hasattr(self, "_logger"):
            logger = logging.getLogger(self.name)
            logger.propagate = False
            logger.setLevel(logging.DEBUG)

            # Console
            console_fmt = logging.Formatter("(%(asctime)s %(levelname)s) [%(name)s] %(message)s", "%H:%M")
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG if self._debug_logger else logging.INFO)
            console_handler.setFormatter(console_fmt)
            logger.addHandler(console_handler)

            self._logger = logger
        
        return self._logger

class Option():
    def __init__(self, key, value=None, required=False):
        self._key = key
        self._value = value
        self._required = required

        if key == None:
            return AttributeError("An option's key cannot be None.")

    @property
    def key(self):
        return self._key

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value

    @property
    def required(self):
        return self._required

    @property
    def valid(self):
        if self.required and not self.value:
            return False

        return True
