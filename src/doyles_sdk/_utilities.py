from __future__ import annotations

import getpass
import logging
import os
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import fields, is_dataclass
from fnmatch import fnmatch
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Union,
    get_args,
    get_origin,
)
from urllib.parse import quote, unquote

import chardet

from doyles_sdk._metaclass import InfoMeta
from doyles_sdk._mixins import SingletonMixin

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

logger = logging.getLogger(__name__)


class NoOp(SingletonMixin):
    """A singleton no-op callable."""

    __slots__ = ()

    def __call__(self, *args, **kwargs):
        pass

    def __repr__(self):
        return "<NoOp>"

    def __hash__(self):
        return id(self)


class Doyles(SingletonMixin, metaclass=InfoMeta):
    """Collection of common utilities"""

    __slots__ = ()
    noop = NoOp()

    @staticmethod
    def dataclass_from_dict(
        t_cls: Union[DataclassInstance, type[DataclassInstance]], data
    ):
        if data is None:
            return None

        if not is_dataclass(t_cls):
            return data

        kwargs = {}

        for f in fields(t_cls):
            field_value = data.get(f.name)
            field_type = f.type
            origin = get_origin(field_type)

            if field_value is None:
                kwargs[f.name] = None
                continue

            if origin is Union:
                args = get_args(field_type)
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1:
                    field_type = non_none[0]
                    origin = get_origin(field_type)

            if is_dataclass(field_type):
                kwargs[f.name] = Doyles.dataclass_from_dict(field_type, field_value)
                continue

            if origin is list:
                item_type = get_args(field_type)[0]
                if is_dataclass(item_type):
                    kwargs[f.name] = [
                        Doyles.dataclass_from_dict(item_type, i) for i in field_value
                    ]
                else:
                    kwargs[f.name] = list(field_value)
                continue

            if origin is dict:
                key_t, val_t = get_args(field_type)
                if is_dataclass(val_t):
                    kwargs[f.name] = {
                        k: Doyles.dataclass_from_dict(val_t, v)
                        for k, v in field_value.items()
                    }
                else:
                    kwargs[f.name] = dict(field_value)
                continue

            kwargs[f.name] = field_value

        ctor = t_cls if isinstance(t_cls, type) else type(t_cls)
        return ctor(**kwargs)

    @staticmethod
    def flatten_dict(
        d: Dict[str, Any],
        parent_key: str = "",
        sep: str = ".",
        skip_keys: Union[List[str], None] = None,
    ):
        """Flatten a nested dictionary into a single-level dict with joined keys.

        Args:
            d (dict): Dictionary to flatten.
            parent_key (str): Prefix for nested keys.
            sep (str): Separator between keys.
            skip_keys (list): List of exact keys or glob patterns to skip.

        Returns:
            dict: Flattened dictionary.
        """
        skip_keys = skip_keys or []
        items = {}

        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k

            # Skip if new_key matches any pattern
            if any(fnmatch(new_key, pattern) for pattern in skip_keys):
                continue

            if isinstance(v, dict):
                items.update(
                    Doyles.flatten_dict(v, new_key, sep=sep, skip_keys=skip_keys)
                )
            elif isinstance(v, list):
                if all(isinstance(elem, dict) for elem in v):
                    # Flatten list of dicts with index
                    for i, elem in enumerate(v):
                        indexed_key = f"{new_key}{sep}{i}"
                        items.update(
                            Doyles.flatten_dict(
                                elem, indexed_key, sep=sep, skip_keys=skip_keys
                            )
                        )
                else:
                    # Flatten list of scalars as semicolon string
                    items[new_key] = ";".join(map(str, v)) if v else ""
            else:
                items[new_key] = v

        return items

    @staticmethod
    def guard_exit_call(func, *args, **kwargs):
        """Wraps a function call and catches SystemExit to prevent premature termination.

        Primarily used when invoking Python CLI entry points that call sys.exit()
        so the main program can continue running normally."""

        try:
            return func(*args, **kwargs)
        except SystemExit as e:
            logger.debug(f"Function tried to exit with code {e.code}, ignoring.")
            return e.code

    @staticmethod
    def get_login() -> tuple[str, str]:
        """
        Prompts user for username and password.

        Returns:
            tuple[str, str]: Username and password.
        """
        username = input("Enter your username: ")
        password = getpass.getpass("Enter your password: ")

        return username, password

    @staticmethod
    def keys_to_str(obj: Union[str, Iterable]):
        """Function to recursively convert iterable keys to strings"""
        if isinstance(obj, dict):
            return {str(k): Doyles.keys_to_str(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [Doyles.keys_to_str(v) for v in obj]
        else:
            return obj

    @staticmethod
    def nullif(source: Any, match: Any) -> Optional[Any]:
        """
        Returns None if source equals match, otherwise returns source.

        Args:
            source (Any): The source object.
            match (Any): The object to compare against.

        Returns:
            Optional[Any]: None if source == match, else source.
        """
        if source == match:
            return None
        else:
            return source

    @staticmethod
    def pretty_dict(obj, level: int = 0) -> str:
        """
        Recursively pretty-prints a Python object using JSON-like formatting,
        tolerating non-serializable types.
        """
        indent = "    " * level
        next_indent = "    " * (level + 1)

        if isinstance(obj, dict):
            if not obj:
                return "{}"
            items = []
            for k, v in obj.items():
                items.append(f'{next_indent}"{k}": {Doyles.pretty_dict(v, level + 1)}')
            return "{\n" + ",\n".join(items) + f"\n{indent}}}"
        elif isinstance(obj, (list, tuple, set)):
            open_b, close_b = ("[", "]") if isinstance(obj, list) else ("(", ")")
            if not obj:
                return f"{open_b}{close_b}"
            items = [Doyles.pretty_dict(v, level + 1) for v in obj]
            return (
                f"{open_b}\n"
                + ",\n".join(f"{next_indent}{i}" for i in items)
                + f"\n{indent}{close_b}"
            )
        elif isinstance(obj, str):
            return f'"{obj}"'
        else:
            return repr(obj)

    @staticmethod
    def read_file_encoding_unknown(
        filename: Union[str, os.PathLike], max_bytes: Optional[int] = None
    ) -> str:
        """
        Reads a text file with unknown or inconsistent encoding.
        Tries UTF-8 first, then chardet detection, then cp1252 as a fallback.
        Always includes the filename in any decode error.


        Args:
            filename (Union[str, os.PathLike]): Path to the file.

        Returns:
            str: Decoded file contents.
        """

        with open(filename, "rb") as f:
            raw_data = f.read(max_bytes)

        # Attempt 1: UTF-8
        try:
            data = raw_data.decode("utf-8-sig").lstrip("\ufeff")
            logger.info("%s decoded as utf-8", filename)
            return data
        except UnicodeDecodeError as e:
            logger.info("%s: %s attempting character set detection", e.reason, filename)

        # Attempt 2: chardet detection
        detected = chardet.detect(raw_data)
        encoding = detected.get("encoding")
        if encoding:
            try:
                data = raw_data.decode(encoding)
                logger.info("%s decoded as %s", filename, encoding)
                return data
            except UnicodeDecodeError as e:
                logger.info("%s: %s falling back to windows-1252", e.reason, filename)

        # Attempt 3: Windows-1252 fallback
        try:
            return raw_data.decode("cp1252")
        except UnicodeDecodeError as e:
            raise UnicodeDecodeError(
                e.encoding,
                e.object,
                e.start,
                e.end,
                f"{filename} (cp1252 fallback): {e.reason}",
            )

    @staticmethod
    def recursive_dict_update(original_dict: dict, update_dict: dict) -> dict:
        """
        Recursively updates a dictionary with values from another dictionary,
        preserving the original dictionary by creating a deep copy.

        Args:
            original_dict (dict): The dictionary to be updated.
            update_dict (dict): The dictionary containing the updates.

        Returns:
            dict: A new dictionary with the merged content.
        """
        # Create a deep copy of the original dictionary to preserve it
        merged_dict = deepcopy(original_dict)

        for key, value in update_dict.items():
            if (
                key in merged_dict
                and isinstance(merged_dict[key], dict)
                and isinstance(value, dict)
            ):
                # If both values are dictionaries, recurse
                merged_dict[key] = Doyles.recursive_dict_update(merged_dict[key], value)
            else:
                # Otherwise, update or add the value
                merged_dict[key] = value

        return merged_dict

    @staticmethod
    def safe_join(
        input: Union[Any, Iterable[Any]], delim: str = ",", ignore_none: bool = False
    ):
        """
        Joins elements of a list or tuple into a string using a delimiter.

        Args:
            input (object): List, tuple, or string.
            delim (str): Delimiter to use.

        Returns:
            str: Joined string or original input if not list/tuple.
        """
        if isinstance(input, str):
            return input
        if isinstance(input, Iterable):
            items = (str(item) for item in input if not (ignore_none and item is None))
            return delim.join(items)
        return str(input)

    @staticmethod
    def sort_dict(input_dict: dict, sort_fn: Callable[[Any], Any] = str) -> dict:
        """
        Recursively sorts dictionary keys (and nested dictionaries).

        Args:
            input_dict (dict): The dictionary to sort.
            sort_fn (Callable[[Any], Any]): Function applied to keys for sorting. Defaults to str.

        Returns:
            dict: A new dictionary with recursively sorted keys.
        """
        if isinstance(input_dict, dict):
            return {
                k: Doyles.sort_dict(v, sort_fn=sort_fn)
                for k, v in sorted(input_dict.items(), key=lambda x: sort_fn(str(x[0])))
            }
        else:
            return input_dict

    @staticmethod
    def union_keys(dict_list: list[dict], use_threads: bool = True) -> set:
        """
        Returns the union of keys from a list of dictionaries.

        Args:
            dict_list (list[dict]): List of dictionaries.
            use_threads (bool, optional): Use ThreadPoolExecutor if True. Defaults to True.

        Returns:
            set: Set of all keys found in any dictionary.
        """
        if not dict_list:
            return set()

        if use_threads:
            from concurrent.futures import ThreadPoolExecutor

            def get_keys(d):
                return set(d.keys())

            with ThreadPoolExecutor() as executor:
                key_sets = list(executor.map(get_keys, dict_list))
            return set().union(*key_sets)
        else:
            return set().union(*[d.keys() for d in dict_list])

    @staticmethod
    def url_quote(
        string: str,
        safe: str = "",
        strip: bool = False,
        fn: Callable[[Any], str] = str,
    ) -> str:
        """
        URL-encodes a string, optionally stripping whitespace and applying a function.

        Args:
            string (str): Input string.
            safe (str, optional): Characters not to quote. Defaults to "".
            strip (bool, optional): Strip whitespace. Defaults to False.
            fn (Callable, optional): Function to apply before quoting. Defaults to str.

        Returns:
            str: URL-quoted string.
        """
        if not isinstance(strip, bool):
            raise ValueError()

        if strip:
            return quote(fn(unquote(string).strip()), safe=safe)

        else:  # strip is False or None or empty
            return quote(fn(unquote(string)), safe=safe)
