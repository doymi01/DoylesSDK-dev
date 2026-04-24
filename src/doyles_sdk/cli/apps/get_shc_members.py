import argparse  # noqa: F401
import csv  # noqa: F401
import json  # noqa: F401
import logging
import os  # noqa: F401
import time  # noqa: F401
from datetime import datetime, timedelta  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import TYPE_CHECKING, Any, Dict, List, Union  # noqa: F401

import dns.resolver

# from doyles_sdk._classes import Doyles, SplunkSession
from doyles_sdk._wrappers import inject_session, token_var
from doyles_sdk.cli.apps._base_app import DoyleApp

from . import register_cmd

if TYPE_CHECKING:
    logger: logging.Logger  # just for type checkers

# if you need an API session to a Splunk instance
# or any access that requires retry and connection pooling
# uncomment the following lines

# from doyles_sdk._wrappers import SplunkSession

# _token = None
# session = SplunkSession(token=_token)

# _token = None


@register_cmd
class GetIpList(DoyleApp):
    """
    Return the list of external IP addresses for a given SHC.

    This requires REST API access to the stack and an authentication token.

    """

    command_name = "get_ip_list"

    @classmethod
    def add_arguments(cls, parser):
        parser.description = "Return the list of external IP addresses for a given SHC. This requires REST API access to the stack and an authentication token."
        parser.add_argument(
            "fqdn",
            help="The FQDN of the target shc (e.g. mystack.splunkcloud.com or es.mystack.splunkcloud.com)",
        )

    @inject_session
    def run(self):
        ip_v4 = set()
        ip_v6 = set()
        try:
            _root = dns.resolver.resolve(self.args.fqdn, "A")
        except dns.resolver.NXDOMAIN:
            raise SystemExit(f"{self.args.fqdn} does not exist")

        # retrieves token from keyring or env or prompts once
        # token = self.secrets.get_secret("api_token", prompt="Enter API token: ")

        # create your session with that token
        # session = SplunkSession(token=token)
        # worker-safe session injection could also use this token

        self.session.set_token(input("Enter token: "))
        response = self.session.get(
            f"https://{self.args.fqdn}:8089/services/shcluster/status",
            data={"output_mode": "json"},
        )
        if response.status_code == 200:
            if entries := response.json().get("entry"):
                for entry in entries:
                    self.logger.info("Discovered %d members", len(entry))
                    for shc_member, data in entry["content"]["peers"].items():
                        name = data["label"]
                        ip_v4.update(
                            [
                                (self.args.fqdn, x.address)
                                for x in dns.resolver.resolve(name, "A")
                            ]
                        )
                        # ip_v6.update([x.address for x in dns.resolver.resolve(data['label'], 'AAAA')])

                for idx, item in enumerate(ip_v4):
                    print(f"{idx + 1}: {', '.join(item)}")
            else:
                self.logger.warning(f"{self.args.fqdn} is not a SHC")
                print((self.args.fqdn, _root[0].address))
        elif response.status_code == 401:
            self.logger.error("Invalid Token")
        elif response.status_code == 403:
            self.logger.error("REST Endpoint not accessible. Check the allow list.")


def cli():
    app = GetIpList()
    try:
        app.run()
    finally:
        app.shutdown_logging()


if __name__ == "__main__":
    import sys

    sys.exit(cli())
