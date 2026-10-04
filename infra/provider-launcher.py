#!/usr/bin/env python3
"""Run the approved integration module with fixed-provider IPv6 transport."""
from pathlib import Path
import os
import runpy
import sys
from provider_ipv6 import install

if Path('/app/flood').is_dir():
    sys.path.insert(0, '/app')
install()
pilot = os.environ.get('FLOOD_TELEGRAM_PILOT_CONFIG')
if pilot:
    if sys.argv[1:] != ['telegram']:
        raise ValueError('Technical pilot adapter is only for Telegram')
    from telegram_pilot import install as install_pilot
    install_pilot(pilot)
else:
    runpy.run_module('flood.integrations', run_name='__main__')
