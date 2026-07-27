# Functional Scope 0.4.0

This document is the implementation contract for HFSS Filter Studio 0.4.0. A
module is marked operational only when it has a backend implementation, an HTTP
entry point, a UI workflow, validation, and an offline test path.

## Functional Matrix

| Module | Backend | UI | Offline validation | Real-system boundary |
| --- | --- | --- | --- | --- |
| Single-filter synthesis | NumPy/SciPy ZPK | Main workbench | Unit tests | No external dependency |
| Diplexer/MUX | Multi-channel composite | Dip/MUX dialog | Unit and Playwright tests | Junction finalized in HFSS |
| Coupling matrix | Prototype and editable matrix | Matrix pane | Unit tests | Generalized Cameron remains a separate advanced solver |
| Cavity/combline | Parametric model plan and PyAEDT builder | Cavity dialog | Simulated adapter and plan tests | Geometry must be solved in HFSS |
| Waveguide | Parametric cavity/iris plan | Cavity recipe | Plan tests | Port/iris dimensions require engineering review |
| Planar/microstrip | Substrate, ground, traces and ports | Planar dialog | Simulated adapter and plan tests | Material library must exist in AEDT |
| SIW | Substrate, metal and via fences | Planar recipe | Plan tests | Final transitions require HFSS validation |
| Distributed LPF | Step, open-stub, elliptic and custom recipes | Planar recipe | Plan tests | Manufacturing constraints are user inputs |
| AEDT sessions | Detect, attach, create and release | Integration dialog | Mocked 2026 contract | Validated with AEDT 2026.1 |
| AEDT setup/sweep | Create or update setup and sweep | Configure Setup | Mock/simulated tests | Uses active HFSS design |
| AEDT solve jobs | Serialized queue, status and cancel | Jobs tab | Threaded simulated test path | Solve time/license depend on AEDT |
| AEDT results | S2P, convergence, reports and result export | Integration actions | Simulated exports | Requires solved setup |
| VNA discovery | VISA resource enumeration | Discover action | Mocked PyVISA | Requires installed VISA runtime |
| VNA acquisition | Corrected S11/S21/S12/S22 | VNA dialog | Four-trace mock test | Requires supported SCPI dialect |
| Touchstone | RI/MA/DB parser and RI writer | Automatic overlays | Parser tests | Two-port `.s2p` only |
| HFSS/VNA comparison | Complex interpolation and dB metrics | Tuning dialog | Unit tests | Frequency ranges must overlap |
| CAT/tuning | Frequency, bandwidth and return-loss actions | CAT/Tuning dialogs | Unit tests | Screw sensitivities must be characterized |
| Global optimization | SciPy differential evolution | Optimization dialogs | Deterministic seeded test | Optimizes the analytical model |
| Monte Carlo | Seeded tolerances and yield | Monte Carlo dialog | Unit test | Correlated process models are not inferred |
| Transmission lines | Microstrip, stripline, waveguide and SIW | TL Calculator | Unit tests | Closed-form models require HFSS verification |
| Projects | Atomic JSON, revisions and restore | Project Management | Filesystem tests | Stored under configured local root |
| e-Library | Versioned built-in templates | e-Library dialog | API/UI tests | User libraries are a later extension point |

## Synthesis

`POST /api/synthesis/calculate` accepts BPF, BSF, LPF and MULTI
specifications. It returns:

- complex-prototype-derived S-parameter magnitudes;
- group delay and delivered power;
- low-pass prototype values;
- scaled lumped elements;
- normalized and physical coupling values;
- topology nodes and edges;
- achieved return loss, insertion loss and ripple.

`POST /api/synthesis/matrix-response` evaluates an edited real coupling matrix
over the active frequency grid. The returned S11, S21, S12 and S22 series
replace the analytical prototype in the workbench, so matrix value and sign
edits have an immediate electrical response.

`POST /api/synthesis/multiplexer` accepts two to sixteen channel
specifications. Each channel is synthesized independently over a common grid.
The aggregate is a lossless initial power-combiner response. It is suitable for
dimensioning and optimization initialization, not as a replacement for an HFSS
manifold or star-junction solve.

## Parametric HFSS Modeling

`POST /api/modeling/plan` creates a side-effect-free model plan. Every plan
contains:

- model name and units;
- primitive list;
- Boolean operations;
- source/load port definitions;
- setup and sweep configuration;
- recipe parameters;
- dry-run and overwrite policy.

The same payload can be sent to a compatible `/api/hfss/<method>` route. The
PyAEDT adapter:

1. selects millimeter model units;
2. optionally removes only objects with the selected model prefix;
3. creates boxes and cylinders;
4. applies subtract/unite operations;
5. creates two lumped ports when enabled;
6. creates or updates setup and frequency sweep;
7. returns all object and boundary names.

Supported recipes:

- `cavity`;
- `combline`;
- `waveguide`;
- `planar`;
- `siw`;
- `lpf_step`;
- `lpf_open_stub`;
- `lpf_elliptic`;
- `lpf_custom`.

The model generator never runs automatically on page load. Preview is the UI
default. Real geometry creation requires the user to clear `Preview only` and
press `Build Model`.

## AEDT Job Lifecycle

HFSS analysis is serialized through one worker because one PyAEDT application
object and one AEDT design must not be mutated concurrently.

States:

```text
queued -> running -> completed
                  -> failed
       -> cancelling -> cancelled
```

