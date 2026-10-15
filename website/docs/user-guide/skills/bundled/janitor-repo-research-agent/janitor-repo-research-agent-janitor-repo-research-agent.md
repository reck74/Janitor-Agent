---
title: "Janitor Repo Research Agent — GitHub repository research agent for Janitor"
sidebar_label: "Janitor Repo Research Agent"
description: "GitHub repository research agent for Janitor"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Janitor Repo Research Agent

GitHub repository research agent for Janitor.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/janitor-repo-research-agent` |
| Version | `1.0.0` |
| Author | Janitor Agent |
| License | MIT |
| Platforms | linux, macos |
| Tags | `research`, `github`, `analysis`, `documentation` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# janitor-repo-research-agent

Specialized Janitor subagent for comprehensive GitHub repository analysis.
Investigates code quality, architecture, security, and community metrics.
Generates markdown documentation and a visual HTML report.

## Usage

Use this agent when you need to:
- Evaluate a GitHub repository for adoption
- Analyze code quality and architecture of a project
- Research open-source alternatives
- Prepare due-diligence reports on libraries/tools

## Input

Provide a GitHub repository URL or `owner/repo` format.

Example: `investigar repo: https://github.com/NousResearch/hermes-agent`

## Output

The agent creates:
- `~/.janitor/docs/{project-name}/` directory
- Multiple `.md` files organized by category
- `reporte.html` — visual report
