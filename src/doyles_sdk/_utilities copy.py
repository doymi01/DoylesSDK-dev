import getpass
import io
import logging
import os
from pathlib import Path
import re
import tarfile
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from fnmatch import fnmatch
from hashlib import md5
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import quote, unquote

import chardet

# from ._classes import DoyleCass

logger = logging.getLogger(__name__)


class Doyles:
    """Collection of utility functions for Splunk app management, string manipulation, dictionary operations, and file handling."""

    __slots__ = ()

    class NoOp:
        """A singleton no-op callable."""

        __slots__ = ()

        def __call__(self, *args, **kwargs):
            pass

        def __repr__(self):
            return "<NoOp>"

        def __hash__(self):
            return id(self)

    @staticmethod
    def safe_call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SystemExit as e:
            logger.debug(f"Function tried to exit with code {e.code}, ignoring.")
            return e.code

    # Singleton instance as a class variable
    noop = NoOp()

    re_extract_from_rest_url = re.compile(
        r"(?:https:\/\/(?P<host>(?:127\.0\.0\.1|[^\.]*)).*:\d+\/)?(?:servicesNS\/)?(?P<context>.*?)\/(?P<app>.*?)\/(?P<location>.*)\/(?P<instance>.*)"
    )
    re_diag_name = re.compile(
        r"(?P<name>(?:diag|magic)-(?P<host>\S+)-(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2}))$"
    )

    @staticmethod
    def move_rest_properties(
        parser, app, new_app, user, owner, sharing, perms_read=None, perms_write=None
    ):
        results = []

        q_app = Doyles.url_quote(app)
        q_user = Doyles.url_quote(user)

        for section in list(parser.sections()):
            q_section = Doyles.url_quote(section)

            # data = {k: v for k, v in parser.items(section)}
            results.append(
                {
                    "method": "POST",
                    "url": f"https://{{host}}:{{port}}/servicesNS/{q_user}/{q_app}/configs/conf-{parser.shortname}/{q_section}/move",
                    "data": {"app": new_app, "user": owner},
                }
            )

        return results

    @staticmethod
    def create_rest_properties(
        parser,
        app,
        user,
        owner,
        sharing,
        perms_read=None,
        perms_write=None,
        option_map: callable = str,
    ):
        results = []

        q_app = Doyles.url_quote(app)
        q_user = Doyles.url_quote(user)

        if user != "nobody":
            results.append(
                {
                    "method": "POST",
                    "url": "https://{host}:{port}/services/admin/SAML-user-role-map",
                    "data": {"name": user, "roles": "user"},
                }
            )

        # build the url string
        url = f"https://{{host}}:{{port}}/servicesNS/{q_user}/{q_app}/properties"

        results.append(
            {"method": "POST", "url": url, "data": {"__conf": parser.shortname}}
        )

        for section in list(parser.sections()):
            q_section = Doyles.url_quote(section)

            data = {option_map(k): v for k, v in parser.items(section)}

            results.append(
                {
                    "method": "POST",
                    "url": "/".join([url, parser.shortname]),
                    "data": {"__stanza": section},
                }
            )
            results.append(
                {
                    "method": "POST",
                    "url": "/".join([url, parser.shortname, q_section]),
                    "data": data,
                }
            )
            acl_data = {
                "owner": owner,
                "sharing": sharing,
                "perms.read": perms_read or "*",
                "perms.write": perms_write or "admin,sc_admin",
            }
            results.append(
                {
                    "method": "POST",
                    "url": f"https://{{host}}:{{port}}/servicesNS/{q_user}/{q_app}/configs/conf-{parser.shortname}/{q_section}/acl",
                    "data": acl_data,
                }
            )

        return results

    @staticmethod
    def validate_diag(name: str):
        return Doyles.re_diag_name.match(name).groups()

    @staticmethod
    def extract_diag_info(name: str) -> dict:
        result = Doyles.re_diag_name.fullmatch(name).groupdict()
        result["short_host"] = result["host"].split(".")[0]
        return result

    # @staticmethod
    # def load_app_from_diag(app_name: str, diag_path: Union[str, os.PathLike, Path, PurePath], flavor: Optional[str] = None):
    #     from .app_factory import app_factory

    #     app_path = Path(diag_path) / 'etc' / 'apps' / app_name
    #     app_object = app_factory(app_name=app_name)
    #     app_object.load_app(app_path)

    @staticmethod
    def _str_keys(obj):
        if isinstance(obj, dict):
            return {str(k): Doyles._str_keys(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [Doyles._str_keys(v) for v in obj]
        else:
            return obj

    @staticmethod
    def extract_from_rest_url(url: str) -> dict:
        """
        Extracts components from a Splunk REST URL using regex.

        Args:
            url (str): The REST URL to parse.

        Returns:
            dict: Dictionary of extracted components, or empty dict if not matched.

            - host
            - context
            - app
            - location
            - instance

        """
        try:
            return Doyles.re_extract_from_rest_url.search(url).groupdict()
        except AttributeError:
            return dict()

    ##################################################
    # NULLIF
    ##################################################
    @staticmethod
    def nullif(source: str, match: str) -> Optional[str]:
        """
        Returns None if source equals match, otherwise returns source.

        Args:
            source (str): The source string.
            match (str): The string to compare against.

        Returns:
            Optional[str]: None if source == match, else source.
        """
        if source == match:
            return None
        else:
            return source

    @staticmethod
    def get_full_path(path: Union[str, os.PathLike]) -> str:
        """
        Expands user and environment variables and returns the absolute path.

        Args:
            path (Union[str, os.PathLike]): Input path.

        Returns:
            str: Absolute path.
        """
        return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))

    @staticmethod
    def safe_join(input: Union[str, Iterable[str]], delim: str = ","):
        """
        Joins elements of a list or tuple into a string using a delimiter.

        Args:
            input (object): List, tuple, or string.
            delim (str): Delimiter to use.

        Returns:
            str: Joined string or original input if not list/tuple.
        """
        if isinstance(input, Iterable):
            return delim.join(input)
        else:
            return input

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
    def url_quote(
        string: str, safe: str = "", strip: bool = False, fn: object = str
    ) -> str:
        """
        URL-encodes a string, optionally stripping whitespace and applying a function.

        Args:
            string (str): Input string.
            safe (str, optional): Characters not to quote. Defaults to "".
            strip (bool, optional): Strip whitespace. Defaults to False.
            fn (object, optional): Function to apply before quoting. Defaults to str.

        Returns:
            str: URL-quoted string.
        """
        if strip is False:
            return quote(fn(unquote(string)), safe=safe)

        if strip is None or strip is True:
            return quote(fn(unquote(string).strip()), safe=safe)

        if strip is not False:
            return quote(fn(unquote(string).strip(strip)), safe=safe)

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
            return raw_data.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass

        # Attempt 2: chardet detection
        detected = chardet.detect(raw_data)
        encoding = detected.get("encoding")
        if encoding:
            try:
                return raw_data.decode(encoding)
            except UnicodeDecodeError as e:
                logger.warning(
                    "%s: %s falling back to windows-1252", e.reason, filename
                )

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
    def sort_dict(input_dict: dict) -> dict:
        """
        Recursively sorts keys and values in a dictionary.

        Args:
            input_dict (dict): Dictionary to sort.

        Returns:
            dict: Sorted dictionary.
        """
        if isinstance(input_dict, dict):
            return {
                k: Doyles.sort_dict(v)
                for k, v in sorted(input_dict.items(), key=lambda x: str(x[0]).lower())
            }
        else:
            return input_dict

    @staticmethod
    def recursive_dict_update(original_dict, update_dict) -> dict:
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
    def pretty_dict(input_dict: dict, level: int = 0) -> dict:
        """
        Recursively formats a dictionary with indentation for pretty printing.

        Args:
            input_dict (dict): Dictionary to format.
            level (int, optional): Indentation level. Defaults to 0.

        Returns:
            dict: Indented dictionary or string.
        """
        INDENT = "  " * level
        if isinstance(input_dict, dict):
            level += 1
            return {k: Doyles.pretty_dict(v, level) for k, v in input_dict.items()}
        else:
            return f"{INDENT}{input_dict}"

    @staticmethod
    def add_object_to_tar(tar: tarfile.TarFile, obj, arcname: str):
        """Add an object's str() output to a tar archive as a UTF-8 text file."""
        # turn arcname into string
        arcname = str(arcname)

        # Turn object into bytes
        data = str(obj).encode("utf-8")
        bio = io.BytesIO(data)

        # Create TarInfo with metadata
        tarinfo = tarfile.TarInfo(name=arcname)
        tarinfo.size = len(data)
        tarinfo.mtime = int(datetime.now().timestamp())  # current timestamp

        # Write into tar
        tar.addfile(tarinfo, bio)

    @staticmethod
    def add_csv_header_to_tar(tar: tarfile.TarFile, csv_path: str, arcname: str):
        """Read only the first line of a CSV file and add it to the tar archive."""
        data = Doyles.read_file_encoding_unknown(csv_path, max_bytes=4096)
        header_line = data.splitlines()[0].strip()

        # Add to tar (reusing your add_object_to_tar logic)
        Doyles.add_object_to_tar(tar, header_line + "\n", arcname=arcname)

    @staticmethod
    def flatten_dict(
        d: Dict[str, Any],
        parent_key: str = "",
        sep: str = ".",
        skip_keys: List[str] = None,
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

            def get_keys(d):
                return set(d.keys())

            with ThreadPoolExecutor() as executor:
                key_sets = list(executor.map(get_keys, dict_list))
            return set().union(*key_sets)
        else:
            return set().union(*[d.keys() for d in dict_list])

    @staticmethod
    def iter_discovered_confs(
        nested_dict: dict,
    ) -> Iterator[Tuple[object, Optional[str], dict]]:
        """
        Iterate a nested discovered structure like discovered_views/panels/models.

        Yields:
            top_path: Path or key for the top-level entry (_APP_* or _USERS_*)
            user: username if applicable, else None
            items_dict: dictionary of objects at this level
        """
        for top_path, top_val in nested_dict.items():
            if isinstance(top_val, Mapping):
                for user, item in top_val.items():
                    if isinstance(item, Mapping):
                        for name, obj in item.items():
                            yield Path(top_path), user, obj
                    else:
                        yield Path(top_path), user, item
            else:
                yield Path(top_path), None, top_val

    @staticmethod
    def iter_discovered_data(
        nested_dict: dict,
    ) -> Iterator[Tuple[object, Optional[str], dict]]:
        """
        Iterate a nested discovered structure like discovered_views/panels/models.

        Yields:
            top_path: Path or key for the top-level entry (_APP_* or _USERS_*)
            user: username if applicable, else None
            items_dict: dictionary of objects at this level
        """
        for top_path, top_val in nested_dict.items():
            if isinstance(top_val, Mapping):
                for (
                    inner_key,
                    inner_val,
                ) in top_val.items():  # this will be the object name or the user name
                    if isinstance(inner_val, Mapping):
                        for inner_name, item in inner_val.items():
                            yield Path(top_path) / inner_name, inner_key, item
                    else:
                        yield (
                            Path(top_path) / inner_key,
                            None,
                            inner_val,
                        )  # this is a top level object
            else:
                yield Path(top_path), None, top_val

    @staticmethod
    def iter_discovered_files(
        nested_dict: dict,
    ) -> Iterator[Tuple[object, Optional[str], dict]]:
        """
        Iterate a nested discovered structure like discovered_views/panels/models.

        Yields:
            top_path: Path or key for the top-level entry (_APP_* or _USERS_*)
            user: username if applicable, else None
            items_dict: dictionary of objects at this level
        """
        for top_path, top_val in nested_dict.items():
            if isinstance(top_val, Mapping):
                for (
                    inner_key,
                    inner_val,
                ) in top_val.items():  # this will be the object name or the user name
                    yield Path(top_path), inner_key, inner_val
            else:
                yield Path(top_path), None, top_val

    @staticmethod
    def create_empty_app(
        app_name: str,
        dest_path: Union[str, os.PathLike],
        app_label: str,
        app_version: str = "0.0.1",
        is_visible: bool = True,
        show_in_nav: bool = True,
        color: str = "random",
        read_import_list: str = "user",
        write_import_list: str = "power",
        ss_default: bool = True,
        dist_default: bool = True,
        export: str = "none",
    ) -> tuple[str, str, list, list]:
        """
        Creates an empty Splunk app template with default configuration files and directories.

        :param app_name: the app name (name of the directory)
        :type app_name: str
        :param dest_path: location to save the newly created app
        :type dest_path: str | os.PathLike
        :param app_label: the label shown in the UI
        :type app_label: str
        :param app_version: the version for app.conf, defaults to '0.0.1'
        :type app_version: str, optional
        :param is_visible: set this to create a UI app, defaults to True
        :type is_visible: bool, optional
        :param show_in_nav: set this to false to prevent the app from displaying in the dropdown, defaults to True
        :type show_in_nav: bool, optional
        :param color: specify an RGB code or 'random' to set the app icon color, defaults to 'random'
        :type color: str, optional
        :param read_import_list: semicolon delimited string of roles to import, defaults to 'user'
        :type read_import_list: str, optional
        :param write_import_list: semicolon delimited string of roles to import, defaults to 'power'
        :type write_import_list: str, optional
        :return: app name, app path relative to the specified path, saml role mapping, contents to add to user-prefs to make this the default app for the roles created
        :rtype: tuple[str, str, list, list]
        """

        if color is None:
            nav = '<nav search_view="search">'
        elif color.lower() == "random":
            nav = f'<nav search_view="search" color="#{md5(bytes(app_name, encoding="utf-8")).hexdigest()[0:6].upper()}">'
        elif re.match(r"[a-fA-F0-9]{6}$", color):
            nav = f'<nav search_view="search" color="#{color.upper()}">'

        read = f"{app_name}_read"
        write = f"{app_name}_write"
        f"{app_name}_admin"

        _export = f"export = {export}"

        app_template = [
            "[install]",
            "",
            "[launcher]",
            "author = Splunk Professional Services",
            "description = App prepared by The Magic Script for Splunk Cloud migration",
            f"version = {app_version}",
            "",
            "[package]",
            "check_for_updates = 0",
            "",
            "[ui]",
            f"label = {app_label}",
            f"is_visible = {(lambda x: 1 if bool(x) else 0)(is_visible)}",
            f"show_in_nav = {(lambda x: 1 if bool(x) else 0)(show_in_nav)}",
        ]

        ss_template = [
            "[default]",
            f"request.ui_dispatch_app = {app_name}",
            "request.ui_dispatch_view = search",
            "allow_skew = 20m",
            "schedule_window = auto",
            "",
        ]

        dist_template = [
            "[replicationDenyList]",
            f"{app_name}_lookups = .../{app_name}/lookups/...",
            "",
        ]

        meta_template = [
            f'# default permissions for "{app_name}"',
            "[]",
            f"access = read : [ {read} ], write : [ {write} ]",
            _export,
            "",
            "[app]",
            f"access = read : [ {read} ], write : [ admin, sc_admin ]",
            _export,
            "",
            "[alert_actions]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
            "[authorize]",
            "access = read : [ * ], write : [ admin, sc_admin ]",
            "_export = system",
            "",
            "[collections]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
            "[eventtypes]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
            "[lookups]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
            "[macros]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
            "[props]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
            "[savedsearches]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
            "[savedsearches/default]",
            "access = read : [ * ], write : [ admin, sc_admin ]",
            "export = none",
            "",
            "[tags]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
            "[transforms]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
            "[views]",
            f"access = read : [ * ], write : [ {write} ]",
            _export,
            "",
        ]

        nav_template = [
            nav,
            '<view name="search" default="true" />',
            '<view name="analytics_workspace" />',
            '<view name="datasets" />',
            '<view name="reports" />',
            '<view name="alerts" />',
            '<view name="dashboards" />',
            "</nav>",
        ]

        saml_map = list()
        apps_dir = os.path.join(dest_path, "etc", "apps")
        app_dir = os.path.join(apps_dir, app_name)
        default_dir = os.path.join(app_dir, "default")
        meta_dir = os.path.join(app_dir, "metadata")
        for dir in [default_dir, meta_dir]:
            os.makedirs(dir, exist_ok=True)

        app_conf = os.path.join(default_dir, "app.conf")
        meta_conf = os.path.join(meta_dir, "default.meta")
        auth_conf = os.path.join(default_dir, "authorize.conf")
        ss_conf = os.path.join(default_dir, "savedsearches.conf")
        dist_conf = os.path.join(default_dir, "distsearch.conf")
        if is_visible:
            default_nav = os.path.join(default_dir, "data", "ui", "nav", "default.xml")
            os.makedirs(os.path.dirname(default_nav), exist_ok=True)
            os.makedirs(os.path.dirname(dist_conf), exist_ok=True)

        os.makedirs(os.path.dirname(app_conf), exist_ok=True)
        os.makedirs(os.path.dirname(auth_conf), exist_ok=True)
        os.makedirs(os.path.dirname(ss_conf), exist_ok=True)
        # os.makedirs(os.path.dirname(dist_conf), exist_ok=True)
        os.makedirs(os.path.dirname(meta_conf), exist_ok=True)

        with open(app_conf, "w", encoding="utf-8") as f:
            f.write("\n".join(app_template))

        with open(meta_conf, "w", encoding="utf-8") as f:
            f.write("\n".join(meta_template))

        with open(default_nav, "w", encoding="utf-8") as f:
            f.write("\n".join(nav_template))

        if ss_default:
            with open(ss_conf, "w", encoding="utf-8") as f:
                f.write("\n".join(ss_template))

        if dist_default:
            with open(dist_conf, "w", encoding="utf-8") as f:
                f.write("\n".join(dist_template))

        auth = [
            "[role_" + read + "]",
            f"importRoles = {read_import_list}",
            "",
            "[role_" + write + "]",
            f"importRoles = {write_import_list}",
            "",
        ]

        user_prefs = [
            "[role_" + read + "]",
            f"default_namespace = {app_name}",
            "",
            "[role_" + write + "]",
            f"default_namespace = {app_name}",
            "",
        ]

        with open(auth_conf, "w") as f:
            f.write("\n".join(auth))

        saml_map.append(f"{read} = <SAML_USER_ROLE>")
        saml_map.append(f"{write} = <SAML_POWER_ROLE>")

        return app_dir, os.path.relpath(app_dir, dest_path), saml_map, user_prefs
