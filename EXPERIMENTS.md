# Experiments

Each entry: hypothesis, the one thing changed, result. Image counts in entries 1 to 5 were made by the coding agent viewing contact sheets on 25 Nov 2026; the pictures are kept in `outputs/extra-cup/` so anyone can check them. Every call is in `runs.jsonl`.

**Done: 15. Target: at least 10.** Nothing is listed here until it has been run.

## 1. Negative wording in an image prompt

- **Hypothesis:** writing "cross-free" earrings keeps crosses out of the portrait.
- **Change:** "small silver cross-free round earrings" became "small plain round silver stud earrings". Same seeds 11, 22, 33, 44. (The shared style block also changed "no text, no lettering, no border" to "full-bleed painting reaching every edge", see 2.)
- **Result:** seeds 11 and 44 drew crosses with the negative wording; none of the four did afterwards. The hypothesis was wrong: naming the thing summoned it.
- **Decision:** prompts say what is present. The intake prompt in `pipeline/script.py` now carries this rule.

## 2. "No border" against "full-bleed"

- **Hypothesis:** saying "no border" prevents ragged paper edges.
- **Change:** the style block wording above, with the coffee-set subject also reworded (see 3), so this is not a clean single-variable test.
- **Result:** ragged paper edges were obvious in coffee-set seeds 11 and 44 and faint in others before; afterwards only small corners remain on 11 and 44. Better, not solved.
- **Decision:** keep "full-bleed"; choose seed 33, which has clean edges.

## 3. Naming a jebena against describing its shape

- **Hypothesis:** the model knows what a jebena is.
- **Change:** "one round black clay jebena coffee pot with a long neck and a side handle" became a description of a ball-shaped base, one tall slender tube neck, straw stopper and loop handle.
- **Result:** 0 of 4 pots looked like a jebena before (wide-mouthed teapots with spouts); 4 of 4 had the long neck afterwards.
- **Decision:** describe culturally specific objects by shape. Naming alone returned a generic teapot.

## 4. Leaving space for subtitles

- **Hypothesis:** asking for "calm empty space near the bottom" leaves room for captions.
- **Change:** vertical framing became "the painted scene continues down to the bottom edge". Some shot prompts changed in the same run.
- **Result:** before, the vertical images s04 and s07 ended in a flat painted band with the subject cut off; after, 0 of 11 vertical images did.
- **Decision:** let the picture fill the frame and give captions an outline instead.

## 5. Attaching a reference image to every shot

- **Hypothesis:** adding the coffee-set reference everywhere improves consistency.
- **Change:** removed it from s01 (house) and s06 (door), where no cup should appear. The s06 wording also changed.
- **Result:** with it, the coffee set appeared outdoors in front of the house in vertical s01, and blocked the door in both versions of s06. Without it, neither shot contained it.
- **Decision:** attach a reference only where its subject belongs. This is a limit on the brief's "condition every keyframe on the sheet" advice.

## 6. Face motion against body motion in Wan

- **Hypothesis:** Wan can move a mouth and a body from one keyframe.
- **Change:** two clips in one job, same model, 30 steps, guidance 5, 121 frames, 480x832. `s04_9x16`: speaking close-up. `s03_9x16`: medium shot, lifting the head, breathing and pouring. Different keyframes and seeds, so this compares two kinds of shot, not one variable. Prompts are in `storyboards/tests/motion-test.json`.
- **Result:** (agent viewing 10 frames from each) the face spoke, blinked, smiled and tilted with the same identity throughout; a small purple tint appears in the lower right corner. The body clip failed: the head folds back out of view from about second 2, and the camera moves.
- **Decision:** let close faces speak; give bodies one small movement; keep the fallback for any clip that breaks.

## 7. Cutting one recording into lines: best guess against refusing

