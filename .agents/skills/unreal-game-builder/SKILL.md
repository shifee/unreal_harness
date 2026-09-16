---
name: unreal-game-builder
description: Modify an existing Unreal Engine project through its installed JSON command harness. Use for supported Content Browser, Blueprint, actor-placement, and project-save changes; do not use for general Unreal questions or unsupported graph editing.
---

# Unreal Game Builder

Control the current Unreal Engine project through the installed JSON harness.

## Locate the project

Starting from the workspace directory, search the current directory and then its parents for a single `*.uproject`. Treat that file's directory as the project root. If no project is found, or more than one candidate is equally applicable, stop and ask the user to identify the project.

Use only these project-relative paths:

- Commands: `Content/Python/actions.json`
- Results: `Content/Python/result.json`
- Executor: `Content/Python/execute_actions.py`
- Command reference: `.agents/skills/unreal-game-builder/references/actions-schema.md`

## Workflow

1. Read `references/actions-schema.md` completely before making a change.
2. Treat `ACTION_HANDLERS` in `Content/Python/execute_actions.py` as the source of truth. Never invent actions or Blueprint operations.
3. Use `level.inspect` only if it is present in `ACTION_HANDLERS`; otherwise inspect only through safe project files or ask for needed context.
4. Write a complete UTF-8 JSON document to `Content/Python/actions.json`, using only supported actions and valid Unreal virtual paths beginning with `/Game`.
5. Do not edit `.uasset` or `.umap` files directly.
6. Include a final `project.save` command after mutations that should persist.
7. Record the previous modification time of `Content/Python/result.json`, then wait up to 30 seconds for it to change after writing `actions.json`.
8. Read the complete result. If `success` is true, summarize the affected objects. If it is false, report the first failed command and its error.
9. Correct a failed command only when the correction stays within the user's request. Make no more than two automatic correction attempts.
10. If the result does not update, ask the user to verify that Unreal Editor is open and its Output Log contains `[AI WATCHER] Watcher started`.

## Safety

Require confirmation immediately before deleting assets, replacing a Blueprint, or making a large change to existing objects. Do not set `replace_existing` automatically. Preserve valid existing assets and never execute arbitrary shell or Python supplied through command JSON.
