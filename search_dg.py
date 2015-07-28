#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" discogs.com search tools """

import httplib
import urllib
import socket
import ssl
import sys
import os
import argparse
import bz2
import zlib
import time
import pprint
import re
import locale
import json as jsonlib

try:
    from default_config import config as default_config
except ImportError:
    default_config = {}
#

import sqlitedict
import discogs_client
from discogs_client import Artist, Label, Release, Master
from discogs_client import exceptions

import cuelib

CLIENT_NAME = "CueTagger"
CLIENT_VERSION = "0.1"

# Consumer Key            aGooJKwUAouJShhoHEgq
# Consumer Secret         MYqcBWXkNettXCkTtarzMCXIuXOVcRBM
CONSUMER_KEY = "aGooJKwUAouJShhoHEgq"
CONSUMER_SECRET = "MYqcBWXkNettXCkTtarzMCXIuXOVcRBM"

SEARCH_TYPES = {'r': 'release', 'm': 'master', 'a': 'artist', 'l': 'label'}
COMPRESS_TYPES = {'0': None, 'z': zlib, 'b': bz2}

# for logger()
VERBOSE_LEVEL = 0

# system config
SYSTEM_CONFIG = default_config.get("system", {})

# default config
DEFAULT_CONFIG = default_config.get(CLIENT_NAME, {})
USER_TOKEN = DEFAULT_CONFIG.get("USER_TOKEN", "")
USER_SECRET = DEFAULT_CONFIG.get("USER_SECRET", "")
CLIENT_ID = DEFAULT_CONFIG.get("CLIENT_ID", "%s/%s" % (CLIENT_NAME, CLIENT_VERSION))
CACHE_USE = DEFAULT_CONFIG.get("CACHE_USE", False)
CACHE_STORAGE = DEFAULT_CONFIG.get("CACHE_STORAGE", "./discogs_cache.db")
CACHE_TABLE = DEFAULT_CONFIG.get("CACHE_TABLE", "CACHE" + CLIENT_NAME.encode('hex'))
CACHE_SYNC = DEFAULT_CONFIG.get("CACHE_SYNC", 100)
CACHE_COMPRESS = DEFAULT_CONFIG.get("CACHE_COMPRESS", False)

# it's f*cking long line
DEFAULT_ENCODING = DEFAULT_CONFIG.get("DEFAULT_ENCODING") or SYSTEM_CONFIG.get("DEFAULT_ENCODING")
DEFAULT_ENCODING = DEFAULT_ENCODING or locale.getpreferredencoding() or "ascii"

# as-dir
DIR_MATCH6 = re.compile("(?P<artist>.+)")
DIR_MATCH5 = re.compile("(?P<artist>.+)( \((?P<country>.+)\))")
# DIR_MATCH4 = re.compile("(?P<artist>(?:[\w\-.&]+|(?: +[\w\-.&]+))+)( \((?P<country>\w+)\))?")
DIR_MATCH4 = re.compile("(?P<artist>.+) - (?P<album>.+) \((?P<year>\d{4})\)")
DIR_MATCH3 = re.compile("(?P<artist>.+) - (?P<album>.+) \{(?P<catno>.+)\} \((?P<year>\d{4})\)")
DIR_MATCH2 = re.compile("(?P<artist>.+) - (?P<album>.+) \[(?P<flags>.+)\] \((?P<year>\d{4})\)")
DIR_MATCH1 = re.compile("(?P<artist>.+) - (?P<album>.+) \[(?P<flags>.+)\] \{(?P<catno>.+)\} \((?P<year>\d{4})\)")
DIR_MATCH0 = re.compile("(?P<artist>.+) - (?P<album>.+) \{(?P<catno>.+)\} \[(?P<flags>.+)\] \((?P<year>\d{4})\)")
DIR_MATCHES = (DIR_MATCH0, DIR_MATCH1, DIR_MATCH2, DIR_MATCH3, DIR_MATCH4, DIR_MATCH5, DIR_MATCH6)
# DIR_MATCHES = (DIR_MATCH1, DIR_MATCH2, DIR_MATCH4)


class ExecuteError(Exception):
    """ execute error """
    pass
#


# ExecuteError global variable
EE = ExecuteError()


class ProtectedCall(object):
    """ protected call """

    def __init__(self, call=None, skip=(KeyboardInterrupt,)):
        """
            :param call: callable object
            :param skip: list-of-exceptions to skip (re-raise)
            :return:
        """

        self.call = call
        self.skip = skip
        self.args = None
        self.kwargs = None
        self.error = None
    #

    def __call__(self, *args, **kwargs):
        """
            :param args:
            :param kwargs:
            :return:
        """

        self.args = args
        self.kwargs = kwargs

        try:
            r = self.call(*args, **kwargs)
            e = None
        except:
            r = EE
            e = sys.exc_info()
            if self.skip:
                _type, _value, _traceback = e
                if _type in self.skip:
                    raise
                #
            #
        #

        self.error = e
        return r
    #
#


