import argparse  # noqa: F401
import csv  # noqa: F401
import json  # noqa: F401
import logging
import os  # noqa: F401
import time  # noqa: F401
from datetime import datetime, timedelta  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import TYPE_CHECKING, Any, Dict, List, Union  # noqa: F401

from doyles_sdk.cli.apps._base_app import DoyleApp

try:
    from . import register_cmd
except ImportError:

    def register_cmd(cls):
        return cls


if TYPE_CHECKING:
    logger: logging.Logger  # just for type checkers

# if you need an API session to a Splunk instance
# or any access that requires retry and connection pooling
# uncomment the following lines

# from doyles_sdk._wrappers import SplunkSession

# _token = None
# session = SplunkSession(token=_token)


@register_cmd
class CreateCertsCliApp(DoyleApp):
    command_name = "create_certs"
    mp_safe = False  # Allow multiprocessing
    thread_safe = False  # Allow threads

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument("--example", help="Example argument", default="value")

    @classmethod
    def args_post_process(cls, parser):
        pass

    @staticmethod
    def do_example_task(arg):
        """
        Example do_* method demonstrating concurrency support.

        logger is automatically injected to all do_* methods

        """
        time.sleep(0.5)
        logger.notice(f"Running task with {arg}")  # noqa: F821

    def run(self):
        """
        # Main application logic.
        Prefer delegating to do_* methods for consitent behavior using any execution method.

        The following are available:

            - self.logger
            - self.args
        """
        args_list = (
            [self.args.example]
            if isinstance(self.args.example, str)
            else self.args.example
        )
        self.run_with_workers(self.do_example_task, args_list)


# The following is required boilerplate
# DO NOT MODIFY
def cli():
    app = CreateCertsCliApp()
    try:
        app.run()
    finally:
        app.shutdown_logging()


if __name__ == "__main__":
    import sys

    sys.exit(cli())
