# Costs

Money spent: **0**. Measured from `runs.jsonl` up to 16:50 EAT, 25 Nov 2026 (92 lines). To be refreshed before submission.

| Stage | Model | Successful calls | Median latency | Failed attempts | List-price equivalent |
|---|---|---:|---:|---:|---:|
| Script draft | gemini-3.6-flash (3.8 overloaded) | 1 | 38.1 s | 3 on 3.8 | $0.0203 (a) |
| Narration, Amharic | gemini-3.8-flash-tts | 11 | 9.6 s | 0 | $0.0123 |
| Narration, English | gemini-3.8-flash-lite-tts | 11 | 6.7 s | 1 (network), plus 1 quota on 3.8 | $0.0124 (a) |
| Reference sheets | FLUX.2 klein 4B | 16 | 11.0 s | 0 | $0.0184 |
| Keyframes | FLUX.2 klein 4B | 42 | 20.0 s | 0 | $0.0747 |
| Moving shots | Wan 2.2 TI2V-5B | 0 | none: 309 s loading, then out of memory | 1 | not priced |
| Score | ACE-Step 1.5 | 3 | 8.0 s per 90 s track (11.8, 7.9, 8.0); 343 s whole job, including install and load | 0 | not priced |
| Assembly | FFmpeg | | 317 s for the radio cut and both first exports, including all 22 Ken Burns renders | | no model |

(a) Priced at the 3.8 Flash or 3.8 Flash TTS rate, which is not the model that ran. Approximate.

Prices used: gemini-3.8-flash $0.75 in and $3.75 out per million tokens; 3.8 Flash TTS $0.50 in and $9.00 out (from a page summary, less certain); klein 4B $0.000059 per input and $0.000287 per output 512 px tile. GPU time will be priced separately once measured.

A clean clone with no keys rebuilt the film in 14 min 40 s with 0 model calls on the same 8 GB laptop and FFmpeg; both MP4s had the same SHA-256 prefix as the originals.

## Free limits found

- Gemini 3.8 Flash TTS: an error reported **10 requests a day**. We had 12 successes before it triggered.
- Cloudflare Workers AI: 10,000 neurons a day, resetting at 00:00 UTC (03:00 EAT). By list price, our 58 stage images plus the smoke test used roughly 8,500. That is an estimate, not a meter reading.
- Kaggle: 30 GPU hours a week, 0 used at the start.

## Frontier comparison

Not run. Frontier models appear in the API listing, but the brief says they need paid billing and no organisation key has been received.
