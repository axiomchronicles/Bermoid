from core.routing.pattern import rule

import main

ROUTER = [
    rule("/", main.main),
    rule("/dashboard", main.get_session),
]