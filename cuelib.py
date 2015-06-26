#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" cue tools library """

from binascii import hexlify
from hashlib import sha256 as hash_func
import chardet

#
# Byte Order Mark (BOM)
#
# Bytes         Encoding Form
# 00 00 FE FF   UTF-32, big-endian
# FF FE 00 00   UTF-32, little-endian
# FE FF         UTF-16, big-endian
# FF FE         UTF-16, little-endian
# EF BB BF      UTF-8

BOM_UTF8 = '\xef\xbb\xbf'
BOM_UTF16LE = '\xff\xfe'
BOM_UTF16BE = '\xfe\xff'


class CueError(ValueError):
    """ cue error """
    pass
#


class CueIndex(object):
    """ cue track index """

    def __init__(self, name, data):
        """
            :param name:
            :param data:
            :return:
        """

        self.name = name
        self.time = cue_parse_timestamp(data)
        self.data = cue_build_timestamp(self.time)
    #
#


class CueTrack(object):
    """ cue track """

    def __init__(self, **kwargs):
        """
            :param kwargs:
            :return:
        """

        self.file = -1
        self.id = ''
        self.type = 'AUDIO'
        self.performer = ''
        self.title = ''
        self.isrc = ''
        self.flags = ''
        self.indexes = []
        self.rems = CueRems()

        self.__dict__.update(kwargs)
    #

    def __repr__(self):
        """
            :return:
        """

        x = (self.file, self.id, self.type, self.performer, self.title, self.isrc, self.indexes)
        # return '<CueTrack> (%s)' % (", ".join(["%r"] * len(x)) % x,)
        return '<CueTrack> (%r, %r, %r, %r, %r, %r, %r)' % x
    #
#


class CueFile(object):
    """ cue FILE attribute """

    def __init__(self, name, filetype='WAVE', **kwargs):
        """

            :param name:
            :param filetype:
            :param kwargs:
            :return:
        """

        self.name = name
        self.type = filetype

        self.__dict__.update(kwargs)
    #

    def __repr__(self):
        """
            :return:
        """

        return '<CueFile> (%r, %r)' % (self.name, self.type)
    #
#


class CueRems(object):
    """ REMs of Cue """

    def __init__(self, data=None):
        """
            :param data:
            :return:
        """

        # place of all REMs
        self._data = None

        if isinstance(data, dict):
            self(data)
        else:
            self._data = {}
        #
    #

    def __getattr__(self, item):
        """
            :param item:
            :return:
        """

        return self._data.get(item, '')
    #

    def __getitem__(self, item):
        """
            :param item:
            :return:
        """

        return self._data.get(item, '')
    #

    def __call__(self, name=None, value=None):
        """
            :param name:
            :param value:
            :return:
        """

        # return current data
        if name is None:
            return self._data
        #

        # setup new data
        if isinstance(name, dict):
            self._data = name
            return self
        #

        if isinstance(value, basestring):
            if not isinstance(name, basestring):
                raise CueError("name isn't string (but %s)" % type(name))
            #
            self._data[name] = value
        elif value is None:
            pass
        else:
            raise CueError("value isn't string (but %s)" % type(value))
        #

        return self._data.get(name, '')
    #
#


