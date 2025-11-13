from __future__ import annotations

import asyncio
import inspect
import threading
from typing import Tuple


class PickleMixin:
    """Generic pickle-safe mixin.

    Expects subclasses to optionally define `_exclude_from_pickle`
    as an iterable of attribute names to remove from instance state.
    """

    _exclude_from_pickle: Tuple[str, ...] = ()

    def __getstate__(self):
        # allow cooperative MRO: call super if it defines __getstate__, else copy __dict__
        state = (
            super().__getstate__()
            if hasattr(super(), "__getstate__")
            else self.__dict__.copy()
        )
        for attr in getattr(self, "_exclude_from_pickle", ()):
            state.pop(attr, None)
        return state

    def __setstate__(self, state):
        # allow cooperative MRO: call super then update state
        if hasattr(super(), "__setstate__"):
            super().__setstate__(state)
        else:
            self.__dict__.update(state)


class SingletonMixin(PickleMixin):
    """Singleton mixin with lazy, pickle-safe locks.

    Inherits PickleMixin so singleton-specific excluded attrs are declared
    on the class and the generic pickling logic handles removal.
    """

    _instances = {}

    # declare singleton lock names to be excluded from pickling
    _exclude_from_pickle = ("_thread_lock", "_async_lock")

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instances:
            lock = cls._get_thread_lock()
            with lock:
                if cls not in cls._instances:
                    inst = super().__new__(cls)
                    cls._instances[cls] = inst
        return cls._instances[cls]

    # --------- lazy lock accessors (class-level) ----------
    @classmethod
    def _get_thread_lock(cls) -> threading.Lock:
        # create lazily and allow pickling to remove it (we set to None on unpickle)
        if not hasattr(cls, "_thread_lock") or cls._thread_lock is None:
            cls._thread_lock = threading.Lock()
        return cls._thread_lock

    @classmethod
    def _get_async_lock(cls) -> asyncio.Lock:
        if not hasattr(cls, "_async_lock") or cls._async_lock is None:
            cls._async_lock = asyncio.Lock()
        return cls._async_lock

    # --------- initialization helpers ----------
    async def _maybe_await(self, func, *args, **kwargs):
        result = func(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def initialize(self, *args, **kwargs):
        if getattr(self, "_initialized", False):
            return

        async_lock = self._get_async_lock()
        async with async_lock:
            if getattr(self, "_initialized", False):
                return

            init_method = getattr(self, "_init_once", None)
            if init_method:
                await self._maybe_await(init_method, *args, **kwargs)

            self._initialized = True

    # --------- pickling behavior ----------
    # We rely on PickleMixin.__getstate__ to remove _thread_lock and _async_lock,
    # because they are declared in _exclude_from_pickle above.

    def __setstate__(self, state):
        # Let PickleMixin (via cooperative MRO) do its updates first.
        super().__setstate__(state)
        # Ensure class-level locks will be recreated lazily when needed.
        # Setting them to None ensures _get_*_lock will recreate them.
        self.__class__._thread_lock = None
        self.__class__._async_lock = None


# class PickleMixin:
#     parent: Any  # this is only needed in code

#     def __json__(self):
#         state = self.__getstate__()  # use your pickle mixin to flatten
#         if "parent" in state:
#             state.pop("parent")  # remove the circular reference
#         return Doyles._str_keys(state)

#     def __getstate__(self):
#         def convert(value):
#             # Handle lxml objects
#             if isinstance(value, ET._ElementTree):
#                 return {"__lxml_etree__": True, "xml": ET.tostring(value.getroot())}
#             elif isinstance(value, ET._Element):
#                 return {"__lxml_element__": True, "xml": ET.tostring(value)}
#             # Handle containers recursively
#             elif isinstance(value, dict):
#                 return {k: convert(v) for k, v in value.items()}
#             elif isinstance(value, (list, tuple, set)):
#                 t = type(value)
#                 return t(convert(v) for v in value)
#             return value

#         state = self.__dict__.copy()

#         # Set ephemeral attributes to None instead of removing
#         for attr in ("logger", "_app", "_meta", "_thread_lock", "_mp_lock"):
#             if attr in state:
#                 state[attr] = None
#             # state.pop(attr, None)
#         return {k: convert(v) for k, v in state.items()}

#     def __setstate__(self, state):
#         def restore(value):
#             if isinstance(value, dict):
#                 if value.get("__lxml_etree__"):
#                     return ET.ElementTree(ET.fromstring(value["xml"]))
#                 elif value.get("__lxml_element__"):
#                     return ET.fromstring(value["xml"])
#                 else:
#                     return {k: restore(v) for k, v in value.items()}
#             elif isinstance(value, (list, tuple, set)):
#                 t = type(value)
#                 return t(restore(v) for v in value)
#             return value

#         self.__dict__.update({k: restore(v) for k, v in state.items()})

#         # Only recreate ephemeral attributes if they existed
#         if getattr(self, "logger", None) is None:
#             self.logger = logging.getLogger(self.__class__.__name__)

#         if getattr(self, "_thread_lock", None) is None:
#             import threading

#             self._thread_lock = threading.Lock()

#         if getattr(self, "_mp_lock", None) is None:
#             self._mp_lock_present = "_mp_lock" in state
#             # NOT IMPLEMENTED
#             self._mp_lock = None  # lazy creation handled via property
