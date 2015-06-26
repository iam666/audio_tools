#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" tag """

try:
    from default_config import config as default_config
except ImportError:
    default_config = {}
#

import search_dg
search_dg.main()
