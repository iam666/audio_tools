#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" wave join routine """

import os
import sys
import wave
import argparse
import locale
import fnmatch
import re

# for logger()
VERBOSE_LEVEL = 0

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

# default
DEFAULT_ENCODING = locale.getpreferredencoding()
FRACTION_LENGTH = 75  # FRACTIONS_IN_SECOND = SAMPLE_RATE / FRACTION_LENGTH

#
# nnn = (ff/75) * 1000  //  switch between <nnn> fractions of seconds and <ff> of frames
#
# samples_per_frame = SAMPLE_RATE / 75)
# bytes_per_sample = num_channels * 3   // 24-bit is 3 byte per channel
# frame_count = ((minutes * 60) + seconds) * 75
# sample_count = sample_count * samples_per_frame
# byte_offset = sample_count * bytes_per_sample
#


def list_dir(path, mask="*"):
    """ get list of files (filtered)

        :param path:
        :param mask:
    """

    path = path or "./"

    try:
        return [os.path.join(path, name) for name in fnmatch.filter(os.listdir(path), mask)]
    except Exception as e:
        print("exception: %r" % e)
        return []
    #
#


def dir_for_cue(name, matches=DIR_MATCHES):
    """get directory name (correct) as dict()

        :param name: dir name
        :param matches: list-of-compiled-matches
    """

    for p in matches:
        m = p.match(name)
        if m:
            return m.groupdict()
        #
    #

    return {}
#


def tty(message=""):
    """ write to stdout with flush

        :param message:
    """

    sys.stdout.write(message)
    sys.stdout.flush()
#


def logger(data="", level=0, codec=DEFAULT_ENCODING, prologue=None, epilog='\n'):
    """ logger

        :param data:
        :param level:
        :param codec: for unicode
        :param prologue: out-before-data
        :param epilog: out-after-data
    """

    global VERBOSE_LEVEL

    if VERBOSE_LEVEL >= level:
        if isinstance(data, unicode):
            data = data.encode(codec)
        #

        if not isinstance(data, str):
            data = str(data)
        #

        for s in (prologue, data, epilog):
            if s:
                tty(s)
            #
        #
    #
#


def get_cue_time(n):
    """ get time as <mm>:<ss>:<ff>

        :param n: frames
        :return:
    """

    ff = n % FRACTION_LENGTH
    ss = (n / FRACTION_LENGTH) % 60
    mm = n / (FRACTION_LENGTH * 60)

    return "%02d:%02d:%02d" % (mm, ss, ff)
#


def make_cue(args, marks, encoding="utf-8-sig", cue_encoding="utf-8"):
    """ make_cue

        :param args:
        :param marks:
        :param encoding:
        :param cue_encoding:
    """

    va = args.va
    if va:
        performer = "Various Artists"
    else:
        performer = args.cue_performer or "Unknown"
    #

    cue = ['REM GENRE "%s"' % (args.cue_genre or "Unknown"),
           'REM DATE "%s"' % (args.cue_year or "2000"),
           'REM LABEL "%s"' % args.cue_label if args.cue_label else '',
           'REM COMMENT "%s"' % (args.cue_comment or "DarkMan Music Collection"),
           'PERFORMER "%s"' % performer,
           'TITLE "%s"' % (args.cue_title or "Unknown"),
           'FILE "%s" WAVE' % args.output]

    # remove empty item(s)
    cue = filter(None, cue)

    offset = 0
    track = 1
    for name, frames, fraction_size in marks:
        if va:
            performer, _, name = name.partition(" - ")
        else:
            performer = ""
        #

        cue.append("  TRACK %02d AUDIO" % track)

        if performer:
            cue.append('    PERFORMER "%s"' % performer)
        #

        cue.append('    TITLE "%s"' % name)
        cue.append('    INDEX 01 %s' % get_cue_time(offset / fraction_size))

        track += 1
        offset += frames
    #
    cue.append('')

    cue = [x if isinstance(x, unicode) else unicode(x, cue_encoding) for x in cue]
    cue_text = "\n".join(cue)
    if not isinstance(cue_text, unicode):
        cue_text = unicode(cue_text, cue_encoding)
    #

    cue_name = os.path.splitext(args.output)[0] + ".cue"
    with open(cue_name, "wb") as f:
        f.write(cue_text.encode(encoding))
    #

    return cue
#


