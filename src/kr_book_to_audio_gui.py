#!/usr/bin/env python3
from __future__ import annotations
import sys
from kr_book_to_audio.gui import main
from kr_book_to_audio.portable import portable_main

if __name__ == '__main__':
    smoke = portable_main(sys.argv[1:])
    if smoke is not None:
        raise SystemExit(smoke)
    main()
