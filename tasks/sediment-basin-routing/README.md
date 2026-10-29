# sediment-basin-routing

A wet-season (April 1 to September 30, 2026) hydrologic and hydraulic simulation of the sediment basins on 12
construction sites in Puerto Rico. For every basin and storm the agent reports the peak inflow, peak outflow, peak
water surface elevation and whether the emergency spillway flowed.

## Difficulty

Water resources engineers check construction sediment basins with the NRCS and FHWA methods that WinTR-20,
WinTR-55 and HydroCAD implement, and every answer here comes from one coupled, continuous simulation. Runoff for
each drainage area comes from the curve number equation of NEH Part 630 Chapter 10 applied to the rain
accumulated since each storm began (example 10-6), with storms separated by six dry hours, and each area's curve
number follows its undisturbed, disturbed or stabilized state as grading and stabilization proceed; areas are
separate hydrologic units, so an averaged curve number (the Chapter 10 example 10-5 contrast) gives wrong peaks.
Each area's unit hydrograph comes from the Chapter 16 dimensionless unit hydrograph (Table 16-1, peak rate factor
484, Tp from the unit duration and lag), convolved with the 6-minute rainfall excess and added at its basin. Each
basin's stage-storage relation is trapezoidal (HEC-22 equation 10.10), and its stage-discharge relation adds a
dewatering orifice with head from its centroid, a riser that acts as a weir on its circumference and then as an
orifice on its area (HEC-22 example 10.11), and a broad-crested emergency spillway (HEC-22 table 10.10).
Storage-indication routing (NEH Chapter 17 equation 17-3) runs continuously through the season, so water left in
a basin changes the next storm's peak, and upstream basins feed downstream basins in the same time step. The
data holds 546 storms across 28 basins (1,432 basin-storm rows), with storm gaps just under and over six hours, curve number changes
between storms, riser control transitions and many storms that come within hundredths of a foot of a spillway
crest. Each shortcut (per-increment runoff, an averaged curve number, restarting basins each storm, ignoring
upstream basins, a weir-only riser, head from the orifice invert, a prismatic basin, a step time in minutes)
gets many rows close and others outside the tolerance. The data is synthetic but follows real construction
sites, Puerto Rico wet-season rainfall and HEC-22 outlet designs.

## Solution

The reference solution (solution/solve.py) splits each site's gauge record into storms, computes each drainage
area's accumulated runoff with the curve number of its state at the storm's start, convolves the 6-minute
excess with the area's unit hydrograph from Table 16-1, and sums the hydrographs at each basin. It builds each
basin's trapezoidal stage-storage relation and composite stage-discharge relation, then routes the basins in
upstream-to-downstream order through the whole season, solving each storage-indication step on the continuous
relations with a safeguarded Newton method, and reports each storm's peaks over the 6-minute points from the
storm's start to the next storm's start.

## Verification

The verifier recomputes every basin and storm with its own independently written engine (tests/engine.py, which
gathers each hydrograph point by point, keeps the unit hydrograph table as a dict of segments and solves each
routing step with the Illinois regula falsi method, while the reference solution scatters convolution sums and
uses Newton's method) from a private copy of the inputs that exists only in the verifier image, and never runs
agent code. The data generator (authoring/sim.py, bisection) is a third implementation; the three agree to about
one millionth of a foot and of a cubic foot per second, and the generator moves any spillway crest that a peak
would come within 0.002 ft of. The engine is checked against published worked examples (NEH Chapter 10 example
10-1 and table 10-2, Chapter 16 example 16-1, HEC-22 examples 10.10 and 10.11 and equation 10.10) and against
planted storms whose peak inflows were worked by hand. Tests check that the inputs are consistent, the value
formats, one row per basin and storm in order, the hand-worked storms, one test per method family (peak inflow,
basins that stay below the riser, riser flow, spillway flow, basins in series, storms that begin with water left
from earlier storms) and finally every row, with flows within 0.5 percent or 0.01 cfs and stages within 0.005
ft. Reward is 1 only if every test passes.
