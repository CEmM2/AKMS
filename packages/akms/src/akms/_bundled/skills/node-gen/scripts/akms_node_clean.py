#!/usr/bin/env python3
"""akms_node_clean.py — Clean, auto-fix, and validate AKMS nodes from Gemini Gem.

Two-stage pipeline:
  Stage 1 (clean):  Strip Gemini artifacts (span tags, citation markers).
  Stage 2 (fix):    Auto-fix structural formatting ($$, frontmatter, headings).
  Validation:       Report remaining issues that need manual attention.

Usage:
    python akms_node_clean.py node.md              # Clean + fix in-place
    python akms_node_clean.py node.md -o out.md     # Clean + fix to new file
    python akms_node_clean.py nodes/                # Batch process directory
    python akms_node_clean.py node.md --validate-only
    python akms_node_clean.py node.md --clean-only  # Skip auto-fix
    python akms_node_clean.py node.md -v
"""

import argparse
import re
import sys
from pathlib import Path

# ── Stage 1: Cleaning patterns ───────────────────────────────────────

RE_SPAN_TAG = re.compile(r'\[span_\d+\]\((start|end)_span\)')
RE_CITATION_BRACKET = re.compile(r'\[\d+(?:,\s*\d+)*\](?!\()')
RE_MULTI_BLANK = re.compile(r'\n{4,}')


def clean_artifacts(text: str) -> tuple[str, dict]:
    """Stage 1: Strip Gemini grounding artifacts."""
    stats = {
        'span_tags': len(RE_SPAN_TAG.findall(text)),
        'citation_brackets': len(RE_CITATION_BRACKET.findall(text)),
    }

    text = RE_SPAN_TAG.sub('', text)
    text = RE_CITATION_BRACKET.sub('', text)
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r' ([.,;:!?])', r'\1', text)
    text = RE_MULTI_BLANK.sub('\n\n\n', text)
    text = '\n'.join(line.rstrip() for line in text.split('\n'))

    return text, stats


# ── Stage 2: Auto-fix ────────────────────────────────────────────────

def fix_structure(text: str) -> tuple[str, list[str]]:
    """Stage 2: Auto-fix structural formatting issues.
    Returns (fixed_text, list_of_fixes_applied).
    """
    fixes = []

    parts = text.split('---', 2)
    if len(parts) < 3:
        return text, ['SKIP: Could not parse frontmatter']

    fm_raw = parts[1]
    body = parts[2]

    # ── Frontmatter fixes ──

    # Add content_ref: null if missing
    if 'content_ref:' not in fm_raw:
        if 'akms_schema:' in fm_raw:
            fm_raw = fm_raw.replace(
                'akms_schema:',
                'content_ref: null\n\nakms_schema:'
            )
        else:
            fm_raw = fm_raw.rstrip() + '\ncontent_ref: null\n'
        fixes.append('Added content_ref: null')

    # ── Body fixes ──

    # Add # [Title] heading if missing
    body_stripped = body.lstrip('\n')
    if not body_stripped.startswith('# '):
        title_match = re.search(r'title:\s*"([^"]+)"', fm_raw)
        if title_match:
            title = title_match.group(1)
            body = f'\n# {title}\n{body}'
            fixes.append(f'Added # {title} heading')

    # Wrap \begin{algorithmic} in $$ if not already wrapped
    lines = body.split('\n')
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if line == r'\begin{algorithmic}':
            prev_content = ''
            for j in range(len(new_lines) - 1, -1, -1):
                if new_lines[j].strip():
                    prev_content = new_lines[j].strip()
                    break
            if prev_content != '$$':
                new_lines.append('$$')
                fixes.append('Added $$ before \\begin{algorithmic}')
            new_lines.append(lines[i])
        elif line == r'\end{algorithmic}':
            new_lines.append(lines[i])
            next_content = ''
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    next_content = lines[j].strip()
                    break
            if next_content != '$$':
                new_lines.append('$$')
                fixes.append('Added $$ after \\end{algorithmic}')
        else:
            new_lines.append(lines[i])
        i += 1

    body = '\n'.join(new_lines)

    # Fix section numbering gaps
    section_pattern = re.compile(r'^## (\d+)\. ', re.MULTILINE)
    section_numbers = [int(m.group(1)) for m in section_pattern.finditer(body)]
    if section_numbers:
        expected = list(range(1, len(section_numbers) + 1))
        if section_numbers != expected:
            for old_num, new_num in zip(section_numbers, expected):
                if old_num != new_num:
                    body = body.replace(f'## {old_num}. ', f'## {new_num}. ', 1)
            fixes.append(f'Renumbered sections: {section_numbers} → {expected}')

    # Strip \Comment{} commands (prohibited)
    comment_pattern = re.compile(r'\s*\\Comment\{[^}]*\}')
    if comment_pattern.search(body):
        body = comment_pattern.sub('', body)
        fixes.append('Stripped \\Comment{} commands')

    text = f'---{fm_raw}---{body}'
    return text, fixes


