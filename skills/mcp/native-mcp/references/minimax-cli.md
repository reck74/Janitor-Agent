# MiniMax CLI (mmx-cli)

## Installation

```bash
npm install -g mmx-cli
```

## Authentication

```bash
mmx auth login --api-key YOUR_TOKEN_PLAN_KEY
```

## Useful Commands

| Command | Description |
|---|---|
| `mmx` | Interactive CLI dashboard |
| `mmx quota show` | Show current quota usage |
| `mmx image "prompt"` | Generate image (requires Plus plan) |
| `mmx video generate --prompt "..."` | Generate video |
| `mmx music generate --prompt "..." --out file.mp3` | Generate music |
| `mmx speech synthesize --text "..." --out file.mp3` | Text-to-speech |
| `mmx text chat --message "..."` | Text chat |

Output files go to `minimax-output/` in current directory.

## Quota Status (Free Tier)

```
MiniMax-M*            129/1500   (text/LLM)
coding-plan-vlm       129/1500   (understand_image)
coding-plan-search    129/1500   (web_search)
image-01              0/0        (NOT AVAILABLE -- requires Plus)
speech-hd             0/0
MiniMax-Hailuo-2.3    0/0
music-2.6             0/100
```

## Plan Limitations

| Capability | Free | Plus+ |
|---|---|---|
| understand_image (vlm) | ✅ 1500/wk | ✅ higher |
| web_search | ✅ 1500/wk | ✅ higher |
| Image generation | ❌ | ✅ |
| Video generation | ❌ | ✅ |
| Music generation | ❌ | ✅ |
| Speech synthesis | ❌ | ✅ |

Upgrade: https://platform.minimax.io/subscribe/token-plan
