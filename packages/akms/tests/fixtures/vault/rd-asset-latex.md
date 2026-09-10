---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/repo-documentor/references/TEMPLATES.tex
context_size: medium
domain: project-meta
edges:
- note: LaTeX templates implement documentation conventions
  to: rd-ref-conventions
  type: implements
  weight: 0.6
- note: LaTeX templates include contract block formatting
  to: rd-ref-contracts
  type: requires
  weight: 0.5
id: rd-asset-latex
reading_priority: summary
source: human
status: established
subdomain: documentation
tags:
- LaTeX
- templates
- article
- book
- macros
- tcolorbox
- algorithm2e
title: LaTeX Templates (Article & Book)
---

# LaTeX Templates (Article & Book)

## Summary

LaTeX output templates: article class for compact docs, book class for chapter-organized larger docs. Custom macros (\vect{}, \mat{}), tcolorbox admonitions, algorithm2e pseudocode environments. Sections file for function/kernel documentation with contract tables, math equations, and safeguard callouts. Includes both main_article.tex and main_book.tex structures.

**Parent skill:** `skill-repo-documentor`
**Content:** `content/repo-documentor/references/TEMPLATES.tex`
