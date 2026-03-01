#!/usr/bin/env python3
"""
Manage platform-level OAuth app registrations.

These are global (not tenant-scoped) OAuth apps. Tenants can opt-in
to use platform credentials instead of providing their own.

Usage:
    uv run python scripts/manage-platform-apps.py list
    uv run python scripts/manage-platform-apps.py register --provider google_workspace --client-id <ID> --redirect-uri <URI>
    uv run python scripts/manage-platform-apps.py delete --provider google_workspace
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from empla.models.database import get_db
from empla.services.integrations import PlatformOAuthAppService, get_token_manager

PROVIDERS = ["google_workspace", "microsoft_graph"]


async def cmd_list() -> None:
    """List all platform OAuth apps."""
    async with get_db() as db:
        service = PlatformOAuthAppService(db, get_token_manager())
        apps = await service.list_apps()

    if not apps:
        print("No platform OAuth apps registered.")
        return

    # Table header
    print(f"{'Provider':<22} {'Client ID':<40} {'Status':<10} {'Created At'}")
    print("-" * 100)
    for app in apps:
        created = app.created_at.strftime("%Y-%m-%d %H:%M") if app.created_at else "N/A"
        print(f"{app.provider:<22} {app.client_id:<40} {app.status:<10} {created}")


async def cmd_register(args: argparse.Namespace) -> None:
    """Register a new platform OAuth app."""
    client_secret = args.client_secret
    if not client_secret:
        client_secret = getpass.getpass("Client secret: ")
        if not client_secret:
            print("Error: Client secret is required.", file=sys.stderr)
            sys.exit(1)

    scopes = [s.strip() for s in args.scopes.split(",")] if args.scopes else []

    async with get_db() as db:
        service = PlatformOAuthAppService(db, get_token_manager())

        # Check if app already exists
        existing = await service.get_app(args.provider)
        if existing:
            print(
                f"Error: Platform app for '{args.provider}' already exists (id={existing.id}).",
                file=sys.stderr,
            )
            sys.exit(1)

        app = await service.create_app(
            provider=args.provider,
            client_id=args.client_id,
            client_secret=client_secret,
            redirect_uri=args.redirect_uri,
            scopes=scopes,
        )

    print("Registered platform OAuth app:")
    print(f"  Provider:     {app.provider}")
    print(f"  Client ID:    {app.client_id}")
    print(f"  Redirect URI: {app.redirect_uri}")
    print(f"  Scopes:       {', '.join(app.default_scopes) if app.default_scopes else '(none)'}")
    print(f"  App ID:       {app.id}")


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete a platform OAuth app."""
    confirm = input(f"Delete platform OAuth app for '{args.provider}'? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    async def _delete() -> None:
        async with get_db() as db:
            service = PlatformOAuthAppService(db, get_token_manager())
            await service.delete_app(args.provider)

    asyncio.run(_delete())
    print(f"Deleted platform OAuth app for '{args.provider}'.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage platform-level OAuth app registrations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List all platform OAuth apps")

    # register
    reg = subparsers.add_parser("register", help="Register a new platform OAuth app")
    reg.add_argument("--provider", required=True, choices=PROVIDERS, help="OAuth provider")
    reg.add_argument("--client-id", required=True, help="OAuth client ID")
    reg.add_argument(
        "--client-secret", default=None, help="OAuth client secret (prompted if omitted)"
    )
    reg.add_argument("--redirect-uri", required=True, help="OAuth redirect URI")
    reg.add_argument("--scopes", default=None, help="Comma-separated list of default scopes")

    # delete
    delete = subparsers.add_parser("delete", help="Delete a platform OAuth app")
    delete.add_argument(
        "--provider", required=True, choices=PROVIDERS, help="OAuth provider to delete"
    )

    args = parser.parse_args()

    if args.command == "list":
        asyncio.run(cmd_list())
    elif args.command == "register":
        asyncio.run(cmd_register(args))
    elif args.command == "delete":
        cmd_delete(args)


if __name__ == "__main__":
    main()
