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
class CreateModuleCliApp(DoyleApp):
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

        - __package__
        - __author__
        - __email__
        - __license__
        - __python__
        - __platform__
        - __system__
        - __machine__
        - __release__
        - __mem_total__
        - __mem_avail__
        - __cpu_count__
        - __version__
    """

    command_name = "create_module"
    mp_safe = False  # Allow multiprocessing
    thread_safe = False  # Allow threads

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
        logger.notice(f"Running task with {arg}")  # noqa: F821

    def run(self):
        module_name = self.args.name.strip()
        src_dir = Path(__file__).resolve().parents[4]
        output_dir = Path(self.args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        print(src_dir)

        project_name = "".join([part.capitalize() for part in module_name.split("_")])
        projectdir = output_dir / project_name

        project_code = self._generate_pyproject(project_name, module_name)
        print(project_code)

    def _generate_pyproject(self, project_name: str, module_name: str) -> str:
        """
        Generate the pyproject.toml code for a new DoylesSDK module.
        """
        return f'''\
[build-system]
requires = ["setuptools>=65", "setuptools_scm[toml]>=6.3"]
build-backend = "setuptools.build_meta"

[project]
name = "{module_name}"
authors = [
    {{name = "Michael Doyle", email = "doymi01@gmail.com"}},
]
description = "The Magic Script"
requires-python = ">=3.9"
dependencies = ["doyles_sdk"]

dynamic = ["version", "readme"]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-cov",
    "build"
]

[tool.setuptools.packages.find]
where = ["src"]  # list of folders that contain the packages (["."] by default)
include = ["{module_name}*"]  # package names should match these glob patterns (["*"] by default)
exclude = []  # exclude packages matching these glob patterns (empty by default)
namespaces = true  # to disable scanning PEP 420 namespaces (true by default)

[tool.setuptools.dynamic]
readme = {{file = ["README.md"], content-type = "text/markdown"}}

[tool.setuptools_scm]
write_to = "_version.py"

[project.scripts]
{module_name} = "{module_name}.cli:main"

[tool.pyright]
typeCheckingMode = "standard"
include = ["src"]
exclude = ["tests"]
reportDeprecated = "none"
reportAttributeAccessIssue = "information"
reportOptionalSubscript = 'information'
'''


# The following is required boilerplate
# DO NOT MODIFY
def cli():
    app = CreateModuleCliApp()
    try:
        app.run()
    finally:
        app.shutdown_logging()


if __name__ == "__main__":
    import sys

    sys.exit(cli())
