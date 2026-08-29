"""agentpack command line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from agentpack import API_VERSION, __version__
from agentpack.core import scaffold
from agentpack.core.builder import build as run_build
from agentpack.core.diagnostics import AgentPackError, Diagnostics, Severity
from agentpack.core.loader import find_project, load_package
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


def _load(project: Path) -> tuple:
    diags = Diagnostics()
    root = find_project(project)
    return load_package(root, diags), diags


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
    name: Annotated[str | None, typer.Option(help="Package name.")] = None,
) -> None:
    """Scaffold a new AgentPack project."""
    created = scaffold.init_project(directory, name or directory.resolve().name)
    typer.secho(f"Created {len(created)} files in {directory}", fg=typer.colors.GREEN)
    for path in created:
        typer.echo(f"  {path}")


@app.command()
def validate(project: ProjectOpt = Path("."), target: TargetOpt = None) -> None:
    """Validate the canonical project and its target compatibility."""
    pkg, diags = _load(project)
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
    format: Annotated[str, typer.Option("--format", "-f", help="yaml or json")] = "yaml",
) -> None:
    """Print the normalized model that adapters receive."""
    pkg, _ = _load(project)
    data = json.loads(pkg.model_dump_json(by_alias=True, exclude_none=True))
    typer.echo(
        json.dumps(data, indent=2)
        if format == "json"
        else yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    )


@app.command()
def build(
    project: ProjectOpt = Path("."),
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
    pkg, diags = _load(project)
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
    if summary.manifest_path:
        typer.secho(f"\nBuild manifest: {summary.manifest_path}", fg=typer.colors.GREEN)


@app.command(name="package")
def package_cmd(
    project: ProjectOpt = Path("."),
    target: TargetOpt = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Build and emit distributable archives (dist/packages/)."""
    build(project=project, target=target, output=output, strict=False, knowledge=None, archive=True)


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
    output: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Remove the build output directory."""
    import shutil

    pkg, _ = _load(project)
    out = output or (pkg.project_dir / pkg.build.output)
    if out.exists():
        shutil.rmtree(out)
        typer.secho(f"Removed {out}", fg=typer.colors.GREEN)
    else:
        typer.echo(f"Nothing to clean at {out}")


@app.command()
def doctor(project: ProjectOpt = Path(".")) -> None:
    """Report environment and project health."""
    import sys

    typer.echo(f"agentpack   {__version__}")
    typer.echo(f"apiVersion  {API_VERSION}")
    typer.echo(f"python      {sys.version.split()[0]}")
    typer.echo(f"targets     {', '.join(registry.names())}")
    try:
        root = find_project(project)
        typer.secho(f"project     {root}", fg=typer.colors.GREEN)
        pkg, diags = _load(root)
        typer.echo(f"skills      {len(pkg.skills)}")
        typer.echo(f"mcp servers {len(pkg.mcp_servers)}")
        _echo_diagnostics(diags)
    except AgentPackError as exc:
        typer.secho(f"project     none ({exc})", fg=typer.colors.YELLOW)


@app.command()
def version() -> None:
    """Print the AgentPack version."""
    typer.echo(__version__)


if __name__ == "__main__":
    main()
