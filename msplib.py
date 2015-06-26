#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" media scan program (library) """

import os
import time
import hashlib
import string
import mutagen
import chardet
import bz2
import binascii
from PIL import Image

try:
    import cPickle as pickle
except ImportError:
    import pickle
#


class FsFile(object):
    """ file from file system """

    def __init__(self, path=None, name=None, stat=None):
        """"""

        self.path = path
        self.name = name
        self.stat = stat
        self.time = time.time()
        self.type = None
        self.data = None
        self.meta = None
        self.tags = None
        self.md5 = None
    #
#


def load_audio_meta(name):
    """ load meta-data from audio file

        :param name:
    """

    info_tags = ('bits_per_sample', 'channels', 'md5_signature', 'sample_rate', 'total_samples', 'length')

    meta = {}
    tags = {}
    audio = mutagen.File(name, easy=True)

    # tags
    for key in audio:
        tags[key] = audio[key]
    #

    # meta
    for key in info_tags:
        meta[key] = getattr(audio.info, key, None)
    #

    return tags, meta
#


def load_picture_meta(name, info=False):
    """ load meta-data from picture file

        :param name:
        :param info:
    """

    meta = {}
    tags = {}

    try:
        image = Image.open(name)
    except IOError, e:
        print "ERROR :: {%r} {%r}" % (e, name)
        raise
    #

    meta["width"], meta["height"] = image.size
    if info:
        meta["info"] = image.info
    #

    return tags, meta
#


def get_unicode(data):
    """ return unicode string (if possible)

    :param data:
    """

    try:
        return unicode(data)
    except UnicodeError:
        pass
    #

    # use auto-detect
    cp = chardet.detect(data)
    en = cp.get('encoding', 'ascii')

    try:
        return unicode(data, en)
    except UnicodeError:
        pass
    #

    raise ValueError("can't encode as unicode for {%r}" % data)
#


def get_bytes(data, encoding='utf-8-sig'):
    """ return binary string (bytes) (if possible)

        :param data:
        :param encoding: default encoding for unicode data
        :return:
    """

    if isinstance(data, str):
        return data
    #

    if isinstance(data, unicode):
        return data.encode(encoding)
    #

    return str(data)
#


def get_hex(n, size=0, radix=string.hexdigits):
    """ get hex string from integer

        :param n:
        :param size:
        :param radix:
    """

    if n is None:
        return None
    #

    a = []

    while True:
        n, r = divmod(n, 16)
        a.append(r)
        if not n:
            if not size or len(a) >= size:
                break
            #
        #
    #

    a.reverse()
    return "".join([radix[n] for n in a])
#


