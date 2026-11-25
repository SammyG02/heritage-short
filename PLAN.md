# Plan: The Heritage Short

Deadline: **Thu 26 Nov 2026, 23:59 EAT**. Internal target: submit by 21:00.
Planning started Wed 25 Nov, about 15:15 EAT, leaving under 33 hours.

## Strategy

1. **Finish a complete film early, then upgrade it.** Every shot first gets a Ken Burns move over its keyframe. Wan clips replace them one by one, so a GPU failure cannot sink the film.
2. **Start slow or human-dependent work first:** accounts, consent, finding testers, the Kaggle queue.
3. **Record evidence as it happens.** Feedback, consent and measurements must be real.
4. **One ceiling experiment only,** after the near-final cut exists.

## Proposed architecture

Python command: `python -m pipeline film` (a Makefile will wrap it as `make film`).

```text
storyboard.json -> schema validation
  -> narration (Gemini TTS, one WAV per shot) -> measured durations -> radio cut
  -> reference sheet -> keyframes (FLUX, Cloudflare) -> shots (Wan on Kaggle | Ken Burns)
  -> music (ACE-Step on Kaggle, 3 candidates, choice recorded in storyboard)
  -> assemble (FFmpeg) -> film_9x16.mp4 + film_16x9.mp4
```

- **Script stage:** Gemini drafts and translates. A human edits and approves the storyboard. `film` never overwrites it.
- **Cache key:** hash of model, parameters, seed, prompt, reference-file hashes and stage version. Editing a narration line must not regenerate pictures. Changing a keyframe prompt regenerates one keyframe and its dependent shot.
- **Live demo:** if a Wan clip is stale and no GPU job has run, the shot falls back to Ken Burns on the new keyframe.
- **Clean clone:** approved outputs and cache manifests are committed, so a cached rebuild needs no keys or GPU. A forced regeneration needs credentials.
- **Failures:** retries with backoff and jitter, at most three attempts per shot, atomic writes, logged fallback.
- **Logging:** every attempt, failures included, goes to `runs.jsonl` with model, parameters, seed, latency, GPU seconds, cost and list-price equivalent. Keys are never logged.
- **Aspect ratios:** compare one centred image cropped twice against a keyframe per ratio (experiment 3).

## Story intake (product direction)

The pipeline accepts anyone's story, not just ours: `python -m pipeline new` asks for story, narration language, theme, audience and ending feeling, then drafts a schema-valid storyboard for human approval. `film` builds from it.

- **Languages:** Amharic and English first. Others are offered only as experimental until a native listener checks them. Subtitles are always English.
- **Theme:** sets the style block (palette, light, medium), music caption and narration tone. All are saved in `storyboard.json`.
- **People:** invented characters and stock TTS voices only. No photo or voice uploads. ETHICS.md records this; a story that identifies a living person still needs care and their agreement.
- **Web form:** a thin local page over the same commands, built Thursday afternoon only if the film is on schedule. No hosted platform, accounts or payments. This is the preferred ceiling item, tested with someone who does not code.

## Schedule (EAT)

| When | Milestone |
|---|---|
| Wed 15:30-17:00 | Story, audience and consent settled; accounts and keys; FFmpeg; smoke test |
| Wed 17:00-19:30 | DESIGN and ETHICS; schema; core pipeline; storyboard v1; narration |
| Wed 19:30-21:30 | **Checkpoint 1:** radio cut, three listeners, storyboard v2 |
| Wed 21:30-01:00 | Reference sheet, keyframes; submit Wan and ACE-Step jobs to run overnight |
| Thu 07:00-10:00 | **Checkpoint 2:** rough cut with a picture per shot; score chosen |
| Thu 10:00-13:00 | Mix, subtitles, end card, both exports |
| Thu 13:00-15:00 | Near-final cut, three viewers, changes applied |
| Thu 15:00-17:00 | Ceiling: story web form (drop first if late); picture lock at 17:00 |
| Thu 17:00-19:00 | Documents, report, clean-clone test, public repository |
| Thu 19:00-21:00 | **Checkpoint 3:** post, walkthrough, logged-out link check, submit both |
| Thu 21:00-23:59 | Emergency buffer |

Cut order if late: ceiling, extra Wan shots, animated extras. Never cut: consent, both user tests, both ratios, end card, documents, walkthrough.

## Candidate experiments (at least ten must produce real results)

1. Style instruction vs a different TTS voice
2. Shorter sentences vs original narration: duration and clarity
3. One centred keyframe cropped twice vs one per ratio
4. Text-only vs reference-conditioned keyframes
5. FLUX.2 klein vs FLUX.1 schnell, where both are available
6. Fixed vs varied seed across shots
7. Wan: motion-only vs full-description prompt
8. Wan: 480p vs 720p, time and quality
9. Ken Burns vs Wan on the same shot
10. Three ACE-Step candidates under narration
11. Brief's ducking settings vs a tuned version
12. One-pass vs two-pass loudness normalisation

**Ceiling:** the story web form, tried by a relative or friend who does not code: can they get from story to approved storyboard unaided, and where do they get stuck? Fallback if late: test the command-line intake the same way.

## Risks

| Risk | Response |
|---|---|
| Consent delayed | Fictional, non-identifiable character and stock TTS voice; no family photos or cloned voice |
| Kaggle verification, queue or T4 memory fails | Colab, lower resolution, then Ken Burns |
| Gemini or Cloudflare quota runs out | Cache, backoff, spread jobs; limited seeds per shot |
| Character drifts | One main character, distinctive clothing, reference sheet, hands and wide shots |
| TTS mispronounces names | Native listen per line; respell or reword |
| Testers unavailable | Contact at least five today |
| 8 GB RAM, no NVIDIA GPU | No local models; low-resolution proxies until final export |
