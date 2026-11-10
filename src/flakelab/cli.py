"""The ``flakelab`` command line."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from flakelab import __version__
from flakelab.engine.baseline import BaselineConfig, BaselineSummary, normalize_target, run_baseline
from flakelab.runner.process import FAILING, RunResult
from flakelab.store.db import Store

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Diagnose why a pytest test is flaky.",
)
console = Console(highlight=False)


def _print_version(value: bool) -> None:
    if value:
        console.print(f"flakelab {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_print_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    pass


@app.command()
def diagnose(
    test: Annotated[
        str, typer.Argument(help="pytest node id, e.g. tests/test_cart.py::test_total")
    ],
    runs: Annotated[int, typer.Option("--runs", "-n", min=1, help="How many times to run.")] = 30,
    suite: Annotated[
        list[str] | None,
        typer.Option(
            "--suite",
            help="Path to run the test inside of (repeatable). Default: the test runs alone.",
        ),
    ] = None,
    jobs: Annotated[
        int,
        typer.Option(
            "--jobs", "-j", min=1, help="Runs to execute at once. More is faster but adds load."
        ),
    ] = 1,
    timeout: Annotated[
        float, typer.Option("--timeout", min=1.0, help="Seconds before a run is killed.")
    ] = 300.0,
    seed: Annotated[
        int | None, typer.Option("--seed", help="Replay a previous session's seed.")
    ] = None,
    repo: Annotated[
        Path,
        typer.Option("--repo", exists=True, file_okay=False, help="Project root."),
    ] = Path("."),
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Where results are stored. Default: <repo>/.flakelab"),
    ] = None,
) -> None:
    """Measure how often a test fails. (Cause analysis arrives in a later version.)"""
    repo = repo.resolve()
    config = BaselineConfig(
        repo=repo,
        target=normalize_target(test),
        suite=tuple(suite or ()),
        runs=runs,
        jobs=jobs,
        timeout_s=timeout,
        seed=seed if seed is not None else random.SystemRandom().randrange(2**32),
    )
    where = "inside " + ", ".join(config.suite) if config.suite else "on its own"
    console.print(f"[bold]flakelab[/bold] baseline: [cyan]{config.target}[/cyan]")
    console.print(f"{runs} runs, {where}, seed {config.seed}")

    store = Store(data_dir.resolve()) if data_dir else Store.for_repo(repo)
    saved_in = store.data_dir
    try:
        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("running", total=runs)
            failed = 0

            def on_result(result: RunResult) -> None:
                nonlocal failed
                failed += result.outcome in FAILING
                progress.update(task, advance=1, description=f"running ({failed} failed)")

            summary = run_baseline(config, store, on_result)
    finally:
        store.close()

    _report(summary, runs, saved_in)


def _report(summary: BaselineSummary, runs: int, saved_in: Path) -> None:
    breakdown = ", ".join(f"{n} {outcome}" for outcome, n in sorted(summary.counts.items()))
    console.print(f"{runs} runs: {breakdown}")

    rate = summary.rate
    if rate is None:
        console.print("\n[red]The test never produced a pass or a fail.[/red]")
        if summary.problem:
            console.print(f"Reason: {summary.problem}")
        console.print(f"Logs: {saved_in / 'logs' / f'session-{summary.session_id:04d}'}")
        raise typer.Exit(code=2)

    console.print(
        f"Failure rate [bold]{rate.rate:.1%}[/bold] "
        f"({rate.confidence:.0%} interval: {rate.low:.1%} to {rate.high:.1%})"
    )
    if summary.excluded:
        console.print(f"{summary.excluded} runs were excluded (skipped, or the test did not run).")
    console.print()

    if rate.failures == 0:
        console.print(
            f"[green]Never failed.[/green] This does not prove the test is stable: "
            f"a true failure rate of up to {rate.high:.1%} would still fit these results."
        )
    elif rate.failures == rate.total:
        console.print(
            "[red]Failed every time.[/red] Under these conditions this is a consistent "
            "failure, not flakiness."
        )
    else:
        console.print(f"[yellow]Flaky:[/yellow] failed {rate.failures} of {rate.total} runs.")
    if summary.top_failure_message:
        console.print(f"Most common failure: {summary.top_failure_message}")
    console.print(f"\nSession {summary.session_id} saved in {saved_in}")
