"""agentpack command line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from agentpack import API_VERSION, __version__
from agentpack.core import edit, mcp_import, scaffold
from agentpack.core.builder import build as run_build
from agentpack.core.diagnostics import AgentPackError, Diagnostics, Severity
from agentpack.core.loader import load_package, resolve_manifest
from agentpack.core.registry import registry
from agentpack.core.validator import validate as run_validate
from agentpack.models.package import KnowledgeMode

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Author AI agent capabilities once; package them for many AI clients.",
)

ProjectOpt = Annotated[
    Path, typer.Option("--project", "-p", help="Project directory (default: search upwards).")
]
FileOpt = Annotated[
    Path | None,
    typer.Option(
        "--file",
        "-f",
        help="Manifest to use, any filename. Paths inside it resolve relative to it.",
    ),
]
TargetOpt = Annotated[
    list[str] | None, typer.Option("--target", "-t", help="Target to build. Repeatable.")
]


def _echo_diagnostics(diags: Diagnostics) -> None:
    colors = {
        Severity.ERROR: typer.colors.RED,
        Severity.WARNING: typer.colors.YELLOW,
        Severity.INFO: typer.colors.CYAN,
    }
    for d in diags:
        typer.secho(d.render(), fg=colors[d.severity])


def _fail(exc: AgentPackError) -> typer.Exit:
    typer.secho(f"ERROR {exc}", fg=typer.colors.RED)
    return typer.Exit(code=1)


def _load(project: Path, file: Path | None = None) -> tuple:
    diags = Diagnostics()
    try:
        package = load_package(file if file is not None else project, diags)
    except AgentPackError as exc:
        raise _fail(exc) from None
    return package, diags


def main() -> None:
    """Console entry point: turn AgentPackError into a clean exit."""
    try:
        app()
    except AgentPackError as exc:
        typer.secho(f"ERROR {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None


@app.command()
def init(
    directory: Annotated[Path, typer.Argument(help="Directory to create.")] = Path("."),
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="Package name (default: directory name).")
    ] = None,
    file: Annotated[
        str, typer.Option("--file", "-f", help="Manifest filename to create.")
    ] = "agentpack.yaml",
    bare: Annotated[
        bool, typer.Option("--bare", help="Manifest only; no example skill or MCP server.")
    ] = False,
) -> None:
    """Scaffold a new AgentPack project."""
    package_name = name or directory.resolve().name
    created = scaffold.init_project(directory, package_name, file, bare=bare)
    if not created:
        typer.secho(f"Nothing to do: {directory} already has these files.", fg=typer.colors.YELLOW)
        return

    typer.secho(f"Created {package_name} in {directory}", fg=typer.colors.GREEN)
    for path in created:
        typer.echo(f"  {path}")
    if file not in ("agentpack.yaml", "agentpack.yml"):
        typer.echo(f"\nPass -f {file} to every command, or rename it to agentpack.yaml.")


@app.command()
def validate(
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
    target: TargetOpt = None,
) -> None:
    """Validate the canonical project and its target compatibility."""
    pkg, diags = _load(project, file)
    diags.extend(run_validate(pkg, list(target) if target else None))
    _echo_diagnostics(diags)

    if diags.has_errors():
        typer.secho(f"Validation failed ({len(diags.errors)} error(s)).", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(
        f"OK: {len(pkg.skills)} skill(s), {len(pkg.mcp_servers)} MCP server(s), "
        f"{len(pkg.targets)} target(s), {len(diags.warnings)} warning(s).",
        fg=typer.colors.GREEN,
    )


@app.command()
def inspect(
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
    format: Annotated[str, typer.Option("--format", help="yaml or json")] = "yaml",
) -> None:
    """Print the normalized model that adapters receive."""
    pkg, _ = _load(project, file)
    data = json.loads(pkg.model_dump_json(by_alias=True, exclude_none=True))
    typer.echo(
        json.dumps(data, indent=2)
        if format == "json"
        else yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    )


@app.command()
def build(
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
    target: TargetOpt = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    strict: Annotated[bool, typer.Option("--strict", help="Fail on any warning.")] = False,
    knowledge: Annotated[
        KnowledgeMode | None,
        typer.Option("--knowledge", help="Ship skill references/ or have an MCP serve them."),
    ] = None,
    archive: Annotated[
        bool, typer.Option("--archive", help="Also emit distributable archives.")
    ] = False,
) -> None:
    """Build client packages into dist/."""
    pkg, diags = _load(project, file)
    if diags.has_errors():
        _echo_diagnostics(diags)
        raise typer.Exit(code=1)
    if knowledge:
        pkg.build.knowledge = knowledge

    summary = run_build(
        pkg,
        targets=list(target) if target else None,
        output_dir=output,
        strict=strict,
        archive=archive,
    )
    _echo_diagnostics(summary.diagnostics)

    if not summary.ok:
        typer.secho("Build failed.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if strict and summary.diagnostics.warnings:
        typer.secho("Build failed (strict mode: warnings present).", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(f"{'TARGET':<20}{'TYPE':<24}{'FILES':>6}")
    for result in summary.results:
        typer.echo(f"{result.target:<20}{result.artifact_type.value:<24}{len(result.files):>6}")
        for path in result.archives:
            typer.echo(f"{'':<20}{path}")
    if summary.install_guide_path:
        typer.secho(f"\nInstall guide:  {summary.install_guide_path}", fg=typer.colors.GREEN)
    if summary.manifest_path:
        typer.echo(f"Build manifest: {summary.manifest_path}")


@app.command(name="package")
def package_cmd(
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
    target: TargetOpt = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    strict: Annotated[bool, typer.Option("--strict", help="Fail on any warning.")] = False,
    knowledge: Annotated[
        KnowledgeMode | None,
        typer.Option("--knowledge", help="Ship skill references/ or have an MCP serve them."),
    ] = None,
) -> None:
    """Build and emit distributable archives (dist/packages/)."""
    build(
        project=project,
        file=file,
        target=target,
        output=output,
        strict=strict,
        knowledge=knowledge,
        archive=True,
    )


@app.command(name="list-targets")
def list_targets(
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """List registered target adapters."""
    for adapter in registry.all():
        caps = adapter.capabilities()
        flag = " (experimental)" if caps.experimental else ""
        typer.echo(f"{adapter.name:<20}{caps.artifact_type.value}{flag}")
        if verbose:
            typer.echo(
                f"{'':<20}skills={caps.skills.value} stdio={caps.mcp_stdio.value} "
                f"http={caps.mcp_http.value} user-config={caps.user_config.value} "
                f"hooks={caps.hooks.value}"
            )


@app.command()
def clean(
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
    output: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Remove the build output directory."""
    import shutil

    pkg, _ = _load(project, file)
    out = output or (pkg.project_dir / pkg.build.output)
    if out.exists():
        shutil.rmtree(out)
        typer.secho(f"Removed {out}", fg=typer.colors.GREEN)
    else:
        typer.echo(f"Nothing to clean at {out}")


