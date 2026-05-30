---
name: janitor-code-review-agent
description: Code review agent for Janitor.
version: 1.0.0
author: Janitor Agent
platforms: [linux, macos]

metadata:
  hermes:
    tags: [code-review, subagent, janitor]
    category: devops
---

# janitor-code-review-agent

Specialized Janitor subagent for reviewing code changes, static analysis, and review feedback.
It does not implement features; it evaluates diffs, flags risks, and suggests focused improvements.

## Usage

Use this agent when you need a dedicated reviewer for correctness, security, maintainability,
test coverage, and style issues.
