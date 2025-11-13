# doyles_sdk/commands/generate_cli.py
from pathlib import Path

from doyles_sdk._metaclass import InfoMeta
from doyles_sdk.cli.apps._base_app import DoyleApp
from . import register_cmd


@register_cmd
class GenerateCLIApp(DoyleApp):
    """
    Generate a new CLI scaffold file for DoyleApp-based applications.

    Usage:

        doyles create_cli_app --name <CommandName> [--output-dir <path>]

    Features:
        - Auto-populates all user hooks (add_arguments, args_post_process)
        - Includes a sample do_* method for concurrency
        - Adds docstrings and instructions for customization
        - Registers the new command automatically
    """

    command_name = "create_cli_app"
    mp_safe = False
    thread_safe = False

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument(
            "--name", required=True, help="Name of the new CLI command/class"
        )
        parser.add_argument(
            "--output-dir",
            default=".",
            help="Directory to place the generated scaffold",
        )

    def run(self):
        name = self.args.name.strip()
        output_dir = Path(self.args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        class_name = "".join([part.capitalize() for part in name.split("_")]) + "CliApp"
        filename = output_dir / f"{name}_app.py"

        # Dynamically generate scaffold code with base arguments injected
        scaffold_code = self._generate_scaffold_code(class_name, name)

        with open(filename, "w", encoding="utf-8") as f:
            f.write(scaffold_code)

        self.logger.notice("CLI scaffold created at %s", filename)

    def _generate_scaffold_code(self, cls_name: str, cmd_name: str) -> str:
        """
        Generate the scaffold code for a new DoyleApp CLI subclass.
        Dynamically injects base parser arguments into the add_arguments docstring.
        """
        base_parser = DoyleApp._build_parser()  # full parser with all base args
        # Exclude private/internal args starting with _
        base_arg_names = [
            a.dest.replace("_", "-")
            for a in base_parser._actions
            if not a.dest.startswith("_")
        ]
        formatted_args = "\n        --".join(base_arg_names)

        # Metaclass attributes (from InfoMeta)
        meta_attrs_formatted = "\n        - ".join(InfoMeta.INJECTED_ATTRIBUTES)

        return f'''\
import argparse  # noqa: F401
import csv  # noqa: F401
import json  # noqa: F401
import logging
import os  # noqa: F401
import time  # noqa: F401
from datetime import datetime, timedelta  # noqa: F401
from pathlib import Path   # noqa: F401
from typing import TYPE_CHECKING, Any, Dict, List, Union   # noqa: F401

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
class {cls_name}(DoyleApp):
    """
    Auto-generated CLI scaffold for DoyleApp.

    Provides:
        - argument parsing
        - logging
        - threading and multiprocessing support

    Customize this class by overriding:
        - add_arguments()
        - args_post_process()
        - do_* methods
        - run()

    The following can referenced directly in your methods:

        - {meta_attrs_formatted}
    """

    command_name = "{cmd_name}"
    mp_safe = False       # Allow multiprocessing
    thread_safe = False   # Allow threads

    @classmethod
    def add_arguments(cls, parser):
        """
        # Add your custom CLI arguments here.

        The following arguments are **already defined by the base parser**
        and should NOT be redefined here:

        --{formatted_args}

        **Example:**
            parser.add_argument("--example", help="Example argument", default="value")
        """
        parser.add_argument("--example", help="Example argument", default="value")

    @classmethod
    def args_post_process(cls, parser):
        """
        # Validate or transform parsed args.

        **Example:**
            if parser.my_option and not valid(parser.my_option):
                raise ValueError("Invalid option")
        """
        pass

    @staticmethod
    def do_example_task(arg):
        """
        Example do_* method demonstrating concurrency support.

        logger is automatically injected to all do_* methods

        """
        time.sleep(0.5)
        logger.notice(f"Running task with {{arg}}") # noqa: F821


    def run(self):
        """
        # Main application logic.
        Prefer delegating to do_* methods for consitent behavior using any execution method.

        The following are available:

            - self.logger
            - self.args
        """
        args_list = [self.args.example] if isinstance(self.args.example, str) else self.args.example
        self.run_with_workers(self.do_example_task, args_list)

# The following is required boilerplate
# DO NOT MODIFY
def cli():
    app = {cls_name}()
    try:
        app.run()
    finally:
        app.shutdown_logging()

if __name__ == "__main__":
    import sys
    sys.exit(cli())
'''