class Fs(object):
    """ file system """

    def __init__(self, root="./"):
        """"""

        self.root = None
        self.root_u = None
        self.files = None
        self.index = None
        self.deleted = None
        self.md5name = None

        self.full_include = (".log", ".cue", ".accurip", ".xml", ".json", ".txt", ".lst", ".dump")
        self.meta_a_include = (".flac", ".ape", ".wv", ".mp3", ".opus", ".ogg")
        self.meta_p_include = (".bmp", ".jpg", ".jpeg", ".gif", ".png", ".tif", ".tiff")

        self.updated = False
        self.autosave = True

        self.set_root(root)
    #

    def __len__(self):
        """
            :return: total file(s) in fs
        """

        return len(self.files) if self.files else 0
    #

    def chg_root(self, root):
        """ change root

            :param root:
            :return:
        """

        self.root = root
        self.root_u = get_unicode(root)
        self.md5name = hashlib.md5(self.root_u.encode('utf-8')).hexdigest()+".fs"
        self.updated = True
    #

    def set_root(self, root):
        """ set new root

            :param root:
        """

        # sane
        root = root or "./"

        self.root = root
        self.root_u = get_unicode(root)
        self.files = {}
        self.index = {}
        self.deleted = []
        self.md5name = hashlib.md5(self.root_u.encode('utf-8')).hexdigest()+".fs"
        self.updated = False

        return self
    #

    def sign(self, hashfunc=hashlib.md5):
        """ generate signature for Fs()

            :param hashfunc: hash function
            :return:
        """

        raw_data = "\x00".join([get_bytes(name, 'utf-8') for name in self.files.keys()])
        return hashfunc(raw_data).digest()
    #

    def hex_sign(self):
        """ generate hex-signature for Fs()

            :return:
        """

        return binascii.b2a_hex(self.sign())
    #

    @staticmethod
    def suffix_class(path, suffs_class):
        """ check by suffix

            :param path:
            :param suffs_class:
        """

        for name, suffs in suffs_class.iteritems():
            for suff in suffs:
                if path.endswith(suff):
                    return name, suff
                #
            #
        #

        return None
    #

    def scan(self, start=None, callback=None):
        """ file scanner

            :param start:
            :param callback:
        """

        _suffix = {"full": self.full_include, "meta_a": self.meta_a_include, "meta_p": self.meta_p_include}
        metafun = {"meta_a": load_audio_meta, "meta_p": load_picture_meta}

        def collector(arg, path, names):
            """ collector

                :param arg:
                :param path:
                :param names:
            """

            updated = False
            o_path = path
            root, _, path = path.partition(arg.root_u)

            # find deleted files
            d_old = arg.files.get(path)
            if d_old:
                for name in d_old.data:
                    if name not in names:
                        fname = os.path.join(path, name)
                        f = arg.files.pop(fname)
                        self.deleted.append(f)
                        updated = True
                        if callback:
                            callback("purge", f)
                        #
                        if f.type == "DIR":
                            for _name in f.data:
                                f = arg.files.pop(os.path.join(fname, _name))
                                self.deleted.append(f)
                                if callback:
                                    callback("purge", f)
                                #
                            #
                        #
                    #
                #
            #

            # load info from folder
            if os.path.isdir(o_path):
                f = FsFile(path, "", os.stat(o_path))
                data = {}
                for fname in os.listdir(o_path):
                    data[fname] = os.stat(os.path.join(o_path, fname))
                #
                f.data = data
                f.type = "DIR"
                arg.files[path] = f
            #

            for name in names:
                _name = os.path.join(o_path, name)
                f_name = os.path.join(path, name)
                if not os.path.isfile(_name):
                    continue
                #

                f = FsFile(path, name, os.stat(_name))
                f_old = arg.files.get(f_name)

                if f_old:
                    if f.stat.st_mtime == f_old.stat.st_mtime:
                        if callback:
                            callback("skip", f)
                        #
                        continue
                    #
                #

                _suff = self.suffix_class(f_name, _suffix)
                if _suff:
                    _class, suff = _suff
                    if _class == "full":
                        f.data = open(_name, "rb").read()
                        f.md5 = hashlib.md5(f.data).hexdigest()
                    elif _class.startswith("meta"):
                        fn = metafun[_class]
                        if callable(fn):
                            f.tags, f.meta = fn(_name)
                            f.md5 = get_hex(f.meta.get("md5_signature"), size=32)
                        #
                    #
                #

                if callback:
                    f = callback("save", f)
                #

                if f:
                    arg.files[f_name] = f
                    updated = True
                #
            #

            if updated:
                arg.updated = True
            #
        #

        # scanning from
        if not start:
            start = ""
        #

        self.deleted = []

        tt = time.time()
        os.path.walk(os.path.join(self.root_u, start), collector, self)

        return time.time() - tt
    #

    def dumps(self, pack=True):
        """ dump files into pickle-string

            :param pack:
        """

        data = pickle.dumps((self.root, self.index, self.files), protocol=-1)

        if pack:
            data = bz2.compress(data, 9)
        #

        return data
    #

    def loads(self, data):
        """ load files from pickle-string

            :param data:
        """

        if data.startswith('BZ'):
            data = bz2.decompress(data)
        #

        root, index, files = pickle.loads(data)
        self.set_root(root)
        self.index, self.files = index, files
        return self
    #

    def dump(self, name=None, pack=None):
        """ save object data

            :param name:
            :param pack:
        """

        if not name:
            name = self.md5name
        #

        with open(name, "wb") as f:
            f.write(self.dumps(pack=pack))
        #

        self.updated = False
        return self
    #

    def load(self, name=None, ignore=False):
        """ load object data

            :param name:
            :param ignore:
        """

        if not name:
            name = self.md5name
        #

        try:
            with open(name, "rb") as f:
                self.loads(f.read())
            #
        except IOError:
            if not ignore:
                raise
            #
        #

        self.updated = False
        return self
    #

    def command(self, cmd, param=None, callback=None):
        """ execute command for file system

            :param cmd:
            :param param:
            :param callback:
        """

        if cmd == "root":
            self.set_root(param or "./")
        elif cmd == "load":
            self.load(name=param, ignore=True)
        elif cmd == "save":
            self.dump(name=param)
        elif cmd == "scan":
            self.scan(start=param, callback=callback)
        else:
            pass
        #

        return self
    #
#


def mk_fs(name, basename=None, callback=None):
    """ make fs

        :param name:
        :param basename:
        :param callback:
        :return:
    """

    if not os.path.isdir(name):
        raise ValueError("'%s' must be folder" % name)
    #

    fs = Fs(root=name)
    fs.scan(callback=callback)

    if basename:
        # change root to basename
        fs.chg_root(basename)
    #

    return fs
#


def scan_print(cmd, f):
    """ print scanning process

        :param cmd:
        :param f:
    """

    if cmd != "skip":
        size = len(f.data) if f.data else 0
        print("{%s} {%r} {%r} {%r}" % (cmd, f.path, f.name, size))
    #

    return f
#

if __name__ == "__main__":
    import sys

    for src_path in sys.argv[1:]:
        print("{%s}" % src_path)
        src_name = os.path.basename(os.path.abspath(src_path))
        src_fs = mk_fs(src_path, basename=src_name, callback=scan_print)
        src_name += ".fs"
        src_fs.dump(src_name, pack=True)
    #
#
