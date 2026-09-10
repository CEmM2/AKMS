# Shared Conventions for Skills Repository

This document defines common conventions, patterns, and best practices used across all skills in this repository.

---

## File Structure

### Required Files
Every skill MUST have:
```
skills/<skill-name>/
├── SKILL.md              # Main skill definition with YAML frontmatter
└── references/           # Reference documentation
    └── *.md
```

### Recommended Structure
```
skills/<skill-name>/
├── SKILL.md
├── references/           # Detailed reference documentation
│   ├── <topic-1>.md
│   ├── <topic-2>.md
│   └── ...
├── domains/              # Domain-specific guides (optional)
│   └── *.md
├── examples/             # Complete, runnable examples (recommended)
│   ├── good-*.py
│   ├── bad-*.md
│   └── templates/
└── assets/               # Supporting files (optional)
    ├── templates/
    ├── images/
    └── data/
```

---

## Naming Conventions

### Files and Directories
- **Lowercase with hyphens:** `my-reference-file.md` (NOT `MyReferenceFile.md` or `my_reference_file.md`)
- **Descriptive names:** `review-checklist.md` (NOT `checklist.md` or `rc.md`)
- **Plural for collections:** `references/`, `examples/`, `domains/`
- **Singular for specific topics:** `references/performance.md` (NOT `references/performances.md`)

### SKILL.md Naming
- Frontmatter `name:` field should match directory name
- Use lowercase with hyphens: `taichi-gpu-sim` (NOT `TaichiGPUSim`)

### Example Files
- **Good examples:** `good-*.py` or `*-example.py`
- **Bad examples (with reviews):** `bad-*-review.md`
- **Templates:** `*-template.md` or `*-template.py`

---

## Documentation Standards

### YAML Frontmatter (SKILL.md)
All SKILL.md files MUST start with YAML frontmatter:
```yaml
---
name: skill-name
description: One-sentence description of what this skill does (max 200 chars)
---
```

**Required fields:**
- `name`: Lowercase with hyphens, matches directory name
- `description`: Concise, actionable description

### Heading Hierarchy
```markdown
# H1: File Title (only one per file, typically at top)

## H2: Major Sections (numbered if sequential)

### H3: Subsections

#### H4: Rare, only for deep nesting
```

**Rules:**
- Don't skip levels (e.g., H1 → H3)
- Use numbered headings for sequential steps (e.g., "## 1) Data Model")
- Use descriptive headings, not generic (e.g., "## Performance Considerations" NOT "## Details")

### Code Blocks
Always specify language:
```
```python
# Python code here
```

```yaml
# YAML config
```

```bash
# Shell commands
```
```

**Preferred language tags:**
- `python` (NOT `py`) - explicit is better
- `bash` for shell commands
- `yaml` (NOT `yml`)
- `json`, `markdown`, `tex`, etc.

### Lists
- **Numbered lists:** Sequential steps, priorities, ordered items
- **Bulleted lists:** Non-sequential items, alternatives, features
- **Checkboxes:** Tasks, requirements, checklists

Example:
```markdown
1. First step
2. Second step
3. Third step

- Feature A
- Feature B
- Feature C

- [ ] Incomplete task
- [x] Completed task
```

### Emphasis
- **Bold (`**text**`):** Important terms, warnings, emphasis
- *Italic (`*text*`):** Terminology, first use of concepts
- `Code (`\`text\``):** Identifiers, file names, commands, inline code

### Links and References
**Internal links (relative):**
```markdown
See `references/performance.md` for details.
See: `domains/fem.md`
```

**Cross-references:**
```markdown
(See `references/conventions.md` for naming standards.)
Reference: `taichi-gpu-sim/references/kernel-patterns.md`
```

**External links:**
```markdown
[Taichi Documentation](https://docs.taichi-lang.org/)
```

---

## Code Standards

### Python Examples
All Python examples should:
1. **Be syntactically valid:** Must compile without errors
2. **Include imports:** Show all required imports
3. **Use explicit initialization:** `ti.init(arch=ti.gpu)` not implicit
4. **Have docstrings:** Explain what, inputs, outputs
5. **Include validation:** Sanity checks, assertions, or test harness

**Example:**
```python
"""
Module-level docstring explaining the example.
"""

import taichi as ti
import numpy as np

# Explicit initialization
ti.init(arch=ti.gpu)

@ti.kernel
def example_kernel(n: ti.i32):
    """
    Brief description of what this kernel does.

    Args:
        n: Description of parameter

    Note:
        Any important details or constraints
    """
    for i in range(n):
        # ... implementation


if __name__ == "__main__":
    # Validation or example usage
    example_kernel(100)
```

### Code Block Annotations
Use comments to explain non-obvious code:
```python
# CFL stability constraint: r = α*dt/dx² ≤ 0.25
r = alpha * dt / (dx * dx)
assert r <= 0.25, f"CFL violation: r={r}"
```