@app.command()
def doctor(project: ProjectOpt = Path("."), file: FileOpt = None) -> None:
    """Report environment and project health."""
    import sys

    typer.echo(f"agentpack   {__version__}")
    typer.echo(f"apiVersion  {API_VERSION}")
    typer.echo(f"python      {sys.version.split()[0]}")
    typer.echo(f"targets     {', '.join(registry.names())}")
    try:
        manifest = resolve_manifest(file if file is not None else project)
        typer.secho(f"manifest    {manifest}", fg=typer.colors.GREEN)
        pkg, diags = _load(project, manifest)
        typer.echo(f"skills      {len(pkg.skills)}")
        typer.echo(f"mcp servers {len(pkg.mcp_servers)}")
        _echo_diagnostics(diags)
    except AgentPackError as exc:
        typer.secho(f"manifest    none ({exc})", fg=typer.colors.YELLOW)


@app.command()
def version() -> None:
    """Print the AgentPack version."""
    typer.echo(__version__)


# --------------------------------------------------------------------------
# Manifest editing
# --------------------------------------------------------------------------
skill_app = typer.Typer(no_args_is_help=True, help="Register skill paths in the manifest.")
mcp_app = typer.Typer(no_args_is_help=True, help="Manage MCP server definitions.")
app.add_typer(skill_app, name="skill")
app.add_typer(mcp_app, name="mcp")


def _open_manifest(project: Path, file: Path | None):
    try:
        manifest = resolve_manifest(file if file is not None else project)
    except AgentPackError as exc:
        raise _fail(exc) from None
    return manifest, edit.read_doc(manifest)


@skill_app.command("add")
def skill_add(
    path: Annotated[str, typer.Argument(help="Skill directory, relative to the manifest.")],
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
) -> None:
    """Register a skill path. Does nothing if it is already covered."""
    manifest, doc = _open_manifest(project, file)

    covering = edit.covering_entry(doc, "skills", path)
    if covering:
        typer.secho(
            f"Already registered via 'skills: {covering}' — nothing to change.",
            fg=typer.colors.YELLOW,
        )
    else:
        edit.add_entry(doc, "skills", path)
        edit.write_doc(manifest, doc)
        typer.secho(f"Registered skills: {edit.normalize(path)}", fg=typer.colors.GREEN)

    target = manifest.parent / path
    if not (target / "SKILL.md").is_file():
        typer.secho(
            f"Note: {edit.normalize(path)}/SKILL.md does not exist yet.", fg=typer.colors.YELLOW
        )


