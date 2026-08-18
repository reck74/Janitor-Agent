---
name: janitor-repo-research-agent
description: GitHub repository research agent for Janitor.
version: 1.0.0
author: Janitor Agent
license: MIT
platforms: [linux, macos]

metadata:
  hermes:
    tags: [research, github, analysis, documentation]
    category: devops
---

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