Mark issues in bad examples:
```python
# ❌ WRONG: Race condition
u[i, j] = u[i+1, j] + u[i-1, j]

# ✅ CORRECT: Use double-buffering
u_new[i, j] = u_old[i+1, j] + u_old[i-1, j]
```

---

## Cross-Skill Integration

### Referencing Other Skills
When one skill references another:
```markdown
See: `../taichi-gpu-sim/references/performance.md`

Or use relative path from repo root:
Reference: `skills/taichi-gpu-sim/SKILL.md`
```

### Shared Resources
Place shared resources in `skills/shared/`:
- `CONVENTIONS.md` - This file
- `GLOSSARY.md` - Common terminology
- `INTEGRATION.md` - How skills work together

---

## Testing Standards

### Test File Organization
```
tests/
├── test_references.py      # Validate file references
├── test_code_examples.py   # Validate code syntax
├── test_consistency.py     # Check naming, formatting
└── README.md               # Test documentation
```

### Test Naming
- File: `test_<category>.py`
- Function: `test_<specific_check>()`

Example:
```python
def test_domain_files_exist():
    """Verify all domain files referenced in SKILL.md exist."""
    # ... test implementation
```

---

## Validation Checklist

Before committing changes to a skill:

- [ ] **SKILL.md has valid frontmatter** (name, description)
- [ ] **All referenced files exist** (run `pytest tests/test_references.py`)
- [ ] **Code examples compile** (run `pytest tests/test_code_examples.py`)
- [ ] **Naming follows conventions** (lowercase-with-hyphens)
- [ ] **Headings use proper hierarchy** (no skipped levels)
- [ ] **Code blocks specify language** (```python not ```)
- [ ] **Links are valid** (no broken internal links)
- [ ] **Examples are complete** (imports, init, validation)

---

## Version Control

### Commit Messages
Follow conventional commits:
```
<type>: <description>

[optional body]

[optional footer]
```

**Types:**
- `feat:` New feature or skill
- `fix:` Bug fix or correction
- `docs:` Documentation only
- `test:` Test additions or fixes
- `refactor:` Code refactoring
- `style:` Formatting changes

**Examples:**
```
feat: Add MPM domain guide to taichi-gpu-sim

- Covers P2G/G2P transfers
- B-spline interpolation
- APIC method
- Complete 2D example

fix: Rename gotcha.md to gotchas.md for consistency

docs: Add review examples to taichi-sim-reviewer

test: Add automated validation for file references
```

### Branch Naming
- `feature/<description>` - New features
- `fix/<issue-number>-<description>` - Bug fixes
- `docs/<description>` - Documentation updates

---

## Error Severity Levels

Use consistent severity markers in reviews and documentation:

- 🔴 **CRITICAL:** Blocks merge, causes incorrect results, major security issue
- 🟡 **MAJOR:** Should fix, significant performance impact, poor practice
- 🟢 **MINOR:** Nice to have, style issue, minor optimization
- ℹ️ **INFO:** Question, suggestion, FYI

---

## Deprecation Policy

When deprecating features or changing conventions:

1. **Mark as deprecated:** Add warning in documentation
2. **Provide migration path:** Show how to update
3. **Set sunset date:** Give users time to migrate (minimum 2 releases)
4. **Remove:** Only after sunset date

Example:
```markdown
> **DEPRECATED:** This convention is deprecated as of 2026-01-15.
> Use `lowercase-with-hyphens` instead of `snake_case`.
> This will be enforced starting 2026-03-01.
```

---

## Style Guide Quick Reference

| Element | Convention | Example |
|---------|-----------|---------|
| File names | lowercase-with-hyphens | `kernel-patterns.md` |
| Directory names | lowercase, plural for collections | `references/`, `examples/` |
| Skill names | lowercase-with-hyphens | `taichi-gpu-sim` |
| Code blocks | Always specify language | ` ```python ` |
| Headings | Descriptive, proper hierarchy | `## Performance Considerations` |
| Links (internal) | Backticks for files | `` `references/file.md` `` |
| Links (external) | Markdown format | `[Text](https://url)` |
| Lists | - for bullets, 1. for ordered | See Lists section |
| Emphasis | **bold** for important, *italic* for terms | `**CRITICAL**`, `*convergence*` |

---

## Contributing

When contributing to this repository:

1. **Read this document first**
2. **Run tests before committing:** `pytest tests/ -v`
3. **Follow the conventions** outlined here
4. **Ask questions** if anything is unclear
5. **Update this document** if you establish new conventions

---

## References

- [Open Agents Skills Standard](https://agentskills.io/)
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Markdown Guide](https://www.markdownguide.org/)

---

**Last Updated:** 2026-01-17
**Maintained by:** Skills Repository Contributors
