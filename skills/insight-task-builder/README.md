# Insight task builder skill (v4): how to install

This folder teaches Claude or ChatGPT to build Project Insight (TB3) tasks the way they were built in
our sessions. Start every new task chat with: "Use the Insight task builder skill. Category: X,
sub-category: Y."

Claude (claude.ai):
- Best: Settings > Capabilities > Skills > upload this folder as a zip (if your plan has Skills).
- Or: create a Project, add all the files in this folder to the Project knowledge, and paste the
  contents of SKILL.md into the Project instructions.
- Make sure code execution is turned on (Settings > Capabilities).

Claude Code: put the folder at `.claude/skills/insight-task-builder/` in your repo.

ChatGPT:
- Create a Project (or a custom GPT), upload all files as knowledge files, and paste SKILL.md into the
  instructions box. If only one file is allowed, upload `SKILL-single-file.md`.
- Use a model with code execution (the Python sandbox). Ask it to run `print(1+1)` once to confirm.

Files:
- SKILL.md: the core (role, hard rules, workflow, verification).
- reference/: difficulty, CI checks, instruction.md, message templates, build steps.
- templates/: files that must be copied exactly, plus local_check.py and calibrate.py.
- example/hos-log-audit/: a complete accepted-quality task to learn from.
- SKILL-single-file.md: everything except the example, in one file.