def search_by_dir(name, matches=DIR_MATCHES):
    """get directory name (correct)

        :param name: dir name
        :param matches: list-of-compiled-matches
    """

    for p in matches:
        m = p.match(name)
        if m:
            d = m.groupdict()
            # print "MATCH ::", repr(name), ":", m.groupdict()
            # print "MATCH ::", repr(name), ":", m.groups()

            s = ' '.join((d.get('artist', ''), d.get('album', ''))).strip()
            if not s:
                return name
            #

            return s
        #
    #

    return name
#


def search_by_cue(name):
    """ search by .cue

        :param name:
        :return:
    """

    with open(name, "rb") as f:
        d = f.read()
    #

    c = cuelib.cue_parse(d)
    s = ' '.join((c.performer, c.title)).strip()

    if not s:
        return name
    #

    return s
#


def search_by_file(name):
    """ search by file

        :param name:
        :return:
    """

    with open(name, "rb") as f:
        d = [s.strip() for s in cuelib.as_unicode(f.read())[0].split("\n")]
        s = ' '.join(d)
    #

    if not s:
        return name
    #

    return s
#


def data_pack(data, min_diff=16):
    """ compress (pack) data (find best compression method)

        :param data:
        :param min_diff: minimal difference
        :return:
    """

    s_type = '0'
    s_data = data
    for c_type, c_meth in COMPRESS_TYPES.iteritems():
        if c_meth:
            c_data = c_meth.compress(data, 9)
            if len(c_data) + min_diff < len(s_data):
                s_type = c_type
                s_data = c_data
            #
        #
    #

    o_len = len(data)
    s_len = len(s_data)
    c_len = max(0, o_len-s_len)
    cc = (c_len * 100) / o_len
    logger("data_pack: type{%r} orig{%r} diff{%r} compression{%.2f%%}" % (s_type, o_len, c_len, cc), level=2)

    return s_type, s_data
#


def data_unpack(c_type, data):
    """ decompress (unpack) data

        :param c_type: compression type
        :param data:
        :return:
    """

    c_meth = COMPRESS_TYPES.get(c_type, None)

    if not c_meth:
        return data
    #

    return c_meth.decompress(data)
#


def tty(message=""):
    """ write to stdout with flush

        :param message:
    """

    sys.stdout.write(message)
    sys.stdout.flush()
#


def die(message="", status=0):
    """ exit (die) with message

        :param message:
        :param status:
    """

    if message:
        tty(message)
        tty("\n")
    #

    sys.exit(status)
#


def error(message, status=1):
    """ print message to stderr and exit with <status>

        :param message:
        :param status:
    """

    return die("error :: %s" % message, status)
#


def logger(data="", level=0, codec='utf8', prologue=None, epilog='\n'):
    """ logger

        :param data:
        :param level:
        :param codec: for unicode
        :param prologue: out-before-data
        :param epilog: out-after-data
    """

    global VERBOSE_LEVEL

    if VERBOSE_LEVEL >= level:
        # print(data)
        if isinstance(data, unicode):
            data = data.encode(codec)
        #

        if not isinstance(data, str):
            data = str(data)
        #

        # out prologue
        if prologue:
            tty(prologue)
        #

        if data:
            tty(data)
        #

        # out epilog
        if epilog:
            tty(epilog)
        #
    #
#


def test_result(o, search_filter=None, q=0.5, max_time=10.0, max_wait=0.5, failed=None):
    """ test & full load

        :param o:
        :param search_filter:
        :param q:
        :param max_time:
        :param max_wait:
        :param failed: None or dict()
        :return:
    """

    # maximum time
    mt = time.time() + max_time

    try:
        logger("test: {%.2f/%s} %r" % (q, search_filter, o), level=2)
        if not search_filter or find_words(get_name_or_title(o).lower(), search_filter)[-1] >= q:
            _ = o.url
        else:
            logger("fail: %r" % o, level=2)
            return False
        #
    except (exceptions.DiscogsAPIError, httplib.BadStatusLine, ssl.SSLError, socket.error) as e:
        logger("error{%r} for {%r}" % (e, o), level=2)
        return False
    except ValueError as e:
        logger("error{%r} for {%r}" % (e, o), level=2)
        logger("{%r} :: data{%r}" % (o, o.data), level=2)
        if time.time() > mt:
            if failed is not None:
                failed[o] = time.time()
            #
            logger("timeout: {%r}, try once more later" % o)
            return False
        #

        # sleep before recursive call
        time.sleep(max_wait)

        # recursive call
        logger("recursive: call for {%r}" % o, level=1)
        return test_result(o, search_filter, q, mt-time.time(), max_wait)
    #

    return True
#


def load_result_raw(query, search_filter=None, q=0.5, failed=None):
    """ load all data from query (all pages)

        :param query: search query object Client.search()
        :param search_filter:
        :param q:
        :param failed: None or dict()
        :return:
    """

    data = []
    try:
        data.extend(list(query.page(1)))
        if data:
            _ = [data.extend(query.page(np)) for np in range(2, query.pages+1)]
        #
    except UnicodeEncodeError as e:
        logger("query{%s} exception{%r}" % (query, e), level=2)
        raise
    except (ValueError, socket.error, httplib.BadStatusLine) as e:
        logger("error: exception{%r}" % e)
    except Exception as e:
        logger("exception{%r}" % e, level=2)
        raise
    #

    # test & full load
    return [o for o in data if test_result(o, search_filter, q, failed=failed)]
