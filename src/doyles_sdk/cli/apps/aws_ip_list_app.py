import logging
from typing import TYPE_CHECKING

from doyles_sdk.cli.apps._base_app import DoyleApp

from . import register_cmd

if TYPE_CHECKING:
    logger: logging.Logger  # just for type checkers

# if you need an API session to a Splunk instance
# or any access that requires retry and connection pooling
# uncomment the following lines
from doyles_sdk._wrappers import SplunkSession

_token = None
session = SplunkSession(token=_token)


@register_cmd
class AwsIpListApp(DoyleApp):
    """
    Create Filtered IP list for amazon services

    Usage:

        doyles aws_ip_list [--region AWS_REGION] [--service AWS_SERVICE]

    Features:
        - Returns a complete or filtered list of aws ip addresses by region and service
    """

    command_name = "aws_ip_list"
    mp_safe = False  # Allow multiprocessing
    thread_safe = False  # Allow threads

    @classmethod
    def add_arguments(cls, parser):
        """
        # Add your custom CLI arguments here.

        The following arguments are **already defined by the base parser**
        and should NOT be redefined here:

        --help
        --debug
        --verbose
        --log-dir
        --prog
        --version
        --log-level

        **Example:**
            parser.add_argument("--example", help="Example argument", default="value")
        """
        parser.add_argument(
            "--region",
            metavar="AWS_REGION",
            action="append",
            help="The specific AWS Region",
            choices=[
                "GLOBAL",
                "af-south-1",
                "ap-east-1",
                "ap-east-2",
                "ap-northeast-1",
                "ap-northeast-2",
                "ap-northeast-3",
                "ap-south-1",
                "ap-south-2",
                "ap-southeast-1",
                "ap-southeast-2",
                "ap-southeast-3",
                "ap-southeast-4",
                "ap-southeast-5",
                "ap-southeast-6",
                "ap-southeast-7",
                "ca-central-1",
                "ca-west-1",
                "cn-north-1",
                "cn-northwest-1",
                "eu-central-1",
                "eu-central-2",
                "eu-north-1",
                "eu-south-1",
                "eu-south-2",
                "eu-west-1",
                "eu-west-2",
                "eu-west-3",
                "eusc-de-east-1",
                "il-central-1",
                "me-central-1",
                "me-south-1",
                "me-west-1",
                "mx-central-1",
                "sa-east-1",
                "us-east-1",
                "us-east-2",
                "us-gov-east-1",
                "us-gov-west-1",
                "us-west-1",
                "us-west-2",
            ],
        )
        parser.add_argument(
            "--service",
            metavar="AWS_SERVICE",
            choices=[
                "AMAZON",
                "AMAZON_APPFLOW",
                "AMAZON_CONNECT",
                "API_GATEWAY",
                "CHIME_MEETINGS",
                "CHIME_VOICECONNECTOR",
                "CLOUD9",
                "CLOUDFRONT",
                "CLOUDFRONT_ORIGIN_FACING",
                "CODEBUILD",
                "DYNAMODB",
                "EBS",
                "EC2",
                "EC2_INSTANCE_CONNECT",
                "GLOBALACCELERATOR",
                "IVS_REALTIME",
                "KINESIS_VIDEO_STREAMS",
                "MEDIA_PACKAGE_V2",
                "ROUTE53",
                "ROUTE53_HEALTHCHECKS",
                "ROUTE53_HEALTHCHECKS_PUBLISHING",
                "ROUTE53_RESOLVER",
                "S3",
                "WORKSPACES_GATEWAYS",
            ],
            help="The specific AWS service name",
            action="append",
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
        jsonResp = session.get(arg)
        jsonResp.raise_for_status()

        return jsonResp.json()

    def run(self):
        """
        # Main application logic.
        Prefer delegating to do_* methods for consitent behavior using any execution method.

        The following are available:

            - self.logger
            - self.args
        """
        args_list = ["https://ip-ranges.amazonaws.com/ip-ranges.json"]
        results = self.run_with_workers(self.do_example_task, args_list)

        if results:
            ranges = results[0]
        else:
            return

        if self.args.service:
            ranges["prefixes"] = [
                x for x in ranges["prefixes"] if x["service"] in self.args.service
            ]
            ranges["ipv6_prefixes"] = [
                x for x in ranges["ipv6_prefixes"] if x["service"] in self.args.service
            ]

        if self.args.region:
            ranges["prefixes"] = [
                x for x in ranges["prefixes"] if x["region"] in self.args.region
            ]
            ranges["ipv6_prefixes"] = [
                x for x in ranges["ipv6_prefixes"] if x["region"] in self.args.region
            ]

        # return [{'service': x['service'], 'region': x['region'], 'prefix': (lambda x: x['ip_prefix'] if 'ip_prefix' in x else x['ipv6_prefix'])(x)} for x in sorted(ranges['prefixes'] + ranges['ipv6_prefixes'], key=lambda x: (x['service'], x['region']))]
        print(
            "\n".join(
                [
                    ",".join(
                        [
                            x["service"],
                            x["region"],
                            (
                                lambda x: x["ip_prefix"]
                                if "ip_prefix" in x
                                else x["ipv6_prefix"]
                            )(x),
                        ]
                    )
                    for x in sorted(
                        ranges["prefixes"] + ranges["ipv6_prefixes"],
                        key=lambda x: (x["service"], x["region"]),
                    )
                ]
            )
        )


# The following is required boilerplate
# DO NOT MODIFY
def cli():
    app = AwsIpListApp()
    try:
        app.run()
    finally:
        app.shutdown_logging()


if __name__ == "__main__":
    import sys

    sys.exit(cli())
