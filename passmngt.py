# -*- coding: utf-8 -*-
#
# Copyright 2022 (c) by Bart Skowron <bxsx@bartskowron.com>
# All rights reserved. Licensed under the MIT license.
#
#
# Password Managers support for Garmin Connect Export
#
#
# Credentials must be stored in the following meta-fields:
# - URL: garmin.com
# - login: username
# - password: password
#
# For setup instructions, see the official documentation for Password Manager
#

import logging
import os
import sys
from abc import ABCMeta, abstractmethod
from subprocess import run


class PasswordManager(metaclass=ABCMeta):
    """Password Manager Abstract Class"""

    name = "Abstract Password Manager"

    # Protected methods that require super() to be called when overriding
    SUPERCALLS = ("destroy_session",)

    def __new__(cls, *args, **kwargs):
        for method in cls.SUPERCALLS:
            if not getattr(cls, method).__code__.co_freevars:
                logging.error("Unsafe Password Manager plugin detected.")
                raise Exception(
                    f"The super() call is required in {cls.__name__}.{method}()"
                )
        return super().__new__(cls, *args, **kwargs)

    def __init__(self, url="garmin.com"):
        self.url = url
        self.session = None
        self.user = None
        self.password = None

        self.__clear_credentials()

    @abstractmethod
    def get_session(self, cmd):
        """
        Get Session ID for Password Manager.

        :return: session ID
        """
        ...

    @abstractmethod
    def destroy_session(self):
        """
        Destroy stored credentials on the Password Manager object.

        First call super() and then follow the PM-specific steps.
        """
        self.__clear_credentials()

    @abstractmethod
    def get_user(self):
        """
        Return the looked-up login.

        :return: the Garmin Connect login
        """
        ...

    @abstractmethod
    def get_password(self):
        """
        Return the looked-up password.

        :return: the Garmin Connect password
        """
        ...

    def __enter__(self):
        """ContextManager to provide credentials in a safe way."""
        self.session = self.get_session()
        self.user = self.get_user()
        self.password = self.get_password()

        if not all((self.user, self.password)):
            logging.error(f"{self.name} cannot find credentials for: {self.url}")
            self.destroy_session()
            sys.exit(1)

        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.destroy_session()

    def __clear_credentials(self):
        self.user = None
        self.password = None
        self.session = None

    def _check_returncode(self, proc):
        """
        Verify the EXIT STATUS for proc.

        :return: True if 0, otherwise, log the error and exit.
        """
        if proc.returncode:
            errmsg = proc.stderr
            try:
                errmsg = errmsg.decode()
            except AttributeError:
                errmsg = str(errmsg)

            logging.error(errmsg)
            self.destroy_session()
            sys.exit(1)

        return True

    def _remove_eol(self, string):
        """
        Remove EOL (line separator) from the string.

        This function provides a safe way to remove trailing newline characters
        from passwords that contain trailing whitespaces.

        :param string: string to chomp
        :return: string without EOL (if existed)
        """
        return string[: -len(os.linesep)] if string.endswith(os.linesep) else string


class BitWarden(PasswordManager):
    name = "BitWarden"
    META = "BW_SESSION="

    def get_session(self):
        print("Enter your master password: ", end="", flush=True)
        bw = run(["bw", "unlock"], capture_output=True, text=True)
        print()

        self._check_returncode(bw)

        output = bw.stdout
        try:
            session_start = output.index(self.META) + len(self.META)
            session_stop = output.index('"', session_start + 1)
        except ValueError:
            logging.error(bw.stderr)
            self.destroy_session()
            sys.exit(1)

        return output[session_start:session_stop]

    def destroy_session(self):
        super().destroy_session()
        run(["bw", "lock"])

    def get_user(self):
        return run(
            ["bw", "get", "username", self.url, "--session", self.session],
            capture_output=True,
            text=True,
        ).stdout

    def get_password(self):
        return run(
            ["bw", "get", "password", self.url, "--session", self.session],
            capture_output=True,
            text=True,
        ).stdout


class OnePassword(PasswordManager):
    name = "1Password"

    def get_session(self):
        op = run(["op", "signin", "--raw"], capture_output=True, text=True)
        self._check_returncode(op)
        return op.stdout

    def destroy_session(self):
        super().destroy_session()
        run(["op", "signout"])

    def get_user(self):
        user = run(
            [
                "op",
                "item",
                "get",
                self.url,
                "--fields",
                "label=username",
                f"--session={self.session}",
            ],
            capture_output=True,
            text=True,
        ).stdout
        return self._remove_eol(user)

    def get_password(self):
        password = run(
            [
                "op",
                "item",
                "get",
                self.url,
                "--fields",
                "label=password",
                f"--session={self.session}",
            ],
            capture_output=True,
            text=True,
        ).stdout
        return self._remove_eol(password)
