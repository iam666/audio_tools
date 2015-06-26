#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" default config """

import sys
[sys.path.append(_) for _ in (r'/home/iam666/bin/tools',)]

config = {}

# system config
_ = {"PROXY": {'http': '666.666.666.666:666'}, "DEFAULT_ENCODING": 'utf-8'}
config["system"] = _

# CueTagger config
_ = {"USER_TOKEN": "*",
     "USER_SECRET": "*",
     "CACHE_USE": True,
     "CACHE_STORAGE": '/home/iam666/bin/tools/discogs_cache.db',
     "CACHE_TABLE": 'CUE_TAGGER_CACHE',
     "CACHE_COMPRESS": True,
     "CACHE_SYNC": 10}
config["CueTagger"] = _

# cleanup
del _