# ── Validation ────────────────────────────────────────────────────────

def validate_node(text: str) -> list[dict]:
    """Validate an AKMS node. Returns list of issues."""
    issues = []

    def error(msg):
        issues.append({'level': 'ERROR', 'message': msg})

    def warn(msg):
        issues.append({'level': 'WARN', 'message': msg})

    if not text.strip().startswith('---'):
        error('No YAML frontmatter (---)')
        return issues

    parts = text.split('---', 2)
    if len(parts) < 3:
        error('Malformed frontmatter — missing closing ---')
        return issues

    fm = parts[1]
    body = parts[2]

    # ── Frontmatter ──
    for field in ['id:', 'title:', 'domain:', 'status:', 'confidence:',
                  'source:', 'context_size:', 'reading_priority:', 'akms_schema:']:
        if field not in fm:
            error(f'Missing frontmatter field: {field}')

    if 'akms_schema:' in fm and 'akms_schema: v2' not in fm:
        error('akms_schema must be v2')
    if 'status:' in fm and 'status: tentative' not in fm:
        warn('status should be "tentative"')
    if 'source:' in fm and 'source: hybrid' not in fm:
        warn('source should be "hybrid"')
    if 'content_ref:' not in fm:
        warn('Missing content_ref: null')

    # ── Structure ──
    body_stripped = body.lstrip('\n')
    if not body_stripped.startswith('# '):
        error('Missing # [Title] heading')

    for section in ['## Summary', '## 1. Core Concept',
                    '## 2. Mathematical Formulation',
                    '## 3. Algorithmic Implementation',
                    '## 4. Known Pitfalls']:
        if section not in body:
            error(f'Missing section: {section}')

    if '$$' not in body and '## 2. Mathematical Formulation' in body:
        error('Mathematical Formulation has no $$ blocks')

    # ── Self-containedness ──

    # Equation-number references
    eq_refs = re.findall(
        r'(?:Eq\.|Equation|equation)\s*[\(\[]?\d+[\.\d]*[\)\]]?', body
    )
    for ref in eq_refs:
        error(f'Equation-number reference: "{ref}" — write the equation out')

    # Source section references (but allow our own §1–§6)
    own_sections = {'§1', '§2', '§3', '§4', '§5', '§6'}
    section_refs = re.findall(r'(?:§|Sect\.|Section)\s*\d+[\.\d]*', body)
    for ref in section_refs:
        if ref.replace(' ', '') not in own_sections:
            warn(f'Source section reference: "{ref}" — may be incomplete extraction')

    # Vague algorithm steps
    if '## 3. Algorithmic Implementation' in body:
        algo_match = re.search(
            r'## 3\. Algorithmic Implementation(.*?)(?=## \d|$)', body, re.DOTALL
        )
        if algo_match:
            algo = algo_match.group(1)

            vague = re.findall(
                r'\\State\s+.*?(?:evaluate|apply|compute from|see)\s+'
                r'(?:Eq|equation|mapping|formula|expression|§)',
                algo, re.IGNORECASE
            )
            for v in vague:
                error(f'Vague algorithm step: "{v[:80]}" — write the math')

            # $$ wrapping check
            if r'\begin{algorithmic}' in algo:
                for m in re.finditer(r'\\begin\{algorithmic\}', algo):
                    pre = algo[:m.start()].rstrip()
                    if not pre.endswith('$$'):
                        error('\\begin{algorithmic} not in $$ delimiters')
                        break
                for m in re.finditer(r'\\end\{algorithmic\}', algo):
                    post = algo[m.end():].lstrip()
                    if not post.startswith('$$'):
                        error('\\end{algorithmic} not closed with $$')
                        break

            # Prohibited commands
            for cmd in [r'\Procedure', r'\Function', r'\Call',
                        r'\Require', r'\Ensure', r'\Comment']:
                if cmd in algo:
                    error(f'Prohibited command: {cmd}')

            # Code-style variable names
            code_vars = re.findall(
                r'(?<!\{)(?<!\\)\b(epsilon|sigma|delta|gamma)\b(?!\})', algo
            )
            if code_vars:
                warn(f'Code-style variable names: {", ".join(set(code_vars))}')

    # ── Section numbering ──
    nums = [int(m.group(1))
            for m in re.finditer(r'^## (\d+)\. ', body, re.MULTILINE)]
    if nums and nums != list(range(1, len(nums) + 1)):
        warn(f'Non-sequential section numbers: {nums}')

    # ── Residual artifacts ──
    if RE_SPAN_TAG.search(body):
        error('Residual span tags')

    if '[INSUFFICIENT SOURCE' in body:
        warn('[INSUFFICIENT SOURCE] markers present')

    return issues


