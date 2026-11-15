# bikefit-buddy

A small CLI that turns three body measurements into **saddle and handlebar coordinates** you can set up on any bike with a tape measure and a laser level.

Instead of recommending a frame size or a stem length, it outputs where the contact points should be, in millimetres from the bottom bracket. It also shows how the handlebar position shifts with riding style and flexibility.

> An 80/20 model: a transparent, simple kinematic estimate, not a substitute for a professional bike fit. Treat results as a starting point.

## Quick start

Requires [uv](https://docs.astral.sh/uv/). Dependencies are declared inline ([PEP 723](https://peps.python.org/pep-0723/)), so there is nothing to install.

```bash
./bikefit.py rider                        # prompts for bar type and crank length
./bikefit.py rider --bar drop --crank 172.5
./bikefit.py rider --bar flat
```

If `profiles/rider.yml` doesn't exist, you'll be asked for the measurements and the profile will be saved there.

## Rider profile

Profiles are read from and saved to `./profiles/<name>.yml` only. All values are in millimetres:

```yaml
inseam: 880.0   # floor to crotch, barefoot, firm pressure
torso: 570.0    # crotch to sternal notch
arm: 700.0      # acromion (shoulder tip) to centre of closed fist
```

Profiles contain personal measurements and are gitignored.

## Output

- **Saddle (X, Y)** and default **Handlebar (X, Y)**, with baseline drop and torso angle.
- **Handlebar X vs Flexibility** (Stiff → High-Flex): roughly ±8–10 mm per step.
- **Handlebar Y vs Riding Style** (Leisure → Aggressive): roughly ±17 mm per step.
- A **5 × 5 heatmap** of handlebar (X, Y) for every style × flexibility combination.
- A suggested frame stack-to-reach ratio (drop bars only).

### Coordinate system

All coordinates are measured from the **centre of the bottom bracket spindle**:

| Point | X | Y | Reference |
|---|---|---|---|
| Saddle | behind the BB | above the BB | Point on the saddle top where the shell is **80 mm wide** |
| Handlebar | in front of the BB | above the BB | **Axis of the 31.8 mm bar** inside the stem clamp |

Measuring tip: the bar radius is ~16 mm, so the clamp axis is **top of the bar − 16 mm** (Y) and **rear edge of the bar + 16 mm** (X).

## How the model works

**Saddle.** Saddle height uses the 109 % of inseam rule from Hamley & Thomas (1967), along an effective seat angle of 73.5°:

```
R_s     = 1.09 × inseam − crank − 16 mm (shoe/cleat/pedal stack)
Saddle  = (R_s · cos 73.5°, R_s · sin 73.5°)
```

The 109 % rule is a convenient starting point, not an optimum. A later review recommends checking the result by knee flexion at the bottom of the stroke (about 25–30°), which the 109 % rule doesn't reliably produce for every rider ([Bini, Hume & Croft 2011](https://pubmed.ncbi.nlm.nih.gov/21615188/)).

**Handlebar.** A two-link chain runs saddle → shoulder → fist:

- The torso link is `0.7636 × torso`. Its angle is 45° (Pruitt) for standard proportions, scaled by torso-to-inseam ratio, so long-legged riders lean lower.
- The arm link is `0.863 × arm`. Its angle is solved so the hands sit at a baseline drop below the saddle that scales with torso length and proportions.
- The bar clamp sits behind the fists by a fixed horizontal offset: **130 mm** for drop bars (hoods) and **45 mm** for flat bars.

**Style and flexibility** are two near-independent adjustments. Style rotates the upper body around the hip, which mainly moves the bar **height**. Flexibility opens or closes the angle between torso and arms, which mainly moves the bar **reach**. Flat bars add a 4° more upright posture.

### Constants

| Constant | Value | Source |
|---|---|---|
| Saddle height | 1.09 × inseam | Hamley & Thomas (1967) |
| Shoe/cleat/pedal stack | 16 mm | Typical value |
| Effective seat angle | 73.5° | Empfield (F.I.S.T.) |
| Baseline torso angle | 45° at torso/inseam = 0.650 | Pruitt, *Complete Medical Guide for Cyclists* (2006) |
| Standard torso/inseam ratio | 0.650 | Drillis & Contini (1966) |
| Torso link | 0.7636 × torso | Derived, not verified against source tables |
| Arm link | 0.863 × arm | **Calibrated** |
| Torso-angle scaling with proportions | linear | **Calibrated** |
| Baseline drop | 0.0830 × torso × (ratio)^1.35 | **Calibrated** / unsourced exponent |
| Style / flexibility steps | 1.2° / 0.8° | Unsourced |
| Flat-bar posture | +4° | Unsourced |
| Hand-to-clamp offset | 130 mm drop / 45 mm flat | Typical component dimensions |

## Tests

```bash
./test_bikefit.py
```

Checks the model against the known reference fits within ±1 mm.
