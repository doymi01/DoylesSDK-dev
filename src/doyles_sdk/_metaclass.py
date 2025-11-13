from __future__ import annotations

from abc import ABCMeta


class InfoMeta(ABCMeta):
    """METACLASS: Adds critical variables to each class namespace"""

    from . import __package__

    INJECTED_ATTRIBUTES = [
        "__package__",
        "__author__",
        "__email__",
        "__license__",
        "__python__",
        "__platform__",
        "__system__",
        "__machine__",
        "__release__",
        "__mem_total__",
        "__mem_avail__",
        "__cpu_count__",
        "__version__",
    ]

    def __new__(mcls, name, bases, namespace, **kwargs):
        import importlib
        import platform
        import math
        import psutil
        from importlib.metadata import PackageNotFoundError, version

        # derive the actual package of the defining module
        module_name = namespace.get("__module__")

        if module_name == "__main__":
            # Running as a standalone template script
            pkg_name = "doyles_sdk"
        else:
            module = importlib.import_module(module_name)
            pkg_name = (
                getattr(module, "__package__", module_name) or module_name
            ).split(".")[0]

        namespace.setdefault("__package__", pkg_name)
        namespace.setdefault("__author__", "Michael Doyle")
        namespace.setdefault("__email__", "doymi01@gmail.com")
        namespace.setdefault("__license__", "MIT")
        namespace.setdefault("__python__", platform.python_version())
        namespace.setdefault(
            "__platform__", platform.platform(aliased=True, terse=True)
        )
        namespace.setdefault("__system__", platform.system())
        namespace.setdefault("__machine__", platform.machine())
        namespace.setdefault("__release__", platform.release())
        __memory = psutil.virtual_memory()
        namespace.setdefault(
            "__mem_total__", f"{math.floor(__memory.total / 1024 / 1024 / 1000)} GB"
        )
        namespace.setdefault(
            "__mem_avail__", f"{math.floor(__memory.available / 1024 / 1024 / 1000)} GB"
        )
        namespace.setdefault("__cpu_count__", psutil.cpu_count())

        try:
            namespace["__version__"] = version(pkg_name)
        except PackageNotFoundError:
            namespace["__version__"] = "UnknownVersion"
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        # force module to where it was defined
        if "__module__" in namespace:
            cls.__module__ = namespace["__module__"]

        return cls
