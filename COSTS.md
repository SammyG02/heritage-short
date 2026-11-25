# Costs

Money spent: **0**. Measured from `runs.jsonl` up to 23:34 EAT, 25 Nov 2026 (142 lines). To be refreshed before submission.

| Stage | Model | Successful calls | Median latency | Failed attempts | List-price equivalent |
|---|---|---:|---:|---:|---:|
| Script draft | gemini-3.6-flash (3.8 overloaded) | 1 | 38.1 s | 3 on 3.8 | $0.0203 (a) |
| Narration | gemini-3.8-flash-tts | 11 | 9.6 s | 1 (daily limit) | $0.0123 |
| Narration | gemini-3.8-flash-lite-tts | 12 | 6.6 s | 2 (network, daily limit) | $0.0140 (a) |
| Narration | gemini-3.1-flash-tts-preview | 11 | 5.8 s | 3 (2 per-minute, 1 daily limit) | not priced |
| Narration | gemini-2.5 flash and pro TTS | 0 | | 2 (limits) | |
| Reference sheets | FLUX.2 klein 4B | 28 | 12.8 s | 0 | $0.0324 |
| Keyframes | FLUX.2 klein 4B | 44 | 20.0 s | 0 | $0.0784 |
| Picture check | gemini-3.8-flash, then 3.6-flash | 2 | 89.9 s and 35.4 s | 4 (overloaded) | $0.0106 (a) |
| Moving shots | Wan 2.2 TI2V-5B | 2 clips | 1,173 s per 5 s clip at 480x832 (about 830 s denoising) | 1 (out of memory) | see GPU |
| Score | ACE-Step 1.5 | 3 tracks | 8.0 s per 90 s track | 0 | see GPU |
| Assembly | FFmpeg | | 759 s for one vertical film with transitions | | no model |

(a) Priced at the 3.8 Flash or 3.8 Flash TTS rate, which is not the model that ran. Approximate.

## GPU minutes

| Kaggle job (2 x T4) | Whole job | Useful work |
|---|---:|---|
| Wan, first try | 312.8 s | none: out of memory |
| Wan, two test clips | 2,647.3 s | 2,346.6 s for two clips |
| ACE-Step, three scores | 342.8 s | 27.7 s for three tracks; the rest is installing and loading |
| **Total** | **3,302.9 s = 55.0 minutes** | |

Kaggle's own counter said 0.93 hours used at 19:53 on 25 Nov; the job totals above are 0.92 hours. List-price equivalent: two T4s at $0.35 an hour each (Google Cloud on-demand, search result of its GPU pricing page, 26 Nov 2026) is **$0.64**.

In `runs.jsonl` the rows named `loaded` and `done` are running totals of a job, not model calls. Four early ones carry the status `ok` (two Wan, two ACE-Step); later ones say `job_event`. Do not add them to the clip rows.

Prices used: gemini-3.8-flash $0.75 in and $3.75 out per million tokens; 3.8 Flash TTS $0.50 in and $9.00 out (from a page summary, less certain); klein 4B $0.000059 per input and $0.000287 per output 512 px tile.

A clean clone with no keys rebuilt the earlier sample film in 14 min 40 s with 0 model calls on the same 8 GB laptop; both MP4s had the same SHA-256 prefix as the originals. This will be repeated for the final film.

## Free limits found

- Gemini TTS: **10 requests a day for each model** (3.8, 3.8 Lite, 3.1 and 2.5 Flash), by their own error messages; we counted 12, 12 and 11 successes before the first three refused. 3.1 also allows 3 a minute. 2.5 Pro: 0. Reset about 11:00 EAT.
- Cloudflare Workers AI: 10,000 neurons a day, reset 03:00 EAT. Klein 4B costs 26.05 per output tile and 5.37 per input tile, so 163 to 167 for our pictures and about 63 for the smaller size new films use. By that estimate we reached about 10,100 on 25 Nov; the service never refused a call.
- Kaggle: 30 GPU hours a week.
- Gemini text, 3.8 Flash: 10 of 11 attempts failed (9 "high demand", 1 connection timeout). Newer is not more available: 3.6 answered both times it was asked.

## Frontier comparison

Not run. Frontier models appear in the API listing, but the brief says they need paid billing and no organisation key has been received.
