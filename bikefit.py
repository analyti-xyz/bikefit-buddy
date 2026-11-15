#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "pyyaml",
# ]
# ///

import math
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import FloatPrompt, Prompt
from rich.table import Table

app = typer.Typer(add_completion=False, help="Hamley (1967) + Pruitt 90° (2006) Bike Fit Calculator.")
console = Console()

PROFILES_DIR = Path.cwd() / "profiles"

# --- Published Biomechanical & Anthropometric Constants ---
HAMLEY_INSEAM_MULT = 1.09
PEDAL_CLEAT_STACK_MM = 16.0  # Shimano bikefitting.com standard shoe/cleat/pedal stack
BASE_SEAT_ANGLE_DEG = 73.5   # Empfield (F.I.S.T.) standard road seat angle to 80mm datum

# De Leva (1996) / Drillis & Contini (1966) Segment Ratios
TORSO_LINK_RATIO = 0.7636
ARM_HAND_LINK_RATIO = 0.863       # Shoulder -> fist chord; calibrated to known reports, not sourced
STD_DROP_RATIO = 0.0830           # Saddle -> hand drop per mm torso for standard proportions
DRILLIS_STD_ARM_TORSO_RATIO = 1.211
DRILLIS_STD_TORSO_INSEAM_RATIO = 0.650

# Pruitt (2006) 45° Baseline & Orthogonal Kinematic Step Sizes
PRUITT_ENDURANCE_TORSO_DEG = 45.0
STYLE_HIP_PITCH_STEP_DEG = 1.2     # Mode 1: Hip rotation -> drives Y (Drop)
FLEX_SHOULDER_EXT_STEP_DEG = 0.8   # Mode 2: Shoulder scissor -> drives X (Reach)
FLATBAR_UPRIGHT_OFFSET_DEG = 4.0

# Fist -> 31.8mm bar clamp offset, applied purely along X
DROPBAR_HAND_TO_CLAMP_MM = 130.0  # 75mm bar reach + 55mm hood body
FLATBAR_HAND_TO_CLAMP_MM = 45.0

STYLE_LABELS = {1: "Leisure", 2: "Casual", 3: "Endurance", 4: "Sport", 5: "Aggressive"}
FLEX_LABELS = {1: "Stiff", 2: "Low-Flex", 3: "Neutral", 4: "Flexible", 5: "High-Flex"}


def default_crank(inseam: float) -> float:
    if inseam < 740:
        return 165.0
    if inseam < 810:
        return 170.0
    if inseam < 890:
        return 172.5
    return 175.0


def load_profile(name: str) -> dict:
    # Profiles live only in ./profiles/; reject names that would escape it
    if not name or Path(name).name != name or name in (".", ".."):
        raise typer.BadParameter(f"Invalid profile name '{name}'")

    path = PROFILES_DIR / f"{name}.yml"
    if path.exists():
        return yaml.safe_load(path.read_text())

    console.print(f"[yellow]Profile '{name}' not found.[/yellow] Let's create {name}.yml:")
    data = {
        "inseam": FloatPrompt.ask("  Inseam (mm)"),
        "torso": FloatPrompt.ask("  Torso (mm)"),
        "arm": FloatPrompt.ask("  Arm length (mm)"),
    }
    PROFILES_DIR.mkdir(exist_ok=True)
    out_path = PROFILES_DIR / f"{name}.yml"
    out_path.write_text(yaml.safe_dump(data, sort_keys=False))
    console.print(f"[green]Saved {out_path}[/green]\n")
    return data


