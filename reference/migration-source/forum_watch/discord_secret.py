"""Current-user Windows DPAPI secret file; only explicit notifier code decrypts it."""

import ctypes
from ctypes import wintypes
import getpass
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

from .models import WatchError, require

WEBHOOK = re.compile(r"https://discord\.com/api/(?:v10/)?webhooks/([0-9]{15,22})/([A-Za-z0-9_-]{20,256})")


def webhook_path(value):
    match = WEBHOOK.fullmatch(value) if isinstance(value, str) else None
    require(match is not None, "INVALID_DISCORD_WEBHOOK",
            "Use a standard HTTPS discord.com webhook without query, fragment or thread parameters; value not shown.")
    return "/api/v10/webhooks/" + match[1] + "/" + match[2] + "?wait=true"


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, *, protect):
    require(os.name == "nt", "WINDOWS_CREDENTIALS_REQUIRED", "Current-user Windows DPAPI is required.")
    api = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    function = api.CryptProtectData if protect else api.CryptUnprotectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel = ctypes.WinDLL("kernel32.dll")
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    raw = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming, outgoing = Blob(len(data), raw), Blob()
    try:
        # UI_FORBIDDEN=1. LOCAL_MACHINE is deliberately NOT set: user scope.
        ok = function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
        if not ok:
            raise WatchError("DISCORD_DPAPI_FAILED", "Windows could not protect/unprotect this user's secret.",
                             {"winerror": ctypes.get_last_error()}) from None
        require(0 < outgoing.size <= 16384, "INVALID_DISCORD_CREDENTIAL", "Protected data has an invalid size.")
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.memset(raw, 0, len(data))
        if outgoing.data:
            ctypes.memset(outgoing.data, 0, outgoing.size)
            kernel.LocalFree(outgoing.data)


class WindowsVault:
    """Encrypted operational file, no plaintext credential file or project config."""

    def __init__(self, path=None):
        require(os.name == "nt" and os.environ.get("LOCALAPPDATA"), "WINDOWS_CREDENTIALS_REQUIRED",
                "Current-user Windows DPAPI is required.")
        candidate = Path(path) if path is not None else (
            Path(os.environ["LOCALAPPDATA"]) / "NozomuForumWatch" / "secrets" / "discord-webhook.dpapi")
        protected_tree = Path(__file__).resolve().parents[2]
        require(not candidate.is_symlink() and not candidate.resolve().is_relative_to(protected_tree),
                "PROTECTED_PATH", "Secret must be stored outside the character tree.")
        self.path = candidate.resolve()

    def read(self):
        require(self.path.is_file() and 0 < self.path.stat().st_size <= 16384,
                "DISCORD_SECRET_UNAVAILABLE", "Configure the webhook locally for this Windows user.")
        value = crypt(self.path.read_bytes(), protect=False).decode("ascii")
        webhook_path(value)
        return value

    def write(self, value):
        webhook_path(value)
        encrypted = crypt(value.encode("ascii"), protect=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.parent / ("discord-secret-" + uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
        finally:
            if temporary.exists():
                temporary.unlink()  # Only this operation's encrypted temporary file.


def read_webhook():
    return WindowsVault().read()


def configure():
    require(sys.stdin.isatty(), "LOCAL_INTERACTIVE_INPUT_REQUIRED",
            "Run configure-discord in your local terminal; do not pass a webhook as an argument or through chat.")
    value = getpass.getpass("Webhook de Discord (entrada oculta, solo en este equipo): ")
    try:
        WindowsVault().write(value.strip())
    except (UnicodeError, OSError):
        raise WatchError("DISCORD_SECRET_WRITE_FAILED", "Unable to store the encrypted secret; value not shown.") from None
    finally:
        value = None
    return {"result": "DISCORD_SECRET_CONFIGURED", "storage": "WINDOWS_DPAPI_CURRENT_USER",
            "value_displayed": False, "message_sent": False}

