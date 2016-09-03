# mindl
A plugin-based downloading tool. It was written with Python 3.5+ in mind, so while it's likely that at least 3.4 works,
it's possible I've used new stuff that could potentially make it incompatible.

It was written for the purpose of downloading e-books using PhantomJS from sites that use HTML5 readers, which is
why it requires Selenium. The framework can however obviously be used for anything.

As of right now, it only works with eBookJapan.

## Installation
* Install Python 3.5+
* Download PhantomJS from [here](http://phantomjs.org/download.html) and put the executable in your PATH. If you're on
Linux, remember to make it executable as well.
* Run the following command to install mindl:
`python3.5 -m pip install git+https://github.com/MinoMino/mindl.git#egg=mindl`
* You should now be able to run mindl from the command line. See below for details about usage.

**NOTE**: If you're not on a virtual environment or something similar, you might need to run `pip` as root.

## Usage
```
usage: mindl [-h] [-o key=value] [-v] [-d] [-p PLUGIN] URL [URL ...]

A plugin-based downloader.

positional arguments:
  URL                   the URL to download from

optional arguments:
  -h, --help            show this help message and exit
  -o key=value, --option key=value
                        a key-value pair to be passed to the plugin to define
                        its options
  -v, --verbose         makes the logger output debugging strings
  -d, --defaults        makes the plugin use default values for options if it
                        can instead of prompting
  -p PLUGIN, --plugin PLUGIN
                        explicitly set which plugin should handle the URL in
                        the case wheretwo or more plugins can handle the same
                        URL
```

To run it, use Python's `-m` argument to run modules: `python -m mindl [...]`

## Example
```
mino$ python -m mindl -o email=some@mail.com -o password=mypassword123 https://br.ebookjapan.jp/br/reader/viewer/view.html?sessionid=[...]
(06:20 INFO) URL is being handled by plugin: eBookJapan v0.1
(06:20 INFO) Starting download...
(06:21 INFO) Creating non-existent directory 'downloads\おやすみプンプン 第3巻'.
(06:21 INFO) Done! A total of 19 were downloaded.
(06:21 INFO) Finalizing...
```

In the above example I've put it my credentials using the `-o` argument, but if you leave one or both out,
you will instead be prompted for the missing options at launch.
