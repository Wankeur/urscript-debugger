# urscript-debugger

A VS Code extension bringing a real debugger (breakpoints, step execution, variable inspection) to **raw URScript** (Universal Robots) — something missing today for anyone writing/sending script outside of PolyScope (integrators, ROS/External Control users, URCap developers).

## Context

See `docs/market-research.md` and `docs/feasibility.md`. Summary:
- PolyScope has had native breakpoints since v5.6, but **no tool covers raw URScript** (`.script` files, code sent over a socket).
- A user on the official UR forum already validated the base mechanism manually (a `breakPoint()` function with a socket rendezvous) — we're packaging and hardening that idea rather than inventing something unproven.
- URSim (the official simulator) runs in Docker and exposes the same network interfaces as a real robot: development and testing are entirely possible without hardware.

## Architecture

1. **Code instrumentation**: the user's `.script` is parsed (syntactic parsing is enough, no full semantic engine needed) and a `checkpoint()` call is inserted after EVERY executable line of the `def program():` block (not just lines marked as breakpoints). Each checkpoint first asks the server "should I stop?" (a one-byte reply). If yes: the robot runs `stopj()` itself (a controlled, decelerated stop), confirms to the server that it's physically stopped, and *only then* does the server notify VS Code — never announcing "stopped" before a real, confirmed stop. If no: instant pass-through, zero impact on any motion in progress (important so as not to break blended moves using a `r=...` radius).
2. **Rendezvous server**: built directly into the DAP adapter (`dap_server.py`), receives socket connections from `checkpoint()`, decides whether to suspend or pass through, holds execution paused as long as needed, then sends the resume signal.
3. **DAP adapter (Debug Adapter Protocol)**: translates standard VS Code requests (setBreakpoints, continue, next/stepIn/stepOut, threads, stackTrace, scopes, variables, **setVariable, evaluate**) into calls to the rendezvous server. This is what gives us all of VS Code's debugging UI for free (breakpoint gutter, call stack, editable variables panel, step buttons) — no UI to build ourselves.
4. **VS Code extension**: declares the URScript language (minimal `.script` association for now — a third-party extension already exists for full syntax highlighting, `ahern.urscript`, worth studying/possibly contributing to rather than duplicating) + registers the DAP adapter. Packaged as a `.vsix` (see "Packaging").

## Reusable foundations (not reinventing the wheel)

- `universalrobots/ursim_e-series` (official Docker image) — test environment.
- `Hirebotics/urscript-tools` — Docker/URSim orchestration for headless execution, a possible base for test infra.
- `ahern.urscript` (existing VS Code extension) — syntax highlighting, to check for reuse/contribution before duplicating.

## Validated features

1. ✅ Set a breakpoint on a line of a `.script`.
2. ✅ Run the script against URSim (Docker).
3. ✅ Execution stops cleanly at the marked line.
4. ✅ See the value of local variables in the VS Code panel (automatic detection by scanning `local X =` declarations preceding the line).
5. ✅ Resume execution (continue).
6. ✅ **Step over/into/out**: advances line by line even on lines that aren't explicit breakpoints, using the same checkpoint mechanism.
7. ✅ **Packaging**: the extension packages into an installable `.vsix` (see "Packaging").
8. ✅ **Safe motion stop**: `stopj()` triggered by the robot itself only when a real pause is decided, never on a simple pass-through — validated with a script containing real motion (two `movej` calls chained with a blend radius).
9. ✅ **Watch expressions / evaluation** (`evaluate`): evaluates local variables known at the current point (viewable in the Watch panel or debug console). Honest limitation: no arbitrary expressions (URScript has no dynamic `eval`) — only already-detected variables can be evaluated.
10. ✅ **Live variable editing** (`setVariable`): editing a numeric variable in the Variables panel actually affects the running execution (tested: changing a counter mid-loop immediately short-circuits the exit condition). Honest limitation: numeric values only (int/float) for now — no strings, lists, or poses.
11. ✅ **Multi-file support**: multiple `.script` files in the same project, each with its own correctly isolated breakpoints; only one file is "launched" at a time (URScript has no cross-file inclusion mechanism like an `import`, so there's no real notion of "a program spanning multiple files" — but a breakpoint set in a file that isn't launched never interferes with the active session).

**Validated four ways, from the lowest level to the most realistic:**
- `tests/test_dap_flow.py` simulates a simplified DAP client against a real URSim — fast validation of the server logic (motionless script).
- `tests/test_motion_safety.py` — same idea but with a script that actually moves the robot (`test-scripts/motion_test.script`): checks that the safety status stays `NORMAL` for the whole duration of the pause (3s, twice), proving no fault/protective stop is triggered by our `stopj()`, even when interrupting a move mid-blend.
- `extension/src/test/suite/debug.test.ts` drives a **real VS Code window** (via `@vscode/test-electron`): breakpoints set through the real API, "Continue"/"Step Over" clicks through the real commands, capturing the full DAP traffic. **5 scenarios** covered: consecutive breakpoints, clean failure when the port is busy, line-by-line stepping, live variable editing, multi-file isolation.
- Manual validation in the VS Code editor by the user, as an optional extra — see "How to test" below.