def compute_fit_model(inseam: float, torso: float, arm: float, bar: str, crank: float) -> dict:
    is_flat = bar == "flat"

    # 1. Fixed Lower Body Vector (Saddle XY)
    saddle_r = HAMLEY_INSEAM_MULT * inseam - crank - PEDAL_CLEAT_STACK_MM
    theta_s = math.radians(BASE_SEAT_ANGLE_DEG)
    saddle_x = saddle_r * math.cos(theta_s)
    saddle_y = saddle_r * math.sin(theta_s)

    # 2. Upper Body Baseline (Style=3, Flex=3)
    l_t = TORSO_LINK_RATIO * torso
    l_a = ARM_HAND_LINK_RATIO * arm
    hand_to_clamp = FLATBAR_HAND_TO_CLAMP_MM if is_flat else DROPBAR_HAND_TO_CLAMP_MM

    # Long Legs / Short Torso (lower T/I) pitches the torso proportionally lower
    ti_ratio = torso / inseam
    theta_t0 = math.radians(PRUITT_ENDURANCE_TORSO_DEG * ti_ratio / DRILLIS_STD_TORSO_INSEAM_RATIO)
    drop_base = torso * STD_DROP_RATIO * ((ti_ratio / DRILLIS_STD_TORSO_INSEAM_RATIO) ** 1.35)

    sin_a0 = max(0.40, min(0.90, (l_t * math.sin(theta_t0) + drop_base) / l_a))
    theta_a0 = math.asin(sin_a0)

    # 3. Evaluate 5x5 Orthogonal Grid (Style 1..5 x Flex 1..5)
    grid = {}
    for s in range(1, 6):
        for f in range(1, 6):
            pitch_rad = math.radians(-STYLE_HIP_PITCH_STEP_DEG * (s - 3) + (FLATBAR_UPRIGHT_OFFSET_DEG if is_flat else 0.0))
            scissor_rad = math.radians(-FLEX_SHOULDER_EXT_STEP_DEG * (f - 3))

            # Mode 1 (pitch) shifts theta_t and theta_a oppositely (drives Y)
            # Mode 2 (scissor) shifts theta_t and theta_a together (drives X)
            theta_t = theta_t0 + pitch_rad + scissor_rad
            theta_a = theta_a0 - pitch_rad + scissor_rad

            # Triangle terminates at the fists; clamp offset is subtracted along X only
            drop = l_a * math.sin(theta_a) - l_t * math.sin(theta_t)
            hand_dx = l_t * math.cos(theta_t) + l_a * math.cos(theta_a)
            bar_dx = hand_dx - hand_to_clamp

            bx = round(bar_dx - saddle_x)
            by = round(saddle_y - drop)
            grid[(s, f)] = {
                "bar_x": bx,
                "bar_y": by,
                "drop": round(drop),
                "theta_t": math.degrees(theta_t),
                "shoulder_fist": 180.0 - math.degrees(theta_t) - math.degrees(theta_a),
            }

    if ti_ratio < 0.68:
        body_type = "Long Legs / Short Torso"
    elif ti_ratio <= 0.73:
        body_type = "Balanced Proportions"
    else:
        body_type = "Short Legs / Long Torso"

    default_pt = grid[(3, 3)]
    target_str = (default_pt["bar_y"] - 107.0) / (default_pt["bar_x"] - 75.0) if not is_flat else None

    return {
        "saddle_r": round(saddle_r),
        "saddle_x": round(saddle_x),
        "saddle_y": round(saddle_y),
        "grid": grid,
        "ti_ratio": ti_ratio,
        "body_type": body_type,
        "target_str": target_str,
    }


def make_bar(val: int, vmin: int, vmax: int, width: int = 16, color: str = "cyan") -> str:
    norm = (val - vmin) / max(1, (vmax - vmin))
    filled = max(1, round(norm * width))
    return f"[{color}]{'█' * filled}[/{color}][dim]{'░' * (width - filled)}[/dim]"


