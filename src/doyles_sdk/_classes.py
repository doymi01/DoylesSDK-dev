from __future__ import annotations

import argparse
import inspect
import logging
import logging.handlers
import multiprocessing as mp
import os
import sys
from contextvars import ContextVar
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Union

import requests

from ._metaclass import InfoMeta
from ._mixins import PickleMixin

if TYPE_CHECKING:
    from logging import Logger

    logger: Logger

worker_class_name_var = ContextVar("worker_class_name_var", default=None)


class BaseParser(argparse.ArgumentParser, metaclass=InfoMeta):
    """
    Enhanced argument parser for command-line applications, pre-configured with common logging and version options.

    Features:
        - Inherits from argparse.ArgumentParser.
        - Supports reading arguments from files (with '@' prefix).
        - Adds standard arguments for log level, log directory, verbosity, debug mode, and version display.
        - Automatically sets log level to DEBUG if --debug is specified.

    Args:
        *args: Positional arguments passed to ArgumentParser.
        **kwargs: Keyword arguments passed to ArgumentParser.

    Methods:
        parse_args(args: list[str] | None = None) -> argparse.Namespace:
            Parses command-line arguments, sets log_level to 'DEBUG' if --debug is used, and returns the parsed namespace.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, fromfile_prefix_chars="@", **kwargs)

        self.add_argument(
            "-l",
            "--log_level",
            help="Set the log level. Defaults to INFO",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            default="INFO",
        )
        self.add_argument(
            "-f", "--log_dir", help="Set the log file location. Defaults to stdout"
        )
        self.add_argument(
            "-v",
            "--verbose",
            help="Increase the verbosity of logging",
            action="store_true",
        )
        self.add_argument(
            "-d",
            "--debug",
            help="Set debug logging. Shortcut for --log_level DEBUG",
            action="store_true",
        )
        self.add_argument(
            "--version",
            help="Return the installed version and exit",
            action="version",
            version=f"{self.prog} {self.__version__}",
        )

    def parse_args(self, args: Optional[list[str]] = None) -> argparse.Namespace:  # pyright: ignore[reportIncompatibleMethodOverride]
        result: argparse.Namespace = super().parse_args(args=args)
        if result.debug:
            result.log_level = "DEBUG"
        return result


class BaseLoggerConfig:
    """
    Configures logging for console and optional file output.
    Supports multiprocessing via a logging queue.

    Features:
        - Sets up a root logger with NOTSET level.
        - Adds a console handler with a simple format.
        - Optionally adds a file handler with standard or verbose formatting.
        - Ensures log directory exists if file logging is enabled.
        - Provides an inner ISO_msec_Formatter for ISO 8601 timestamp formatting.

    Args:
        program_name (str): Name of the program, used for the log file name.
        log_level (int, optional): Logging level (e.g., logging.INFO, logging.DEBUG). Defaults to logging.WARNING.
        log_file_path (str | None, optional): Directory to store the log file. If None, logs are not written to a file.
        verbose (bool | None, optional): If True, enables verbose logging format for file handler.
        log_queue (mp.Queue | None, optional): Multiprocessing log queue.
        is_worker (bool, optional): True if configuring a worker process.

    Methods:
        stop_listener() -> None: Stops the logging listener if started.
    """

    # --- custom log level setup ---
    NOTICE_LEVEL = 25
    logging.addLevelName(NOTICE_LEVEL, "NOTICE")
    logging.NOTICE = NOTICE_LEVEL  # pyright: ignore[reportAttributeAccessIssue]

    @staticmethod
    def _patch_notice_level():
        """Add `logger.notice(...)` support to all loggers."""

        def notice(self, message, *args, **kwargs):
            if self.isEnabledFor(BaseLoggerConfig.NOTICE_LEVEL):
                self._log(BaseLoggerConfig.NOTICE_LEVEL, message, args, **kwargs)

        logging.Logger.notice = notice  # pyright: ignore[reportAttributeAccessIssue]

        # optional convenience for root logger
        def root_notice(message, *args, **kwargs):
            logging.log(BaseLoggerConfig.NOTICE_LEVEL, message, *args, **kwargs)

        logging.notice = root_notice  # pyright: ignore[reportAttributeAccessIssue]

    class ISO_msec_Formatter(logging.Formatter):
        def formatTime(
            self, record: logging.LogRecord, datefmt: Optional[str] = None
        ) -> str:
            return (
                datetime.fromtimestamp(record.created)
                .astimezone()
                .strftime(datefmt or self.datefmt)  # pyright: ignore[reportArgumentType]
            )

    class Doyle_Formatter(logging.Formatter):
        def formatTime(
            self, record: logging.LogRecord, datefmt: Optional[str] = None
        ) -> str:
            return (
                datetime.fromtimestamp(record.created)
                .astimezone()
                .strftime(datefmt or self.datefmt)  # pyright: ignore[reportArgumentType]
            )

        def format(self, record: logging.LogRecord) -> str:
            extra_parts: list[str] = []
            if record.processName != "MainProcess":
                extra_parts.append(f"[{record.processName}]")
            if record.threadName != "MainThread":
                extra_parts.append(f"[{record.threadName}]")

            record.proc_thread_info = "".join(extra_parts)
            return super().format(record)

    FMT_CONSOLE: logging.Formatter = logging.Formatter("%(levelname)-8s - %(message)s")
    FMT_STD: logging.Formatter = Doyle_Formatter(
        "%(asctime)s %(levelname)8s %(name)s%(proc_thread_info)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S.%f%z",
    )
    FMT_VERBOSE: logging.Formatter = ISO_msec_Formatter(
        '%(asctime)15s %(levelname)8s [%(name)s]: msg="%(message)s", process="%(processName)s", '
        'thread="%(threadName)s", file="%(filename)s", func="%(funcName)s()", line_no=%(lineno)s',
        datefmt="%Y-%m-%dT%H:%M:%S.%f%z",
    )

    class JoinableQueueListener(logging.handlers.QueueListener):
        def handle(self, record: logging.LogRecord) -> None:
            try:
                super().handle(record)
            finally:
                self.queue.task_done()

    def __init__(
        self,
        program_name: str,
        log_level: int = logging.WARNING,
        log_file_path: Optional[str] = None,
        verbose: Optional[bool] = None,
        log_queue: Optional[mp.Queue] = None,
        is_worker: bool = False,
    ):
        """
        Setup logging handlers.

        Args:
            program_name (str): Used in log file name if file logging enabled.
            log_level (int): Logging level.
            log_file_path (str | None): Directory path for log file; if None, no file logging.
            verbose (bool | None): Use verbose file format.
            log_queue (mp.Queue | None): Queue for multiprocessing logging; if provided workers send logs here.
            is_worker (bool): True if this is a worker process (to set up QueueHandler only).
        """
        BaseLoggerConfig._patch_notice_level()

        def create_handlers():
            handlers = []

            h_console = logging.StreamHandler(sys.stdout)
            h_console.setFormatter(self.FMT_CONSOLE)
            h_console.setLevel(log_level)
            handlers.append(h_console)

            if log_file_path:
                os.makedirs(log_file_path, exist_ok=True)
                filename_suffix = "_debug.log" if log_level < logging.INFO else ".log"
                log_file = os.path.join(
                    log_file_path, f"{program_name}{filename_suffix}"
                )
                h_file = logging.FileHandler(
                    log_file, mode="w", delay=True, encoding="utf-8"
                )
                h_file.setFormatter(self.FMT_VERBOSE if verbose else self.FMT_STD)
                h_file.setLevel(log_level)
                handlers.append(h_file)

            return handlers

        root = logging.getLogger()
        root.setLevel(logging.NOTSET)
        root.handlers.clear()

        start_method = mp.get_start_method()

        if log_queue:
            if is_worker:
                # Worker process: send logs to the queue
                qh = logging.handlers.QueueHandler(log_queue)
                qh.setLevel(log_level)
                root.addHandler(qh)
                return

            else:
                # Main process
                if start_method in ("spawn", "forkserver"):
                    # Main with spawn/forkserver: send logs to queue AND start listener
                    qh = logging.handlers.QueueHandler(log_queue)
                    qh.setLevel(log_level)
                    root.addHandler(qh)

                    # Create handlers and start listener to consume from queue
                    handlers = create_handlers()
                    self.listener = logging.handlers.QueueListener(log_queue, *handlers)
                    self.listener.start()

                else:
                    # Main with fork: just add handlers directly
                    handlers = create_handlers()
                    for h in handlers:
                        root.addHandler(h)
        else:
            # No queue at all, just add handlers directly
            handlers = create_handlers()
            for h in handlers:
                root.addHandler(h)

    def stop_listener(self) -> None:
        if hasattr(self, "listener"):
            self.listener.stop()


class DoyleClass(PickleMixin, metaclass=InfoMeta):
    """
    Base class providing logging and context manager support.

    Features:
        - Initializes a logger named after the class.
        - Logs initialization and context manager entry/exit events.
        - Supports use as a context manager (`with` statement).
        - Delegates attribute access to a delegate object if specified.

    Attributes:
        logger (logging.Logger): Logger instance for the class.
        _delegate_attr (str | None): Name of the delegate attribute.

    Properties:
        __module__ (str): Full module name.
        __package__ (str): Top-level package name.
        __version__ (str): Installed version (if available).
    """

    parent = None

    _delegate_attr: Optional[str] = (
        None  # Subclasses should override or define this attribute
    )

    def __init__(self, *args, **kwargs):
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug("Initializing Class Instance %s", self)
        super().__init__(*args, **kwargs)

    def __enter__(self) -> "DoyleClass":
        self.logger.debug("%s Entering context manager", self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.logger.debug("%s Exiting context manager", self)
        return

    def __getattr__(self, name: str):
        """
        Delegates attribute access to self._delegate if attribute not found.
        Only called if normal lookup fails.

        Args:
            name (str): Attribute name.

        Returns:
            Any: Attribute from delegate or raises AttributeError.
        """

        # Don’t intercept Python’s internal magic/ABC lookups
        if name == "__isabstractmethod__":
            return False

        delegate_attr = getattr(self, "_delegate_attr", None)

        if not delegate_attr:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}' "
                f"and '_delegate_attr' is not defined or empty."
            )

        try:
            delegate = super().__getattribute__(delegate_attr)
        except AttributeError:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}' "
                + f"and no delegate '{delegate_attr}' found on instance."
            )

        try:
            return getattr(delegate, name)
        except AttributeError:
            raise AttributeError(
                f"'{self.__class__.__name__}' object and its delegate '{delegate.__class__.__name__}' "
                + f"have no attribute '{name}'"
            )

    def unwrap(self):
        """
        Return the delegated object if _delegate_attr is set.

        Raises:
            AttributeError: if _delegate_attr is not defined or the delegate is missing.
        """
        delegate_attr = getattr(self, "_delegate_attr", None)
        if not delegate_attr:
            raise AttributeError(
                f"{self.__class__.__name__} does not define '_delegate_attr'"
            )

        try:
            delegate = getattr(self, delegate_attr)
        except AttributeError:
            raise AttributeError(
                f"{self.__class__.__name__} has no attribute '{delegate_attr}'"
            )

        return delegate

    @classmethod
    def func_name(cls, back: int = 1) -> str:
        """
        Return the name of the calling function/method.

        Args:
            back (int): How many frames up the stack to look.
                        Default=1 means "caller".
        """
        return inspect.stack()[back].function

    @property
    def root(self):
        if self.parent is None:
            return self
        return self.parent.root

    def _get_picklable_state(self, state):
        # convert special attributes to picklable form
        return state

    def _restore_from_state(self, state):
        # rebuild special attributes
        pass


# class SecureStore:
#     """
#     Cross-platform credential store that uses the system keyring when available,
#     and falls back to an encrypted local file with corruption detection and backup.
#     """

