# Message templates

Everything the person pastes somewhere (proposal, PR title, PR description) goes in a code block so
they can copy it in one go. No em dashes anywhere.

## 1. Task ideas (after they give a category and sub-category)

```
| # | Task | Governing rule | What makes it hard | Main risk |
|---|------|----------------|--------------------|-----------|
| 1 | <job, one line> | <CFR / statute> | <exact computation + rare exclusion> | <what could make it easy or ambiguous> |
| 2 | ... | ... | ... | ... |
| 3 | ... | ... | ... | ... |
```
Then: "I recommend #N because <one line>. You'd paste these pages: <URLs>."

## 2. Asking for the law

```
Please paste these pages (open each, press Ctrl+A, Ctrl+C, then paste here; one message or several is fine):
1. https://www.law.cornell.edu/cfr/text/49/395.1 (scope and exceptions)
2. https://www.law.cornell.edu/cfr/text/49/395.2 (definitions)
3. https://www.law.cornell.edu/cfr/text/49/395.3 (the limits)
```
If a message is too long, tell them how to split it.

## 3. Proposal (fill every field; the HOS proposal is a model)

```
Title: <plain title, e.g. Hours-of-service audit of truck drivers' duty records (49 CFR 395)>

Category: <Operations>
Sub-category: <Logistics>

Summary:
<2-4 sentences: who does the job, what the agent receives, what it must output, which rule.>

Real-world grounding:
<Who does this work for real and why. The governing law with its version date.>

Why it is hard:
<The rule details and computations that decide answers, as a short list. Mention near-miss cases.>

Inputs: <files and formats>

Output: <file, columns, exact comparison>

Verification: <independent engine recomputes everything, checked against hand-worked cases; tests per rule family plus the full output.>
```
If Proposal QC asks to pin a convention, pin it as a fact in instruction.md. If QC asks for a
"rules file" with the law's numbers, explain that it would fail the artificiality check (A5) and
that the task cites the rule and version date instead.

## 4. Upload steps (send with every zip)

```
1. Unzip the file on your computer. You'll get a folder tasks/<task-name>.
2. On GitHub, open the PR's branch (the branch name is on the PR page).
3. If an older version of the folder is there and you changed data, delete the old folder first:
   open it, use the "..." menu, Delete directory, Commit changes.
4. Add file > Upload files > drag the tasks folder in > Commit changes (commit to the same branch).
5. Check the PR's "Files changed" tab shows only tasks/<task-name>/.
```
For a brand-new task the first time: create the branch from the Code tab's branch menu, upload,
then Contribute > Open pull request.

## 5. PR title and description

Title:
```
Add <task-name>: <one-line job description with the rule, e.g. hours-of-service audit of drivers' duty records under 49 CFR 395.1-395.3>
```
Description:
```
## Summary
<Who does the job, what the agent gets, what it outputs, the rule and its version date.>

## What makes it hard
- <rule detail 1, stated plainly>
- <rule detail 2>
- ...

## Data
- /app/data/<file>: <what it holds>
- ...

## Output
<path, header, what a row means, exact comparison>

## Verification
- tests/engine.py recomputes everything independently (<method>), while the reference solution uses <other method>. Both agree on all <N> rows.
- The engine is checked against <N> hand-worked planted cases (tests/golden.json).
- Tests: format, hand-worked cases, one test per rule family (<list>), and the full output. Reward is 1 only if every test passes.
- The verifier runs in a separate image from a private copy of the data and never runs agent code.
- <N> shortcut solutions (<examples>) each fail at least one test. The oracle passes and an empty output fails.
```

## 6. Status after CI

```
<Task> result: <stage that failed, or "all checks passed">.
Log line: "<exact quote>"
What it means: <plain words>
What I changed: <bullets>
Checks I ran: <numbers>
Next run: spends <1 / no> Pass@2 attempt (<N> of 15 used so far).
```

## 7. When you cannot do something

Say it directly: "I can't open that page from here; please paste it." "I can't see the Handshake
site, so check with your project lead whether the proposal can be edited." Never guess about the
platform's rules.
