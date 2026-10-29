# Messages to the person

Everything they paste goes in a code block. Plain words, no em dashes, short.

## Asking for a document

```
I need one PDF: "<exact title>" (<issuer>, <edition or year>).
Download it here: <link you confirmed by web search>
It should be about <N> pages, with <sections that prove it is the full document>.
If that link doesn't work, try <second confirmed link> and click "PDF".
```
If the file is over the upload limit: ask for chapter page ranges (Chrome or Edge: Ctrl+P, Save as
PDF, Pages: Custom; the browser's page counter, not the printed numbers), or use a document you
already have.

## Sending a zip

```
<task-name> is ready: <one-line description>.
What's in it: <cases, the main data mess, word count of the instruction, what is compared exactly>.
Checks I ran: <three models agree on every row; oracle N/N; empty output fails; M of M shortcuts caught>.
Upload: delete the old tasks/<old-name> folder on your PR branch (only one task folder is allowed),
then upload tasks/<task-name> from the zip. Keep the folder name <task-name>; it must match the name
line in task.toml.
```

## Upload steps (when they ask how)

```
1. Unzip the file. You get tasks/<task-name>/.
2. On GitHub, open your repository and switch to the PR's branch.
3. If an old task folder is there, open it, use the "..." menu, Delete directory, Commit changes.
4. Add file > Upload files > drag the tasks folder in > Commit changes to the same branch.
5. On the PR, the "Files changed" tab should show only tasks/<task-name>/.
```

## PR title and description

Title:
```
Add <task-name>: <job in plain words> (<standard short name>)
```
Description:
```
## Summary
<who, how many cases, what the agent produces, the standard with citation>

## What the agent receives
- <file>: <contents>

## Output
<path, header, one row per, comparison>

## Why it is hard
<the method that breaks down, the messy records, near-threshold planting, the exact decisions>

## Data
<synthetic, seeded generator, ranges from the standard>

## Verification
- <independent engine and its methods; private data; never runs agent code>
- <generator as third implementation; agreement level; uniqueness and margins>
- <golden checks against published examples>
- <tests: formats, order, families, every row; reward 1 only if all pass>

## Local checks (saved in authoring/evidence/)
- Oracle: N of N tests pass. Empty output: M fail.
- Agreement: <numbers>.
- Calibration: all K shortcuts fail, for example <three with their wrong-row counts>.
```

## Status after a log zip

```
Result: <stage> failed (<everything else that passed>). / All stages passed.
Log line: "<exact quote>"
What it means: <plain words>
What I changed: <files>
Rechecked: <numbers>
Cost: <this stopped before Pass@2, so no attempt was used / this used attempt N of 15>
Update your PR: <replace these files or the folder>
```

## Time questions

- The agent gets up to 8 hours per trial (task.toml `timeout_sec = 28800`, required by static
  checks). It stops when it finishes; earlier trials took 27 to 43 minutes.
- The person's own work time on Handshake is a different clock.
