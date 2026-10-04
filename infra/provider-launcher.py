#!/usr/bin/env python3
"""Run the approved integration module with fixed-provider IPv6 transport."""
from pathlib import Path
import runpy
import sys
from provider_ipv6 import install

if Path('/app/flood').is_dir():
    sys.path.insert(0, '/app')
install()
runpy.run_module('flood.integrations', run_name='__main__')