@skill_app.command("remove")
def skill_remove(
    path: Annotated[str, typer.Argument(help="Skill path to unregister.")],
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
) -> None:
    """Unregister a skill path. Files on disk are left alone."""
    manifest, doc = _open_manifest(project, file)
    if not edit.remove_entry(doc, "skills", path):
        typer.secho(f"'{edit.normalize(path)}' is not registered.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    edit.write_doc(manifest, doc)
    typer.secho(f"Unregistered skills: {edit.normalize(path)}", fg=typer.colors.GREEN)


TransportOpt = Annotated[
    str, typer.Option("--transport", "-t", help="stdio, http or sse.")
]
CommandOpt = Annotated[str | None, typer.Option("--command", "-c", help="stdio executable.")]
ArgsOpt = Annotated[
    list[str] | None, typer.Option("--arg", "-a", help="stdio argument. Repeatable, ordered.")
]
UrlOpt = Annotated[str | None, typer.Option("--url", "-u", help="Endpoint URL for http/sse.")]
EnvOpt = Annotated[
    list[str] | None,
    typer.Option("--env", "-e", help="KEY for a user-supplied value, or KEY=VALUE for a literal."),
]
SecretOpt = Annotated[
    list[str] | None, typer.Option("--secret", "-s", help="KEY of a user-supplied secret.")
]
HeaderOpt = Annotated[
    list[str] | None, typer.Option("--header", help="Secret HTTP header name, e.g. Authorization.")
]


@mcp_app.command("add")
def mcp_add(
    name: Annotated[str, typer.Argument(help="Server name.")],
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
    transport: TransportOpt = "stdio",
    command: CommandOpt = None,
    arg: ArgsOpt = None,
    cwd: Annotated[str | None, typer.Option("--cwd")] = None,
    url: UrlOpt = None,
    env: EnvOpt = None,
    secret: SecretOpt = None,
    header: HeaderOpt = None,
    description: Annotated[str, typer.Option("--description", "-d")] = "",
    display_name: Annotated[str | None, typer.Option("--display-name")] = None,
) -> None:
    """Create an MCP definition and register it."""
    manifest, doc = _open_manifest(project, file)
    mcp_dir = edit.default_dir(doc, "mcp", edit.DEFAULT_MCP_DIR)
    target = manifest.parent / mcp_dir / f"{name}.yaml"

    if target.exists():
        typer.secho(
            f"{mcp_dir}/{name}.yaml already exists. Use 'agentpack mcp update'.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    try:
        server = edit.mcp_document(
            name,
            transport=transport,
            description=description,
            display_name=display_name,
            command=command,
            args=list(arg or []),
            cwd=cwd,
            url=url,
            env=list(env or []),
            secret_env=list(secret or []),
            headers=list(header or []),
        )
    except AgentPackError as exc:
        raise _fail(exc) from None

    edit.write_doc(target, server)
    typer.secho(f"Created {mcp_dir}/{name}.yaml", fg=typer.colors.GREEN)

    if edit.covering_entry(doc, "mcp", f"{mcp_dir}/{name}.yaml"):
        typer.echo(f"Already covered by 'mcp: {mcp_dir}'.")
    else:
        edit.add_entry(doc, "mcp", mcp_dir)
        edit.write_doc(manifest, doc)
        typer.secho(f"Registered mcp: {mcp_dir}", fg=typer.colors.GREEN)


@mcp_app.command("update")
def mcp_update(
    name: Annotated[str, typer.Argument(help="Server name.")],
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
    transport: Annotated[str | None, typer.Option("--transport", "-t")] = None,
    command: CommandOpt = None,
    arg: ArgsOpt = None,
    cwd: Annotated[str | None, typer.Option("--cwd")] = None,
    url: UrlOpt = None,
    env: EnvOpt = None,
    secret: SecretOpt = None,
    remove_env: Annotated[
        list[str] | None, typer.Option("--remove-env", help="Environment key to drop.")
    ] = None,
    header: HeaderOpt = None,
    description: Annotated[str, typer.Option("--description", "-d")] = "",
    display_name: Annotated[str | None, typer.Option("--display-name")] = None,
) -> None:
    """Change fields of an existing MCP definition, leaving the rest intact."""
    manifest, doc = _open_manifest(project, file)
    target = _find_mcp_file(manifest, doc, name)

    server = edit.read_doc(target)
    changed = edit.apply_mcp_updates(
        server,
        transport=transport,
        command=command,
        args=list(arg or []),
        cwd=cwd,
        url=url,
        env=list(env or []),
        secret_env=list(secret or []),
        remove_env=list(remove_env or []),
        headers=list(header or []),
        description=description,
        display_name=display_name,
    )
    if not changed:
        typer.secho("No options given — nothing changed.", fg=typer.colors.YELLOW)
        return

    edit.write_doc(target, server)
    typer.secho(f"Updated {target.name}: {', '.join(changed)}", fg=typer.colors.GREEN)


@mcp_app.command("import")
def mcp_import_cmd(
    source: Annotated[Path, typer.Argument(help="JSON file holding one or more MCP servers.")],
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Import only this server, or name a bare server object."),
    ] = None,
    update: Annotated[
        bool, typer.Option("--update", "-u", help="Merge into existing definitions.")
    ] = False,
) -> None:
    """Create or update MCP definitions from a client's JSON config."""
    manifest, doc = _open_manifest(project, file)
    mcp_dir = edit.default_dir(doc, "mcp", edit.DEFAULT_MCP_DIR)

    try:
        servers = mcp_import.servers_from_json(mcp_import.load_json(source), name)
    except AgentPackError as exc:
        raise _fail(exc) from None

    registered = False
    for server_name, incoming in servers:
        target = manifest.parent / mcp_dir / f"{server_name}.yaml"

        if target.exists():
            if not update:
                typer.secho(
                    f"{mcp_dir}/{server_name}.yaml exists — pass --update to merge into it.",
                    fg=typer.colors.YELLOW,
                )
                continue
            existing = edit.read_doc(target)
            changed = mcp_import.merge_server(existing, incoming)
            if not changed:
                typer.echo(f"{server_name}: already matches the JSON.")
                continue
            edit.write_doc(target, existing)
            typer.secho(
                f"Updated {mcp_dir}/{server_name}.yaml: {', '.join(changed)}", fg=typer.colors.GREEN
            )
        else:
            edit.write_doc(target, incoming)
            typer.secho(f"Created {mcp_dir}/{server_name}.yaml", fg=typer.colors.GREEN)

        secrets = [
            key
            for section in ("environment", "headers")
            for key, var in (incoming.get(section) or {}).items()
            if var.get("secret")
        ]
        if secrets:
            typer.secho(
                f"  {server_name}: {', '.join(secrets)} declared as user-supplied secrets; "
                "no values were copied.",
                fg=typer.colors.CYAN,
            )

        if not registered and not edit.covering_entry(doc, "mcp", f"{mcp_dir}/{server_name}.yaml"):
            edit.add_entry(doc, "mcp", mcp_dir)
            edit.write_doc(manifest, doc)
            typer.secho(f"Registered mcp: {mcp_dir}", fg=typer.colors.GREEN)
            registered = True


@mcp_app.command("remove")
def mcp_remove(
    name: Annotated[str, typer.Argument(help="Server name.")],
    project: ProjectOpt = Path("."),
    file: FileOpt = None,
    keep_file: Annotated[
        bool, typer.Option("--keep-file", help="Unregister only; leave the YAML on disk.")
    ] = False,
) -> None:
    """Remove an MCP definition and any manifest entry pointing at it."""
    manifest, doc = _open_manifest(project, file)
    target = _find_mcp_file(manifest, doc, name)
    relative = target.relative_to(manifest.parent).as_posix()

    if not keep_file:
        target.unlink()
        typer.secho(f"Deleted {relative}", fg=typer.colors.GREEN)

    if edit.remove_entry(doc, "mcp", relative):
        edit.write_doc(manifest, doc)
        typer.secho(f"Unregistered mcp: {relative}", fg=typer.colors.GREEN)


def _find_mcp_file(manifest: Path, doc, name: str) -> Path:
    """Locate <name>.yaml under any directory the manifest lists for MCP."""
    roots = [edit.entry_path(e) for e in (doc.get("mcp") or [])] or [edit.DEFAULT_MCP_DIR]
    for root in roots:
        candidate = manifest.parent / root
        if candidate.is_file() and candidate.stem == name:
            return candidate
        for suffix in (".yaml", ".yml"):
            hit = candidate / f"{name}{suffix}"
            if hit.is_file():
                return hit
    typer.secho(f"No MCP definition named '{name}' found.", fg=typer.colors.RED)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    main()
