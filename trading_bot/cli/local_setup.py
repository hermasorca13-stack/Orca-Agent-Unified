"""Interactive local API-key setup; values are read without command-line exposure."""
from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from trading_bot.security.vault import LocalApiVault


def main() -> int:
    parser = argparse.ArgumentParser(prog="orca-api-setup")
    parser.add_argument("action", choices=("set", "list", "delete"))
    parser.add_argument("exchange", nargs="?")
    parser.add_argument("--metadata", default="data/orca_max_mouny/credentials.json")
    parser.add_argument("--sandbox", action="store_true", default=False)
    args = parser.parse_args()
    vault = LocalApiVault(Path(args.metadata))
    if args.action == "list":
        print(vault.list_exchanges())
        return 0
    if not args.exchange:
        parser.error("exchange is required for set/delete")
    if args.action == "delete":
        vault.delete_exchange(args.exchange)
        print(f"deleted metadata and credentials for {args.exchange}")
        return 0
    api_key = getpass.getpass(f"{args.exchange} API key: ")
    api_secret = getpass.getpass(f"{args.exchange} API secret: ")
    password = getpass.getpass("Password/passphrase (optional): ")
    uid = input("UID (optional): ").strip()
    vault.set_exchange(args.exchange, api_key, api_secret, password=password, uid=uid, sandbox=args.sandbox)
    print(f"stored {args.exchange} credentials in the OS keyring; withdrawals remain disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
