import os

from core.asgi.application import ASGI
from core.asgi.routing import Router

from core.application import Bermoid

os.environ['Bermoid_SETTINGS_MODULE'] = "settings"

# Warning: Do not modify this file or rename the variables.
# Making any changes could potentially break the application and cause malfunctions.

# The 'application' variable declares the current ASGI (Asynchronous Server Gateway Interface) application.
# This application originates from the '__root__' directory of this project.

application: Bermoid = ASGI.application()

# The Router.finalize() method checks all the routes and schematic instances
# to ensure they are properly configured before finalizing the route to the web.

Router().finalize()
