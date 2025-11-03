from core.routing import HTTPRouting

import main

ROUTER = [
    HTTPRouting.rule("/", main.main)
]