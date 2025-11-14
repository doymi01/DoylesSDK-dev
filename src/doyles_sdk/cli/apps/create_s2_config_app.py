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
class CreateS2ConfigCliApp(DoyleApp):
    """Create a SmartStore configuration app"""

    command_name = "create_s2_config"
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
            "--name", help="Name of the app to create", default="000-s2-config"
        )

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
            "description = App to define default SmartStore configuration",
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

    def indexes_conf(self):
        args = self.args
        app_name = args.name
        app_path = Path(args.outdir) / app_name

        default = [
            "# SmartStore indexes.conf",
            "",
            "# hotlist_recency_seconds can be set per-index to allow certain",
            "# indexes to be protect buckets from eviction for longer than the default.",
            "# Only apply the setting to indexes that are critical and do not exceed the",
            "# amount of available disk cache.",
            "",
            "# For 30 days",
            "# hotlist_recency_seconds = 2592000",
            "",
            "[default]",
            "remotePath = volume:smartstore_vol/$_index_name",
            "homePath = $SPLUNK_DB/$_index_name/db",
            "coldPath = $SPLUNK_DB/$_index_name/colddb",
            "thawedPath = $SPLUNK_DB/$_index_name/thaweddb",
            "maxDataSize = 750",
            "",
            "[main]",
            "maxDataSize = 750",
            "",
            "[volume:smartstore_vol]",
            "storageType = remote",
            "",
            "remote.s3.sslVerifyServerCert = true",
            "remote.s3.sslVersions = tls1.2",
            "remote.s3.sslRootCAPath = /opt/splunk/etc/auth/aws_rootcert.pem",
            "remote.s3.cipherSuite = TLSv1+HIGH:TLSv1.2+HIGH:@STRENGTH",
            "remote.s3.ecdhCurves = prime256v1, secp384r1, secp521r1",
            "remote.s3.signature_version = v4",
            "",
        ]

        local = [
            "# SmartStore indexes.conf",
            "",
            "[volume:smartstore_vol]",
            "remote.s3.endpoint = https://s3.<<REGION>>.amazonaws.com",
            "path = s3://<<BUCKET_NAME>>/<<STACK_NAME>>/",
            "remote.s3.access_key = <<KEY>>",
            "remote.s3.secret_key = <<SECRET>>",
            "remote.s3.sslAltNameToCheck = s3.<<REGION>>.amazonaws.com",
            "remote.s3.kms.auth_region = <<REGION>>",
            "remote.s3.kms.key_id = <<KMS_KEY>>",
            "remote.s3.kms.sslAltNameToCheck = kms.<<REGION>>.amazonaws.com",
            "",
        ]

        app_default = app_path / "default"
        app_default.mkdir(parents=True, exist_ok=True)

        app_local = app_path / "local"
        app_local.mkdir(parents=True, exist_ok=True)

        with open(app_default / "indexes.conf", "w", encoding="utf-8") as f:
            f.write("\n".join(default))
        with open(app_local / "indexes.conf", "w", encoding="utf-8") as f:
            f.write("\n".join(local))

        return "\n".join(default), "\n".join(local)

    def server_conf(self):
        args = self.args
        app_name = args.name
        app_path = Path(args.outdir) / app_name

        server = [
            "# SmartStore server.conf",
            "",
            "[cachemanager]",
            "eviction_policy = lruk",
            "",
        ]

        app_default = app_path / "default"
        app_default.mkdir(parents=True, exist_ok=True)

        with open(app_default / "server.conf", "w", encoding="utf-8") as f:
            f.write("\n".join(server))

        return "\n".join(server)

    def run(self):
        args = self.args
        app_name = args.name
        app_path = Path(args.outdir) / app_name

        app_default = app_path / "default"
        app_default.mkdir(parents=True, exist_ok=True)

        with open(app_default / "app.conf", "w", encoding="utf-8") as f:
            f.write(self.app_conf(app_name))

        self.indexes_conf()
        self.server_conf()


# The following is required boilerplate
# DO NOT MODIFY
def cli():
    app = CreateS2ConfigCliApp()
    try:
        app.run()
    finally:
        app.shutdown_logging()


if __name__ == "__main__":
    import sys

    sys.exit(cli())
