# Overview

AKMS solves a narrower problem than “build an autonomous agent”: it makes
project and domain knowledge explicit, typed, queryable, and reusable across
agent sessions and harnesses.

## The problem

Coding and research agents repeatedly face three failures:

1. Relevant domain knowledge exists, but is buried in prose, prior sessions, or
   another repository.
2. Task context is selected heuristically, so a required constraint can be
   omitted without anyone noticing.
3. Lessons and failures are recorded inconsistently, mixed with generated
   artifacts, or promoted into shared memory without a clear owner.

## The AKMS approach

AKMS separates these concerns:

- **Knowledge nodes** are Markdown documents with strict v2 frontmatter.
- **Graph compilation** merges global, local, code-mirror, and overlay inputs.
- **Ranked queries** select advisory knowledge from tags and role profiles.
- **Task routes** bind exact source paths or symbols to required node IDs.
- **Resolution manifests** fingerprint the task, graph, routes, selections, and
  role used to create a loadout.
- **Explicit updates** apply agent-memory or phase-completion feedback only to
  project-local state.
- **Failure memory** is an optional sidecar whose canonical registry stays in the
  project repository.

## Deterministic and LLM-assisted boundaries

Graph compilation, query, route resolution, manifest creation, and ordinary
updates are algorithmic. They do not need a model or network service.

LLMs may appear in separate workflows such as node generation, learning-packet
expansion, or task execution. Those paths consume or produce AKMS artifacts;
they do not redefine graph semantics.

## Not an orchestration requirement

The repository's optional pipeline runner can build graphs, prepare loadouts,
dispatch roles, checkpoint, and update state. It is one consumer of the core.
Projects may instead call the CLI from Codex, Claude Code, Pi, Hermes, CI, a
custom service, or no agent framework at all.