- **Hypothesis:** matching piece length to text length finds the right cuts in one recording of the whole script, so a film needs one voice call.
- **Method:** real narration lines (9 Amharic, 11 Amharic, 11 English) joined with known pauses of 0.3-0.5, 0.6-1.0 or 1.2-2.0 s, six random versions each; no voice call used. Known cuts give the truth.
- **Result, best guess:** at 0.3-0.5 s, 12 of 18 recordings were cut wrongly without any sign (3 to 8 lines off); at 0.6-1.0 s, 4 of 18; at 1.2-2.0 s, 0 of 18.
- **Change:** cut only at the longest pauses, and only when the shortest of them is at least 0.6 s and 1.2 times the longest pause inside a line. Otherwise refuse and keep the recording. A 1.8-2.6 s set was added.
- **Result, refusing:** 72 recordings: 36 cut, all correct; 36 refused; 0 wrong.
- **Decision:** refuse. A wrong cut spoils lines silently; a refusal costs at most a few more calls. Whether the model leaves long enough pauses: on 26 Nov a real recording did not, which led to experiment 15.

## 8. How hard to duck the score

- **Hypothesis:** the brief's starting point (threshold 0.02, ratio 6, attack 300 ms, release 1500 ms) separates voice and music enough without removing the music.
- **Change:** ratio only: off, 2, 6 and 12. Real Amharic lines 1 to 9 and each of the three ACE-Step scores, FFmpeg, no model calls. RMS level of the music while the voice speaks and in a stretch without voice, and how far the voice is above the music.
- **Result:**

| Score | Off | 2:1 | 6:1 | 12:1 | Music without voice |
|---|---:|---:|---:|---:|---:|
| 101, voice above music | 3.3 dB | 11.3 | 15.7 | 16.7 | -22.6 dB |
| 202 | 4.1 | 12.0 | 16.2 | 17.0 | -20.6 |
| 303 | 3.4 | 11.5 | 15.7 | 16.5 | -23.2 |

- **Decision:** keep 6:1. Doubling it buys only 0.8 to 1.0 dB; 2:1 leaves the voice about 4 dB less clear. The choice of score hardly matters for clarity (0.5 dB), so it can be made by ear. Not yet checked by listening.

## 9. One-pass against two-pass loudness

- **Hypothesis:** the brief says two passes are more accurate; on a short mix the difference may be too small to matter.
- **Change:** the same mix (lines 1 to 9, score 101; -18.94 LUFS, -1.44 dB true peak) through `loudnorm` once, and through it twice with the first measurement.
- **Result:** target -14 LUFS. One pass: -15.08. Two passes: -14.32. True peak -1.48 dB in both.
- **Decision:** two passes. One pass would have missed our own limit (1 LU) and failed the automatic check, so the hypothesis was wrong.

## 10. Do the scores keep the tempo they were asked for

- **Hypothesis:** ACE-Step follows the tempo field, so cuts placed on a 72 bpm grid land on the beat of any of the three scores.
- **Change:** seed only (101, 202, 303); same caption, 72 bpm, D minor, 90 s. Strength of repetition in the first 84 s of each track (autocorrelation of spectral change, 1.0 would be perfect repetition).
- **Result:**

| Score | Strongest tempo | At 72 bpm | Energy in the speech band, 300-3400 Hz |
|---|---|---:|---:|
| 101 | 72.0 bpm (0.63) | 0.63 | 47% |
| 202 | 72.0 bpm (0.14) | 0.14 | 51% |
| 303 | 75.0 bpm (0.10) | 0.09 | 55% |

- **Reading:** 101 has a clear pulse at the tempo asked for. 202 leans the same way very weakly. 303 has no pulse we can measure, so "cutting to its beat" would mean nothing. 101 also leaves the voice the most room.
- **Decision:** the hypothesis held for one track of three. 101 was the measured recommendation, and on 26 Nov the applicant chose it by ear: "I like it, it went well with the story, it was warm." The measurement and the ear agreed. The grid's starting point against the first beat is not checked.

## 11. When does Cloudflare's daily picture allowance reset?

