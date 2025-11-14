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


@register_cmd
class CreateSslInputsCliApp(DoyleApp):
    command_name = "create_ssl_inputs"
    mp_safe = False  # Allow multiprocessing
    thread_safe = False  # Allow threads

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument(
            "outdir",
            metavar="OUT_DIR",
            help="Output Directory",
            nargs="?",
            default=os.getcwd(),
        )
        parser.add_argument(
            "--name", help="Name of the app to create", default="000-indexer-inputs"
        )
        parser.add_argument("--splunk-port", help="Port for splunktcp", default="9997")
        parser.add_argument("--ssl-port", help="Port for splunktcp-ssl", default="9998")

    @classmethod
    def args_post_process(cls, parser):
        pass

    def app_conf(self, name):
        app = [
            "# app.conf",
            "",
            "[id]",
            f"name = {name}",
            "version = 1.0.1",
            "",
            "[install]",
            "",
            "[launcher]",
            "author = Splunk Professional Services",
            "description = App to define default splunktcp-ssl input configuration",
            "version = 1.0.1",
            "",
            "[package]",
            "check_for_updates = 0",
            "",
            "[ui]",
            f"label = {name}",
            "",
        ]

        return "\n".join(app)

    def auth_dir(self):
        args = self.args
        app_name = args.name
        app_path = Path(args.outdir) / app_name
        app_auth = app_path / "auth"
        app_auth.mkdir(parents=True, exist_ok=True)
        with open(app_auth / "ssl-inputs.pem", "w") as f:
            f.write("This is a dummy file. replace with your actual cert file\n")

        with open(app_auth / "cacert.pem", "w") as f:
            f.write(
                "This is a dummy file. concat your actual CA cert\nto the file referenced in [sslConfig]/sslRootCAPath\n"
            )

    def server_conf(self):
        args = self.args
        app_name = args.name
        app_path = Path(args.outdir) / app_name
        app_default = app_path / "default"
        cert_path = app_path.relative_to(args.outdir) / "auth" / "cacert.pem"

        default = [
            f"# {app_name} server.conf",
            "",
            "[sslConfig]",
            f"# sslRootCAPath = $SPLUNK_ETC/apps/{cert_path}",
            "# For pushing from manager-apps",
            f"# sslRootCAPath = $SPLUNK_ETC/peer-apps/{cert_path}",
            "",
            "# The path to the certificate authority (CA), or root",
            "# certificate store.",
            "",
            "# The certificate store must be a file that contains one or more",
            "# CA certificates that have been concatenated together.",
            "",
            "# This setting expects a value that represents a file object,",
            "# not a directory object.",
            "",
            "# The certificates in the certificate store file must be",
            "# in privacy-enhanced mail (PEM) format.",
            "",
            "# If you run Splunk Enterprise in Common Criteria mode, then",
            "# you must give this setting a value.",
            "",
            "# This setting is valid on Windows machines only if the",
            "# 'sslRootCAPathHonoredOnWindows' has a value of \"true\".",
            "",
            "# No default.",
            "",
        ]

        with open(app_default / "server.conf", "w", encoding="utf-8") as f:
            f.write("\n".join(default))

    def inputs_conf(self):
        args = self.args
        app_name = args.name
        app_path = Path(args.outdir) / app_name
        cert_path = app_path.relative_to(args.outdir) / "auth" / "ssl-inputs.pem"

        default = [
            f"# {app_name} inputs.conf",
            "",
            f"[splunktcp-ssl://{args.ssl_port}]",
            f"serverCert = $SPLUNK_ETC/apps/{cert_path}",
            "# For pushing from manager-apps",
            f"# serverCert = $SPLUNK_ETC/peer-apps/{cert_path}",
            "compressed = false",
            "queueSize = 2MB",
            "",
        ]

        local = [
            f"# {app_name} inputs.conf",
            "",
            f"[splunktcp-ssl://{args.ssl_port}]",
            "# sslPassword = <string>",
            "",
        ]

        app_default = app_path / "default"
        app_default.mkdir(parents=True, exist_ok=True)

        app_local = app_path / "local"
        app_local.mkdir(parents=True, exist_ok=True)

        with open(app_default / "inputs.conf", "w", encoding="utf-8") as f:
            f.write("\n".join(default))
        with open(app_local / "inputs.conf", "w", encoding="utf-8") as f:
            f.write("\n".join(local))

    def run(self):
        args = self.args
        app_name = args.name
        app_path = Path(args.outdir) / app_name

        app_default = app_path / "default"
        app_default.mkdir(parents=True, exist_ok=True)

        with open(app_default / "app.conf", "w", encoding="utf-8") as f:
            f.write(self.app_conf(app_name))

        self.auth_dir()
        self.inputs_conf()
        self.server_conf()


# The following is required boilerplate
# DO NOT MODIFY
def cli():
    app = CreateSslInputsCliApp()
    try:
        app.run()
    finally:
        app.shutdown_logging()


if __name__ == "__main__":
    import sys

    sys.exit(cli())
