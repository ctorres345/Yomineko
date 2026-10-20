"""The local web interface: pages served from this computer to its own browser or app window.

Needs the web extra (``pip install "yomineko[web]"``). Nothing here is reachable from another
machine: the server binds to 127.0.0.1 and ``security`` refuses requests that do not look like they
came from a page this server served.
"""
