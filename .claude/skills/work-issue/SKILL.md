---
name: work-issue
description: Pick up a GitHub issue in this repo, implement it on a feature branch, and open a PR with a comment linking back to the issue. Use when asked to work an issue, pick up a ticket, "do issue #N," or continue a loop of issues.
---

# Work a GitHub issue

Repo: **`bry5an/podcast-parrot`** (origin). `gh` is already authenticated as `bry5an`.

This repo has an evolving memory record (per-issue gotchas for whisper.cpp, PyInstaller, the Tauri sidecar, objc2, etc.) — consult it for context on the area you're touching, and it'll pick up whatever you learn this session automatically.

## 0. Start in plan mode

Call `EnterPlanMode` before doing anything else in this skill. Do steps 1-2 and the scoping part of step 4 (research: reading the issue, checking the dependency chain, deciding ambiguous points) while in plan mode, then present the resulting plan — which issue, base branch, the concrete changes, and how any ambiguous points were resolved — via `ExitPlanMode` for the user's approval. Only start branching/implementing (step 3 onward) after that approval.

## 1. Pick the issue

If a number or URL was given, use it directly. Otherwise:
```
gh issue list --state open
```
Use AskUserQuestion to let the user pick if there's more than one live candidate — don't guess which one they mean.

## 2. Read full context, and check the dependency chain for real

```
gh issue view <n> --comments
```
Read the whole body **and** the comments. If the issue has a `Depends on #X` line, don't trust the issue text alone — check that dependency's *actual current code state*:
```
gh pr list --state all --search "<X> in:body"
git log --oneline main -5
```
- If the dependency is merged to `main`, branch off `main` even if other unmerged sibling branches exist — don't assume every new issue stacks onto the most recent branch.
- If it isn't merged yet, branch off the dependency's branch instead of `main`.
- If local `main` looks behind `origin/main` (a stale local checkout), fast-forward it first: `git checkout main && git merge --ff-only origin/main`.

## 3. Branch

```
git status                      # don't build on top of unrelated uncommitted work — stop and ask instead
git checkout -b issue-<n>-<short-slug>
```
(from wherever step 2 concluded — `main` or the dependency's branch)

## 4. Scope and, if needed, decide ambiguous points yourself

Where the issue's checklist is silent or ambiguous on a design point, make the smallest decision consistent with the codebase's existing patterns and document the reasoning in the PR body rather than stopping to ask — unless the ambiguity is genuinely costly to get wrong or irreversible, in which case use AskUserQuestion. For an issue with several independent deliverables, use TaskCreate to track them individually rather than holding the checklist in your head.

Keep the diff scoped to the issue — no drive-by refactors or unrelated fixes (file a note for the user instead if something else looks broken).

## 5. Implement — ground every external dependency in the real thing

Before writing code against an external binary/tool/library/bundler the issue touches (whisper-cli, a system framework, PyInstaller, Tauri, a new package), install/build/run the real thing if it's reasonably cheap, and actually execute the produced artifact end-to-end. **"It built with no errors" is not evidence it works** — this has caught a real, otherwise invisible bug essentially every time it was tried in this repo (whisper.cpp's exact JSON field names, a dictionary path that silently failed without an explicit flag, PyInstaller quietly omitting a dependency's data files despite a clean build log and a healthy `/api/health`, and a PyInstaller bootloader that only breaks once actually running from inside a real `.app` bundle). Treat "it compiled" and "I read the docs and reasoned about it" as insufficient on their own for anything touching a real external tool.

## 6. Verify before moving on

- Backend: `uv run pytest`, `uv run ruff check .`
- Frontend: `npm run build && npm run lint && npm run test`
- UI changes: actually drive them against a real dev server (not just component tests) — cheap once the servers are up, and the only way to be sure end-to-end wiring (polling, redirects, progress) really works.
- Anything touching a bundler/packaging step (Tauri, PyInstaller): build the real artifact and launch it, don't just trust the build log.

## 7. Commit

Stage specific paths (check `git status` after any broad `git add`, and double-check contents of anything that could hold a secret before it's staged). Write the commit message to a scratch file first if it will contain backticks, `<>`, or other shell-special characters — they silently mangle a `git commit -m "..."` string — then:
```
git commit -F <scratch-file>
```

## 8. Push and open a PR

```
git push -u origin issue-<n>-<short-slug>
gh pr create --title "feat: <summary> (#<n>)" --body-file <scratch-file> --base main --head issue-<n>-<short-slug>
```
PR body style: Summary bullets mirroring the issue's deliverables, a Verification section (what you actually ran/built/launched, and anything you *couldn't* verify — e.g. no GUI automation available — say so plainly rather than implying it was click-tested), and a Known limitations section for anything explicitly out of scope. **Include a `Closes #<n>` line** (GitHub's linking keyword — `Fixes`/`Resolves` also work) so the issue auto-closes when the PR merges to `main`. Use `--body-file`, not an inline `--body` string, for the same shell-escaping reason as step 7.

## 9. Comment on the issue with the PR link

```
gh issue comment <n> --body-file <scratch-file>
```
Summarize what shipped (not a re-explanation of the issue body) and link the PR (the `Closes #<n>` in the PR body already wires up auto-close — the comment is for a human-readable summary, not a substitute for that link). **Do not close or merge the PR, and do not close the issue** — that's the user's call to make after reviewing.

## 10. Report and continue

Summarize what changed, what you verified (and what you explicitly couldn't), and the PR link. If this is one of a loop of issues, wait for the user's go-ahead (or a standing instruction to keep looping) before picking up the next one — a growing pile of unmerged branches or a sharp jump in technology area (e.g. Python/TS work followed by Rust/Tauri work) is a reasonable natural point to check in even under a "keep going" instruction.
