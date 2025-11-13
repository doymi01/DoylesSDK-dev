import shutil
import sys
import tempfile
from pathlib import Path

try:
    from importlib import metadata
except ImportError:
    import importlib_metadata as metadata

from doyles_sdk.cli.apps._base_app import DoyleApp

from . import register_cmd

width = 50
INDENT = " " * 4


def get_entrypoints(group: str):
    eps = metadata.entry_points()
    if hasattr(eps, "select"):  # Python 3.10+
        entries = eps.select(group=group)  # pyright: ignore[reportAttributeAccessIssue]
    else:  # Python 3.9 and earlier
        entries = eps.get(group, [])  # pyright: ignore[reportAttributeAccessIssue]

    for ep in entries:
        dist_name = getattr(getattr(ep, "dist", None), "name", None)
        yield (dist_name, ep)


@register_cmd
class Info(DoyleApp):
    """
    Provides diagnostic information useful for troubleshooting

    - package name and version
    - system information
    - installed scripts
    - python information

    """

    command_name = "info"

    def run(self):
        info = [
            "",
            "=" * width,
            f"Package: {self.__package__}",
            "=" * width,
            "",
            f"{INDENT}Version: {self.__version__}",
            f"{INDENT}Author:  {self.__author__}",
            f"{INDENT}Email:   {self.__email__}",
            f"{INDENT}License: {self.__license__}",
            "",
            "=" * width,
            "System Info:",
            "=" * width,
            "",
            f"{INDENT}Platform: {self.__platform__}",
            f"{INDENT}Python: {self.__python__}",
            f"{INDENT}Total Memory: {self.__mem_total__}",
            f"{INDENT}Available Memory: {self.__mem_avail__}",
            f"{INDENT}CPU Count: {self.__cpu_count__}",
            "",
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            usage = shutil.disk_usage(tmpdir)
            info.extend(
                [
                    f"{INDENT}Temp dir: {Path(tmpdir).parent}",
                    f"{INDENT * 2}Total: {usage.total / (1024**3):.2f} GB",
                    f"{INDENT * 2}Used: {usage.used / (1024**3):.2f} GB",
                    f"{INDENT * 2}Free: {usage.free / (1024**3):.2f} GB",
                    "",
                ]
            )

        if self.args.verbose:
            info.extend(
                [
                    "=" * width,
                    "Console Scripts:",
                    "=" * width,
                    "",
                    *[
                        f"{INDENT}{ep.name:.<20}{ep.value:.>20}"
                        for dn, ep in get_entrypoints("console_scripts")
                        if dn == self.__package__
                    ],
                    "",
                ]
            )
            dists = metadata.distributions()
            info.extend(["=" * width, "Python:", "=" * width, "", sys.executable, ""])

            for name, version in sorted(
                [(x.metadata["Name"], x.version) for x in dists],
                key=lambda x: x[0].lower(),
            ):
                # name = dist.metadata["Name"]
                # version = dist.version
                info.append(f"{INDENT}{name:.<35}{version:<35}")
            info.append("")

        info.extend(
            [
                "=" * width,
                f"END INFO: {self.__package__} {self.__version__}",
                "=" * width,
                "",
            ]
        )
        print("\n".join(info))
