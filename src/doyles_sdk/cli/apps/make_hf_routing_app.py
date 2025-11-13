import argparse  # noqa: F401
import csv  # noqa: F401
import json  # noqa: F401
import logging
import os  # noqa: F401
import re
import tarfile
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
class MakeHfRoutingCliApp(DoyleApp):
    """
    Creates the selective routing app for data cloning

    Creates the A00-
    """

    command_name = "make_hf_routing"
    mp_safe = False  # Allow multiprocessing
    thread_safe = False  # Allow threads

    @classmethod
    def add_arguments(cls, parser):
        """ """
        parser.add_argument(
            "outdir",
            metavar="OUT_DIR",
            help="Output Directory",
            nargs="?",
            default=os.getcwd(),
        )
        parser.add_argument(
            "--onprem", help="Name of the existing output group", default="idxcluster"
        )

        parser.add_argument(
            "--uf-package",
            help="Path to the splunkclouduf.spl file",
        )
        parser.add_argument(
            "--splunkcloud",
            help="Name of the splunkcloud output group",
            default="splunkcloud",
        )
        parser.add_argument(
            "--prefix",
            help="Variable prefis for the added fields",
            default="md",
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

    def import_tarfile(self):
        args = self.args
        relative_path = "default/outputs.conf"
        if args.uf_package:
            with tarfile.open(args.uf_package, "r:*") as tar:
                # find member whose path ends with your relative path
                member = next(
                    (m for m in tar.getmembers() if m.name.endswith(relative_path)),
                    None,
                )
                if member is None:
                    raise FileNotFoundError(
                        f"No file ending with '{relative_path}' found in {args.uf_package}"
                    )

                # extract to memory
                file_obj = tar.extractfile(member)
                if file_obj is None:
                    raise ValueError(f"Failed to extract '{member.name}'")

                # read as text
                contents = file_obj.read().decode("utf-8")

            return re.search(
                r"^defaultGroup\s*=\s*(\S+)",
                contents,
                flags=re.MULTILINE,
            )

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
            "description = App prepared by The Magic Script for Splunk Cloud migration",
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

    def meta_tagging(self, prefix: str):
        """Creates the _meta_tagging app"""

        app_name = "_meta_tagging"

        app = self.app_conf(app_name)
        props = [
            "# props.conf",
            "",
            "# for all sources",
            "[source::...]",
            "RULESET-0__set_meta = preserve_original, add_meta_tags",
            "RULESET-1__add_forwarder_name = add_forwarder_name",
            "",
        ]

        transforms = [
            "# transforms.conf",
            "",
            "[add_forwarder_name]",
            f"INGEST_EVAL = {prefix}_parsed_by=splunk_server",
            "",
            "[add_meta_tags]",
            f'INGEST_EVAL = {prefix}_origin:=coalesce({prefix}_origin, "ON_PREM")',
            "",
            "[preserve_original]",
            f"INGEST_EVAL = $field:{prefix}_orig_source$:=coalesce( {prefix}_orig_source, source ), $field:{prefix}_orig_sourcetype$:=coalesce( {prefix}_orig_sourcetype, sourcetype ), $field:{prefix}_orig_host$:=coalesce( {prefix}_orig_host, host ), $field:{prefix}_orig_index$:=coalesce( {prefix}_orig_index, index )",
            "",
        ]

        app_path = Path(self.args.outdir) / app_name
        app_default = app_path / "default"
        app_default.mkdir(parents=True, exist_ok=True)
        with open(app_default / "app.conf", "w") as f:
            f.write(app)
        with open(app_default / "props.conf", "w") as f:
            f.write("\n".join(props))
        with open(app_default / "transforms.conf", "w") as f:
            f.write("\n".join(transforms))

        return app, "\n".join(props), "\n".join(transforms)

    def intermediate_base(
        self, cloud: str, classic: bool = False, private_link: bool = False
    ):
        """Build _intermediate_base app"""

        app_name = "_intermediate_base"
        app = self.app_conf(app_name)
        inputs = [
            "# inputs.conf",
            "",
            "[splunktcp://9997]",
            "compressed = true",
            "queueSize = 2MB",
            "",
        ]

        outputs = [
            "[tcpout]",
            "# 10MB",
            "# when using autoLBVolume on a Universal Forwarder you must",
            "# ensure that EVENT_BREAKERS are defined and enabled for all",
            "# sourcetypes that will pass through the forwarder.",
            "autoLBVolume = 10485760",
            "forceTimebasedAutoLB = false",
            "connectionTTL = 300",
            "maxQueueSize = 10MB",
            "connectionsPerTarget = 300",
            "heartbeatFrequency = 10",
            "",
        ]

        if not classic:
            outputs.extend(
                [
                    f"[tcpout:{cloud}]",
                    "# if your stack uses NLB (aws Victoria)",
                    "#### ONLY ON INTERMEDIATES NOT SOURCE UF #########",
                    "dnsResolutionInterval = 300000000",
                    "",
                ]
            )

        if private_link:
            outputs.extend(
                [
                    "[tcpout:splunkcloud_pvt]",
                    "# for aws privatelink",
                    "#### ONLY ON INTERMEDIATES NOT SOURCE UF #########",
                    "dnsResolutionInterval = 300000000",
                    "",
                ]
            )

        server = [
            "# server.conf",
            "",
            "[general]",
            "# A value between 8 and 12 is optimal",
            "# for a **Universal** Intermediate Forwarder",
            "# with 4 or more vCPUs",
            "parallelIngestionPipelines = 8",
            "",
        ]

        limits = ["# limits.conf", "", "[thruput]", "maxKBps = 0", ""]

        app_path = Path(self.args.outdir) / app_name

        app_default = app_path / "default"
        app_default.mkdir(parents=True, exist_ok=True)

        app_local = app_path / "local"
        app_local.mkdir(parents=True, exist_ok=True)

        with open(app_default / "app.conf", "w") as f:
            f.write(app)
        with open(app_default / "inputs.conf", "w") as f:
            f.write("\n".join(inputs))
        with open(app_local / "outputs.conf", "w") as f:
            f.write("\n".join(outputs))
        with open(app_local / "server.conf", "w") as f:
            f.write("\n".join(server))
        with open(app_local / "limits.conf", "w") as f:
            f.write("\n".join(limits))

        return app, "\n".join(inputs), "\n".join(outputs), "\n".join(server)

    def selective_routing(self, onprem: str, cloud: str):
        """Build selective routing app"""

        app_name = "_selective_routing"
        app = self.app_conf(app_name)
        props = [
            "# props.conf",
            "",
            "# for all sources",
            "[source::...]",
            "RULESET-z_set_routing = routing_rules",
            "",
        ]

        transforms = [
            "# transforms.conf",
            "",
            "# Use this for testing",
            "# This will set the routing for indexes that start with underscore",
            "# to clone to both on-premises and Splunk Cloud indexers",
            "# All other events will be routed exclusively on-premises",
            "",
            "[routing_rules]",
            f'INGEST_EVAL = _TCP_ROUTING=if(match(lower(index), "^(?:_)"), "{onprem}, {cloud}", "{onprem}")',
            "",
        ]

        outputs = [
            "# outputs.conf",
            "",
            "[tcpout]",
            "# if cloning data (dual feed)",
            "# uncomment the lines below",
            "# dropClonedEventsOnQueueFull = -1",
            "",
        ]

        app_path = Path(self.args.outdir) / app_name
        app_default = app_path / "default"
        app_default.mkdir(parents=True, exist_ok=True)
        with open(app_default / "app.conf", "w") as f:
            f.write(app)
        with open(app_default / "props.conf", "w") as f:
            f.write("\n".join(props))
        with open(app_default / "transforms.conf", "w") as f:
            f.write("\n".join(transforms))
        with open(app_default / "outputs.conf", "w") as f:
            f.write("\n".join(outputs))

        return app, "\n".join(props), "\n".join(transforms), "\n".join(outputs)

    def cloud_app(self, prefix: str = "md"):
        """Build cloud A00-METADATA app"""

        app_name = "A00-META_TAGGING"

        app = self.app_conf(app_name)
        props = [
            "# props.conf",
            "",
            "# for all sources",
            "[source::...]",
            "RULESET-0__set_meta = preserve_original, add_meta_tags",
            "RULESET-1__add_forwarder_name = add_forwarder_name",
            "",
        ]

        transforms = [
            "# transforms.conf",
            "",
            "[add_forwarder_name]",
            f"INGEST_EVAL = {prefix}_parsed_by=splunk_server",
            "",
            "[add_meta_tags]",
            f"""INGEST_EVAL = {prefix}_origin:=coalesce('{prefix}_origin', if(match(lower(host), "splunkcloud(?:gc|fed)?\\.com$"), "SPLUNK_CLOUD_PLATFORM", "UNKNOWN"))""",
            "",
            "[preserve_original]",
            f"INGEST_EVAL = $field:{prefix}_orig_source$:=coalesce( {prefix}_orig_source, source ), $field:{prefix}_orig_sourcetype$:=coalesce( {prefix}_orig_sourcetype, sourcetype ), $field:{prefix}_orig_host$:=coalesce( {prefix}_orig_host, host ), $field:{prefix}_orig_index$:=coalesce( {prefix}_orig_index, index )",
            "",
        ]

        fields = [
            "# fields.conf",
            "",
            f"[{prefix}_origin]",
            "INDEXED = 1",
            "",
            f"[{prefix}_parsed_by]",
            "INDEXED = 1",
            "",
            f"[{prefix}_orig_source]",
            "INDEXED = 1",
            "",
            f"[{prefix}_orig_sourcetype]",
            "INDEXED = 1",
            "",
            f"[{prefix}_orig_host]",
            "INDEXED = 1",
            "",
            f"[{prefix}_orig_index]",
            "INDEXED = 1",
            "",
        ]

        app_path = Path(self.args.outdir) / app_name
        app_default = app_path / "default"
        app_default.mkdir(parents=True, exist_ok=True)
        with open(app_default / "app.conf", "w") as f:
            f.write(app)
        with open(app_default / "props.conf", "w") as f:
            f.write("\n".join(props))
        with open(app_default / "transforms.conf", "w") as f:
            f.write("\n".join(transforms))
        with open(app_default / "fields.conf", "w") as f:
            f.write("\n".join(fields))

        return app, "\n".join(props), "\n".join(transforms)

    def run(self):
        """
        # Main application logic.
        """
        args = self.args
        tcpout = self.import_tarfile()
        if tcpout:
            args.splunkcloud = tcpout.group(1)

        app, props, transforms, outputs = self.selective_routing(
            args.onprem, args.splunkcloud
        )
        print(app)
        print(props)
        print(transforms)
        print(outputs)

        app, props, transforms = self.meta_tagging(prefix=args.prefix)
        print(app)
        print(props)
        print(transforms)

        app, inputs, outputs, server = self.intermediate_base(args.splunkcloud)
        print(app)
        print(inputs)
        print(outputs)
        print(server)

        self.cloud_app(prefix=args.prefix)


# The following is required boilerplate
# DO NOT MODIFY
def cli():
    app = MakeHfRoutingCliApp()
    try:
        app.run()
    finally:
        app.shutdown_logging()


if __name__ == "__main__":
    import sys

    sys.exit(cli())
