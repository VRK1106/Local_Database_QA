"""CLI management commands for Developer administration."""

from __future__ import annotations
import click
from getpass import getpass
from src.auth import create_developer_account, get_user_by_username


@click.command("create-developer")
@click.argument("username", required=False, default=None)
@click.option("--username", "-u", "username_opt", default=None, help="Developer username")
@click.option("--password", "-p", default=None, help="Password (for non-interactive scripts only)")
def create_developer_cmd(username: str | None = None, username_opt: str | None = None, password: str | None = None):
    """CLI-only command to create a new developer account with all authorities."""
    uname = (username or username_opt or "").strip()
    if not uname:
        raise click.ClickException("Username is required. Usage: flask create-developer <username> or --username <username>")

    existing = get_user_by_username(uname)
    if existing:
        raise click.ClickException(f"User '{uname}' already exists.")

    if not password:
        pw = getpass("Enter developer password (min 12 characters): ")
        pw_confirm = getpass("Confirm developer password: ")
        if pw != pw_confirm:
            raise click.ClickException("Passwords do not match.")
    else:
        pw = password

    if len(pw) < 12:
        raise click.ClickException("Developer password must be at least 12 characters.")

    user_id = create_developer_account(uname, pw)
    click.echo(f"Successfully provisioned developer account '{uname}' (User ID: {user_id}).")