class Cue(object):
    """ cue """

    def __init__(self):
        """
            :return:
        """

        self.data = ''
        self.encoding = 'ascii'
        self.rems = CueRems()
        self.catalog = ''
        self.performer = ''
        self.title = ''
        self.files = []
        self.tracks = []
    #

    def dumps(self, encoding='utf-8', bom=True):
        """ dump cue into string

            :param encoding:
            :param bom:
            :return:
        """

        out = []
        prefix = ''

        if bom:
            if encoding.lower() == 'utf-8':
                prefix = BOM_UTF8
            elif encoding.lower() == 'utf-16le':
                prefix = BOM_UTF16LE
            elif encoding.lower() == 'utf-16be':
                prefix = BOM_UTF16BE
            elif encoding.lower() == 'utf-16':
                encoding = 'utf-16le'
                prefix = BOM_UTF16LE
            else:
                prefix = ''
                #
        #

        # REMs
        for _1, _2 in self.rems().items():
            out.append('REM %s "%s"' % (_1, _2))
        #

        # Attributes
        for _1, _2 in (('CATALOG', self.catalog), ('PERFORMER', self.performer), ('TITLE', self.title)):
            if _2:
                out.append('%s "%s"' % (_1, _2))
                #
        #

        file_id = -1

        # Tracks
        skip = '  '
        skip2 = skip * 2
        for trk in self.tracks:
            # FILE
            if trk.file != file_id:
                file_id = trk.file
                _file = self.files[file_id]
                out.append('FILE "%s" %s' % (_file.name, _file.type))
            #

            # TRACK ID
            out.append('%sTRACK %s %s' % (skip, trk.id, trk.type))

            # HEADER
            for _1, _2 in (('TITLE', trk.title), ('PERFORMER', trk.performer), ('ISRC', trk.isrc)):
                if _2:
                    out.append('%s%s "%s"' % (skip2, _1, _2))
                    #
            #

            # FLAGS
            if trk.flags:
                out.append('%sFLAGS %s' % (skip2, trk.flags))
            #

            # INDEX
            for idx in trk.indexes:
                out.append('%sINDEX %s %s' % (skip2, idx.name, idx.data))
            #

            # REMs
            for _1, _2 in trk.rems().items():
                out.append('%sREM %s "%s"' % (skip2, _1, _2))
                #
        #

        # last-empty-line
        out.append('')

        # return prefix + '\n'.join([_.encode(encoding) for _ in out])
        return prefix + ('\n'.join(out)).encode(encoding)
    #

    def sign(self, ignore_head=True, ignore_files=True, ignore_tracks=True):
        """ calculate disc (rip) signature (as binary string)

            :param ignore_head:
            :param ignore_files:
            :param ignore_tracks:
            :return:
        """

        # from head
        if ignore_head:
            _1 = ''
        else:
            _head = ('%03d' % len(self.files), '%03d' % len(self.tracks), self.performer, self.title)
            _1 = (''.join([_.lower().encode('utf-8') for _ in _head])).replace(' ', '')
        #

        # from files
        if ignore_files:
            _2 = ''
        else:
            _2 = (''.join([_.name.lower().encode('utf-8') for _ in self.files])).replace(' ', '')
        #

        # from tracks
        _3 = ''
        _4 = "%02X" % len(self.tracks)
        for trk in self.tracks:
            if not ignore_tracks:
                _3 += trk.title.lower().encode('utf-8')
            #
            _4 += ',' + '.'.join(["%06X" % _.time for _ in trk.indexes])
        #
        _3 = _3.replace(' ', '')

        h = hash_func()
        for _ in (_1, _2, _3, _4):
            h.update(_)
        #

        # print(_1)
        # print(_2)
        # print(_3)
        # print(_4)

        return h.digest()
    #

    def hex_sign(self, ignore_head=True, ignore_files=True, ignore_tracks=True):
        """ return cue-signature as hex-string (upper-case)

            :param ignore_head:
            :param ignore_files:
            :param ignore_tracks:
        """

        return hexlify(self.sign(ignore_head, ignore_files, ignore_tracks)).upper()
    #

    def check(self):
        """ check cue

            :return:
        """

        errors = []
        warnings = []

        _empty = (
            (self.files, 'no file(s)'),
            (self.tracks, 'no track(s)'),
            (self.performer, 'no performer (head)'),
            (self.title, 'no title (head)')
        )

        # error(s)
        for _1, _2 in _empty:
            if not _1:
                errors.append(_2)
                #
        #

        # warning(s)
        _rems = ((self.rems.GENRE, 'no genre'), (self.rems.DATE, 'no date'))
        for _1, _2 in _rems:
            if not _1:
                warnings.append(_2)
                #
        #

        return errors, warnings
    #

    def is_image(self):
        """ check if cue for image """

        return len(self.files) == 1
    #

    def is_tracks(self):
        """ check if cue for tracks """

        return len(self.files) == len(self.tracks)
    #

    def __getitem__(self, item):
        """
            :param item: get track by number
            :return:
        """

        return self.tracks[item]
    #

    def __len__(self):
        """ return total tracks

            :return:
        """

        return len(self.tracks)
    #
