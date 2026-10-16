# Specialized Agent Specification

This document defines the schema for specialized agent configuration files (`agent.yaml`). Specialized agents are focused sub-agents designed for specific tasks like code review, security auditing, or documentation.

## Schema Definition

The configuration file uses YAML format.

### Fields

#### `name` (Required)
- **Type**: String
- **Description**: The unique identifier for the specialized agent.
- **Example**:
  ```yaml
  name: code-reviewer
  ```

#### `description` (Required)
- **Type**: String
- **Description**: A brief summary of the agent's purpose and capabilities.
- **Example**:
  ```yaml
  description: Expert agent for reviewing code changes and identifying potential bugs.
  ```

#### `systemPrompt` (Required)
- **Type**: String
- **Description**: The core system instructions that define the agent's persona, goals, and constraints.
- **Example**:
  ```yaml
  systemPrompt: |
    You are an expert senior software engineer. Your goal is to review code changes
    for quality, security, and performance. Be concise and actionable.
  ```

#### `skills` (Optional)
- **Type**: List of Strings
- **Description**: A list of Janitor skills to load when the agent is initialized.
- **Example**:
  ```yaml
  skills:
    - git-master
    - review-work
  ```

#### `model` (Optional)
- **Type**: String
- **Description**: The specific LLM model to use for this agent. If not provided, the default model from the main configuration will be used.
- **Example**:
  ```yaml
  model: claude-3-5-sonnet-20240620
  ```

#### `toolsets` (Optional)
- **Type**: List of Strings
- **Description**: A list of toolsets to enable for the agent.
- **Example**:
  ```yaml
  toolsets:
    - terminal
    - file
    - search
  ```

#### `reasoningEffort` (Optional)
- **Type**: String
- **Description**: The level of reasoning effort for models that support it (e.g., OpenAI o1).
- **Values**: `low`, `medium`, `high`
- **Example**:
  ```yaml
  reasoningEffort: high
  ```

## Validation Rules

1. `name`, `description`, and `systemPrompt` are mandatory.
2. `skills` and `toolsets` should be lists of strings.
3. `model` must be a valid model identifier supported by the configured provider.
4. `reasoningEffort` is only applicable to specific models.

## Example: Code Review Agent

Below is a complete example of a specialized agent configuration for code reviews.

```yaml
name: code-reviewer
description: Specialized agent for deep code analysis and PR reviews.
systemPrompt: |
  You are a Senior Security Engineer and Code Architect.
  Your task is to analyze code changes for:
  1. Security vulnerabilities (OWASP Top 10).
  2. Performance bottlenecks.
  3. Maintainability and adherence to best practices.
  4. Logic errors.
  
  Provide feedback in a structured format, prioritizing critical issues.
skills:
  - git-master
  - review-work
  - ai-slop-remover
model: gpt-4o
toolsets:
  - terminal
  - file
  - search
reasoningEffort: medium
```
