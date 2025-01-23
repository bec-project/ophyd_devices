#!/bin/python
import base64
import sys

with open(sys.argv[1], mode="rb") as f:
    with open(sys.argv[2], "w") as o:
        o.write(str(base64.b64encode(f.read())))