#     def __init__(self, service_name: str, fallback_file: str | None = None):
#         self.service_name = service_name
#         self.fallback_file = fallback_file or os.path.expanduser(
#             f"~/.{service_name}_secrets"
#         )
#         self._backend = self._detect_backend()

#     # ---------- Public API ----------

#     def save(self, username: str, secret: str):
#         """Save or update credentials for a user."""
#         if self._backend == "keyring":
#             keyring.set_password(self.service_name, username, secret)
#         else:
#             self._file_safe_save(username, secret)

#     def load(self, username: str) -> str | None:
#         """Retrieve credentials; returns None if not found."""
#         if self._backend == "keyring":
#             return keyring.get_password(self.service_name, username)
#         return self._file_safe_load(username)

#     def delete(self, username: str):
#         """Delete stored credentials for a given user."""
#         if self._backend == "keyring":
#             try:
#                 keyring.delete_password(self.service_name, username)
#             except keyring.errors.PasswordDeleteError:
#                 pass
#         else:
#             self._file_safe_delete(username)

#     # ---------- Backend detection ----------

#     def _detect_backend(self) -> str:
#         try:
#             keyring.get_keyring()
#             keyring.get_password("keyring_test", "dummy")
#             return "keyring"
#         except (NoKeyringError, InitError, RuntimeError):
#             return "file"