Endpoints:

```text
GET  /api/jobs
POST /api/jobs
GET  /api/jobs/<id>
POST /api/jobs/<id>/cancel
```

Cancellation sets the local cancellation event. For a running job it also
calls `Hfss.stop_simulations(clean_stop=True)`; cancelling a queued job never
interrupts the analysis currently using the AEDT session. A completed job can
expose the exported Touchstone path; the UI imports it and adds HFSS S11/S21
overlays.

## VNA Acquisition

The PyVISA backend provides profiles for:

- Keysight PNA/ENA;
- Rohde & Schwarz ZNA/ZNB/ZND;
- Copper Mountain;
- generic SCPI fallback.

Connection performs `*IDN?` and selects a profile. A two-port sweep:

1. defines `S11`, `S21`, `S12` and `S22` measurements;
2. switches to corrected complex ASCII data;
3. holds continuous sweep;
4. triggers one acquisition and waits with `*OPC?`;
5. reads the actual stimulus axis when available;
6. selects and reads every S-parameter trace;
7. restores continuous mode when it was previously enabled.

The local `.s2p` writer is used instead of relying on a file path inside the
instrument. This keeps file ownership and path semantics on the server machine.

Instrument-dependent operations include:

- reset and clear;
- sweep range, points, IFBW, power and type;
- continuous/background sweep;
- marker placement/readback;
- trace autoscale;
- sweep-time query;
- error-queue readback;
- state-file load where supported.

## Touchstone and Comparison

The parser accepts:

- units `Hz`, `kHz`, `MHz`, `GHz`;
- formats `RI`, `MA`, `DB`;
- inline and full-line comments;
- arbitrary reference impedance;
- wrapped numeric records.

Comparison uses the common frequency interval. Complex real and imaginary parts
are interpolated before conversion to dB. Results include RMSE, mean error and
maximum absolute error for all four S-parameters, plus center-frequency and
3 dB bandwidth deltas.

## Tuning

The tuning engine computes three independent first-order actions:

- common resonator adjustment for center-frequency error;
- inter-resonator coupling adjustment for bandwidth error;
- source/load coupling adjustment for return-loss error.

Sensitivity inputs are explicit:

```json
{
  "frequency_hz_per_turn": 2000000,
  "bandwidth_hz_per_turn": 1000000,
  "return_loss_db_per_turn": 1
}
```

These values must come from measurement, EM perturbation runs, or mechanical
characterization. The application does not guess a hardware tuning law.

## Optimization and Monte Carlo

Global optimization uses SciPy differential evolution with:

- explicit bounds;
- deterministic seed;
- bounded population and iteration count;
- objective history;
- optional final polishing;
- target center, bandwidth, return loss and insertion-loss limit.

Monte Carlo supports Gaussian tolerances for center frequency, bandwidth,
return loss and unloaded Q. It reports:

- pass/fail count;
- yield percentage;
- mean, standard deviation, extrema and P05/P50/P95;
- a bounded preview of individual samples.

## Project Persistence

The server project format is version 2. Every project has:

- stable slug ID;
- name and description;
- specification and matrix;
- integration and measurement metadata;
- creation/update timestamps;
- monotonic revision.

Writes use a temporary file followed by an atomic replacement. Revisions are
stored under `<project_root>/<id>/versions/NNNNNN.json`. Paths are validated
against the configured root.

Environment:

```powershell
$env:HFSS_BRIDGE_PROJECT_DIR = "D:\simulation\filter-projects"
```

## Safety Rules

- Attaching to a user-owned AEDT desktop does not imply ownership.
- Release defaults do not close the attached desktop.
- Project locks are removed only when explicitly requested.
- No solve or model build is triggered by page initialization.
- Model replacement is restricted to names sharing the selected prefix.
- AEDT solve jobs are serialized.
- VNA RF power is not enabled by connection alone.
- Real VNA validation must be performed with a terminated or connected DUT.

## Validation Commands

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
npm run check:js
npm run test:ui
git diff --check
```

The real AEDT diagnostic utility remains read-only unless `--analyze` is
explicitly supplied:

```powershell
.\.venv\Scripts\python scripts\validate_aedt_2026.py `
  --project "D:\dev\HFSS_AUTO\painel triBand.aedt" `
  --attach --machine localhost --port 49152
```

## Primary References

- [PyAEDT HFSS API](https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.hfss.Hfss.html)
- [PyAEDT Modeler](https://aedt.docs.pyansys.com/version/stable/User_guide/modeler.html)
- [PyAEDT setup and sweep classes](https://aedt.docs.pyansys.com/version/stable/API/Setup.html)
- [PyAEDT linear-count sweep](https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.hfss.Hfss.create_linear_count_sweep.html)
- [PyVISA user guide](https://pyvisa.readthedocs.io/en/1.14.1/introduction/)
- [Keysight corrected SDATA](https://helpfiles.keysight.com/csg/e5063a/programming/command_reference/calculate/calc_data_sdat.htm)
- [Rohde & Schwarz ZNA manual](https://www.rohde-schwarz.com/ch-en/manual/zna/)
- [Copper Mountain all-trace SDATA](https://coppermountaintech.com/help-cmtvna/Programming-Manual/calcalltdatasdat_.html)
- [SciPy Signal API](https://docs.scipy.org/doc/scipy/reference/signal.html)
