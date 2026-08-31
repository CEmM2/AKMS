# Extraction query sets

Query DeepWiki for the shape of the node body you have to fill, not for general
prose. Each set below maps to one section the AKMS validator expects.

Substitute `{TOPIC}` with the concrete subject (e.g. "the J2 return-mapping
update"), and `{REPO}` where a query needs to name the repository.

## `## Summary` — required

The validator **errors** without it, and it is the only text routing-mode loadouts
display, so for most retrievals it is the only part of the node an agent reads.
Aim for 40–80 words.

```
### [ask_question] Summary: {TOPIC}
In three to five sentences, what is {TOPIC} and when does it apply? State what it
computes or decides, and what it is for. Do not describe the file layout or the
API surface — describe the knowledge.
```

## `## 1. Core Concept`

```
### [ask_question] Core concept: {TOPIC}
Explain {TOPIC} well enough that someone could reimplement it from scratch without
reading this repository. Define every symbol and term you use. State the inputs,
the outputs, and the invariant that must hold throughout.
```

## `## 2. Mathematical Formulation`

Skip for non-mathematical topics rather than padding it.

```
### [ask_question] Formulation: {TOPIC}
Give the governing equations for {TOPIC} as implemented here, not as they appear in
the general literature. Define each symbol. Where the implementation deviates from
the textbook form, state the deviation and the reason given in the code or docs.
```

## `## 3. Procedure`

```
### [ask_question] Procedure: {TOPIC}
List the steps of {TOPIC} in execution order, as actually implemented. For each
step, name what it reads and what it writes. Flag any step whose order matters and
say what breaks if it is reordered.
```

## `## 4. Known Pitfalls` — the highest-value set

This is what an agent cannot derive from first principles, and it is the reason to
do this at all. Ask several ways; pitfalls hide in different places.

```
### [ask_question] Pitfalls: {TOPIC}
What goes wrong when {TOPIC} is implemented naively? Name the specific failure
mode, the symptom a developer would observe, and the correct handling.

### [ask_question] Guards and assertions: {TOPIC}
What assertions, clamps, tolerances, or guard clauses does {REPO} apply around
{TOPIC}? For each, what does it protect against? A guard is a recorded bug.

### [ask_question] Edge cases: {TOPIC}
Which inputs or states does {TOPIC} treat as special cases in {REPO}? Why is each
one special?

### [ask_question] Comments and warnings: {TOPIC}
Quote any comments in the {TOPIC} implementation that warn a reader, explain a
non-obvious choice, or reference an issue. Give the file for each.
```

The last one is disproportionately productive: a `# do not reorder these` comment
is a pitfall someone already paid for.

## Edges

Nodes need at least one structural edge — an edgeless node is unreachable from any
related node, and the validator warns about it.

```
### [ask_question] Dependencies: {TOPIC}
What must be computed or established before {TOPIC} can run, and what consumes its
output? Name the concepts, not the function names.
```

Map the answer onto edge types: prerequisites → `requires`, consumers →
`feeds-into`, specialisations → `refines`, traps → `pitfall`, concrete
realisations → `implements`.

## Structure discovery

Run this first; its answer is the input to your node plan.

```
### [read_wiki_structure] Topic map
```

Then, per candidate node, pull the page before asking questions about it:

```
### [read_wiki_contents] {TOPIC} page
```

## Verification pass

Before writing a node, ask DeepWiki to contradict itself. An answer that survives
this is worth writing down; one that does not is a node you should skip.

```
### [ask_question] Contradiction check: {TOPIC}
Is anything in {REPO} inconsistent with the claim that {CLAIM}? Cite the file and
line if so. If the repository does not actually establish this claim, say so
plainly.
```

If the check comes back vague or hedged, treat the claim as unsupported. Do not
promote a hedge into a confident node body — it will be retrieved and trusted.
