from pathlib import Path
import importlib
import pkgutil

# Module-local registry for this folder
COMMAND_REGISTRY = {}


# Decorator to register commands
def register_cmd(cls):
    name = getattr(cls, "command_name", cls.__name__.lower())
    COMMAND_REGISTRY[name] = cls
    return cls


# Dynamically import all modules in this folder
package_name = __name__
package_path = Path(__file__).parent

for _, module_name, is_pkg in pkgutil.iter_modules([str(package_path)]):
    if not is_pkg and not module_name.startswith("_"):
        importlib.import_module(f"{package_name}.{module_name}")

# Optionally expose __all__
__all__ = ["COMMAND_REGISTRY", "register_cmd"]