#     # ---------- Encryption helpers ----------

#     def _file_key(self) -> bytes:
#         """Get or create a persistent encryption key."""
#         keyfile = self.fallback_file + ".key"
#         if not os.path.exists(keyfile):
#             key = Fernet.generate_key()
#             with open(keyfile, "wb") as f:
#                 f.write(key)
#             os.chmod(keyfile, 0o600)
#         else:
#             with open(keyfile, "rb") as f:
#                 key = f.read()
#         return key

#     # ---------- File-based backend ----------

#     def _file_load_data(self) -> dict:
#         """
#         Load all credentials from the fallback file.
#         Returns a dict (possibly empty) on success.
#         Raises CorruptStoreError if the file cannot be decrypted or parsed.
#         """
#         if not os.path.exists(self.fallback_file):
#             return {}

#         with open(self.fallback_file, "rb") as f:
#             key = self._file_key()
#             cipher = Fernet(key)
#             encrypted_data = f.read()
#             try:
#                 decrypted = cipher.decrypt(encrypted_data)
#                 return json.loads(decrypted.decode("utf-8"))
#             except (InvalidToken, json.JSONDecodeError) as e:
#                 # Backup the corrupt file before raising
#                 backup = self.fallback_file + ".corrupt"
#                 try:
#                     os.rename(self.fallback_file, backup)
#                 except OSError:
#                     pass
#                 raise CorruptStoreError(
#                     f"Credential store '{self.fallback_file}' is unreadable or corrupt. "
#                     f"A backup was saved to '{backup}'."
#                 ) from e

