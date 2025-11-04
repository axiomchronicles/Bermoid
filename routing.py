from core.routing.pattern import rule

import main

ROUTER = [
    rule("/", main.main)
]