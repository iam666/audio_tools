#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" media scan program """

import os
import sys
import time
import pprint
import argparse
import json as jsonlib
from zipfile import ZipFile, ZipInfo, ZIP_STORED

from msplib import Fs, FsFile, scan_print, mk_fs, get_bytes


ZIP_FILE_RW = 0644 << 16L  # permissions -rw-r--r--


def tty(s):
    """

        :param s:
    """

    sys.stdout.write(s)
    sys.stdout.flush()
#


def get_path(path):
    """

        :param path:
    """

    if isinstance(path, (list, tuple)):
        return os.path.join(*path)
    #

    a = path.split("/")
    if len(a) > 1:
        return get_path(a)
    #

    return get_path(path.split("\\"))
#


def dump(fs):
    """

        :param fs:
    """

    names = {}

    files = fs.files
    for k, v in files.iteritems():
        name = os.path.join(get_path(v.path), v.name)
        names[name] = v
    #

    return names
#


def mk_zip(name, fs, encoding="utf-8"):
    """make .zip from fs

        :param name:
        :param fs:
        :param encoding:
    """

    data = dump(fs)
    names = sorted(data.keys())

    with ZipFile(name, "w", ZIP_STORED) as zipf:
        # # save fs object as binary data
        # fs_name = (fs.root_u.encode(encoding) + ".fs").replace('/', '_').replace('\\', '_')
        # fs_time = time.localtime(time.time())
        # fs_data = fs.dumps()
        # zi = ZipInfo(fs_name, fs_time)
        # zi.external_attr = ZIP_FILE_RW
        # zipf.writestr(zi, fs_data)

        for name in names:
            f = data[name]

            if not isinstance(f, FsFile):
                # oops! unknown object
                continue
            #

            if f.type == "DIR":
                continue
            #

            tags = f.tags or {}
            meta = f.meta or {}

            # compress tags
            for k, v in tags.items():
                if len(v) == 1 and isinstance(v, (tuple, list)):
                    tags[k] = v[0]
                #
            #

            if not f.data:
                if f.md5:
                    meta['md5'] = f.md5
                #

                meta['file_size'] = f.stat.st_size
                meta['file_time'] = f.stat.st_mtime
                meta['file_date'] = time.ctime(f.stat.st_mtime)
                meta['file_mode'] = f.stat.st_mode
            #

            # st = repr(tags) if tags else ""
            st = pprint.pformat(tags, 2, ) if tags else ""
            # sm = repr(meta) if meta else ""
            sm = pprint.pformat(meta, 2) if meta else ""

            fn = name.encode(encoding)
            ft = time.localtime(f.stat.st_mtime)[:6]
            meta_data = None

            if f.data:
                # tags
                if tags:
                    zi = ZipInfo(fn+".tags", ft)
                    zi.external_attr = ZIP_FILE_RW
                    zipf.writestr(zi, st)
                #

                # meta
                if meta:
                    zi = ZipInfo(fn+".meta", ft)
                    zi.external_attr = ZIP_FILE_RW
                    zipf.writestr(zi, sm)
                #
            else:
                meta_tags = dict(filter(None, [("META", meta) if meta else None, ("TAGS", tags) if tags else None]))
                meta_tags['DATE'] = time.ctime()
                meta_data = jsonlib.dumps(meta_tags, ensure_ascii=False, sort_keys=True, indent=2)
            #

            zi = ZipInfo(fn, ft)
            zi.external_attr = ZIP_FILE_RW
            s = get_bytes(f.data or meta_data)
            zipf.writestr(zi, s)
        #
    #
#


def mk_txt(name, fs, encoding="utf-8"):
    """ make .txt from fs

        :param name:
        :param fs:
        :param encoding:
        :return:
    """

    data = dump(fs)

    with open(name, "wb") as txt:
        for f_name in sorted(data.keys()):
            if f_name:
                txt.write(f_name.encode(encoding))
                txt.write("\n")
            #
        #
    #
#


def main():
    """
        :return:
    """
    parser = argparse.ArgumentParser(description="media scan program")
    parser.add_argument('path', help='scan path/.fs file', nargs='*')
    parser.add_argument('-o', '--out', help='save to file (prefix)', type=str, action="store")
    parser.add_argument('-f', '--make_fs', help='make .fs', default=False, action='store_true')
    parser.add_argument('-z', '--make_zip', help='make .zip', default=False, action='store_true')
    parser.add_argument('-t', '--make_text', help='make .txt', default=False, action='store_true')
    parser.add_argument('-s', '--sign', help='make signature as prefix', default=False, action='store_true')
    parser.add_argument('-d', '--dir', help='make one .fs for every dir', default=False, action='store_true')
    parser.add_argument('-v', '--verbose', help='increase output verbosity', action="count", default=0)
    args = parser.parse_args()

    if args.dir:
        args.make_fs = True
        new_dirs = []
        for path in args.path:
            for name in os.listdir(path):
                name = os.path.join(path, name)
                if os.path.isdir(name):
                    new_dirs.append(name)
                #
            #
        #

        if new_dirs:
            args.path = sorted(new_dirs)
        #
    #

    if args.out and len(args.path) > 1:
        print("error: '--out' only for one path")
        return 1
    #

    if args.verbose:
        callback = scan_print
    else:
        callback = None
    #

    for path in args.path:

        if args.out:
            name = args.out
        else:
            name = os.path.basename(os.path.abspath(path))
        #

        if os.path.isdir(path):
            print("scan {%s}" % path)
            fs = mk_fs(path, basename=name, callback=callback)
        else:
            print("load {%s}" % path)
            fs = Fs()
            fs.load(path)
            print("root{%r} index{%r} files{%r}" % (fs.root, len(fs.index), len(fs.files)))
        #

        if not isinstance(fs, Fs):
            print("fatal: unknown object {%r}" % fs)
            return 2
        #

        # empty fs?
        if len(fs) < 2:
            continue
        #

        if args.sign:
            sign = fs.hex_sign()
            name = "fs" + sign.lower()
        #

        if args.make_fs:
            fn = name + ".fs"
            tty("\n")
            tty("make {%s} {%r}" % (fn, len(fs)))
            fs.dump(fn, pack=True)
        #

        if args.make_zip:
            fn = name + ".zip"
            tty("\n")
            tty("make {%s}" % fn)
            mk_zip(fn, fs)
        #

        if args.make_text:
            fn = name + ".txt"
            tty("\n")
            tty("make {%s}" % fn)
            mk_txt(fn, fs)
        #

        tty('\n')
    #
#

if __name__ == "__main__":
    main()
#
