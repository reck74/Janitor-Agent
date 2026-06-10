import { detectAcpModels, DEFAULT_MODEL_OPTION } from './shared.js';
import type { RuntimeAgentDef } from '../types.js';

// Janitor — fork de Hermes Agent con identidad "The Janitor".
// Wrapper ACP-compatible: misma interfaz que hermesAgentDef,
// binario diferente, branding diferenciado.
//
// Binario: `janitor` (ya en PATH del host tras install de Janitor).
// Protocolo: ACP JSON-RPC (igual que Hermes).
// Icono: agent-icons/janitor.svg (monoline, color #1c1b1a).

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
  // Fallback models cuando Janitor no está en PATH.
  // Cubre los providers configurados en ~/.janitor/config.yaml:
  // MiniMax (M2.7/M2), xAI Grok, OpenAI Codex.
  fallbackModels: [
    DEFAULT_MODEL_OPTION,
    // MiniMax
    { id: 'MiniMax-M2.7', label: 'MiniMax-M2.7 (default)' },
    { id: 'MiniMax-M2', label: 'MiniMax-M2' },
    // xAI Grok (disponible via hermes auth add xai-oauth)
    { id: 'grok-4.3', label: 'grok-4.3 (xAI · default)' },
    { id: 'grok-4.20-reasoning', label: 'grok-4.20-reasoning (xAI · deep)' },
    { id: 'grok-4.20-0309-non-reasoning', label: 'grok-4.20-non-reasoning (xAI · fast)' },
    { id: 'grok-4.20-multi-agent-0309', label: 'grok-4.20-multi-agent (xAI · orchestration)' },
    // OpenAI Codex (disponible via hermes auth add openai)
    { id: 'openai-codex:gpt-5.5', label: 'gpt-5.5 (openai-codex:gpt-5.5)' },
    { id: 'openai-codex:gpt-5.4', label: 'gpt-5.4 (openai-codex:gpt-5.4)' },
    { id: 'openai-codex:gpt-5.4-mini', label: 'gpt-5.4-mini (openai-codex:gpt-5.4-mini)' },
  ],
  buildArgs: () => ['acp', '--accept-hooks'],
  streamFormat: 'acp-json-rpc',
  mcpDiscovery: 'mature-acp',
  externalMcpInjection: 'acp-merge',
  installUrl: 'https://github.com/nickarora01/janitor',
  docsUrl: 'https://janitor.sh/docs',
} satisfies RuntimeAgentDef;