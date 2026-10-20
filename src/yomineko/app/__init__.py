"""The desktop app: the web interface in a window of its own.

It starts the same local server as ``yomineko serve`` on a free port and shows it in a native
window (pywebview). Where no window can be made (some Linux setups), it opens the default browser
instead and the page gets a Quit button. Needs the app extra (``pip install "yomineko[app]"``).
"""
