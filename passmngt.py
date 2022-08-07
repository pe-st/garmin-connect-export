# Password Managers support
#
# Credentials must be stored in the following metafields:
# - URL: garmin.com
# - login: username
# - password: password

import logging
import sys
from subprocess import run


class BitWarden:
    META = "BW_SESSION="

    def __init__(self, url="garmin.com"):
        self.user = None
        self.password = None
        self.session = None
        self.url = url

    def lock(self):
        self.user = None
        self.password = None
        self.session = None
        run(["bw", "lock"])

    def __enter__(self):
        print("Enter your master password: ", end="", flush=True)
        bw = run(["bw", "unlock"], capture_output=True)
        print()

        output = bw.stdout.decode()
        try:
            session_start = output.index(self.META) + len(self.META)
            session_stop = output.index('"', session_start + 1)
        except ValueError:
            logging.error(bw.stderr.decode())
            self.lock()
            sys.exit(1)

        self.session = output[session_start:session_stop]
        self.user = run(
            ["bw", "get", "username", self.url, "--session", self.session],
            capture_output=True,
        ).stdout.decode()
        self.password = run(
            ["bw", "get", "password", self.url, "--session", self.session],
            capture_output=True,
        ).stdout.decode()

        if not all((self.user, self.password)):
            logging.error("BitWarden cannot find credentials for: %s", self.url)
            self.lock()
            sys.exit(1)

        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.lock()

