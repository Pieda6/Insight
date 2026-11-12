# Reading the Pass@2 trajectories and what beats the model

## Getting them
Ask the person to download, from the GitHub Actions run page (Summary, Artifacts), `pass2-output` (and
`pass2-summary`). Unzip each into its own new folder. Layout:

```
<runid>-pass2/
  result.json, config.json, job.log
  task__XXXX/                     one folder per trial
    agent/trajectory.json         steps: [{source, message, tool_calls:[{arguments}]}], final_metrics
    agent/mini-swe-agent.trajectory.json
    artifacts/app/output/...      the agent's output files
    verifier/test-stdout.txt      pytest output: which tests failed and the bad-row list
    verifier/reward.txt           1 = solved
```

## The three things to do with them
1. Score each trial's output against the engine yourself (load tests/engine.py, compare every row, print the worst
   deviations and which allowed variant each row matched). This tells you whether a solve was exact or lucky.
2. Print the steps in order (index, source, first 400 characters of the message, first 400 of the command):

```python
import json,sys
d=json.load(open(sys.argv[1])); st=d['steps']; print(len(st), d.get('final_metrics'))
for i,s in enumerate(st):
    cmd=' | '.join(json.dumps(c.get('arguments',''))[:300] for c in (s.get('tool_calls') or []))
    print(f"--{i} [{s.get('source')}] {(s.get('message') or '')[:400]!r}\n   CMD {cmd[:400]}")
```
3. Read `verifier/test-stdout.txt` for a failed trial: the bad-row list shows exactly which family it missed.

## What the model (Gemini, mini-swe-agent) does, every time
- Lists the data, prints every table and a summary of every field value.
- If any standard text is in /app/data, reads it section by section (TG-71: ~15 of 44 steps), including the worked
  examples, and reproduces a worked example by hand.
- Tests every alternative reading against the data and keeps the one the text supports: KDIGO naive time vs DST,
  26.5 vs 26.52, thresholds within 0.005; TG-71 Eq. 1 vs Eq. 3, the Mayneord bracket, WF field, OAR projection,
  power-law distances, both SSDeff means.
- Bounds-checks every lookup against every table range, then writes one script and runs it once over all records.
- So: the number of records adds no difficulty; planted edges with one correct reading never trap it; anything the
  shipped text states, it applies correctly.

## What made it fail
- **Long chained computation that cannot be checked from the data** (HEC-22 grade lines through a network): an early
  slip leaves no trace.
- **A recent or detailed standard it only half remembers, with no text shipped**: TG-71 without tg71.txt, the model
  misremembered the rectangular-insert rule for SSDeff and the air-gap factor (it believed "III.B.3 does NOT
  explicitly state a square-root method") and both trials failed the same 4 beams.
- **Categorical outputs at many planted boundaries** (civil case letters).

## The trap in that last success
When failures land on one undisclosed rule, the deep review fails the task (G-DIFF, U1-U3). When the rule is written
out, the model gets everything right. The resolution that keeps both (see `disclosure.md`): name the standard and the
governing sections in the instruction, keep the text out of /app/data, put the exact quotes in `authoring/sources/`
and as comments in tests/engine.py, and make sure there are many independent places to slip, not one.

## Timings seen
sediment-basin 27/43 min (solved), vancomycin v1 56 min, v2 25 min (0/2), v3 16 min, v5 34 min, TG-71 v1 ~28 min
(solved, exact), KDIGO solved after ~57 steps. Under 45 minutes for 2/2 means the instruction or shipped text is
doing the work.
