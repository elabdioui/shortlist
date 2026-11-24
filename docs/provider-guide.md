# AI Provider & Cost Guide

Shortlist routes all AI calls through **LiteLLM** with a local key-pool router supporting multiple keys per provider, automatic rate-limit cooldowns (`429`), and fallback profiles.

## Supported Providers & Getting a Key

| Provider | How to Get a Key | Free Tier Available? | Data Leaves Machine? |
| --- | --- | --- | --- |
| **Ollama (local)** | No key needed (`docker compose --profile ollama up`) | 100% Free (local) | **No** |
| **Google Gemini** | Google AI Studio (`aistudio.google.com`) | Yes (rate-limited) | Yes (anonymized) |
| **OpenAI** | OpenAI Platform (`platform.openai.com`) | No (pay-as-you-go) | Yes (anonymized) |
| **Anthropic** | Anthropic Console (`console.anthropic.com`) | No (pay-as-you-go) | Yes (anonymized) |
| **Mistral** | Mistral La Plateforme (`console.mistral.ai`) | Yes (Experiment tier) | Yes (anonymized) |
| **Groq** | Groq Console (`console.groq.com`) | Yes (rate-limited) | Yes (anonymized) |
| **OpenRouter** | OpenRouter (`openrouter.ai`) | Some `:free` models | Yes (anonymized) |
| **OpenAI-compatible** | LM Studio, vLLM, Azure OpenAI URL | Depends on host | Depends on host |

## Free-Tier Data Privacy Caveat

> **Important:** Some providers (including free tiers on Google AI Studio, Mistral Experiment, Groq, and OpenRouter free models) may log or use prompts to improve their models. When you mark a key as **Free tier** in Shortlist, the UI displays an explicit warning.
>
> Even though Shortlist **anonymizes CVs locally before any external call**, for strict confidentiality or sensitive hiring pipelines, use a **paid API tier with zero-data-retention** or run **Ollama locally**.

## Estimated Cost for 200 CVs

Assuming an average CV is ~1,500–2,500 input tokens (plus job description & criteria ~800 tokens) and structured JSON output is ~400 output tokens (~3,000 input + 400 output tokens per CV = **600k input + 80k output tokens** for 200 CVs):

| Model Tier | Typical Model | Estimated Cost (200 CVs) |
| --- | --- | --- |
| **Local** | Ollama (`llama3.1:8b`, `qwen2.5:14b`) | **$0.00** (hardware/electricity only) |
| **Economical** | Gemini 2.0 Flash-Lite / GPT-4o-mini / Mistral Small | **~$0.05 – $0.20** |
| **Balanced** | Gemini 2.0 Flash / Claude 3.5 Haiku | **~$0.15 – $0.75** |
| **High-accuracy** | GPT-4o / Claude 3.5 Sonnet | **~$2.00 – $3.50** |

*Note: Actual costs depend on CV length, OCR noise, and provider pricing at the time of execution. Shortlist displays a pre-run estimate and tracks actual token cost per key and per job.*