#


def load_result(query, search_filter=None, q=0.5, failed=None, timeout=60.0):
    """ load all data from query (all pages)

        :param query: search query object Client.search()
        :param search_filter:
        :param q:
        :param failed: None or dict()
        :param timeout: timeout for operation(s)
        :return:
    """

    pc_load_result = ProtectedCall(load_result_raw)

    tb = 0
    te = timeout
    tw = 1.0
    r = None
    e = None

    while tb <= te:
        e = None
        r = pc_load_result(query, search_filter, q, failed)
        if r != EE:
            break
        else:
            r = None
        #

        e = pc_load_result.error
        if e:
            tw *= 1.3
            logger("error: query{%r}, load_result{%r}" % (query.url, e[0]), level=1)
        #

        logger("wait: %.4f" % tw, level=1)
        time.sleep(tw)
        tb += tw
    #

    if e:
        logger("error: can't load data, query{%r}, load_result{%r}" % (query.url, e[0]))
    #

    return r or []
#


def sort_result(data):
    """ sort result by object type

        :param data:
        :return: {Label, Artist, Master, Release}
    """

    o = {Label: [], Artist: [], Master: [], Release: []}
    for x in data:
        a = o.get(type(x))
        if a is None:
            continue
        #
        a.append(x)
    #

    return o
#


def deep_result(o, d=None, search_filter=None, q=0.5, timeout=60.0):
    """ load all releases for object (Label, Artist, Master)

        :param o: object
        :param d: deep data collector
        :param search_filter:
        :param q:
        :param timeout:
        :return:
    """
    
    if not obj_filter(o, search_filter, q):
        logger("deep fail: %s {%.2f %s}" % (o, q, search_filter), level=2)
        return None
    #

    if d is None:
        d = {}
    #

    r = []

    if isinstance(o, Release):
        _ = o.url
        return None
    #

    if isinstance(o, Master):
        _ = o.url
        r = load_result(o.versions, search_filter, q, timeout)
    #

    if isinstance(o, Artist):
        _ = o.url
        r = load_result(o.releases, search_filter, q, timeout)
    #

    if isinstance(o, Label):
        _ = o.url
        r = load_result(o.releases, search_filter, q, timeout)
    #

    if r:
        # pre-filter
        # if search_filter:
        #     r = [x for x in r if obj_filter(x, search_filter, q)]
        # #
        d[o] = r

        logger("deep: %s :: %s" % (o, len(r)), level=1)
        for v in r:
            logger("deep load: %s" % v, level=1)
            deep_result(v, d, search_filter, q, timeout)
        #
    #

    return d
#


def content_pack(x):
    """ pack content

        :param x:
        :return:
    """

    content, status_code = x
    c_type, content = data_pack(content)

    return c_type, content, status_code
#


def content_unpack(x):
    """ unpack content

        :param x:
        :return:
    """

    c_type, content, status_code = x
    return data_unpack(c_type, content), status_code
#


class ProxyFetcher(object):
    """ proxy fetcher """

    def __init__(self, fetcher):
        """
            :param fetcher:
            :return:
        """

        self.fetcher = fetcher
    #

    def __getattr__(self, item):
        """
            :param item:
            :return:
        """

        return getattr(self, item) or getattr(self.fetcher, item)
    #
#


class CacheFetcherDict(ProxyFetcher):
    """ dict as cache for fetcher """

    def __init__(self, fetcher, cache=None):
        """

                :param fetcher: original fetcher
                :param cache: cache (dict-like, simple)
                :return:
            """

        super(CacheFetcherDict, self).__init__(fetcher)

        if cache is None:
            cache = {}

        self.cache = cache
        self.changes = 0
    #

    def fetch(self, client, method, url, data=None, headers=None, json=True):
        """ request fetcher (only GET method)

            :param client:
            :param method:
            :param url:
            :param data:
            :param headers:
            :param json:
            :return:
        """

        if method != "GET":
            return self.fetcher.fetch(client, method, url, data, headers, json)
        #

        x = self.cache.get(url, None)

        if not x:
            x = self.fetcher.fetch(client, method, url, data, headers, json)
            self.cache[url] = x
            self.changes += 1
        else:
            logger("CACHE {%r}" % url, level=2)
        #

        return x
    #

    def commit(self):
        """ clear changes

            :return:
        """

        self.changes = 0
        return self
    #
#


