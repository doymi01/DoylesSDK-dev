from doyles_sdk.cli.apps._base_app import DoyleApp

from . import COMMAND_REGISTRY, register_cmd


@register_cmd
class HelpApp(DoyleApp):
    """Lists available commands and summary"""

    command_name = "help"
    mp_safe = False  # Allow multiprocessing
    thread_safe = False  # Allow threads

    def run(self):
        print("Available Commands:")
        print()
        for command_name, command_class in sorted(
            COMMAND_REGISTRY.items(), key=lambda x: x[0]
        ):
            # print()
            usage = command_class.get_usage()
            print(f"    {self.caller} {usage}")
            if self.args.verbose:
                print(f"    {'=' * 50}")
                if doc := command_class.__doc__:
                    for line in doc.split("\n"):
                        print(f"    {line}")
                print()
        print()