#


def as_unicode(data, default='cp1251', strict=False):
    """ return unicode data and encoding (and cutoff BOM)

        :param data:
        :param default:
        :param strict: use mode
        :return: unicode-data, encoding-as-string
    """

    # (in)sane check
    if isinstance(data, unicode):
        return data, ''
    #

    if strict:
        encoding = default
    else:
        encoding = chardet.detect(data).get('encoding', default)
        if encoding in ("MacCyrillic",):
            encoding = default
        #
    #

    if data.startswith(BOM_UTF8):
        _skip = len(BOM_UTF8)
    elif data.startswith(BOM_UTF16LE) or data.startswith(BOM_UTF16BE):
        _skip = len(BOM_UTF16BE)
    else:
        _skip = 0
    #

    # cutoff BOM
    if _skip:
        data = data[_skip:]
    #

    return unicode(data, encoding), encoding
#


def cue_parse_timestamp(data):
    """ parses a timestamp string into an integer

        :param data:
        :return:
    """

    if ":" in data:
        (_m, _s, _f) = map(int, data.split(":"))
        return (_m * 60 * 75) + (_s * 75) + _f
    #

    return int(data)
#


def cue_build_timestamp(data):
    """ returns a timestamp string from an integer number of CD frames

        :param data:
        :return:
    """

    return "%2.2d:%2.2d:%2.2d" % ((data / 75) / 60, (data / 75) % 60, data % 75)
#


def cue_normalize(data):
    """ normalize data (remove {\t}, strip {'} {"} and space)

        :param data:
        :return:
    """

    data = data.replace('\t', '').strip()

    if data.startswith('"'):
        data = data.strip('"').strip()
    #

    if data.startswith("'"):
        data = data.strip("'").strip()
    #

    return data
#


def cue_get_attrib(attrib, data, div=' ', param=1):
    """ get attribute

        :param attrib: attribute name
        :param data: raw data
        :param div: divisor
        :param param: total params
        :return:
    """

    if not data:
        return [""]
    #

    d = data.split(div, param)

    if (len(d) != param + 1) or (attrib != d[0]):
        raise CueError('invalid: {%r} from {%r}' % (attrib, data))
    #

    return map(cue_normalize, d[1:])
#


def cue_get_token(data):
    """ get token

        :param data:
        :return:
    """

    if not data:
        return [""]
    #

    d = data.split(' ', 1)
    if len(d) != 2:
        raise CueError('invalid format: %r' % data)
    #

    return map(cue_normalize, d)
#


def cue_get_file(data):
    """ get 'file' attribute

        :param data:
        :return:
    """

    d = data.replace('FILE', '').strip().rsplit(' ', 1)
    if len(d) != 2:
        raise CueError('invalid: {%r}' % data)
    #

    return map(cue_normalize, d)
#


def cue_add_track(tracks, data):
    """ add track

        :param tracks:
        :param data:
        :return:
    """

    tr_id, tr_title, tr_perf, tr_isrc, tr_flags, tr_index, tr_file = data

    if not tr_id:
        raise CueError('track: no id')
    #

    if not tr_index:
        raise CueError('track: no index {%r}' % tr_id)
    #

    if tr_file < 0:
        raise CueError('track: no file {%r}' % tr_id)
    #

    if not tr_title:
        tr_title = ''
    #

    tr_num, tr_type = cue_get_attrib('TRACK', tr_id, param=2)
    tr_isrc = cue_get_attrib('ISRC', tr_isrc)[0]

    tr_indexes = []
    for index in tr_index:
        _1, _2 = cue_get_attrib('INDEX', index, param=2)
        tr_indexes.append((_1, cue_parse_timestamp(_2), _2))
    #

    track = CueTrack(id=tr_num, title=tr_title, indexes=tr_indexes, file=tr_file,
                     performer=tr_perf, type=tr_type, isrc=tr_isrc, flags=tr_flags)

    tracks.append(track)
