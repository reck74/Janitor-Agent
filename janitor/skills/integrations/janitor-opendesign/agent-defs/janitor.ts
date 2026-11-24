import { detectAcpModels, DEFAULT_MODEL_OPTION } from './shared.js';
import type { RuntimeAgentDef } from '../types.js';

// Janitor as an Open Design coding agent. Copied into
// apps/daemon/src/runtimes/defs/ by the janitor-opendesign skill
// (opendesign_setup.py register). Same ACP JSON-RPC interface as
// hermesAgentDef; only the binary and the branding differ.
// Icon: apps/web/public/agent-icons/janitor.png (rendered as <img>).
// The real model list comes from `janitor acp`; the fallback only covers
// Janitor's recommended provider, used when the probe times out.

export const janitorAgentDef = {
  id: 'janitor',
  name: 'The Janitor',
  bin: 'janitor',
  versionArgs: ['--version'],
  fetchModels: async (resolvedBin: string, env: NodeJS.ProcessEnv) =>
    detectAcpModels({
      bin: resolvedBin,
      args: ['acp', '--accept-hooks'],
      env,
      timeoutMs: 15_000,
      defaultModelOption: DEFAULT_MODEL_OPTION,
    }),
  fallbackModels: [
    DEFAULT_MODEL_OPTION,
    { id: 'MiniMax-M2.7', label: 'MiniMax-M2.7' },
  ],
  buildArgs: () => ['acp', '--accept-hooks'],
  streamFormat: 'acp-json-rpc',
  mcpDiscovery: 'mature-acp',
  externalMcpInjection: 'acp-merge',
  installUrl: 'https://github.com/reck74/Janitor-Agent',
  docsUrl: 'https://github.com/reck74/Janitor-Agent',
} satisfies RuntimeAgentDef;
