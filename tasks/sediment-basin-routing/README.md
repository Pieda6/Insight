# sediment-basin-routing

A wet-season (April 1 to September 30, 2026) hydrologic and hydraulic simulation of the sediment basins on 12
construction sites in Puerto Rico. For every basin cell and storm the agent reports the peak inflow and outflow,
the peak water surface and its time, whether the emergency spillway flowed, and the volume that went over it.

## Difficulty

Water resources engineers check construction sediment basins with the NRCS and FHWA methods that WinTR-20,
WinTR-55 and HydroCAD implement, and every answer here comes from one coupled, continuous simulation in which the
steps depend on each other. Each drainage area's time of concentration comes from its flow path by TR-55
Chapter 3 (sheet flow with the Table 3-1 roughness of its current surface and the site's 2-year rainfall, shallow
concentrated flow, Manning channel flow, and the 0.1-hour minimum that graded areas often fall below), so the unit
hydrograph changes when an area is graded or stabilized, along with its curve number. Runoff comes from the rain
accumulated in each storm (NEH Part 630 Chapter 10 example 10-6, storms separated by six dry hours), and each
area's Chapter 16 unit hydrograph (Table 16-1, peak rate factor 484) is convolved with the 6-minute excess.
Basins are trapezoids or surveyed contours (HEC-22 conic formula, equation 10.19). Main cells drain through a
dewatering orifice with head from its centroid, a riser that changes from weir to orifice control (HEC-22
example 10.11) and a broad-crested spillway. Many basins have a forebay that drains to the main cell through a
divider weir and orifice; when the main cell rises, it submerges the divider (HEC-22 equation 10.34 for the weir,
the difference of water surfaces for the orifice) and flow can run back into the forebay, so the forebay and main
cell must be routed together at every step: routing them one after the other with a lagged level gives wrong
peaks in exactly the storms that matter. Routing runs continuously through the season, so water left from one
storm changes the next, and some main cells feed other basins. The data holds 2,201 cell-storm rows with storm
gaps just under and over six hours, state changes between storms, divider submergence and reversal, riser control
changes and storms within hundredths of a foot of a spillway crest, and asks for the time of peak stage and the
spilled volume, which magnify small errors. Each shortcut (per-increment runoff, a fixed time of concentration,
no TR-55 minimum, average-end storage, a free or one-way divider, lagged forebay routing, restarting basins,
ignoring upstream cells) gets many rows close and others outside the tolerance. The data is synthetic but follows
real construction sites, Puerto Rico wet-season rainfall and HEC-22 outlet designs.

## Solution

The reference solution (solution/solve.py) splits each site's gauge record into storms, computes each area's time
of concentration for each state from its flow path, its accumulated runoff with the curve number of its state at
the storm's start, and convolves the 6-minute excess with the unit hydrograph of that state. It builds each cell's
stage-storage relation (trapezoid or conic contours) and outlet or divider relations, then routes the main cells
in upstream-to-downstream order through the whole season, solving each storage-indication step on the continuous
relations; a forebay and its main cell are solved together with nested bracketed Newton steps. It reports each
storm's values over the 6-minute points from the storm's start to the next storm's start.

## Verification

The verifier recomputes every cell and storm with its own independently written engine (tests/engine.py, which
gathers hydrographs point by point, accumulates conic slices, solves single cells with the Illinois regula falsi
method and coupled cells with a two-dimensional Newton method that falls back to nested regula falsi, while the
reference solution scatters convolution sums and uses nested bracketed Newton steps) from a private copy of the
inputs that exists only in the verifier image, and never runs agent code. The data generator (authoring/sim.py,
nested bisection) is a third implementation; the engine and generator agree within 0.0001 cfs and 0.000001 ft,
and the generator moves any spillway crest that a peak would come within 0.002 ft of. The engine is checked
against published worked examples (NEH Chapter 10 example 10-1 and table 10-2, Chapter 16 example 16-1, TR-55
example 3-1, HEC-22 examples 10.10 and 10.11 and equations 10.10, 10.19 and 10.34) and against planted storms
whose peak inflows were worked by hand. Tests check that the inputs are consistent, the value formats, one row per
cell and storm in order, the hand-worked storms, one test per method family (peak inflow, cells below the riser,
riser flow, spillway flow and volume, forebays and their main cells, cells fed by other main cells, surveyed
contour cells, storms that begin with water left from earlier storms) and finally every row, with flows within
0.5 percent or 0.01 cfs, stages within 0.005 ft, spill volumes within 1 percent or 5 cubic feet, and any time of
peak whose stage is within 0.0005 ft of the peak. Reward is 1 only if every test passes.
