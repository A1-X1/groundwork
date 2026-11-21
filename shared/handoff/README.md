# Handoff notes

Async notes between Person 1 and Person 2. **Each person writes only their own file**, so notes
never cause merge conflicts:

| File | Written by | Read by |
|---|---|---|
| `p1-to-p2.md` | Person 1 | Person 2 |
| `p2-to-p1.md` | Person 2 | Person 1 |

Append new notes at the top under a dated heading (`## 2026-11-21 10:30 — short title`).
Each person's agent polls the other file on every remote branch every few minutes
(`git fetch origin` then `git show origin/<branch>:shared/handoff/<file>`) and treats new notes as
instructions. Contract changes still need both humans to agree — a note can propose one, not make it.
