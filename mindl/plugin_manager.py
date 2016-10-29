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

from .base_plugin import BasePlugin

import importlib
import pkgutil
import logging
import sys

class PluginManager():
    def __init__(self):
        self.plugins = {}
        self.logger = logging.getLogger("mindl")

        try:
            package = importlib.import_module("mindl.plugins")
        except:
            self.logger.exception("Make sure 'plugins' is a submodule of mindl.")
            sys.exit(1)

        prefix = package.__name__ + "."
        for importer, modname, ispkg in pkgutil.iter_modules(package.__path__, prefix):
            try:
                module = importlib.import_module(modname)
            except ImportError as e:
                self.logger.warning("Plugin '{}' could not be loaded: {}".format(modname.split(".")[-1], e))
                continue
            
            classname = modname.split(".")[-1]
            if hasattr(module, classname) and issubclass(getattr(module, classname).__class__, BasePlugin.__class__):
                self.logger.debug("Loading plugin '{}'...".format(classname))
                try:
                    ver = getattr(module, "__version__")
                except AttributeError:
                    ver = None
                self.plugins[getattr(module, classname)] = ver

    def find_handlers(self, url):
        self.logger.debug("Finding handlers for '{}'".format(url))
        # A list of plugin classes that will handle the URL.
        handlers = []
        # A list of strings with plugin name and version for debug purposes.
        out = []
        for plugin, version in self.plugins.items():
            if plugin.can_handle(url):
                handlers.append((plugin, version))
                out.append("{} v{}".format(plugin.name, version) if version else plugin.name)

        if not handlers:
            self.logger.debug("Found no handlers.")
            return None

        self.logger.debug("Found the following handlers: {}".format(", ".join(out)))
        return handlers

    def select_plugin(self, url, plugins):
        self.logger.info("Found multiple plugins that can handle '{}'.".format(url))
        self.logger.info("Please select one of the following plugins:")

        i = 1
        for plugin, version in plugins:
            if version is None:
                print("  {:2d}) {}".format(i, plugin.name))
            else:
                print("  {:2d}) {} v{}".format(i, plugin.name, version))
            i += 1

        got = ""
        while not got:
            try:
                got = int(input("Desired plugin: ").strip())
                if 0 < got < len(plugins) + 1:
                    return plugins[got - 1]
                else:
                    self.logger.error("The number does not match any plugin. Please try again...")
                    got = ""
            except ValueError:
                self.logger.error("Unintelligible number. Please try again...")