@app.command()
def main(
    profile: str = typer.Argument(..., help="Rider profile name (e.g., 'pranas' loads pranas.yml)"),
    bar: Optional[str] = typer.Option(None, "--bar", "-b", help="Bar type: 'drop' or 'flat'"),
    crank: Optional[float] = typer.Option(None, "--crank", "-c", help="Crank length in mm"),
):
    data = load_profile(profile)
    inseam = float(data["inseam"])

    if bar is None:
        bar = Prompt.ask("Bar design", choices=["drop", "flat"], default="drop")
    if crank is None:
        crank = FloatPrompt.ask("Crank length (mm)", default=default_crank(inseam))

    res = compute_fit_model(
        inseam=inseam,
        torso=float(data["torso"]),
        arm=float(data["arm"]),
        bar=bar.lower(),
        crank=crank,
    )
    grid = res["grid"]
    d_pt = grid[(3, 3)]

    console.print()
    # 1. Baseline Summary Table
    summary = Table(
        title=f"[bold]{profile.capitalize()}[/bold] • {bar.capitalize()}bar • {crank:g}mm Crank",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    summary.add_column("Contact Point", style="bold")
    summary.add_column("X (mm)", justify="right", style="bold green")
    summary.add_column("Y (mm)", justify="right", style="bold green")
    summary.add_column("Baseline Notes", style="dim")

    summary.add_row("Saddle (80mm ref)", str(res["saddle_x"]), str(res["saddle_y"]), f"Radial height: {res['saddle_r']} mm (Fixed)")
    summary.add_row(
        "Handlebar ★ Default",
        str(d_pt["bar_x"]),
        str(d_pt["bar_y"]),
        f"Drop: {d_pt['drop']} mm • Torso: {d_pt['theta_t']:.0f}° • Shoulder: {d_pt['shoulder_fist']:.0f}°",
    )
    console.print(summary)

    # 2. Two Decoupled 1D Range Graphs (X vs Flexibility, Y vs Style)
    x_vals = [grid[(3, f)]["bar_x"] for f in range(1, 6)]
    y_vals = [grid[(s, 3)]["bar_y"] for s in range(1, 6)]

    gx = Table(title="[bold]Handlebar X (Reach) vs Flexibility[/bold]\n[dim]Lower X = Stiffer (Closed Shoulder)[/dim]", box=box.SIMPLE_HEAVY)
    gx.add_column("Flexibility", style="bold")
    gx.add_column("X (mm)", justify="right")
    gx.add_column("Reach Scale", no_wrap=True)
    gx.add_column("Δ", justify="right", style="dim")

    for f in range(1, 6):
        pt = grid[(3, f)]
        delta = pt["bar_x"] - d_pt["bar_x"]
        color = "bold green" if f == 3 else ("cyan" if f < 3 else "yellow")
        gx.add_row(
            f"[{color}]{FLEX_LABELS[f]}[/{color}]",
            f"[{color}]{pt['bar_x']}[/{color}]",
            make_bar(pt["bar_x"], min(x_vals), max(x_vals), color=color),
            f"{delta:+d}" if delta else "0",
        )

    gy = Table(title="[bold]Handlebar Y (Height) vs Style[/bold]\n[dim]Lower Y = Aggressive (More Drop)[/dim]", box=box.SIMPLE_HEAVY)
    gy.add_column("Riding Style", style="bold")
    gy.add_column("Y (mm)", justify="right")
    gy.add_column("Height Scale", no_wrap=True)
    gy.add_column("Drop", justify="right", style="dim")

    for s in range(1, 6):
        pt = grid[(s, 3)]
        color = "bold green" if s == 3 else ("cyan" if s < 3 else "magenta")
        gy.add_row(
            f"[{color}]{STYLE_LABELS[s]}[/{color}]",
            f"[{color}]{pt['bar_y']}[/{color}]",
            make_bar(pt["bar_y"], min(y_vals), max(y_vals), color=color),
            f"{pt['drop']}mm",
        )

    console.print(Columns([Panel(gx, border_style="dim"), Panel(gy, border_style="dim")]))

    # 3. 5x5 2D Handlebar (X, Y) Heatmap Matrix
    heatmap = Table(
        title="[bold]Handlebar (X, Y) Heatmap Matrix[/bold]",
        box=box.ROUNDED,
        show_lines=True,
    )
    heatmap.add_column("Style \\ Flex", style="bold")
    for f in range(1, 6):
        heatmap.add_column(FLEX_LABELS[f], justify="center")

    heat_colors = {
        2: "bright_cyan", 3: "cyan", 4: "blue", 5: "green",
        6: "yellow", 7: "dark_orange", 8: "red", 9: "bright_red", 10: "magenta"
    }

    for s in range(1, 6):
        row_cells = [f"[bold]{STYLE_LABELS[s]}[/bold]"]
        for f in range(1, 6):
            pt = grid[(s, f)]
            if s == 3 and f == 3:
                cell = f"[bold black on green] ★ {pt['bar_x']}, {pt['bar_y']} [/bold black on green]\n[green]Drop {pt['drop']}mm[/green]"
            else:
                c = heat_colors[s + f]
                cell = f"[bold {c}]{pt['bar_x']}, {pt['bar_y']}[/bold {c}]\n[dim]Drop {pt['drop']}mm[/dim]"
            row_cells.append(cell)
        heatmap.add_row(*row_cells)

    console.print(heatmap)

    meta = f"[dim]Body Type:[/dim] {res['body_type']} (T/I: {res['ti_ratio']:.2f})"
    if res["target_str"]:
        meta += f"  •  [dim]Default Target Frame STR:[/dim] {res['target_str']:.2f}"
    console.print(f" {meta}\n")


if __name__ == "__main__":
    app()