class CacheFetcher(ProxyFetcher):
    """ use cache for fetch """

    def __init__(self, fetcher, cache, update=0, commit_max=100, compression=False):
        """

                :param fetcher: original fetcher
                :param cache: cache
                :param update: level of update-by-force
                :param commit_max: commit after max changes
                :param compression: use compression for content
                :return:
            """

        super(CacheFetcher, self).__init__(fetcher)

        self.cache = cache
        self.update = update
        self.commit_max = commit_max
        self.compression = compression
        self.changes = 0
        self.search_url = "api.discogs.com/database/search"
    #

    def fetch(self, client, method, url, data=None, headers=None, json=True):
        """ request fetcher (only GET method)

            :param client:
            :param method:
            :param url:
            :param data:
            :param headers:
            :param json:
            :return:
        """

        if method != "GET":
            return self.fetcher.fetch(client, method, url, data, headers, json)
        #

        # level =1: api.discogs.com/database/search
        # level >1: other
        if self.search_url in url:
            update_level = 1
        else:
            update_level = 2
        #

        if self.update >= update_level:
            x = None
        else:
            x = self.cache.get(url, None)
            if x and self.compression:
                x = content_unpack(x)
            #
        #

        if not x:
            x = self.fetcher.fetch(client, method, url, data, headers, json)
            if self.compression:
                z = content_pack(x)
            else:
                z = x
            #

            if isinstance(x, (tuple, list)):
                s = x[0]
            else:
                s = x
            #

            # check if JSON
            try:
                jsonlib.loads(s)
                self.cache[url] = z
                self.changes += 1
            except Exception as e:
                logger("cache: error{%r} url{%r} data{%r}" % (e, url, x), level=2)
            #

            if self.changes >= self.commit_max:
                self.commit()
            #
        else:
            # print "CACHE", repr(url)
            logger("cache: url{%r}" % url, level=2)
        #

        # dump data-packet
        logger("cache: fetch url{%r} data{%r}" % (url, x), level=3)

        return x
    #

    def commit(self):
        """ commit updates

            :return:
        """

        self.cache.commit()
        self.changes = 0

        return self
    #
#


def print_raw(o, indent=2, width=100):
    """ dump raw data from object

        :param o:
        :param indent:
        :param width:
        :return:
    """

    logger("object{%r}" % o)
    # logger("raw{%r}" % o.data)
    for key in dir(o):
        if key != "data" and not key.startswith("_"):
            logger("> %s = %r" % (key, getattr(o, key)))
        #
    #

    logger(">>> data <<<")
    pprint.pprint(o.data, indent=indent, width=width)
    logger()
#


def get_pure_name(name):
    """ remove (if exists) number-id from name (artist, label, ...)

        :param name:
    """

    a = name.split(' ')
    _1 = a[-1].strip()
    if _1.startswith('(') and _1.endswith(')') and _1[1:-1].isdigit():
        name = ' '.join(a[:-1])
    #

    return name
#


def get_formats(o):
    """ get formats

        :param o: object
        :return: string
    """

    d = o.data
    f = d.get('formats')
    if not f:
        return ''
    #

    out = []
    fmt = [f] if not isinstance(f, list) else f
    for f in fmt:
        name = f.get('name', 'Unknown').strip()
        desc = ','.join(f.get('descriptions', []))
        text = f.get('text', '').strip()
        qty = f.get('qty', '0').strip()
        note = ",".join(filter(None, (desc, text)))
        if note:
            out.append("%s>%s>%s" % (name, qty, note))
        else:
            out.append("%s>%s" % (name, qty))
        #
    #

    ntrk = str(len(d.get('tracklist', [])))
    return "%s:%s" % (ntrk, " ".join(["{%s}" % x for x in out]))
#


def get_labels(o):
    """ get labels

        :param o:
        :return:
    """

    d = o.data
    l = d.get('labels')
    if not l:
        return ''
    #

    names = ', '.join([get_pure_name(x.get('name', 'none')) for x in l])
    catno = ', '.join([x.get('catno', 'none') for x in l])

    return "%s {%s}" % (names, catno)
#


# def get_name_or_title_(o):
#     """
#         :param o:
#         :return:
#     """
#
#     return getattr(o, "name", None) or getattr(o, "title", "")
##


def get_name_or_title(o):
    """
        :param o:
        :return:
    """

    # load object
    _ = o.url

    # if <title> exists => try to find <name>
    title = getattr(o, "title", "")
    if title:
        out = []
        data = getattr(o, "data", {})
        for artist in data.get("artists", []):
            logger("ARTIST: {%s}" % artist, level=2)
            name = artist.get("name", "")
            if name:
                out.append(name)
            #
        #
        out.append(title)
        out = " ".join(out)
        logger("TITLE: %s {%s}" % (o, out), level=2)
    else:
        # ok, only <name>
        out = getattr(o, "name", "")
        logger("NAME: %s {%s}" % (o, out), level=2)
    #

    return out
#


def get_track_artist(track, default=''):
    """ get track artist (if exists)

        :param track:
        :param default:
        :return:
    """

    return get_artists(track) or default
#


def get_track_title(track, default=''):
    """  get track title (if exists) and credits

        :param track:
        :param default:
        :return:
    """

    title = track.title or default
    extra = get_artists(track, attribute='credits')
    return title.replace('\t', ' ').strip(), extra
#


def get_artists(o, make_join='/', attribute='artists'):
    """

        :param o:
        :param make_join:
        :param attribute:
        :return: joined names or list-of-names
    """

    names = [get_pure_name(x.name) for x in getattr(o, attribute, ())]

    if make_join:
        return make_join.join(names)
    #

    return names
