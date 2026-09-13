# URScript Debugger

A real debugger for **raw URScript** in VS Code — breakpoints, step execution, and live variable inspection/editing for Universal Robots cobots.

PolyScope has had native breakpoints since v5.6, but only for programs built in its graphical editor. If you write or send `.script` files directly — as an integrator, a ROS/External Control user, or a URCap developer — you've had no way to pause execution, inspect a variable, or step through your code. This extension fills that gap.

## Features

- **Breakpoints** — set them like in any other language, right in the editor gutter.
- **Step Over / Into / Out** — advance line by line, including lines without a breakpoint.
- **Variable inspection** — see the value of every local variable in scope, live, in the Variables panel.
- **Live variable editing** — change a numeric variable mid-run and watch it actually affect the program's control flow (e.g. short-circuit a loop condition).
- **Watch panel** — evaluate any variable already in scope.
- **Multi-file projects** — breakpoints are tracked per file; only the launched file executes.
- **Safe by design** — a breakpoint only pauses the robot after it has been brought to a full, controlled stop (`stopj`). Nothing is ever frozen mid-motion, and a pass-through checkpoint (no breakpoint hit) never touches motion in progress — so blended moves (`r=...`) aren't disturbed.

## Free vs. Premium

The extension is free to install and use, with one limit: **1 active breakpoint** and read-only variable inspection. A one-time license (39€, lifetime) unlocks:

- Unlimited breakpoints
- Live variable editing (`setVariable`) — change a value mid-run and see it actually affect execution

Run and step controls (Continue, Step Over/Into/Out) are always free, no limit. Use the **"URScript Debugger: Enter License Key"** command (Command Palette) to activate a purchased license.

## Requirements

- VS Code 1.85 or newer.
- **Python 3** installed and available on your `PATH` (no extra packages needed — the debugger uses only the standard library).
- A URScript-capable target: [URSim](https://www.universal-robots.com/download/software-e-series/simulation-non-linux/offline-simulator-e-series-ur-simulator-linux-64-bit/) (the official simulator, easiest way to try this out with no hardware) or a real UR controller reachable on your network.

## Getting started

1. Install the extension.
2. Make sure something is listening on the robot/simulator side: for URSim, power on the robot and release the brakes from the Dashboard, or PolyScope's own start screen.
3. Open a `.script` file in VS Code.
4. Click in the gutter to the left of a line to set a breakpoint.
5. Create a launch configuration (Run and Debug → "create a launch.json file" → URScript), or use this minimal one:
   ```json
   {
     "type": "urscript",
     "request": "launch",
     "name": "Debug this URScript file",
     "program": "${file}",
     "ursimHost": "127.0.0.1"
   }
   ```
6. Press F5. Execution stops at your breakpoint, variables show up in the Variables panel, and you can Continue or Step Over from there.

## How the safety mechanism works

Every executable line is instrumented with a lightweight checkpoint that asks, over a local socket, "should I stop here?" If the answer is no (no breakpoint, no step in progress), the robot passes through instantly with no effect on any motion underway. If the answer is yes, the robot brings itself to a controlled stop (`stopj`) *before* confirming it's paused — VS Code is only ever told "stopped" after that stop is physically confirmed, never before. This is what lets you safely interrupt a program that's actually moving the robot, without risking an uncontrolled halt mid-trajectory.

## Known limitations

- Live variable editing supports numeric values only (int/float) — not strings, lists, or poses.
- The Watch panel can only evaluate variables already detected in scope, not arbitrary expressions (URScript has no dynamic `eval`).
- Only one file executes at a time — URScript has no cross-file `import` mechanism, so there's no notion of a single program spanning multiple files.

## Development

This repository contains the full source: the VS Code extension (`extension/`), the Python DAP server (`server/`), the license validation server (`license-server/`), a Dockerized URSim test environment (`docker/`), and an automated test suite covering the debugger end-to-end against a real simulated robot (`tests/`, `extension/src/test/`). See `docs/feasibility.md` and `docs/market-research.md` for the background behind the design choices.

To run the tests yourself: start URSim (`cd docker && docker compose up -d`), then `cd extension && npm test`.

## License

Source-available under the [Elastic License 2.0](LICENSE) — free to use and modify, but it may not be redistributed as a competing hosted/managed service. Interested in a commercial license or support? Open an issue.
