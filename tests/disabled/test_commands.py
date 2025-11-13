import sys

import pytest

from doyles_sdk import cli


@pytest.mark.parametrize("prefix", ["doyles"])
def test_all_commands(prefix):
    for command in [
        x
        for x in cli.COMMAND_REGISTRY.keys()
        if x not in ["create_cli_app", "create_module"]
    ]:
        sys.argv = [prefix, command]
        assert cli.main() is None