#


def get_tracks(o, duration=True, position=True):
    """ get tracks from object (and filter by duration/position)

        :param o:
        :param duration:
        :param position:
        :return:
    """

    tracks = []
    for track in getattr(o, "tracklist", ()):
        if duration and not track.duration:
            continue
        #

        if position and not track.position:
            continue
        #

        tracks.append(track)
    #

    return tracks
#


def print_release(o, head=None, really_print=True):
    """


        :param o:
        :param head:
        :param really_print:
        :return:
    """

    p = []
    r_dump = dump_release(o)

    if not r_dump:
        return p
    #

    r_info = r_dump[0]
    r_id, r_artists, r_title, r_year, r_formats, r_labels, r_genres = r_info

    if head:
        p.append(head % r_info)
    #

    # print tracks
    n_trk = 1
    for track in get_tracks(o, duration=False, position=True):
        artists = get_artists(track).strip()
        if not artists:
            artists = r_artists
        #

        if artists == r_artists:
            name = track.title
        else:
            name = "%s - %s" % (artists, track.title)
        #

        tr_credits = get_artists(track, attribute='credits')
        if tr_credits:
            name += " (%s)" % tr_credits
        #

        s = ("    " + "%02d" % n_trk, "%6s" % (track.duration or 'xx.xx'), "%4s" % (track.position or 'xx'), name)
        p.append(" / ".join(s))
        n_trk += 1
    #

    # p.append('')
    # really print
    if really_print:
        for s in p:
            logger(s)
        #
    #

    return p
#


def dump_release(o, d=None):
    """ dump release info

        :param o:
        :param d: dump list
        :return: list-of-strings
    """

    if d is None:
        d = []
    #

    if not isinstance(o, Release):
        return d
    #

    data = o.data

    # artists = ' / '.join([x.name for x in o.artists])
    artists = get_artists(o, ' / ')
    genres = '/'.join(o.genres)
    styles = '/'.join(data.get('styles', []))
    labels = get_labels(o)
    formats = get_formats(o)

    # s = "%10d | %s - %s (%s) | %s | %s" % (o.id, artists, o.title, o.year, labels, styles or genres)
    d.append((o.id, artists, o.title, str(o.year or ''), formats, labels, styles or genres))

    return d
#


def sort_release(d):
    """ sort list-of-release

        :param d:
        :return:
    """

    def r_cmp(r1, r2):
        """ compare two releases

            :param r1:
            :param r2:
            :return:
        """

        k1 = r1[1].strip().lower() + r1[2].strip().lower() + (r1[3].strip() or '0')
        i1 = int(r1[0])

        k2 = r2[1].strip().lower() + r2[2].strip().lower() + (r2[3].strip() or '0')
        i2 = int(r2[0])

        if k1 == k2:
            return cmp(i1, i2)
        #

        return cmp(k1, k2)
    #

    return sorted(d, r_cmp)
#


def dump_label(o, d=None):
    """ dump label info

        :param o:
        :param d:
        :return:
    """

    if d is None:
        d = []
    #

    if not isinstance(o, Label):
        return d
    #

    d.append((o.id, o.name))
    return d
#


def sort_label(d):
    """ sort list-of-label

        :param d:
        :return:
    """

    def a_cmp(a1, a2):
        """ compare two labels

            :param a1:
            :param a2:
            :return:
        """

        return cmp(a1[1], a2[1])
    #

    return sorted(d, a_cmp)
#


def dump_artist(o, d=None):
    """ dump artist info

        :param o:
        :param d:
        :return:
    """

    if d is None:
        d = []
    #

    if not isinstance(o, Artist):
        return d
    #

    nv = ' / '.join(o.name_variations or [])
    d.append((o.id, o.name, nv))

    return d
#


def sort_artist(d):
    """ sort list-of-artist

        :param d:
        :return:
    """

    def a_cmp(a1, a2):
        """ compare two artists

            :param a1:
            :param a2:
            :return:
        """

        return cmp(a1[1], a2[1])
    #

    return sorted(d, a_cmp)
#


def obj_filter(o, search_filter=None, q=0.5):
    """ object filter

        :param o:
        :param search_filter:
        :param q:
    """

    return not search_filter or find_words(get_name_or_title(o).lower(), search_filter)[-1] >= q
#


def obj_dump(o, d=None):
    """ object dump

        :param o:
        :param d:
        :return:
    """

    d_dump = {Artist: dump_artist, Label: dump_label, Release: dump_release}
    d_func = d_dump.get(type(o), None)

    if callable(d_func):
        try:
            return d_func(o, d)
        except Exception as e:
            logger("error: func{%r} object{%r} exception{%r}" % (d_func, o, e))
            logger("error: object{%r} data{%r}" % (o, o.data), level=2)
        #
    #

    return None
#


def obj_sort(t, d):
    """ object dump

        :param t: type-of-objects (class object)
        :param d: data
        :return:
    """

    d_sort = {Artist: sort_artist, Label: sort_label, Release: sort_release}
    d_func = d_sort.get(t, None)

    if callable(d_func):
        return d_func(d)
    #

    return None
