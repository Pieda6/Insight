# Worked examples

Two illustrative trucks (not units from the fleet). Both use the same tractor and tare
weights and two 240 in pallets. Positions are in inches from the inside front wall of the
trailer, and the kingpin is at 36 in. Each pallet's weight acts at the middle of its
footprint. Each tandem's load is split equally between its two axles.

Spans are converted to feet and rounded to the nearest whole foot, with exactly half a
foot rounding up. W = 500 x (L x N / (N - 1) + 12N + 36) is then rounded to the nearest
500 lb, with exactly 250 rounding up.

## Example 1: legal at 79,500 lb gross

Axle positions (in): steer -190, drive 20 and 72, trailer 402 and 452.
Pallets (weight lb, front edge in, length in): (27000, 0, 240), (24500, 240, 240).
Tare (lb): 11000, 4600, 4600, 3900, 3900.

Exact axle loads (lb): 12076.17, 16760.76, 16760.76, 16951.15, 16951.15; gross 79500.00.

| Axles | Span (in) | Span (ft, rounded) | N | Formula W (lb) | Limit used (lb) | Load (lb) | OK |
|---|---|---|---|---|---|---|---|
| 1-2 | 210 | 17.500 -> 18 | 2 | 48000 | 48000 | 28836.94 | yes |
| 1-3 | 262 | 21.833 -> 22 | 3 | 52500 | 52500 | 45597.70 | yes |
| 1-4 | 592 | 49.333 -> 49 | 4 | 74500 | 74500 | 62548.85 | yes |
| 1-5 | 642 | 53.500 -> 54 | 5 | 82000 | 82000 | 79500.00 | yes |
| 2-3 | 52 | 4.333 -> 4 | 2 | 34000 | 34000 | 33521.52 | yes |
| 2-4 | 382 | 31.833 -> 32 | 3 | 60000 | 60000 | 50472.68 | yes |
| 2-5 | 432 | 36.000 -> 36 | 4 | 66000 | 68000 | 67423.83 | yes |
| 3-4 | 330 | 27.500 -> 28 | 2 | 58000 | 58000 | 33711.91 | yes |
| 3-5 | 380 | 31.667 -> 32 | 3 | 60000 | 60000 | 50663.06 | yes |
| 4-5 | 50 | 4.167 -> 4 | 2 | 34000 | 34000 | 33902.30 | yes |

Axles 2-5 are two consecutive tandems at 36 ft, so they may carry 34,000 lb each
(68,000 lb) even though the formula alone gives 66,000 lb. The steer axle (20,000 lb),
both tandems (34,000 lb) and gross (80,000 lb) are also within limits.

## Example 2: illegal at 76,500 lb gross

Same tractor and tare. Trailer tandem slid forward: trailer axles at 382 and 432.
Pallets: (25000, 0, 240), (23500, 240, 240).

Exact axle loads (lb): 11945.62, 15285.54, 15285.54, 16991.64, 16991.64; gross 76500.00.

| Axles | Span (in) | Span (ft, rounded) | N | Formula W (lb) | Limit used (lb) | Load (lb) | OK |
|---|---|---|---|---|---|---|---|
| 1-2 | 210 | 17.500 -> 18 | 2 | 48000 | 48000 | 27231.17 | yes |
| 1-3 | 262 | 21.833 -> 22 | 3 | 52500 | 52500 | 42516.71 | yes |
| 1-4 | 572 | 47.667 -> 48 | 4 | 74000 | 74000 | 59508.36 | yes |
| 1-5 | 622 | 51.833 -> 52 | 5 | 80500 | 80500 | 76500.00 | yes |
| 2-3 | 52 | 4.333 -> 4 | 2 | 34000 | 34000 | 30571.09 | yes |
| 2-4 | 362 | 30.167 -> 30 | 3 | 58500 | 58500 | 47562.73 | yes |
| 2-5 | 412 | 34.333 -> 34 | 4 | 64500 | 64500 | 64554.38 | NO |
| 3-4 | 310 | 25.833 -> 26 | 2 | 56000 | 56000 | 32277.19 | yes |
| 3-5 | 360 | 30.000 -> 30 | 3 | 58500 | 58500 | 49268.83 | yes |
| 4-5 | 50 | 4.167 -> 4 | 2 | 34000 | 34000 | 33983.29 | yes |

Gross, the steer axle and both tandems are within limits, but the group of axles 2-5
spans only 34 ft, so its limit is 64,500 lb and the truck is overweight on that group.
