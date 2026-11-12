"""Sandbox configuration and explicit authentication-only checks.

The maintained private file is read as data, never sourced as shell code.
"""
import os
import shlex
import stat
import urllib.error
from pathlib import Path

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
_KEYS = {"PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_BASE_URL"}


class SandboxConfigurationError(ValueError):
    pass


def _private_file():
    return Path.home() / ".config" / "royalty-loom" / "paypal-sandbox.env"


def _read_private_file():
    # Portable launchers on other platforms remain environment-only.
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "getuid"):
        return {}
    try:
        fd = os.open(_private_file(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {}
    except OSError:
        raise SandboxConfigurationError("Could not read the private Sandbox configuration file.") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise SandboxConfigurationError("The private Sandbox configuration must be a regular file owned by this user with owner-only permissions.")
        if info.st_size > 16384:
            raise SandboxConfigurationError("The private Sandbox configuration file is too large.")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = None
            body = stream.read(16385)
        if len(body) > 16384:
            raise SandboxConfigurationError("The private Sandbox configuration file is too large.")
    except (OSError, UnicodeError):
        raise SandboxConfigurationError("Could not read the private Sandbox configuration file.") from None
    finally:
        if fd is not None:
            os.close(fd)
    values = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or key not in _KEYS or key in values:
            raise SandboxConfigurationError("The private Sandbox configuration contains an unsupported or duplicate setting.")
        # Reject shell expressions instead of treating them as credentials.
        if any(char in value for char in ("$", "`", "\x00", ";", "|", "&", "<", ">")):
            raise SandboxConfigurationError("The private Sandbox configuration must contain literal values, without shell expressions.")
        try:
            parts = shlex.split(value, comments=True, posix=True)
        except ValueError:
            raise SandboxConfigurationError("The private Sandbox configuration contains an invalid quoted value.") from None
        if len(parts) != 1 or not parts[0].strip():
            raise SandboxConfigurationError("The private Sandbox configuration contains an empty or invalid value.")
        values[key] = parts[0]
    return values


def credentials():
    # A partial explicit pair must not be combined with another app's secret.
    explicit = any(key in os.environ for key in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"))
    values = os.environ if explicit else _read_private_file()
    base = os.environ.get("PAYPAL_BASE_URL", values.get("PAYPAL_BASE_URL", SANDBOX_BASE))
    if base.rstrip("/") != SANDBOX_BASE:
        raise SandboxConfigurationError("Only the PayPal Sandbox endpoint is supported.")
    client_id = values.get("PAYPAL_CLIENT_ID", "").strip()
    secret = values.get("PAYPAL_CLIENT_SECRET", "").strip()
    if bool(client_id) != bool(secret):
        raise SandboxConfigurationError("Provide both Sandbox credentials from the same app; a partial environment pair does not use the private file.")
    return client_id, secret


def configuration():
    try:
        client_id, secret = credentials()
        configured = bool(client_id and secret)
    except SandboxConfigurationError:
        configured = False
    return {"sandbox_credentials_configured": configured}


def check_authentication(request):
    try:
        client_id, secret = credentials()
    except SandboxConfigurationError as exc:
        return {"authenticated": False, "message": str(exc)}
    if not client_id or not secret:
        return {"authenticated": False, "message": "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET privately before launching the app, or use the maintained private Sandbox configuration file. Use credentials from your existing Sandbox app."}
    try:
        response = request(SANDBOX_BASE + "/v1/oauth2/token", "POST", b"grant_type=client_credentials", basic=client_id + ":" + secret)
        if not isinstance(response, dict) or not isinstance(response.get("access_token"), str) or not response["access_token"].strip():
            return {"authenticated": False, "message": "Invalid Sandbox authentication response. Retry the check; no payout was requested."}
    except urllib.error.HTTPError as exc:
        message = ("Sandbox rejected these credentials. Check that both belong to the same Sandbox app and restart." if exc.code in (400, 401, 403) else "Sandbox authentication is temporarily unavailable. Retry the check later.")
        return {"authenticated": False, "message": message}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
        return {"authenticated": False, "message": "Could not authenticate with PayPal Sandbox. Check the network and retry. No payout was requested."}
    return {"authenticated": True, "message": "Sandbox authentication succeeded. Payouts entitlement, balance and recipient accounts remain unverified. No payout was requested."}