#


def load_images(o):
    """ load image(s) from object

        :param o:
        :return:
    """

    for image in getattr(o, "images", []):
        url = image.get("resource_url", None)
        name = os.path.basename(url)
        if url:
            logger("image: %r" % name)
            if os.path.exists(name):
                continue
            #

            logger("path: %r" % url, level=1)

            try:
                data = urllib.urlopen(url).read()
                with open(name, "wb") as f:
                    f.write(data)
                #
            except socket.error as e:
                logger("error: %r" % e)
            #
        #
    #
#


def find_words(x, words):
    """ find all words

        :param x: source data (list, dict or string)
        :param words: list-of-words
        :return:
    """

    found = 0

    if isinstance(x, (unicode, str)):
        a = filter(None, x.replace(".", " ").replace(",", " ").replace("&", " ").split(" "))
    else:
        a = x
    #

    for w in words:
        if w in a:
            found += 1
        #
    #

    # logger("find: where{%r} what{%r} found{%r}" % (a, words, found), level=2)
    return found, float(found) / max(len(words), len(a))
#


def make_json(o):
    """

        :param o:
    """

    data = getattr(o, "data", None)
    if not data:
        logger("error: [json] no data")
        return None
    #

    o_id = data.get("id")
    if not o_id:
        logger("error: [json] no id")
        return None
    #

    name = type(o).__name__[0] + ("%010d" % o_id) + ".json"

    s = jsonlib.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    with open(name, "wb") as f:
        if isinstance(s, unicode):
            s = s.encode(DEFAULT_ENCODING)
        #
        f.write(s)
    #

    logger("json: '%s'" % name)
    return name
#


def cue_tagger(releases, name, skip=0):
    """ .cue tagger

        :param releases:
        :param name:
        :param skip: skip tracks before tagging (<0 for old, >0 for new)
        :return: return Cue() and save new cue as "name.<DISCOGS_ID>.ext"
    """

    if skip < 0:
        cue_skip = abs(skip)
    else:
        cue_skip = 0
    #

    cue_rems = []
    r = releases[0]

    if len(releases) > 1:
        logger("warning: too many releases (%r), using first only {%r}" % (len(releases), r))
    #

    r_dump = dump_release(r)

    if not r_dump:
        return None
    #

    r_info = r_dump[0]
    r_id, r_artists, r_title, r_year, r_formats, r_labels, r_genres = r_info

    if not os.path.isfile(name):
        logger("warning: can't find {%r}" % name)

        r_tracks = get_tracks(r, duration=False)
        tracks = [(get_track_title(r_track, "")[0], "00:00:00") for r_track in r_tracks]
        data = cuelib.cue_maker(tracks=tracks)
    else:
        with open(name, "rb") as f:
            data = f.read()
        #
    #
    cue = cuelib.cue_parse(data)

    # head
    cue.performer = r_artists or cue.performer
    cue.title = r_title or cue.title

    # REMs
    cue_rems.append(("DISCOGS", str(r_id)))
    cue_rems.append(("LABEL", r_labels))
    cue_rems.append(("DATE", r_year))
    cue_rems.append(("GENRE", r_genres))
    [cue.rems(*v) for v in cue_rems if v[-1]]

    # tracks
    c_tracks = cue.tracks
    r_tracks = get_tracks(r, duration=False)
    if len(r_tracks)-skip < len(c_tracks):
        logger("warning: release tracks(%d) < cue tracks (%d) (skip %d)" % (len(r_tracks), len(c_tracks), skip))
    #

    for n_track in range(len(r_tracks)):
        try:
            c_track = c_tracks[n_track + cue_skip]
            r_track = r_tracks[n_track + skip]

            title, extra = get_track_title(r_track, c_track.title)
            c_track.performer = get_track_artist(r_track, r_artists or c_track.performer)
            c_track.title = title
            if extra:
                c_track.rems("CREDITS", extra)
            #
        except IndexError:
            break
        #
    #

    # save new .cue
    if cue:
        _name, _ext = os.path.splitext(name)
        _name = "%s.%010d" % (_name, r_id)

        cue_name = _name + _ext
        with open(cue_name, "wb") as f:
            s = cue.dumps()
            f.write(s)
        #
    else:
        cue_name = ''
    #

    return cue, cue_name
#


