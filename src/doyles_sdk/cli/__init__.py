import os
import sys

from .apps import COMMAND_REGISTRY


def get_command_class(name: str):
    cls = COMMAND_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown command: {name}")
    return cls


def main():
    command_name = os.path.basename(sys.argv[0])
    if len(sys.argv) < 2:
        print(f"Usage: {command_name} <command> [options...]")
        sys.exit(1)

    root, command, *args = sys.argv[0:]

    try:
        AppClass = get_command_class(command)
        sys.argv = [f"{root} {command}"] + args
    except ValueError:
        print(f"\n==> Unknown command '{command}' <==\n", file=sys.stderr)
        AppClass = get_command_class("help")
        sys.argv = [f"{root} {command}"]

    # sys.argv = [f"{root} {command}"] + args

    app = AppClass(caller=command_name)
    try:
        app.run()
    finally:
        app.shutdown_logging()
