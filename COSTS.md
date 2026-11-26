# Costs

**Money spent: none.** Everything ran inside free limits or free sign-up credits. Measured from `runs.jsonl` (280 lines, 25 Nov 15:58 to 26 Nov 15:43 EAT) and from each credit's own balance on 26 Nov 2026.

| Service with a sign-up credit | Used | How we know |
|---|---:|---|
| WaveSpeed (3 moving clips, Wan 2.2 I2V 480p "ultra fast") | **$0.34** of its free $1.00 sign-up credit | Its balance API: $1.00 before, $0.66 after. Our log counted $0.29 (see below) |
| Addis AI (28 voice lines, tried and not used in the film) | **9.50 Birr** of its free 500 Birr sign-up credit | Its usage API: 490.50 Birr left; price 5 Birr a minute |

**The two counts disagree.** The first WaveSpeed batch took the balance from $1.00 to $0.74 for one 8 s and one 5 s clip, which the listed price ($0.01 a second) puts at $0.13; two other clips in that batch were refused (HTTP 429) and are not supposed to be charged. A later single 8 s clip took it from $0.74 to $0.66, exactly the listed $0.08. The extra $0.13 of the first batch is unexplained. The studio now reads the real balance before every batch and spends at most the lower of the balance and the budget, and paid clips are sent one shot at a time so each charge can be seen.

## Per stage

| Stage | Model, where | Successful calls | Median latency | Failed attempts | List-price equivalent |
|---|---|---:|---:|---:|---:|
| Script draft | gemini-3.6-flash (3.8 overloaded) | 1 | 38.1 s | 3 on 3.8 | $0.020 (a) |
| Narration, both films (the final voice) | gemini-3.8-flash-tts, 3.8-flash-lite-tts and 3.1-flash-tts-preview | 38 | 5.8 to 9.5 s | 8 (daily limits, network) | $0.030 (a) |
| Narration, tried | Addis AI Voices 2 | 28 | 4.8 s | 0 | 9.50 Birr of a free credit |
| Character pictures | FLUX.2 klein 4B, Cloudflare | 30 | 12.7 s | 2 (safety filter, daily limit) | $0.035 |
| Shot pictures | FLUX.2 klein 4B, Cloudflare | 66 | 18.9 s | 2 (daily limit) | $0.118 |
| Picture checks | gemini-3.6-flash, 3.8-flash, 3.5-flash-lite | 17 | 15.7 s (3.6) | 60 (3.8: 40 of 41 failed, overloaded) | $0.080 (a) |
| Moving shots, free | Wan 2.2 TI2V-5B, Kaggle 2 x T4 | 2 clips | 1,173 s per 5 s clip at 480x832 (about 830 s denoising) | 1 (out of memory) | see GPU |
| Moving shots, paid | Wan 2.2 I2V 480p ultra fast, WaveSpeed | 3 clips | 75 s per clip (about 40 to 51 s of it on WaveSpeed's GPU) | 2 (refused: 2 running at once is the plan's limit) | $0.29 counted, $0.34 charged |
| Score | ACE-Step 1.5, Kaggle | 3 tracks | 8 to 12 s per 90 s track | 0 | see GPU |
| Preview video (540x960) | FFmpeg, this laptop | | 85 s for 88.8 s of film | | no model |
| Final film, both shapes | FFmpeg, this laptop | | about 13 min (file times: mix 16:13, vertical 16:22, wide 16:26) | | no model |

(a) Priced at the 3.8 Flash or 3.8 Flash TTS rate where the model that ran has no published price. Approximate.

Moving clips compared: a WaveSpeed clip came back in **about 1 minute for $0.08 to $0.16**, a Kaggle clip in **about 20 minutes for no money**, plus about 5 minutes to load the model once per job and a queue of up to an hour.

## GPU minutes

| Kaggle job (2 x T4) | Whole job | Useful work |
|---|---:|---|
| Wan, first try | 312.8 s | none: out of memory |
| Wan, two test clips | 2,647.3 s | 2,346.6 s for two clips |
| ACE-Step, three scores | 342.8 s | 27.7 s for three tracks; the rest is installing and loading |
| **Total** | **3,302.9 s = 55.0 minutes** | |

Kaggle's own counter said 0.93 hours used; the job totals above are 0.92 hours. List-price equivalent: two T4s at $0.35 an hour each (Google Cloud on-demand) is **$0.64**.

In `runs.jsonl` the rows named `loaded` and `done` are running totals of a job, not model calls. Do not add them to the clip rows.

Prices used: gemini-3.8-flash $0.75 in and $3.75 out per million tokens; 3.8 Flash TTS $0.50 in and $9.00 out (from a page summary, less certain); klein 4B $0.000059 per input and $0.000287 per output 512 px tile; WaveSpeed ultra fast $0.01 a second, standard $0.03 (model pages, 26 Nov 2026).

## Free limits found

- **Gemini TTS:** 10 requests a day for each model, by its own error messages. 2.5 Pro TTS: 0. Resets at midnight Pacific, 11:00 EAT. One call can now record every missing line at once and be cut into one file per line (experiment 7 and 15), so a 12-line film fits in one call when the cut is safe.
- **Cloudflare Workers AI:** 10,000 neurons a day, **counted over the last 24 hours, not since midnight** (experiment 11). Klein 4B costs 26.05 per output tile and 5.37 per input tile: 163 to 167 for our pictures, about 104 for a character face.
- **Kaggle:** 30 GPU hours a week; 29.1 left.
- **Gemini text, 3.8 Flash:** 1 of 47 attempts succeeded over both days (smoke test, script, picture checks), almost all failures "high demand". 3.6 Flash answered 12 of 32 (experiment 12).
- **WaveSpeed:** paid; at most 2 clips running at once on this plan.

## Clean-clone rebuild

On 26 Nov at 17:47 EAT a fresh `git clone` of commit `302dc81`, with no `.env` and every key removed from the environment, ran `python -m pipeline film`: **7 min 6 s, exit 0, 0 model calls** (`runs.jsonl` had 280 lines before and after). Both videos came out **identical** to the ones built in the studio: SHA-256 `844272ebb3758eb4...` (vertical) and `0869df3ec21c9335...` (wide), 88.83 s, -14.2 LUFS, true peak -1.33 dB. The earlier sample film was rebuilt the same way on 25 Nov in 14 min 40 s.

## Frontier comparison

Not run. Frontier models appear in the API listing, but they need paid billing and no organisation key was received. WaveSpeed hosts the same open Wan 2.2 family, not a frontier model.
