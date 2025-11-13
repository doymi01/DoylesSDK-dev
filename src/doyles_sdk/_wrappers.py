import inspect
from contextvars import ContextVar
from functools import wraps

from doyles_sdk._classes import SplunkSession

# from doyles_sdk._context_vars import token_var
token_var = ContextVar("token", default=None)


def inject_session(obj):
    """
    Decorator to inject a SplunkSession instance:
    - Free function → sets `session` in globals
    - Bound method → sets `self.session`
    - Class → patches `__init__` to create `self.session`
    """
    if inspect.isclass(obj):
        return _decorate_class(obj)
    elif inspect.isfunction(obj):
        return _decorate_function(obj)
    else:
        raise TypeError(f"@inject_session cannot be applied to {obj!r}")


def _decorate_function(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Detect bound method by checking if first arg looks like `self`
        if args and hasattr(args[0], "__class__"):
            self = args[0]
            if not hasattr(self, "session"):
                self.session = SplunkSession(token=token_var.get())
        else:
            # Free function
            func_globals = func.__globals__
            if "session" not in func_globals:
                func_globals["session"] = SplunkSession(token=token_var.get())
        return func(*args, **kwargs)

    return wrapper


def _decorate_class(cls):
    orig_init = cls.__init__

    @wraps(orig_init)
    def __init__(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        if not hasattr(self, "session"):
            self.session = SplunkSession(token=token_var.get)

    cls.__init__ = __init__
    return cls