def main():
    """ main """

    global VERBOSE_LEVEL

    cwd = os.path.basename(os.getcwdu())
    cwd_search = search_by_dir(cwd)

    parser = argparse.ArgumentParser(description="search on discogs.com")
    parser.add_argument('search', help='search string', nargs='*')
    parser.add_argument('-a', '--as_dir', help='add current dir for search', action="store_true")
    parser.add_argument('-A', '--as_dir_log', help='add current dir for search & output to .lst', action="store_true")
    parser.add_argument('-l', '--log', help='save stdout to log-file, use "." for as-dir', type=str, action="store")
    parser.add_argument('-t', '--tag_cue', help='tag .cue for one release', type=str, action="store")
    parser.add_argument('-s', '--tag_skip', help='skip some tracks', type=int, action="store", default=0)
    parser.add_argument('-p', '--param', help='search parameter: <name>=<value> (ex. type=artist)', action='append')
    parser.add_argument('-d', '--deep', help='deep search, "-dd" for labels', action='count', default=0)
    parser.add_argument('-i', '--id', help='client id [%r]' % CLIENT_ID, default=CLIENT_ID)
    parser.add_argument('-q', '--quality', help='search quality', type=float, default=0.1)
    parser.add_argument('-J', '--make_json', help='make .json', action='store_true')
    parser.add_argument('-R', '--raw_print', help='print raw data (for debug)', action='store_true')
    parser.add_argument('-P', '--print_release', help='print formatted release info', action='store_true')
    parser.add_argument('-I', '--object_id', help='search by id, default for "type=release"', action='store_true')
    parser.add_argument('-c', '--cache', help='use cache [%r]' % CACHE_USE, action='store_true', default=CACHE_USE)
    parser.add_argument('-C', '--cache_db', help='cache name [%r]' % CACHE_STORAGE, default=CACHE_STORAGE)
    parser.add_argument('-U', '--update_db', help='update cache, "-UU" for full update', action='count', default=0)
    parser.add_argument('-T', '--table_db', help='table name for cache [%r]' % CACHE_TABLE, default=CACHE_TABLE)
    parser.add_argument('-v', '--verbose', help='increase output verbosity, "-vv" for more', action="count", default=0)
    parser.add_argument('--timeout', help='maximum timeout for network operation(s)', type=float, default=120.0)
    parser.add_argument('--images', help='load release image(s)', action="store_true")
    parser.add_argument('--all_images', help='load all image(s)', action="store_true")
    parser.add_argument('--user_token', help='user token [%r]' % USER_TOKEN, default=USER_TOKEN)
    parser.add_argument('--user_secret', help='user secret [%r]' % USER_SECRET, default=USER_SECRET)
    args = parser.parse_args()

    # global param
    VERBOSE_LEVEL = args.verbose
    logger("{%r}" % args, level=2)

    if args.quality < 0.0:
        args.quality = 0.1
    #

    if args.quality > 1.0:
        args.quality = 1.0
    #

    if args.as_dir_log:
        args.as_dir = True
        args.log = cwd + ".lst"
    #

    if args.log:
        if args.log == ".":
            args.log = cwd + ".lst"
        #

        # need unicode log-name
        name = args.log
        if isinstance(name, str):
            name = name.decode(DEFAULT_ENCODING)
        #

        logger("info: stdout => {%s}" % name)
        log = open(name, "w")
        sys.stdout = log
    #

    if args.as_dir:
        args.search.append(cwd_search)
        logger("info: dir-search for {%s} => {%s}" % (cwd, cwd_search))
        # args.search.append(os.getcwdu())
    #

    dc = discogs_client.Client(args.id)
    dc.set_consumer_key(CONSUMER_KEY, CONSUMER_SECRET)

    if not (args.user_token and args.user_secret):
        logger("authorization (discogs.com):")
        access_token, access_secret, authorize_url = dc.get_authorize_url()
        logger("access_token{%s} access_secret{%s}" % (access_token, access_secret))
        logger("authorize_url{%s}" % authorize_url)
        verifier = raw_input("verifier> ")
        token, secret = dc.get_access_token(verifier)
        logger("user token{%s}" % token)
        logger("user secret{%s}" % secret)
        return None
    else:
        dc.set_token(args.user_token, args.user_secret)
    #

    dc_fetcher = getattr(dc, "_fetcher", None)

    # setup verbose
    if VERBOSE_LEVEL > 1:
        dc.verbose = True
    #

    # setup cache
    if args.cache:
        logger("cache: db{%r}, table{%r}, update{%r}" % (args.cache_db, args.table_db, args.update_db), level=2)
        db = sqlitedict.open(filename=args.cache_db, tablename=args.table_db)
        cache = CacheFetcher(dc_fetcher, db, args.update_db, commit_max=CACHE_SYNC, compression=CACHE_COMPRESS)
        dc._fetcher = cache
    else:
        logger("cache: internal (temporary)")
        cache = CacheFetcherDict(dc_fetcher)
        dc._fetcher = cache
    #

    # parse params
    p = {}
    if args.param:
        for params in args.param:
            for param in params.split(","):
                name, _, value = param.partition("=")
                name = name.strip()
                value = value.strip()

                if not (name or value):
                    continue
                #

                if not value:
                    value = name
                    name = "type"
                #

                p[name.strip()] = value.strip()
            #
        #
    #

    s_type = p.get("type", "release")
    s_meth = getattr(dc, s_type, None)

    # all is unicode now (must be)
    logger("search [1]: %s" % args.search, level=1)
    args.search = [cuelib.as_unicode(s, DEFAULT_ENCODING, True)[0] for s in args.search]
    logger("search [2]: %s" % args.search, level=1)

    # load info from db
    rt = []
    tt = time.time()
    deep_data = None
    for search in args.search:

        # if isinstance(search, unicode):
        #     search = search.encode(encoding='utf-8')
        # #

        # auto-detect: .cue & folder
        if search.lower().endswith(".cue") and os.path.isfile(search):
            old_search = search
            search = search_by_cue(old_search)
            logger("info: cue-search for {%s} => {%s}" % (old_search, search))
        elif os.path.isdir(search):
            old_search = search
            search = search_by_dir(os.path.basename(old_search))
            logger("info: dir-search for {%s} => {%s}" % (old_search, search))
        elif search.startswith("@") and os.path.isfile(search[1:]):
            old_search = search[1:]
            search = search_by_file(old_search)
            logger("info: file-search for {%s} => {%s}" % (old_search, search))
        #

        search = search.lower()
        a_search = filter(None, search.replace(".", " ").replace(",", " ").replace("&", " ").split(" "))
        a_search = [s.strip() for s in a_search]
        search = ' '.join(a_search)
        logger("info: search for {%s}" % a_search, level=1)

        # warning
        # if len(a_search) == 1:
        #     # #args.quality = 1.0
        #     # if args.quality != 1.0:
        #     #     logger("warning: use quality setting as 1.0 for better result")
        #     # #
        #     pass
        # #

        if search.isdigit() and args.object_id:
            object_id = int(search)
            if callable(s_meth):
                o = s_meth(object_id)
                sr = [o]
                url = o.url

                # ignore "quality" setting
                args.quality = 0
            else:
                sr = []
                url = ""
            #
        else:
            if isinstance(search, unicode):
                searchu = search
            else:
                searchu = unicode(search, DEFAULT_ENCODING)
            #
            # search8 = searchu.encode('utf-8')
            sq = dc.search(searchu, **p)
            url = sq.url
            logger("search{%s} url{%s}" % (search, sq.url), level=1)
            sr = load_result(sq, a_search, args.quality, timeout=args.timeout)

            # logger("for %r found %s item(s)" % (search, len(sr)), level=1)
            # sr = [x for x in sr if find_words(get_name_or_title(x), a_search)[-1] >= args.quality]
            logger("after filter{%r} found %s item(s)" % (args.quality, len(sr)), level=1)
        #

        # deep loading
        deep_data = {}
        if sr:
            for o in sr:
                if args.raw_print:
                    print_raw(o)
                #

                ok = False

                if isinstance(o, Artist) and args.deep >= 1:
                    ok = True
                elif isinstance(o, Label) and args.deep > 1:
                    ok = True
                elif isinstance(o, Master):
                    ok = True
                #

                if ok:
                    deep_result(o, deep_data, a_search, args.quality, args.timeout)
                #
            #

            # add found objects from deep loding (object => list-if-releases)
            for o in deep_data:
                if o not in sr:
                    sr.append(o)
                #
            #

            logger("deep{%s}" % repr(deep_data), level=2)
        #

        if sr:
            rt.append((search, url, sort_result(sr), deep_data))
            logger("items{%s}" % repr(rt[-1]), level=2)
        #
    #

    # collect all releases, artists, labels
    releases = []
    artists = []
    labels = []
    for _search, _url, sr, dd in rt:
        releases.extend(sr[Release])
        for o_type in (Label, Artist, Master):
            for o in sr[o_type]:
                releases.extend(dd.get(o, []))
            #
        #

        artists.extend(sr[Artist])
        labels.extend(sr[Label])
        # logger("%r: labels: %r, artists: %r, releases: %r" % (_search, len(labels), len(artists), len(releases)))
    #

    if cache:
        cache.commit()
    #

    if len(releases) == 1:
        args.print_release = True
    #

    # total time
    tt = time.time() - tt

    logger()
    s = "time {%.4f}, search {%s}" % (tt, ' | '.join(args.search))
    logger(s, level=0)
    logger("~" * len(s), level=0)
    logger()

    dump = ((Label, labels, "%10d | %s"),
            (Artist, artists, "%10d | %s {%s}"),
            (Release, releases, "%10d | %s - %s (%s) @ %s # %s <%s>"))

    for t, data, s in dump:
        d = []
        _ = [obj_dump(o, d) for o in data]
        d = obj_sort(t, d)
        if not d:
            continue
        #

        ids = {}
        for x in d:
            _id = x[0]
            if _id not in ids:
                logger(s % x)
                ids[_id] = True
            #
        #

        logger()
        logger("%r: found %d item(s)" % (t.__name__, len(ids)))
        logger()
    #

    if args.print_release:
        head_fmt = (("id", "%d"), ("title", "%s - %s (%s)"), ("format", "%s"), ("label", "%s"), ("genre", "%s"))
        head = '\n'.join(["%-6s / %s" % x for x in head_fmt])

        for o in releases:
            print_release(o, head=head)
            logger()
        #
    #

    if args.make_json:
        for o in releases:
            make_json(o)
        #
    #

    # try to tag .cue
    if args.tag_cue:
        _, cue_name = cue_tagger(releases, args.tag_cue, args.tag_skip)
        logger("tag: '%s'" % cue_name)
    #

    # load release image(s)
    if args.images:
        for o in releases:
            load_images(o)
        #
    #

    return rt, deep_data
#

if __name__ == "__main__":
    _rt, _deep = main()
#