- **Hypothesis:** the 10,000-neuron daily allowance resets at 00:00 UTC (03:00 EAT), so the morning of 26 Nov starts with a full allowance.
- **Change:** none: an observation, read from `runs.jsonl`.
- **Result:** after 00:00 UTC our log showed only about 220 units used, yet at 05:22 UTC (08:22 EAT) Cloudflare refused a picture: "you have used up your daily free allocation of 10,000 neurons". Counting the 24 hours before that moment instead gives 10,095 units, almost all drawn between 13:01 and 13:24 UTC the day before. The studio had shown "98% left".
- **Decision:** the hypothesis was wrong: the window behaves as the last 24 hours. The studio now counts a rolling 24 hours, believes the service's refusal over its own count, and shows when room comes back (when the oldest picture turns a day old). Not confirmed by waiting: the applicant switched to a second Cloudflare account that morning (FAILURES.md), so the predicted return at 16:10 EAT was not observed.

## 12. Which model to ask first for picture checks

- **Hypothesis:** the newest model, gemini-3.8-flash, is the best first choice for the face check.
- **Change:** none at first; then the order was swapped to try gemini-3.6-flash first.
- **Result:** in the log, 3.8 Flash answered 1 of 41 checks (40 "high demand" or timeouts, each costing up to three attempts with backoff, about 45 s a picture); 3.6 Flash answered 11 of 31; 3.5 Flash-Lite 5 of 5. Drawing 11 pictures took over 30 minutes, mostly waiting on 3.8.
- **Decision:** newest is not most available. 3.6 is asked first, then 3.8, then 3.5 Lite. If none answers, the picture is kept and marked unchecked for a person to look at.

## 13. Moving shots: free GPU against a paid host of the same model family

- **Hypothesis:** a hosted Wan 2.2 (WaveSpeed, image-to-video, 480p "ultra fast") is fast enough and cheap enough to animate the shots that matter on the last day, where Kaggle cannot.
- **Change:** the service only; the same approved keyframes and motion prompts.
- **Result:**

| | Kaggle, Wan 2.2 TI2V-5B, 2 x T4 | WaveSpeed, Wan 2.2 I2V 480p ultra fast |
|---|---|---|
| Time per clip | 1,173 s (plus about 5 min loading per job and up to an hour in the queue) | 51 to 79 s from upload to download (40 to 51 s on its GPU) |
| Cost per clip | free (30 GPU hours a week) | $0.05 for 5 s, $0.08 for 8 s listed; see COSTS.md for what was charged |
| Running at once | one clip at a time, both cards in one pipeline | 2 (a third and fourth were refused with HTTP 429) |
| Clips in the film | 0 | 3 (shots 1, 3 and 5) |

- **Decision:** paid clips for a few chosen shots, free Kaggle as the default for the rest, a camera move where neither is worth it. Quality was not compared blind, so this is a decision on time and cost only.

## 14. Listed price against charged price

- **Hypothesis:** WaveSpeed charges its listed price, so a budget counted from our own log is safe.
- **Change:** read the account balance through WaveSpeed's API before and after paid clips.
- **Result:** first batch: $1.00 to $0.74 for clips listed at $0.13. Second, a single 8 s clip: $0.74 to $0.66, exactly the listed $0.08. Total $0.34 against $0.29 in our log.
- **Decision:** the hypothesis held for a single clip and failed for the batch, for a reason not found. The studio now spends at most the lower of the budget and the real balance, asks before every paid clip, and sends one shot at a time.

## 15. Cutting one recording when the pauses are the same length

- **Hypothesis:** when a pause inside a line is as long as the pauses between lines, the lines' text lengths can still tell them apart.
- **Change:** the cutter from experiment 7 refused a real 3-line recording on 26 Nov (pauses of 0.88, 0.82 and 0.82 s; the last one inside line 12), and three single-line calls were spent instead. A fallback was added: when the pause rule fails, choose the cut points whose pieces best match each line's share of the text, but only if every piece is within 1.4 times its share and the next-best choice is clearly worse (1.35 times).
- **Result:** on that same recording, kept from the paid call, it now cuts 4.0, 3.9 and 7.8 s; the lines made one by one were 4.7, 4.1 and 8.4 s, which include more silence at the ends. The equal-length case from experiment 7 is still refused.
- **Decision:** keep the fallback; it would have saved three of the day's ten voice calls.
