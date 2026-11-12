# insight-science-task-builder

A skill for Claude that builds Project Insight Science (TB-Science) tasks end to end and runs Project Hertz
tasks (codebase, brief, conversation, flags, finish notes), with the full record of every run so far.

## How to use it

- **Claude Code or the Claude desktop app with skills:** put this folder in `.claude/skills/` (project)
  or `~/.claude/skills/` (personal). Claude loads `SKILL.md` and reads the reference files as needed.
- **Claude.ai with code execution:** upload the zip as a skill (Settings, Capabilities, Skills), or
  attach `SKILL-single-file.md` to the conversation or a Project's knowledge.
- Start with: "Use the insight-science-task-builder skill. My subcategory is <X>. Give me a task idea."
  For Hertz: "Use the insight-science-task-builder skill, Hertz part. Here is my claimed task."

## Contents

- `SKILL.md`: the procedure and the hard rules.
- `reference/`: the full run-by-run record (`history.md`), the disclosure playbook for Pass@2 versus the deep
  review and AVA (`disclosure.md`), trajectory reading (`trajectories.md`), Kyoto checks and the REPAIR_PORT design
  (`kyoto.md`), source documents (`sources.md`), Project Hertz end to end (`hertz.md`), pipeline and log reading,
  difficulty lessons, proposal template with a real example, build details, file formats, instruction style,
  message templates.
- `templates/`: files to copy unchanged (Dockerfiles, test.sh, .dockerignore, solve.sh,
  local_check.py) and skeletons (task.toml, test_outputs.py, calibrate.py).
- `examples/vancomycin-auc-dosing/`: a complete Medicine task that passed static checks, the
  artificiality probes A1 to A7, the TB-Science authoring review and the scientifically-grounded
  review. `examples/storm-drain-energy/`: a complete Civil Engineering task that cleared the checks.
  `examples/hertz-csvkit-attempt1/`: a Hertz attempt1 folder that passed the automated pre-check and the
  automated brief review. The repository's `tasks/tg71-mu-check/` (passed Pass@2 and a deep review) and
  `tasks/tg51-output-audit/` (Kyoto REPAIR_PORT) are the latest medicine builds.
- `SKILL-single-file.md`: everything above except the example code, in one file.
