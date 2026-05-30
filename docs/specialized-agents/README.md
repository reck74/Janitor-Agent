# Specialized Agents

Specialized Agents are focused sub-agents designed to handle specific types of tasks with expert-level precision. Instead of using a generic sub-agent for everything, Janitor can route tasks to agents tailored for code review, debugging, refactoring, or writing.

## Architecture Overview

The specialized agents system consists of several key components:

- **Agent Skills (`skills/janitor-*-agent/`)**: Each specialized agent is packaged as a Janitor skill. The directory contains an `agent.yaml` file defining the agent's identity and behavior.
- **Agent Registry (`tools/specialized_agents.py`)**: Discovers and loads agent specifications from the skills directory. It provides a central registry for all available specialized agents.
- **Agent Router (`tools/agent_router.py`)**: An LLM-powered component that analyzes task descriptions to determine if they should be handled by a specialized agent and selects the best match.
- **Delegation Integration (`tools/delegate_tool.py`)**: The `delegate_task` tool is enhanced to support an `agent_type` parameter. When an agent type is specified, the sub-agent is initialized with the persona, skills, and toolsets defined in the agent's specification.
- **Core Integration (`run_agent.py`)**: The main agent loop intercepts delegation requests and consults the router to automatically apply specialized agents when appropriate.

## Creating a New Specialized Agent

To create a new specialized agent, follow these steps:

1. **Create a Skill Directory**: Create a new directory under `skills/` following the naming convention `janitor-<name>-agent/`.
   ```bash
   mkdir -p skills/janitor-security-agent/
   ```

2. **Define the Agent Spec**: Create an `agent.yaml` file in the new directory.
   ```yaml
   name: security-expert
   description: Specialized in security auditing and vulnerability research.
   systemPrompt: |
     You are a Senior Security Researcher. Your goal is to identify security
     vulnerabilities in code and infrastructure.
   toolsets:
     - terminal
     - file
     - search
   ```

3. **(Optional) Add Supporting Files**: You can include additional files like `SKILL.md` to document the agent or scripts it might need.

## Agent Specification Format (`agent.yaml`)

The `agent.yaml` file supports the following fields:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier for the agent. |
| `description` | Yes | Brief summary of the agent's purpose. |
| `systemPrompt` | Yes | Core instructions defining the agent's persona and goals. |
| `skills` | No | List of Janitor skills to load for the agent. |
| `model` | No | Specific LLM model to use for this agent. |
| `toolsets` | No | List of toolsets to enable for the agent. |
| `reasoningEffort` | No | Reasoning level for supported models (`low`, `medium`, `high`). |

For a detailed schema, see [AGENT_SPEC.md](./AGENT_SPEC.md).

## How Routing Works

Routing is automatic and transparent. When the main agent decides to delegate a task:

1. **Classification**: The `Agent Router` uses an LLM to classify the task description.
2. **Suitability Check**: It determines if the task type matches any available specialized agents.
3. **Selection**: If a match is found (e.g., a "code review" task), the router returns the corresponding agent type.
4. **Initialization**: The sub-agent is created using the specialized agent's configuration, overriding default delegation settings.

## Configuration Options

You can control the specialized agents system via `config.yaml`:

```yaml
specialized_agents:
  enabled: true  # Set to false to disable automatic routing
```

## Examples

### Code Review Agent
Located at `skills/janitor-code-review-agent/`.

```yaml
name: code-review
description: Specialized in code review, static analysis, best practices
systemPrompt: |
  You are the Janitor code review agent.
  Your job is to review code changes for correctness, security, maintainability,
  performance, and test coverage.
toolsets:
  - file
  - terminal
  - code_execution
```

### Custom Security Agent
```yaml
name: security-audit
description: Expert in identifying security flaws and OWASP vulnerabilities.
systemPrompt: |
  You are a security auditor. Analyze the provided context for security risks.
  Focus on input validation, authentication, and data protection.
skills:
  - janitor-vault
model: gpt-4-turbo
```
