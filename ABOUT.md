# About Project Dashboard

A lightweight dashboard that surfaces what your projects need next — by checking actual git state in `~/Projectos/`. No review pipeline, no agent handoffs, no approval gates.

## What it does

Each project card shows one recommendation based on real state:
- **Uncommitted changes** — finish and push before context-switching
- **Unpushed commits** — branch has work not on remote
- **Stale repos** — no commits in 14+ days
- **In-flight projects** — code exists, track ongoing work
- **New projects** — no local directory yet

Recommendations are local-only: `git status`, `git log`, and directory checks. No API calls, no AI.

## Design Principles

### Honest state
The dashboard reads your actual directories. It doesn't guess, doesn't call external services, and doesn't pretend a worker is doing something.

### Explainable
Every recommendation has a clear reason — "Heimdall has uncommitted changes" is something you can verify with `cd ~/Projectos/Heimdall && git status`.

### Local-first
SQLite, git subprocess, and filesystem checks. Runs on your machine, serves over an SSH tunnel to your VPS.

## What It Covers
- Project overview with git-aware recommendations
- Project detail pages
- Basic project CRUD (create, edit, archive)
- Settings

## What It Does Not Cover
- It is not a proposal/review/approval system — that was removed in v2
- It does not call LLM APIs or agent runtimes
- It does not manage workflows, budgets, or agent teams

## Deployment
Hosted at [reidar.tech/proposals](https://reidar.tech/proposals). Can run locally: `HERMES_REQUIRE_AUTH=0 .venv/bin/python -m uvicorn main:app --port 8089`.