#


def cue_parse_head(data):
    """ parse cue head and return Cue()

        :param data:
        :return:
    """

    rems = {}
    cue = Cue()
    cue.rems(rems)

    for line in data:
        attr, rest = cue_get_token(line)

        if attr == "PERFORMER":
            cue.performer = rest
        elif attr == "TITLE":
            cue.title = rest
        elif attr == "CATALOG":
            cue.catalog = rest
        elif attr == "REM":
            _1, _2 = cue_get_token(rest)
            rems[_1] = _2
        else:
            raise CueError('unknown param %r' % attr)
        #
    #

    return cue
#


def cue_parse_track(cue, data):
    """ parse cue track and return CueTrack()

        :param cue:
        :param data:
        :return:
    """

    _id, _fl, _data = data
    tr_id, tr_type = _id

    indx = []
    rems = {}
    trk = CueTrack(id=tr_id, type=tr_type, file=_fl)
    trk.rems(rems)

    for line in _data:
        attr, rest = cue_get_token(line)

        if attr == "PERFORMER":
            trk.performer = rest
        elif attr == "TITLE":
            trk.title = rest
        elif attr == "ISRC":
            trk.isrc = rest
        elif attr == "FLAGS":
            trk.flags = rest
        elif attr == "INDEX":
            _1, _2 = cue_get_token(rest)
            indx.append(CueIndex(_1, _2))
        elif attr == "REM":
            _1, _2 = cue_get_token(rest)
            rems[_1] = _2
        else:
            raise CueError('unknown param %r' % attr)
            #
    #

    if indx:
        trk.indexes = indx
    else:
        raise CueError('no track index(-es)')
    #

    if not trk.performer:
        trk.performer = cue.performer
    #

    return trk
#


def cue_parse(data, encoding="cp1251"):
    """ parse .cue from string and return Cue()

        :param data:
        :param encoding:
        :return: Cue() object
    """

    data_orig = data
    data, encoding = as_unicode(data, encoding)

    head = []  # cue head
    files = []  # cue files
    tracks = []  # cue tracks
    track = []  # track info
    track_id = ''  # track id (TRACK ...)
    track_fl = -1  # track file-id

    line_id = 0
    for line in data.split('\n'):
        line_id += 1
        line = line.strip()

        if not line:
            continue
        #

        if line.startswith('TRACK '):
            if track_id and track:
                tracks.append((track_id, track_fl, track))
            #
            track = []
            track_id = cue_get_attrib('TRACK', line, param=2)
            track_fl = len(files) - 1
        elif line.startswith('FILE '):
            files.append(CueFile(*cue_get_file(line)))
        else:
            if track_id:
                track.append(line)
            else:
                head.append(line)
            #
        #
    #

    # add last track
    if track_id and track:
        tracks.append((track_id, track_fl, track))
    #

    # print head, files, tracks

    if not head:
        raise CueError('empty head')
    #

    if not files:
        raise CueError('no file(s)')
    #

    if not tracks:
        raise CueError('no track(s)')
    #

    cue = cue_parse_head(head)
    cue.data = data_orig
    cue.encoding = encoding
    cue.files = files
    cue.tracks = [cue_parse_track(cue, _) for _ in tracks]

    return cue
#


if __name__ == "__main__":
    import sys

    for cue_name in sys.argv[1:]:
        with open(cue_name, "rb") as f:
            f_cue = cue_parse(f.read(), encoding="utf-8")
            print("%r %r" % (cue_name, f_cue.hex_sign()))
            # print("%r %r" % (cue_name, cue.hex_sign(ignore_files=True)))
            # print("%r %r" % (cue_name, cue.hex_sign(ignore_files=True, ignore_head=True)))
            # print("%r %r" % (cue_name, cue.hex_sign(ignore_files=True, ignore_head=True, ignore_tracks=True)))
            for f_track in f_cue:
                print("TRK(%r)" % f_track)
            #
        #
    #
#
