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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--sandbox", dest="sandbox", action="store_true", help="store credentials for sandbox/test mode (default)")
    mode.add_argument("--live", dest="sandbox", action="store_false", help="explicitly select live metadata; requires confirmation")
    parser.set_defaults(sandbox=True)
    parser.add_argument("--confirm-live", default="", help=argparse.SUPPRESS)
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
    if not args.sandbox and args.confirm_live != "I_UNDERSTAND_ORCA_LIVE":
        parser.error("live credential metadata requires --confirm-live I_UNDERSTAND_ORCA_LIVE")
    api_key = getpass.getpass(f"{args.exchange} API key: ")
    api_secret = getpass.getpass(f"{args.exchange} API secret: ")
    password = getpass.getpass("Password/passphrase (optional): ")
    uid = input("UID (optional): ").strip()
    vault.set_exchange(args.exchange, api_key, api_secret, password=password, uid=uid, sandbox=args.sandbox)
    label = "sandbox" if args.sandbox else "live metadata"
    print(f"stored {args.exchange} {label} credentials in the OS keyring; withdrawals remain disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