#     def _file_save_data(self, data: dict):
#         """Encrypt and persist all credentials."""
#         key = self._file_key()
#         cipher = Fernet(key)
#         encrypted = cipher.encrypt(json.dumps(data).encode("utf-8"))
#         with open(self.fallback_file, "wb") as f:
#             f.write(encrypted)
#         os.chmod(self.fallback_file, 0o600)

#     # ---------- File operations ----------

#     def _file_safe_save(self, username: str, secret: str):
#         """Safely save credentials, refusing to overwrite if the store is corrupt."""
#         try:
#             data = self._file_load_data()
#         except CorruptStoreError as e:
#             raise RuntimeError(
#                 f"Cannot save credentials — store is corrupt. "
#                 f"Please inspect or remove '{self.fallback_file}.corrupt' and retry."
#             ) from e

#         data[username] = secret
#         self._file_save_data(data)

#     def _file_safe_load(self, username: str) -> str | None:
#         """Retrieve credentials safely."""
#         try:
#             data = self._file_load_data()
#         except CorruptStoreError as e:
#             raise RuntimeError(
#                 f"Cannot load credentials — store is corrupt. "
#                 f"Please inspect '{self.fallback_file}.corrupt'."
#             ) from e

#         return data.get(username)

#     def _file_safe_delete(self, username: str):
#         """Safely delete credentials, aborting if the store is corrupt."""
#         try:
#             data = self._file_load_data()
#         except CorruptStoreError as e:
#             raise RuntimeError(
#                 f"Cannot delete credentials — store is corrupt. "
#                 f"Please inspect or remove '{self.fallback_file}.corrupt'."
#             ) from e

#         if username in data:
#             del data[username]
#             self._file_save_data(data)


class SplunkSession(DoyleClass, requests.Session):
    def __init__(
        self,
        token: Optional[str] = None,
        name: Optional[str] = None,
        verify: Union[bool, str] = False,
    ):
        from requests.adapters import HTTPAdapter
        from urllib3.exceptions import InsecureRequestWarning
        from urllib3.util import Retry

        super().__init__()

        if not verify:
            # Suppress the InsecureRequestWarning
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)  # pyright: ignore[reportAttributeAccessIssue]
        name = name or self.__class__.__name__
        self.headers.update(
            {
                "User-Agent": f"{name}/{self.__version__} ({'; '.join([self.__system__, self.__machine__])}) Python/{self.__python__}",  # pyright: ignore[reportArgumentType, reportCallIssue]
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )
        self.verify = verify

        retry_strategy = Retry(
            total=10,  # Total retries
            status_forcelist=[429, 500, 502, 503, 504],  # Status codes to retry on
            backoff_factor=1,  # Exponential backoff
            allowed_methods=[
                "HEAD",
                "GET",
                "PUT",
                "PATCH",
                "DELETE",
                "OPTIONS",
                "TRACE",
            ],
        )

        # class SafeLoggingAdapter(HTTPAdapter):
        #     def send(self, request, **kwargs):
        #         # Make a copy of headers so you don’t mutate the original request
        #         safe_headers = request.headers.copy()
        #         if "Authorization" in safe_headers:
        #             safe_headers["Authorization"] = "REDACTED"
        #         # Optional: log safely
        #         self.logger.debug("Sending %s %s with headers %s", request.method, request.url, safe_headers)
        #         return super().send(request, **kwargs)

        adapter = HTTPAdapter(
            pool_connections=10, pool_maxsize=500, max_retries=retry_strategy
        )
        self.mount("http://", adapter)
        self.mount("https://", adapter)

    def set_token(self, value):
        self.headers["Authorization"] = f"Bearer {value}"
