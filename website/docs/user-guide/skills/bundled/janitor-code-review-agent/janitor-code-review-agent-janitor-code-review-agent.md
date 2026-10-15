---
title: "Janitor Code Review Agent — Code review agent for Janitor"
sidebar_label: "Janitor Code Review Agent"
description: "Code review agent for Janitor"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Janitor Code Review Agent

Code review agent for Janitor.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/janitor-code-review-agent` |
| Version | `1.0.0` |
| Author | Janitor Agent |
| License | MIT |
| Platforms | linux, macos |
| Tags | `code-review`, `subagent`, `janitor` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# janitor-code-review-agent

Specialized Janitor subagent for reviewing code changes, static analysis, and review feedback.
It does not implement features; it evaluates diffs, flags risks, and suggests focused improvements.

## Usage

Use this agent when you need a dedicated reviewer for correctness, security, maintainability,
test coverage, and style issues.