# ── CLI ───────────────────────────────────────────────────────────────

def process_file(filepath: Path, output: Path | None,
                 validate_only: bool, clean_only: bool, verbose: bool) -> bool:
    text = filepath.read_text(encoding='utf-8')
    original = text

    if not validate_only:
        text, cstats = clean_artifacts(text)
        if verbose and (cstats['span_tags'] or cstats['citation_brackets']):
            print(f"  [clean] {cstats['span_tags']} span tags, "
                  f"{cstats['citation_brackets']} citation brackets")

    if not validate_only and not clean_only:
        text, fix_list = fix_structure(text)
        if verbose and fix_list:
            for f in fix_list:
                print(f"  [fix]   {f}")

    issues = validate_node(text)
    errors = [i for i in issues if i['level'] == 'ERROR']

    if issues:
        print(f"\n{'─' * 60}")
        print(f"  {filepath.name}")
        print(f"{'─' * 60}")
        for issue in issues:
            marker = '✗' if issue['level'] == 'ERROR' else '⚠'
            print(f"  {marker} [{issue['level']}] {issue['message']}")
        print()
    elif verbose:
        print(f"  ✓ {filepath.name} — all checks pass")

    if not validate_only and text != original:
        target = output or filepath
        target.write_text(text, encoding='utf-8')
        if verbose:
            print(f"  → Written to {target}")

    return len(errors) == 0


def main():
    parser = argparse.ArgumentParser(
        description='Clean, auto-fix, and validate AKMS nodes from Gemini Gem'
    )
    parser.add_argument('input', type=Path)
    parser.add_argument('-o', '--output', type=Path, default=None)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--clean-only', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    if args.input.is_dir():
        files = sorted(args.input.glob('*.md'))
        if not files:
            print(f"No .md files in {args.input}")
            sys.exit(1)
        if args.output:
            print("Error: -o not supported in directory mode")
            sys.exit(1)

        print(f"Processing {len(files)} files\n")
        ok = all(
            process_file(f, None, args.validate_only, args.clean_only, args.verbose)
            for f in files
        )
        print(f"\n{'✓ All pass' if ok else '✗ Errors found'}")
        sys.exit(0 if ok else 1)
    else:
        if not args.input.exists():
            print(f"Not found: {args.input}")
            sys.exit(1)
        ok = process_file(args.input, args.output, args.validate_only,
                          args.clean_only, args.verbose)
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
