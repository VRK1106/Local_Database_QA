"""CLI management commands for Developer administration."""

from __future__ import annotations
import click
from getpass import getpass
from src.auth import create_developer_account, get_user_by_username


@click.command("create-developer")
@click.argument("username")
@click.option("--password", "-p", default=None, help="Password (for non-interactive scripts only)")
def create_developer_cmd(username: str, password: str | None = None):
    """CLI-only command to create a new developer account with all authorities."""
    existing = get_user_by_username(username)
    if existing:
        raise click.ClickException(f"User '{username}' already exists.")

    if not password:
        pw = getpass("Enter developer password (min 12 characters): ")
        pw_confirm = getpass("Confirm developer password: ")
        if pw != pw_confirm:
            raise click.ClickException("Passwords do not match.")
    else:
        pw = password

    if len(pw) < 12:
        raise click.ClickException("Developer password must be at least 12 characters.")

    user_id = create_developer_account(username, pw)
    click.echo(f"Successfully provisioned developer account '{username}' (User ID: {user_id}).")
