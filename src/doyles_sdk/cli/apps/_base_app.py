import argparse
import logging
import multiprocessing as mp
import multiprocessing.synchronize
import os
import signal
import sys
import threading
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from datetime import datetime, timedelta
from functools import wraps
from io import TextIOWrapper
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, Union

from doyles_sdk._classes import BaseLoggerConfig
from doyles_sdk._metaclass import InfoMeta

if TYPE_CHECKING:
    from logging import Logger

    logger: Logger


class DoyleApp(metaclass=InfoMeta):
    """
    Base CLI app class with argument parsing, logging, and multiprocessing support.

    Subclasses add CLI args by overriding `add_arguments(parser)`.
    Override `run()` to implement app logic.

    Attributes:
        args (argparse.Namespace): Parsed command-line arguments.
        logger (logging.Logger): Logger instance.
        logger_config (BaseLoggerConfig): Logger configuration.
        log_queue (mp.Queue | None): Multiprocessing log queue.
        use_multiprocessing (bool): Whether multiprocessing is enabled.
        class_name (str): Name of the class.
        _log_file_path (str): Path to log file.
    """

    command_name = None
    mp_safe = False
    thread_safe = False

    THREAD_LIMIT = 500
    PROCESS_LIMIT = 100

    # --- Lazy ---
    _thread_lock: Union[threading.Lock, None] = None
    _mp_lock: Union[multiprocessing.synchronize.Lock, None] = None
    _results_file_path: Union[os.PathLike, None] = None

    def __init__(self, caller: Optional[str] = None, **kwargs):
        self._exiting = False
        self._exit_lock = threading.Lock()
        self.caller = caller
        # self._log_file_path = log_file_path or "./doyle_app.log"

        self._install_signal_handler()

        self.class_name = self.__class__.__name__
        self._secrets = None

        parser = self._build_parser()
        self.args = parser.parse_args()
        self.args.log_level = "DEBUG" if self.args.debug else self.args.log_level
        self.args_post_process(parser)

        # --- Concurrency resolution ---
        self._resolve_concurrency()

        # Override multiprocessing start method if requested
        if getattr(self.args, "mp_start_method", None):
            try:
                mp.set_start_method(self.args.mp_start_method, force=True)
            except RuntimeError:
                try:
                    if self.__system__ == "Linux":
                        mp.set_start_method("fork", force=True)
                    else:
                        mp.set_start_method("spawn", force=True)
                except RuntimeError:
                    pass

        # Determine multiprocessing start method and whether queue is needed
        start_method = mp.get_start_method()
        needs_queue = start_method == "spawn"

        # Setup log queue only if multiprocessing enabled and queue needed
        self.log_queue = (
            mp.JoinableQueue(-1) if self.use_multiprocessing and needs_queue else None
        )

        log_level = (
            logging.DEBUG
            if self.args.debug
            else getattr(logging, self.args.log_level.upper(), logging.INFO)
        )
        self.logger_config = BaseLoggerConfig(
            program_name=self.command_name,  # pyright: ignore[reportArgumentType]
            log_level=log_level,
            log_file_path=str(self.args.log_dir) if self.args.log_dir else None,
            verbose=self.args.verbose,
            log_queue=self.log_queue,
            is_worker=False,
        )

        self.logger = logging.getLogger(self.class_name)
        self.logger.debug(
            "%s initialized with args: %s", self.__class__.__name__, self.args
        )
        self.logger.notice(
            "%s: %s-%s, Python: %s, Platform: %s",
            self.class_name,
            self.__package__,  # pyright: ignore[reportAttributeAccessIssue]
            self.__version__,  # pyright: ignore[reportAttributeAccessIssue]
            self.__python__,  # pyright: ignore[reportAttributeAccessIssue]
            self.__platform__,  # pyright: ignore[reportAttributeAccessIssue]
        )
        if "multiprocessing" in sys.modules:
            self.logger.debug("Start Method: %s", mp.get_start_method())
            self.logger.debug("CPU Count: %s", self.__cpu_count__)  # pyright: ignore[reportAttributeAccessIssue]
        self.logger.debug("Total Memory: %s", self.__mem_total__)  # pyright: ignore[reportAttributeAccessIssue]
        self.logger.debug("Available Memory: %s", self.__mem_avail__)  # pyright: ignore[reportAttributeAccessIssue]

    # --- Lazy properties ---
    @property
    def thread_lock(self):
        if self._thread_lock is None:
            self._thread_lock = threading.Lock()
        return self._thread_lock

    @property
    def mp_lock(self):
        if self._mp_lock is None:
            self._mp_lock = mp.Lock()
        return self._mp_lock

    # @property
    # def secrets(self) -> AppSecrets:
    #     """
    #     Lazy-loaded secure secrets manager for this app instance.
    #     Each app gets its own namespace in the OS keyring.
    #     """
    #     if self._secrets is None:
    #         self._secrets = AppSecrets(app_name=self.__class__.__name__)
    #     return self._secrets

    def _install_signal_handler(self) -> None:
        if mp.current_process().name != "MainProcess":
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            return

        def handler(signum, frame):
            with self._exit_lock:
                if self._exiting:
                    # Ignore subsequent interrupts during shutdown
                    self.logger.notice("KeyboardInterrupt ignored during shutdown.")
                    return
                self._exiting = True
            self.logger.warning("KeyboardInterrupt received, cancelling all workers...")
            # Restore default handler so force quit works if pressed again later
            signal.signal(signal.SIGINT, signal.default_int_handler)
            # Raising here lets your try-except catch it properly
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, handler)

    @classmethod
    def _wrap_worker(cls, func):
        """
        Decorator to wrap a worker function with shared boilerplate:
        - Sets contextvar dynamically if needed
        - Sets up logger from contextvar
        - Logs start/finish
        - Handles exceptions

        Args:
            func (callable): Worker function.

        Returns:
            callable: Wrapped function.
        """

        @wraps(func)
        def wrapper(*args, **kwargs):
            if mp.current_process().name != "MainProcess":
                signal.signal(signal.SIGINT, signal.SIG_IGN)

            # Get logger and inject into function globals
            logger = logging.getLogger(cls.__name__)
            func_globals = func.__globals__
            if "logger" not in func_globals:
                func_globals["logger"] = logger

            try:
                logger.debug(
                    "%s starting with args=%s, kwargs=%s", func.__name__, args, kwargs
                )
                _start_time = time.perf_counter()
                result = func(*args, **kwargs)
                _runtime = time.perf_counter() - _start_time
                logger.debug(
                    "%s finished successfully in %s",
                    func.__name__,
                    timedelta(seconds=_runtime),
                )
                return result
            except Exception as e:
                logger.exception(f"Error in {func.__name__}: {e}")
                raise

        return wrapper

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Find all methods named do_* (no leading underscore)
        for attr_name in dir(cls):
            if attr_name.startswith("do_"):
                orig_method = getattr(cls, attr_name)
                # Only wrap if it's not already wrapped (avoid infinite wrap)
                if not getattr(orig_method, "_is_wrapped", False):
                    wrapped = cls._wrap_worker(orig_method)
                    wrapped._is_wrapped = True
                    setattr(
                        cls, attr_name, staticmethod(wrapped)
                    )  # Important: keep as staticmethod
                    # setattr(cls, attr_name, wrapped)

        # Automatically register the subclass using its lowercase name
        # You can override with a custom command_name attribute if desired
        #
        # Register into the current module’s registry
        # registry = COMMAND_REGISTRY_CTX.get()
        # if registry is not None:
        #     cmd_name = getattr(cls, "command_name", cls.__name__.lower())
        #     registry[cmd_name] = cls
        # else:
        #     raise KeyError
        # cmd_name = getattr(cls, "command_name", cls.__name__.lower())
        # register_command(cmd_name, cls)

    @classmethod
    def _build_parser(cls, prog: Optional[str] = None) -> argparse.ArgumentParser:
        """
        Build an argument parser for the CLI app.

        Returns:
            argparse.ArgumentParser: Configured parser.
        """
        parser = argparse.ArgumentParser(
            prog=prog or cls.command_name,
            description=cls.__doc__,
            fromfile_prefix_chars="@",
        )
        parser.set_defaults(process_limit=cls.__cpu_count__)
        parser.set_defaults(thread_limit=100)
        parser.set_defaults(
            start_time=datetime.today()
            .isoformat(sep="T", timespec="seconds")
            .replace(":", "-")
        )
        parser.add_argument("--debug", action="store_true", help="Enable debug logging")
        parser.add_argument(
            "--verbose", action="store_true", help="Enable verbose logging"
        )
        parser.add_argument(
            "--log-dir", type=Path, help="Directory for log file output"
        )
        # parser.add_argument(
        #     "--prog", default=cls.__name__, help="Program name for logging"
        # )
        parser.add_argument(
            "--version",
            action="version",
            help="Returns the installed version",
            version=f"{cls.__name__}: {cls.__package__} Version: {cls.__version__}",
        )
        parser.add_argument(
            "--log-level",
            metavar="LEVEL",
            default="NOTICE",
            type=str.upper,
            choices=["DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL"],
            help="Logging level",
        )
        if cls.mp_safe or cls.thread_safe:
            concurrency_group = parser.add_argument_group(
                "Concurrency options",
                description="These options control concurrency settings.",
            )

            if cls.mp_safe and cls.thread_safe:
                mp_group = parser.add_argument_group(
                    "Concurrency mode",
                    description="These options are mutually exclusive; choose only one.",
                )
                mp_x_group = mp_group.add_mutually_exclusive_group(required=False)

                mp_x_group.add_argument(
                    "--no-mp",
                    action="store_true",
                    help="Disable multiprocessing (go to single process)",
                )
                mp_x_group.add_argument(
                    "--use-threads",
                    action="store_true",
                    help="Use threads instead of multiprocessing",
                )
            elif cls.mp_safe:
                concurrency_group.add_argument(
                    "--no-mp",
                    action="store_true",
                    help="Disable multiprocessing (go to single process)",
                )
            elif cls.thread_safe:
                concurrency_group.add_argument(
                    "--no-threads",
                    action="store_true",
                    help="Disable threads (go to single process)",
                )

            if cls.mp_safe:
                concurrency_group.add_argument(
                    "--process-limit",
                    type=int,
                    help="Maximum number of multiprocessing processes.",
                )
                concurrency_group.add_argument(
                    "--mp-start-method",
                    choices=["fork", "spawn", "forkserver"],
                    help="Force multiprocessing start method (for testing)",
                    default="spawn",
                )

            if cls.thread_safe:
                concurrency_group.add_argument(
                    "--thread-limit",
                    type=int,
                    help="Maximum number of threads.",
                    default=500,
                )

        cls.add_arguments(parser)
        return parser

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """
        Subclasses override to add CLI arguments.

        Args:
            parser (argparse.ArgumentParser): Argument parser.
        """
        return

    @classmethod
    def get_usage(cls, prog: Optional[str] = None) -> str:
        """Return a concise one-line usage string for this command."""
        parser = cls._build_parser()
        usage = parser.format_usage().strip()

        # Strip leading "usage:" and optional prog name
        if usage.startswith("usage:"):
            usage = usage[len("usage:") :].strip()

        if prog:
            parts = usage.split()
            if parts and parts[0] == prog:
                usage = " ".join(parts[1:])

        return usage

    @classmethod
    def args_post_process(cls, parser):
        """
        Subclasses override to validate args after parsing.
        """
        return

    def _resolve_concurrency(self):
        """
        Determine actual concurrency mode ('mp', 'threads', 'single')
        based on class flags and CLI arguments.
        """
        cls = self.__class__
        mode = "single"

        if getattr(cls, "mp_safe", False) and getattr(cls, "thread_safe", False):
            if getattr(self.args, "no_mp", False):
                mode = (
                    "threads" if getattr(self.args, "use_threads", False) else "single"
                )
            elif getattr(self.args, "use_threads", False):
                mode = "threads"
            else:
                mode = "mp"

        elif getattr(cls, "mp_safe", False):
            mode = "single" if getattr(self.args, "no_mp", False) else "mp"

        elif getattr(cls, "thread_safe", False):
            mode = "single" if getattr(self.args, "no_threads", False) else "threads"

        # Set instance attributes
        self.use_multiprocessing = mode == "mp"
        self.use_threads = mode == "threads"
        self.mp_model = ThreadPoolExecutor if mode == "threads" else ProcessPoolExecutor

    @classmethod
    def init_worker_logging(
        cls, log_queue: mp.Queue, log_level_str: str, prog_name: str, class_name: str
    ) -> None:
        """
        Initialize logging for worker processes.

        Args:
            log_queue (mp.Queue): Multiprocessing log queue.
            log_level_str (str): Log level as string.
            prog_name (str): Program name.
            class_name (str): Class name.
        """
        # Ignore KeyboardInterrupt in workers
        import signal

        signal.signal(signal.SIGINT, signal.SIG_IGN)

        log_level = getattr(logging, log_level_str.upper(), logging.INFO)
        BaseLoggerConfig(
            prog_name, log_level=log_level, log_queue=log_queue, is_worker=True
        )
        cls.post_init_worker()

    @classmethod
    def post_init_worker(cls):
        """Do nothing by default but allow classes to perform other initialization without modifying the init_worker_logging"""
        return

    def _get_file_handle(self, path: os.PathLike) -> TextIOWrapper:
        """
        Return the persistent file handle for the current process.
        Creates it on first call per process.

        Args:
            path (str): Path to the log file.

        Returns:
            object: File handle.
        """
        if not hasattr(self, "_fh"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._fh = open(path, "a", buffering=1)
        return self._fh

    def log_result(self, result: dict) -> None:
        """
        Append a message to the persistent log file safely across threads and processes.

        Args:
            message (str): Message to log.
        """
        import json

        if self._results_file_path:
            fh = self._get_file_handle(self._results_file_path)
            with self.mp_lock:  # process-level safety
                with self.thread_lock:  # thread-level safety
                    fh.write(f"{json.dumps(result)}\n")
                    fh.flush()

    def run_with_workers(
        self,
        func,
        iterable: list,
        max_workers: Optional[int] = None,
        exception_handler: Optional[Callable] = None,
    ) -> Optional[list]:
        """
        Run tasks with multiprocessing if enabled, else inline.

        Args:
            func (callable): Function to run on each item.
            iterable (list): Iterable of inputs.
            max_workers (int | None): Number of worker processes if multiprocessing enabled.
            exception_handler (callable | None): Exception handler.

        Returns:
            list | None: List of results or None if interrupted.
        """
        if exception_handler is None:

            def default_handler(future, exc, item):
                self.logger.exception("Error processing %s: %s", item, exc)

            exception_handler = default_handler

        if not self.use_multiprocessing and not self.use_threads:
            self.logger.notice("Running inline without multiprocessing")
            results = []
            for item in iterable:
                try:
                    results.append(func(item))
                except Exception as e:
                    exception_handler(None, e, item)
            return results

        if self.use_threads:
            max_workers = min(self.args.thread_limit, self.THREAD_LIMIT)
            self.logger.notice("Running with thread pool (max_threads=%s)", max_workers)
        else:
            max_workers = min(max_workers, self.args.process_limit, self.PROCESS_LIMIT)
            self.logger.notice(
                "Running with multiprocessing pool (max_workers=%s)", max_workers
            )

        self.logger.debug("Still in DEBUG %s", self.args)
        kwargs = {}
        if self.log_queue:
            kwargs["initializer"] = self.init_worker_logging
            kwargs["initargs"] = (
                self.log_queue,
                self.args.log_level,
                self.args.prog,
                self.class_name,
            )

        with self.mp_model(max_workers=max_workers, **kwargs) as pool:
            futures = {pool.submit(func, item): item for item in iterable}
            results = []
            try:
                # Use a small timeout loop to check futures and catch KeyboardInterrupt cleanly
                while futures:
                    done, _ = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
                    for future in done:
                        item = futures.pop(future)
                        try:
                            results.append(future.result())
                        except Exception as e:
                            exception_handler(future, e, item)

                    time.sleep(0.01)  # tiny sleep to reduce CPU and signal noise

            except KeyboardInterrupt:
                self.logger.warning(
                    "KeyboardInterrupt received, cancelling all workers..."
                )
                for future in futures:
                    future.cancel()
                pool.shutdown(wait=False)
                return None

        return results

    def shutdown_logging(self) -> None:
        """
        Stop logging listener if started.
        """
        if self.log_queue:
            # Wait until all log records processed
            self.log_queue.join()
            self.logger_config.stop_listener()

    def run(self) -> None:
        """
        Override this method in subclasses with your application logic.

        Raises:
            NotImplementedError: If not implemented in subclass.
        """
        raise NotImplementedError("Subclasses must implement run()")
