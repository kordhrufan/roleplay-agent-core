"""Explicit current-user DPAPI roundtrip on a synthetic temporary file only."""

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forum_watch.discord_secret import WindowsVault
from forum_watch.models import WatchError

def main():
    value = "https://discord.com/api/webhooks/123456789012345678/SYNTHETIC_VAULT_CANARY_NOT_A_REAL_TOKEN"
    with tempfile.TemporaryDirectory(prefix="forum-discord-dpapi-") as folder:
        path = Path(folder) / "canary.dpapi"
        vault = WindowsVault(path)
        vault.write(value)
        checked = vault.read() == value
        encrypted = value.encode("ascii") not in path.read_bytes()
    print(json.dumps({"result": "DPAPI_CANARY_OK" if checked and encrypted else "DPAPI_CANARY_FAILED",
                      "read_matches_synthetic_value": checked, "file_contains_no_plaintext": encrypted,
                      "own_test_directory_removed": not Path(folder).exists(),
                      "production_credential_accessed": False}))
    return 0 if checked and encrypted else 2

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WatchError as error:
        print(json.dumps({"result":"DPAPI_CANARY_FAILED","error":error.code,"details":error.details,"secret_displayed":False}))
        raise SystemExit(2)
    except (OSError, UnicodeError):
        print('{"result":"DPAPI_CANARY_FAILED","secret_displayed":false}')
        raise SystemExit(2)

