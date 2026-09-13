# Technical feasibility analysis

## UR controller / URSim network interfaces

- **Dashboard Server (29999)**: `play`/`pause`/`stop`/`load` commands. `pause` does not properly suspend a running script — confirmed by a user on the official forum ("the robot doesn't know what to execute anymore, it killed the last line of the script"). Not usable as-is for reliable debugging.
- **Primary (30001) / Secondary (30002)**: 10 Hz, sends URScript commands and returns robot state.
- **Realtime (30003)**: 500 Hz, write-only, no reliable acknowledgment.
- **RTDE (30004)**: configurable input/output registers at control-loop frequency — a good continuous telemetry channel, but a limited number of registers, not sized for inspecting an arbitrary number of user variables.

## No native pause/resume for raw script — confirmed, with an important nuance

PolyScope has had native breakpoints on graphical program nodes since v5.6.x.x, but a user on the official forum explicitly confirms there's no way to apply that to a script file. The real gap is precise: **no debugging for URScript written/sent as raw text**, not "no UR debugging" in general.

A user on that same forum already hand-rolled the solution manually: a homemade `breakPoint()` function using `socket_open` to a local server to suspend execution on command. This directly validates the architecture chosen below as an idiom already discovered by the community, just never packaged properly into a tool.

Source: [Breakpoint in debugging URScript (official UR forum)](https://forum.universal-robots.com/t/breakpoint-in-debugging-urscript/7469)

## Hirebotics/urscript-tools

A headless executor against URSim in Docker, CI-style (pass/fail) — not an interactive debugger, no pause/step/inspection. Useful as reusable Docker/URSim orchestration infrastructure; the debugging logic still has to be built entirely from scratch.

## Chosen architecture: code instrumentation + Debug Adapter Protocol

**Why not a reimplemented URScript interpreter** (the alternative considered): loses all fidelity as soon as real motion is involved (`movej`/`movel` can't be faithfully "simulated" outside the controller/URSim), and no precedent was found for this approach on a robot language. Dropped.

**Chosen architecture:**
1. Parse the user's `.script` (syntactic parsing is enough to locate instruction boundaries, no full semantic engine needed) and insert `breakPoint()` calls at the marked lines.
2. Before blocking on the socket, cleanly stop any motion in progress (`stopl`/`stopj`) — don't reproduce the Dashboard Server's `pause` bug, which freezes mid-motion.
3. An external (Python) rendezvous server that receives the socket connection, holds the pause, reads/writes variables, and sends the resume signal.
4. A **DAP (Debug Adapter Protocol) adapter** on top of that server: translates standard VS Code requests (setBreakpoints, continue, next, variables, evaluate) into calls to the socket mechanism. Gives all of VS Code's debugging UI for free, with nothing to build on the interface side.

## URSim

Official Docker images are available (`universalrobots/ursim_e-series`, `universalrobots/ursim_cb3`, robot model selectable via an environment variable). Exposes the same network interfaces as a real controller — development and testing are entirely feasible in simulation before any access to a real robot.

## Overall assessment

**Feasibility: good.** The core mechanism is already informally practiced by the community, and fully testable on dockerized URSim. A working prototype (parse + instrumentation + pause/continue + basic variable) is realistic within a few weeks part-time; a polished IDE, a few months.

## Main risks

- **Narrower market than "all UR users"**: the real target is authors of raw script (integrators, ROS/External Control users, URCap developers) — regular PolyScope users already have native breakpoints since v5.6.
- **RTDE limited in register count** — keep the ad hoc socket channel for arbitrary variable inspection, RTDE for high-frequency telemetry only.
- **Breakpoint safety**: never naively block mid-motion — cleanly stop (`stopl`/`stopj`) before suspending, or risk reproducing the Dashboard Server bug.
