# Market research — industrial robotics niche

Following the PLC market research (see the `plc-code-bridge` project, where a direct free competitor was found for the cross-brand code conversion idea), this research shifted to robotics, systematically checking for competition on each lead before keeping it.

## Leads evaluated

**1. Cross-brand robot program portability (RAPID/KRL/TP/URScript) — dropped.**
No automatic cross-brand conversion seems to exist, but for a structural reason rather than an opportunity: motion instructions depend on the robot's physical kinematics (geometry, singularities, tool conventions). A bad conversion can produce dangerous trajectories. High risk, uncertain value.

**2. IDE/debugger for URScript (Universal Robots) — kept.**
Real, recurring demand over several years on the official UR forum ("URScript IDE for writing and debugging", "Breakpoint in debugging URScript"). Competition checked and confirmed weak: only a syntax-highlighting VS Code extension (`ahern.urscript`) and an open-source headless execution project (`Hirebotics/urscript-tools`) — no tool with step debugging/breakpoints. Universal Robots has the largest installed base of cobots in the world.

**3. Offline simulation/programming of robot cells — dropped.**
RoboDK ($1,800-5,000 perpetual) already dominates this market alongside OCTOPUZ, SprutCAM X Robot, RoboCell, RobotWorks. Established market, already well-served by serious competitors.

**4. PackML compliance — confirmed weak.**
Real, documented pain point (a P&G thread about brittle implementations) but MathWorks already offers a PackML product in Simulink (state-machine verification + test generation). Major incumbent already in place.

**5. Freelance signal (Upwork)**: ~2,980 "Automation" listings and 48 "PLC Programming" — real service demand but too generic to point to a specific product.

## Decision

Product chosen: **URScript IDE/debugger for Universal Robots**, the only lead combining documented, recurring demand, confirmed absence of a dominant competitor, a massive installed base, and realistic solo feasibility.
