import json
import os
import time
from threading import RLock
from typing import Optional

import keyring
from cryptography.fernet import Fernet, InvalidToken
from keyring.errors import InitError, NoKeyringError

# f"{env}:{identity}:{type}:{scope}"
# f"{stack}:{host}:{type}:{identity}" # "wf_lp:API:wf_lp.splunkcloud.com::token_id" -> token_value
# "wf_lp:STACK:LOGIN:username" -> password
# "wf_lp:STACK:API:token_id" -> token_value


class SecureStore:
    """Singleton secure credential store with in-memory write-through cache."""

    _instance: "SecureStore | None" = None
    _lock = RLock()

    def __new__(cls, service_name: str = "myapp", fallback_file: str | None = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, service_name: str = "myapp", fallback_file: str | None = None):
        if self._initialized:
            return
        self.service_name = service_name
        self.fallback_file = fallback_file or os.path.expanduser(
            f"~/.{service_name}_secrets.json"
        )
        self._cache: dict[str, str] = {}
        self._initialized = True

    # ---------------------
    # Public API
    # ---------------------
    def get_secret(self, username: str) -> str | None:
        """Retrieve secret from cache, keyring, or fallback."""
        with self._lock:
            # 1️⃣ Memory cache
            if username in self._cache:
                return self._cache[username]

            # 2️⃣ System keyring
            secret = keyring.get_password(self.service_name, username)
            if secret:
                self._cache[username] = secret
                return secret

            # 3️⃣ Fallback encrypted file
            data = self._file_load_data()
            if data and username in data:
                self._cache[username] = data[username]
                return data[username]

            return None

    def set_secret(self, username: str, password: str) -> None:
        """Store secret in cache, keyring, and fallback file."""
        with self._lock:
            # 1️⃣ Update memory cache
            self._cache[username] = password

            # 2️⃣ Write-through to keyring
            keyring.set_password(self.service_name, username, password)

            # 3️⃣ Write-through to encrypted fallback file
            data = self._file_load_data() or {}
            data[username] = password
            self._file_save_data(data)

    def clear_secret(self, username: str) -> None:
        """Remove secret from cache and storage."""
        with self._lock:
            self._cache.pop(username, None)
            try:
                keyring.delete_password(self.service_name, username)
            except keyring.errors.PasswordDeleteError:
                pass
            data = self._file_load_data() or {}
            data.pop(username, None)
            self._file_save_data(data)

    def clear_cache(self):
        """Clear in-memory cache only (keep persisted)."""
        with self._lock:
            self._cache.clear()

    # ---------------------
    # Fallback file helpers
    # ---------------------
    def _file_key(self) -> bytes:
        key_path = f"{self.fallback_file}.key"
        if os.path.exists(key_path):
            return open(key_path, "rb").read()
        key = Fernet.generate_key()
        with open(key_path, "wb") as f:
            f.write(key)
        return key

    def _file_load_data(self) -> dict | None:
        if not os.path.exists(self.fallback_file):
            return {}
        try:
            with open(self.fallback_file, "rb") as f:
                cipher = Fernet(self._file_key())
                decrypted = cipher.decrypt(f.read())
                return json.loads(decrypted.decode("utf-8"))
        except (InvalidToken, json.JSONDecodeError):
            return None

    def _file_save_data(self, data: dict):
        cipher = Fernet(self._file_key())
        encrypted = cipher.encrypt(json.dumps(data).encode("utf-8"))
        with open(self.fallback_file, "wb") as f:
            f.write(encrypted)


class SecureStore:
    _instance = None
    _cache = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _make_key(self, env: str, identity: str, ctype: str, scope: str) -> str:
        return f"{env}:{identity}:{ctype}:{scope}"

    def get(
        self,
        env: str,
        identity: str,
        ctype: str,
        scope: str,
        *,
        refresh=False,
    ):
        key = self._make_key(env, identity, ctype, scope)
        if not refresh and key in self._cache:
            entry = self._cache[key]
            if entry["expires"] is None or entry["expires"] > time.time():
                return entry["value"]

        # Retrieve from backend (file, keyring, vault, etc.)
        value, expires = self._load_from_backend(key)

        # Cache it (write-through)
        self._cache[key] = {"value": value, "expires": expires}
        return value

    def set(
        self,
        env: str,
        identity: str,
        ctype: str,
        scope: str,
        value,
        ttl: Optional[int] = None,
    ):
        key = self._make_key(env, identity, ctype, scope)
        expires = time.time() + ttl if ttl else None
        self._cache[key] = {"value": value, "expires": expires}
        self._save_to_backend(key, value, expires)

    def _load_from_backend(self, key):
        # TODO: implement persistent lookup (file, keyring, DB, etc.)
        return None, None

    def _save_to_backend(self, key, value, expires):
        # TODO: implement persistent write
        pass