**Bugs found and fixed thanks to real E2E tests (2026-09-13):**
- A rendezvous port already held by a previous, improperly stopped session made `_start_program` fail silently — no error ever reached VS Code. Fixed: the error now surfaces via an explicit `output` event + `terminated`, with a regression test.
- End-of-program detection via **periodic dashboard polling** missed fast scripts (an entire program can run in under 50ms, before the first poll even happens) — replaced with an **explicit signal sent by the script itself right before it ends**, deterministic and instant, no more timing dependency.
- A malformed checkpoint connection (a leftover from a previous session that wasn't fully stopped) used to crash the **entire** rendezvous loop instead of simply being ignored — isolated into a per-connection handler with its own error handling.
- On session disconnect, the robot program wasn't explicitly stopped on the controller side, which could leave a script running and interfere with the next session — fixed (explicit `dashboard stop` on cleanup).

**Technical detail on the safe stop and variable editing (2026-09-13)**: two URScript functions I initially assumed existed (`socket_read_byte`) actually didn't — found via the controller's real error log (`/ursim/URControl.log` inside the container, far more reliable than `docker logs` for this kind of error), then confirmed the correct functions (`socket_read_byte_list`, `socket_read_ascii_float`) in the official Universal Robots manual before integrating them.

Out of scope for now (see "Next steps"): non-numeric variable editing, Marketplace publication.

## Test environment (URSim)

Everything is contained in this folder — nothing is installed elsewhere on the machine.

```bash
cd docker
docker compose up -d      # starts URSim (dashboard 29999, primary/secondary/realtime/RTDE 30001-30004, PolyScope web at http://localhost:6080/vnc.html)
docker compose down       # stops and removes the container
```

Persisted programs/URCaps live in `ursim-data/` (git-ignored). Validated on 2026-09-13: all control ports respond correctly once the container is up (~1-2 min internal startup).

## Project structure

```
urscript-debugger/
├── docs/               # market research + technical feasibility
├── docker/             # docker-compose.yml for URSim (test environment)
├── server/             # Python logic: instrumentation + DAP server
│   ├── instrument.py   # inserts checkpoint() into a .script
│   ├── dap_server.py   # DAP adapter, spawned by the VS Code extension
│   └── .venv/          # project-local Python environment
├── extension/          # VS Code extension (TypeScript)
│   ├── src/extension.ts
│   ├── src/test/       # E2E test suite (@vscode/test-electron)
│   ├── .vscodeignore   # excludes sources/tests from the packaged .vsix
│   └── package.json
├── test-scripts/       # example .script files (including motion_test.script with real motion, second_test.script for multi-file)
└── tests/              # low-level automated validation (test_dap_flow.py, test_motion_safety.py)
```

## Running the automated tests (me or you)

```bash
# 1. Start URSim + power on the robot (see "How to test" below, step 1)
# 2. Real E2E test in an actual VS Code window (opens and closes a window automatically):
cd extension && npm test
```

`npm test` compiles, downloads a real copy of VS Code the first time (~330 MB, cached in `extension/.vscode-test/`, git-ignored), opens it with the extension loaded, runs the 5 scenarios, and closes the window (~3s of test execution once VS Code is up). This is what I use to verify a change myself before telling you it works, instead of asking you to test every time.

## How to test in VS Code (the part that needs you)

1. `cd docker && docker compose up -d` — wait ~1-2 min, then power on the simulated robot:
   ```bash
   python3 -c "
   import socket, time
   s = socket.create_connection(('localhost', 29999), timeout=5)
   s.recv(4096); s.sendall(b'power on\n'); time.sleep(3)
   s.recv(4096); s.sendall(b'brake release\n'); time.sleep(5)
   print(s.recv(4096).decode())
   "
   ```
2. Open the `extension/` folder in VS Code, press **F5** — this opens a second VS Code window ("Extension Development Host") with the extension loaded.
3. In that new window, open the `test-scripts/` folder (it already has a `.vscode/launch.json` ready to go).
4. Open `counter_clean.script`, click in the gutter to the left of the `counter = counter + 1` line (line 5) to set a breakpoint.
5. Start debugging (F5, or the green triangle in the Run and Debug tab).
6. You should see execution stop at that line, the `counter` variable appear in the Variables panel, and be able to click "Continue" to move to the next iteration — or "Step Over" to advance line by line, including on lines without a breakpoint.

(Optional — I already run this check myself via `npm test` before telling you a change works; no need to redo it unless you want to see the UI with your own eyes.)

## Packaging

```bash
cd extension
npx @vscode/vsce package
```

Produces `urscript-debugger-<version>.vsix` (a few KB, zero runtime dependency — only `package.json` + `out/extension.js` are bundled thanks to `.vscodeignore`). Installable manually in VS Code via "Extensions" → "..." → "Install from VSIX...", or `code --install-extension urscript-debugger-<version>.vsix`.

## Publishing

See `docs/publishing.md` for the full step-by-step guide (publisher account, access token, publishing itself).

## Next steps (deliberately out of scope for now)

- Non-numeric variable editing (strings, lists, poses) — would need a richer protocol than `socket_read_ascii_float`.
- Marketplace freemium licensing model (license-key gated premium features).

## Status

A complete, functional extension covering the full scope originally targeted: breakpoints, stepping, safe motion stop, live variable inspection AND editing, multi-file support — validated automatically end-to-end through a real, test-driven VS Code window (5 scenarios), packaged as an installable `.vsix`. Ready for real-world use; Marketplace publication is now underway.
