"""FR-1096 AC-543/AC-544: AI keys are kept only in the OS credential vault, never in files, arguments or environment.

Windows: Credential Manager (CredWriteW / CredReadW / CredDeleteW through ctypes).
macOS:   the login keychain (SecKeychain*GenericPassword through ctypes; the value is passed in memory).
Linux:   Secret Service through `secret-tool`, the secret written to its standard input (never an argument).
Any other case is "unavailable" and the caller keeps the key in memory for this session only.

HVE_STUDIO_SECRET_STORE=memory|none replaces the vault in tests (memory: an in-process vault; none: unavailable).
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys

SERVICE = "HVE-Studio"
_MEMORY: dict[str, str] = {}


class StoreError(Exception):
    pass


def _target(name: str) -> str:
    return f"{SERVICE}:{name}"


def backend() -> str:
    forced = os.environ.get("HVE_STUDIO_SECRET_STORE")
    if forced in ("memory", "none"):
        return forced
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux") and shutil.which("secret-tool"):
        return "secret-tool"
    return "none"


def availability() -> dict:
    b = backend()
    if b == "none":
        reason = ("secret-tool (libsecret-tools) is not installed, so the Secret Service cannot be used without passing "
                  "the key as a command-line argument") if sys.platform.startswith("linux") else "no supported OS credential vault"
        return {"available": False, "backend": b, "reason": reason}
    return {"available": True, "backend": b, "reason": ""}


# ---------------------------------------------------------------- Windows
if sys.platform == "win32":
    from ctypes import wintypes

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", _FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_char)), ("Persist", wintypes.DWORD),
                    ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    _CRED_TYPE_GENERIC, _CRED_PERSIST_LOCAL_MACHINE, _ERROR_NOT_FOUND = 1, 2, 1168

    def _advapi():
        lib = ctypes.WinDLL("advapi32", use_last_error=True)
        lib.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), wintypes.DWORD]
        lib.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
        lib.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        lib.CredFree.argtypes = [ctypes.c_void_p]
        return lib

    def _win_save(name: str, secret: str) -> None:
        blob = secret.encode("utf-16-le")
        buf = ctypes.create_string_buffer(blob, len(blob))
        cred = _CREDENTIAL(Type=_CRED_TYPE_GENERIC, TargetName=_target(name), CredentialBlobSize=len(blob),
                           CredentialBlob=ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)),
                           Persist=_CRED_PERSIST_LOCAL_MACHINE, UserName=SERVICE)
        try:
            if not _advapi().CredWriteW(ctypes.byref(cred), 0):
                raise StoreError(f"CredWriteW failed (error {ctypes.get_last_error()})")
        finally:
            ctypes.memset(buf, 0, len(blob))

    def _win_load(name: str) -> str | None:
        lib = _advapi()
        ptr = ctypes.POINTER(_CREDENTIAL)()
        if not lib.CredReadW(_target(name), _CRED_TYPE_GENERIC, 0, ctypes.byref(ptr)):
            err = ctypes.get_last_error()
            if err == _ERROR_NOT_FOUND:
                return None
            raise StoreError(f"CredReadW failed (error {err})")
        try:
            c = ptr.contents
            return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-16-le")
        finally:
            lib.CredFree(ptr)

    def _win_delete(name: str) -> None:
        if not _advapi().CredDeleteW(_target(name), _CRED_TYPE_GENERIC, 0):
            err = ctypes.get_last_error()
            if err != _ERROR_NOT_FOUND:
                raise StoreError(f"CredDeleteW failed (error {err})")


# ---------------------------------------------------------------- macOS
def _sec():
    lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Security.framework/Security")
    lib.SecKeychainAddGenericPassword.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
                                                  ctypes.c_char_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    lib.SecKeychainFindGenericPassword.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
                                                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32),
                                                   ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
    lib.SecKeychainItemDelete.argtypes = [ctypes.c_void_p]
    lib.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    return lib


_ERR_SEC_ITEM_NOT_FOUND = -25300


def _mac_find(name: str):
    lib, svc, acct = _sec(), SERVICE.encode(), name.encode()
    length, data, item = ctypes.c_uint32(), ctypes.c_void_p(), ctypes.c_void_p()
    rc = lib.SecKeychainFindGenericPassword(None, len(svc), svc, len(acct), acct, ctypes.byref(length),
                                            ctypes.byref(data), ctypes.byref(item))
    if rc == _ERR_SEC_ITEM_NOT_FOUND:
        return lib, None, None
    if rc != 0:
        raise StoreError(f"SecKeychainFindGenericPassword failed ({rc})")
    value = ctypes.string_at(data, length.value).decode("utf-8")
    lib.SecKeychainItemFreeContent(None, data)
    return lib, value, item


def _mac_delete(name: str) -> None:
    lib, _, item = _mac_find(name)
    if item is not None:
        rc = lib.SecKeychainItemDelete(item)
        if rc != 0:
            raise StoreError(f"SecKeychainItemDelete failed ({rc})")


def _mac_save(name: str, secret: str) -> None:
    _mac_delete(name)
    lib, svc, acct = _sec(), SERVICE.encode(), name.encode()
    blob = secret.encode("utf-8")
    buf = ctypes.create_string_buffer(blob, len(blob))
    try:
        rc = lib.SecKeychainAddGenericPassword(None, len(svc), svc, len(acct), acct, len(blob), buf, None)
    finally:
        ctypes.memset(buf, 0, len(blob))
    if rc != 0:
        raise StoreError(f"SecKeychainAddGenericPassword failed ({rc})")


# ---------------------------------------------------------------- Linux (secret-tool reads the secret from stdin)
def _st(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["secret-tool", *args], input=stdin, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise StoreError(f"secret-tool failed: {exc}") from exc


def _attrs(name: str) -> list[str]:
    return ["service", SERVICE, "account", name]


# ---------------------------------------------------------------- public API
def save(name: str, secret: str) -> None:
    b = backend()
    if b == "memory":
        _MEMORY[name] = secret
    elif b == "windows":
        _win_save(name, secret)
    elif b == "macos":
        _mac_save(name, secret)
    elif b == "secret-tool":
        r = _st(["store", f"--label={SERVICE} AI key", *_attrs(name)], stdin=secret)
        if r.returncode:
            raise StoreError((r.stderr or "secret-tool store failed").strip())
    else:
        raise StoreError(availability()["reason"])


def load(name: str) -> str | None:
    b = backend()
    if b == "memory":
        return _MEMORY.get(name)
    if b == "windows":
        return _win_load(name)
    if b == "macos":
        return _mac_find(name)[1]
    if b == "secret-tool":
        r = _st(["lookup", *_attrs(name)])
        return r.stdout.rstrip("\n") if r.returncode == 0 and r.stdout else None
    return None


def delete(name: str) -> None:
    b = backend()
    if b == "memory":
        _MEMORY.pop(name, None)
    elif b == "windows":
        _win_delete(name)
    elif b == "macos":
        _mac_delete(name)
    elif b == "secret-tool":
        r = _st(["clear", *_attrs(name)])
        if r.returncode not in (0, 1):
            raise StoreError((r.stderr or "secret-tool clear failed").strip())
    else:
        raise StoreError(availability()["reason"])


def exists(name: str) -> bool:
    try:
        return load(name) is not None
    except StoreError:
        return False
