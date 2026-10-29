# storm-drain-energy-grade

Energy grade line evaluation of 44 storm drain networks (530 structures) for a 10-year design event and a 100-year
check event. For every pipe and event the agent reports the Table 9.6 case at the pipe's downstream end, the
Table 9.7 condition at its upstream end, the energy grade line at both ends, the energy level (EGLa) of the
structure at its upstream end, and whether that structure surcharges.

## Difficulty

Drainage engineers check storm drain systems for surcharge with the energy loss method of FHWA HEC-22, 4th
edition, Section 9.4, and HEC-22 notes that much software does not apply the full method. Every answer comes from
one pass that starts at the outfall and works upstream through every branch, so an error at one structure carries
into everything above it. Each pipe's downstream end falls into one of five cases by comparing the downstream
energy level with the pipe's crown, normal depth, critical depth and invert (Table 9.6), each with its own exit
loss (one velocity head at the still receiving water, 0.4 at structures, at the full-pipe or the face-depth
velocity). Its upstream end falls into one of four conditions (Table 9.7), with full-flow friction from equation
9.4 or the pipe slope, and supercritical pipes reset to normal depth instead of carrying losses upstream. Normal
and critical depth in partly full circular pipes must be solved. At every structure the FHWA method of Section
9.1.6.7 takes the largest of an outlet control and two inlet control energy levels (none in outlet control after
a supercritical reset), then adds benching losses (Table 9.5, interpolated between the submerged and unsubmerged
columns on Eai/Do), angled inflow losses from the flow-weighted angle of only the non-plunging pipes, and plunging
losses with drops limited to 10 diameters, with a zero floor on the added loss and a floor at the outflow pipe's
energy. The plunging test compares an inflow invert with the initial energy level Eai, while the exit loss and
Table 9.6 compare it with the final level, and the two disagree for some pipes. The data holds 1,060 pipe and
event rows. The generator places values just to either side of the thresholds that change an answer: 431
comparisons sit within 0.03 ft of their threshold (receiving water and structure energy levels against crowns,
normal and critical depths and inverts, upstream grade lines against crowns, inflow inverts against Eai, and
energy levels against rims). Each shortcut tried (29, from swapping the 0.2 and 0.4 coefficients to a single
plunging test or rounding like Example 9.2) gets some rows right and others wrong. The networks are synthetic but
follow HEC-22 pipe sizes, slopes, roughness values and structure configurations.

## Solution

The reference solution (solution/solve.py) builds each network as a tree, adds inlet flows downstream, and then
walks upstream from the outfall recursively. For each pipe it solves normal depth by bisection on Manning's
equation for the circular segment and critical depth by bisection on the minimum specific energy condition,
classifies the downstream end by Table 9.6 and the upstream end by Table 9.7, and then computes the structure's
energy level by equations 9.13 to 9.29 before continuing into each inflow pipe.

## Verification

The verifier recomputes every pipe and event with its own independently written engine (tests/engine.py, which
orders each network with an explicit queue from the outfall, works in the central angle of the circular section,
solves normal depth by a safeguarded Newton iteration and critical depth by the Illinois regula falsi method) from
a private copy of the inputs that exists only in the verifier image, and never runs agent code. The data generator
(authoring/sim.py, bisection in depth) is a third implementation; the engine and generator agree on every letter
and within 1e-12 ft, and the generator keeps every threshold comparison at least 0.001 ft away from its
threshold. The engine is checked against the worked values of HEC-22 Examples 9.1 and 9.2 (full-flow capacities,
friction slope, discharge intensities, the three initial energy levels, the angled inflow coefficient and the
energy levels of structures 40 to 43) and the Table 9.5 interpolation. Tests check that the inputs are consistent,
the value formats, one row per pipe and event in order, one test per method family (outfall pipes, submerged,
partly full and normal-depth outlets, full flow and supercritical resets at the upstream end, plunging and angled
inflows, terminal structures, interpolated benching, drops over 10 diameters, structures where the outflow
pipe's energy governs, surcharged structures and rows near a threshold) and finally every row. The letters and
surcharge must match exactly; where a pipe runs at normal depth its upstream grade line equals the invert plus
normal depth by construction, and either Table 9.7 letter on that boundary is accepted. Elevations must be within
0.002 ft. Reward is 1 only if every test passes.