def main():
    """ main """

    global VERBOSE_LEVEL

    # parse "current work directory"
    cwd = os.path.basename(os.getcwdu())
    dir_params = dir_for_cue(cwd)

    parser = argparse.ArgumentParser(description="wave join routine")
    parser.add_argument('in_files', help='input .wav names', nargs='*')
    parser.add_argument('-o', '--output', help='output .wav filename', default='output.wav', action='store')
    parser.add_argument('-s', '--sort', help='sort input names', default=False, action='store_true')
    parser.add_argument('-O', '--overwrite', help='overwrite output', default=False, action='store_true')
    parser.add_argument('-S', '--simulate', help='simulate output', default=False, action='store_true')
    parser.add_argument('-v', '--verbose', help='increase output verbosity, "-vv" for more', action="count", default=0)
    parser.add_argument('-G', '--cue_genre', help='cue param "GENRE"', default=dir_params.get("genre", ""))
    parser.add_argument('-P', '--cue_performer', help='cue param "PERFORMER"', default=dir_params.get("artist", ""))
    parser.add_argument('-T', '--cue_title', help='cue param "TILE"', default=dir_params.get("album", ""))
    parser.add_argument('-Y', '--cue_year', help='cue param "YEAR"', default=dir_params.get("year", ""))
    parser.add_argument('-L', '--cue_label', help='cue param "LABEL"', default=dir_params.get("catno", ""))
    parser.add_argument('-C', '--cue_comment', help='cue param "COMMENT"', default=dir_params.get("comment", ""))
    parser.add_argument('-V', '--va', help='various artists flag', default=False, action='store_true')
    args = parser.parse_args()

    # tracks mark
    marks = []

    # global param
    VERBOSE_LEVEL = args.verbose
    logger("{%r}" % args, level=2)

    if not args.in_files:
        logger("warning: no input file(s)")
        return 1
    #

    # only simulate
    simulation = args.simulate

    # make output file
    o_name = args.output
    o_params = None

    if simulation:
        o = None
    else:
        if args.overwrite and os.path.isfile(o_name):
            logger("error: output file exists {%s}" % o_name)
            return 2
        else:
            o = wave.open(o_name, "wb")
        #
    #

    logger("simulation: %s" % simulation, level=1)

    # wildcard process
    in_files = []
    for name in args.in_files:
        _dir, _mask = os.path.split(name)
        if ("*" in _mask) or ("?" in _mask):
            in_files.extend(list_dir(_dir, _mask))
            logger("wildcard: %r => %r" % (name, in_files), level=1)
        else:
            in_files.append(name)
        #
    #

    logger("files: %r" % in_files, level=1)
    if not in_files:
        logger("warning: no input file(s)")
        return 1
    #

    for name in in_files:
        if os.path.abspath(name) == os.path.abspath(o_name):
            logger("skip: {%s}" % name, level=1)
            continue
        #

        if not os.path.isfile(name):
            logger("error: can't find {%s}" % name)
            continue
        #

        w = wave.open(name, "rb")
        w_params = w.getparams()
        w_params3 = w_params[:3]
        w_n_frames = w.getnframes()
        w_channels, w_sample_width, w_frame_rate = w_params[:3]
        w_fraction_size = int(w_frame_rate / FRACTION_LENGTH)

        if w_fraction_size * FRACTION_LENGTH != w_frame_rate:
            logger("error: unsupported rate{%s}" % w_frame_rate)
            w.close()
            continue
        #

        w_padding = (w_fraction_size - (w_n_frames % w_fraction_size)) % w_fraction_size

        if not o_params:
            o_params = w_params
            o_params3 = o_params[:3]
            if o:
                o.setparams(o_params)
            #
        #

        # check params: n_channels, sample_width, frame_rate
        if o_params3 != w_params3:
            logger("error: illegal param{%s} for {%s}, need {%s}" % (w_params3, name, o_params3))
            w.close()
            continue
        #

        if simulation:
            w_frames = ""
        else:
            w_frames = w.readframes(w_n_frames)
        #
        w.close()

        logger("add: {%s} param{%s} frames{%s} padding{%s} fraction{%s}" %
               (name, w_params3, w_n_frames, w_padding, w_fraction_size), level=1)

        if o and w_frames:
            o.writeframes(w_frames)
            if w_padding:
                padding = '\x00' * (w_channels * w_sample_width) * w_padding
                o.writeframes(padding)
            #
        #

        # get "track name"
        trk_name = os.path.basename(os.path.splitext(name)[0]).title()
        x = trk_name.partition(" ")
        if x[0].isdigit():
            trk_name = x[-1].strip()
        #

        logger("track name: {%s} => {%s}" % (name, trk_name), level=1)
        marks.append((trk_name, w_n_frames+w_padding, w_fraction_size))
    #
    if o:
        o.close()
    #

    make_cue(args, marks)
    return 0
#

if __name__ == "__main__":
    sys.exit(main())
#
