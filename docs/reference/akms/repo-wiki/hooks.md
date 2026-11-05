# hooks

`repo-wiki hooks` installs optional git hooks that keep the symbol graph and
`flows.json` current. After git changes the tree, a hook starts the incremental build
in the background, so `context`, `impact`, `changes` and `flows` find a fresh graph
without a manual rebuild. Nothing is installed until you run `hooks install`.

```bash
repo-wiki hooks install     # add the hook blocks
repo-wiki hooks status      # what is installed, and the last background build
repo-wiki hooks uninstall   # remove exactly what install added
```

Each takes `--json`. Put `--repo-root PATH` before `hooks` when the wiki lives in a
subdirectory of the git worktree; that root is recorded in the repository's git
config as `akms-repo-wiki.root`, not in a tracked file.

## What is installed

One marked block in each of `post-checkout`, `post-commit`, `post-merge` and
`post-rewrite`, in the directory git runs hooks from (`git rev-parse --git-path hooks`,
which honours `core.hooksPath` and linked worktrees):

- A hook that does not exist is created with mode `0700`, holding only the block.
- An existing POSIX shell hook (`sh`, `bash`, `dash`, `zsh`, ...) gets the block right
  after its `#!` line. Everything outside the markers is kept byte for byte, and the
  file keeps its mode.
- A symlinked hook, a hook in another language, a hook that is not executable (git
  would not run it) and a hook tracked by git are refused, and nothing is written.

The block sits between `# >>> akms-repo-wiki hook >>>` and
`# <<< akms-repo-wiki hook <<<`. The `failure-memory` hooks use the same rules with
their own markers, so the two tools can be installed in either order and each one's
`uninstall` leaves the other's block untouched. When both are removed, a hook file may
be left holding only `#!/bin/sh`, which git runs as a no-op.

`install` is idempotent; run it again after moving the virtual environment, since the
block names the Python that installed it. `status` flags a block that no longer
matches (`outdated`).

## What runs, and when

The block runs `python -m akms.repo_wiki.hooks run <hook>`, which decides from files
in the worktree's git directory whether this git command should refresh. A refresh
happens at most once per git command:

| Git command | Hooks git runs | Refreshes |
|---|---|---|
| `git commit` | `post-commit` | once |
| `git commit --amend` | `post-commit`, `post-rewrite amend` | once, from `post-rewrite` |
| `git checkout BRANCH`, `git switch` | `post-checkout` (branch flag) | once, if `HEAD` moved |
| `git checkout -- FILE` | `post-checkout` (file flag) | no |
| `git merge`, `git pull` | `post-merge` | once |
| `git rebase` | `post-checkout`, one `post-commit` per commit, `post-rewrite rebase` | once, at the end |
| `git cherry-pick A..B`, `git revert A..B` | one `post-commit` per commit | once, after the last commit |
| `git bisect ...` | `post-checkout` per step | no, not even for `bisect reset` |

During a bisect the graph is never rebuilt, so after `git bisect reset` it still
matches the branch you return to.

A refresh is `repo-wiki build --changed-only --no-summaries --no-index`, run by a
detached worker:

1. The hook records a pending refresh in `.repo_wiki/hooks/pending` and starts the
   worker. The git command does not wait: a `git commit` that triggers a refresh
   takes about 0.07 s instead of 0.02 s on the AKMS repository (mostly Python
   start-up).
2. The worker takes the build lock (`.repo_wiki/locks/repo-wiki-build.lock`, shared
   with `repo-wiki build` and `changes --refresh`) and runs the build, about 1 s on
   the AKMS repository.
3. While a refresh is pending, it builds again. Only one worker runs at a time, so a
   burst of git commands costs one or two builds.

The worker writes to `.repo_wiki/hooks/build.log` (rotated to `build.log.1` past
512 KB): one line per trigger and per build, with what it re-parsed and how long it
took. A failed build is logged and never reported to git.

## Turning it off

- `AKMS_REPO_WIKI_HOOKS=0` skips the hooks for one command or a whole shell.
- `repo-wiki hooks uninstall` removes the blocks and the recorded root.
- In a repository that never ran `install` (for example one sharing a global
  `core.hooksPath`), the block does nothing.

## Hooks and `--refresh`

With the hooks installed, the graph is usually current after any git command. It
does not follow edits you have not committed, and the background build may still be
running. `repo-wiki changes --refresh` builds under the same lock first, so it always
reports on a graph that matches the working tree. See
[changes](changes.md#flags).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | Refused or failed: `not_a_git_repository`, `hook_unsupported`, `hook_disabled`, `hook_tracked`, `hook_block_damaged` or `git`. Nothing is written when any hook is refused. |

With `--json`, a failure prints a `repo-wiki/error/v1` object on stdout.
