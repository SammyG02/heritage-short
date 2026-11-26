# Architecture

```text
story + language + theme + consent --> script.py (or the studio) --> storyboard JSON --> a person edits and approves
                                                                         |
                                                         validated before every run (schema + rules)
                                                                         |
   narration.py --> one WAV per shot (Gemini TTS, or Addis AI) ---------+--> timeline (voice length, snapped to the beat)
   keyframes.py --> character faces --> one vertical PNG per shot ------+--> shots.py --> clip, or a slow camera move
                     (FLUX.2 klein on Cloudflare; checked by qa.py)      |       wide shot = vertical shot over its blurred copy
   gpu.py (Kaggle) / wavespeed.py --> Wan 2.2 clips; ACE-Step scores ----+--> music.py --> chosen score, or placeholder
                                                                         |
                                                                    assemble.py --> film_9x16.mp4, film_16x9.mp4, report.json
```

One command runs it all: `python -m pipeline film` (`make film`). It calls a model only for what is missing or out of date, so a fresh clone with no keys rebuilds the committed film without any call.

## Contract

`storyboard.json` is the only thing stages share. Prompts, seeds, models, voices, motion, mix settings, music cues, consent and approvals live there, not in code. `schema/storyboard.schema.json` checks its shape; `core/storyboard.py` checks what a schema cannot: unique ids, narration in every language, known references, chosen seeds, a 60-90 s plan, and that `people.real_people` is true only when a character is drawn from a photo its person agreed to. Each shot must state a `reason`.

| Stage | Reads | Writes under `outputs/<id>/` |
|---|---|---|
| narration | narration text, voice, service | `narration/<lang>/<shot>.wav` (Gemini), `narration/<lang>/<service>/` (others) |
| keyframes | prompts, seed, chosen characters | `references/<name>_<seed>.png`, `keyframes/<shot>_9x16.png` |
| shots | keyframe, motion prompt, timeline | `shots/wan/` (model clips), `shots/cut/` (rebuilt locally, not committed) |
| music | caption, bpm, key, seeds | `music/score_<seed>.wav` |
| assemble | all of the above | `film/<lang>/` |

## One film, two shapes

Only vertical pictures are drawn (`wide_from_vertical`, default true). Each wide shot is the finished vertical shot, sharp in the middle, over a blurred and darkened copy of itself (`shots.from_vertical`, FFmpeg only). The two films match frame for frame, the moving clips appear in both, and no picture or GPU minute is spent twice. Chosen on 26 Nov: drawing 12 wide pictures would have cost 12 more picture calls and approvals, and wide clips double the motion budget. Before that, each shot had its own wide picture, which kept faces whole in both shapes but made the two versions differ. Setting `wide_from_vertical` to false brings that back.

## Motion, shot by shot

Each shot is a slow camera move (free, FFmpeg), a clip from the free Kaggle GPU, or a clip from WaveSpeed (paid). New films start with camera moves; a person chooses which shots move and where.

- **Kaggle** (`gpu.py`, `kaggle_jobs/wan_worker.py`): Wan 2.2 TI2V-5B on two T4s, about 20 minutes a clip. Batched, so the model loads once per job.
- **WaveSpeed** (`wavespeed.py`): Wan 2.2 image-to-video at 480p, about a minute a clip. Only with `WAVESPEED_API_KEY`; without it those shots fall back to Kaggle. The studio sends one named shot at a time, after a confirmation that shows the price. Spending stops at the lower of the person's budget and the account's real balance.
- **Clip length:** 5 s unless slowing a 5 s clip to fill the shot would show (more than 1.25x with people, 1.6x for scenery); then 8 s.
- Clips are cached by their inputs whichever service made them, so switching service never throws a finished clip away. A replaced clip is kept in `shots/wan/versions/`.

## Caching

Each model output has a `.meta.json` with a SHA-256 key over its exact inputs (model, prompt, seed, parameters, and the content hash of any image it depends on) and a hash of the file. A file is reused only if both match. So:

- a changed narration line regenerates one WAV;
- a changed image prompt regenerates that shot's picture and makes its clip out of date;
- a changed character face regenerates every picture that shows it, and nothing else;
- a damaged or hand-edited file is regenerated.

`python -m pipeline status` shows what a run would remake, without calling a model. Tests prove the first two without network access. Writes go to a temporary file and are then renamed, so an interrupted run never leaves a half-written output, the finished film included.

## Approvals

A person approves each step: script lines, voices, pictures and movements, by content hash, so any change cancels its approval. The studio builds the final film only when everything in it is approved. `python -m pipeline film` skips the gates on purpose: it is the one command that must rebuild the film from a clean clone. `film --review` keeps them.

## Consent

A true story is locked until consent is recorded (`people.consent`), and nothing is sent to a model before that (`require_consent`, called before every call). It is recorded person by person (role; their story told, drawn as a character, their words quoted, their photo used; when and how) and service by service (`people.ai_services`): a service left unticked is never called (`require_service`). Adding, changing or withdrawing consent writes a dated line to `people.consent_record`; withdrawing locks the film again. A character may be drawn from a photo only when its person ticked that box; the photo is scaled down, stripped of its metadata, kept out of Git, and deleted if the consent is taken back.

## Failure handling

- **Hosted calls:** three attempts with exponential backoff and jitter, honouring the server's suggested wait. Client errors and daily quotas are not retried.
- **Text models:** fall through a list (3.6 Flash, 3.8 Flash, 3.5 Flash-Lite).
- **Voice:** one call records every missing line and is cut at its pauses (or by line length when pauses tie); if no cut is safe, the recording is kept and the lines are made one by one. Each voice service keeps its own files, so switching back loses nothing.
- **Pictures:** a picture blocked by Cloudflare's safety filter is drawn again with another seed, up to three times. Each is checked by a vision model (identity, emotion, content, anatomy, style); below 7 it is redrawn, best of three kept. If no checker answers it is kept and marked unchecked, never passed.
- **Limits:** counted per account and, for Cloudflare, over the last 24 hours; a service's own refusal overrides our count. A job that would pass a limit stops before it, keeps what it made, and can be scheduled for when the limit returns.
- **Kaggle:** workers save each result as it finishes; `gpu fetch` imports what succeeded. Commands are tried again on a connection timeout.
- **WaveSpeed:** a submit is never repeated after an unclear failure (it would be a second paid clip); one refused for "concurrency" was never created, so it waits and is sent again.
- **Motion and music fallbacks:** no clip, a camera move; no score, a placeholder made in code. A stale clip or score is never used.
- **Assembly** measures the finished files (length, size, frame rate, loudness, true peak) and writes any problem to `report.json`.

## Logging

Every attempt, including failures, is one line in `runs.jsonl`: run id, stage, item, provider, model, parameters, seed, attempt, status, latency, GPU seconds, money spent, list-price equivalent, and a one-way fingerprint of the account. Secret values are replaced before writing. Films made in the studio log to `my-films/runs.jsonl`, outside Git.

## The studio

`python -m pipeline web` serves a local page (Story, Script, Cast, Shots, Film, Services) that drives the same stages; every long job runs the same command line as a separate process, so the terminal and the studio cannot disagree. It shows progress and time left, a draft video to download before the film is built (`python -m pipeline preview`, no model call), and on Services what is left of each limit. A service is offered only if its key is set and it has produced something here, or, for a paid one, its price is shown.

## Quality rules every film gets

| Promise | How it is kept | If it fails |
|---|---|---|
| Same characters throughout | One approved face per character; a locked `look` sentence added to every prompt that shows them; older versions drawn `from` the approved face | Changing a face makes exactly that character's shots out of date |
| Emotion fits the moment | `emotion` per shot goes into the picture and motion prompts; `voice_emotion` into the voice style | New drafts without an emotion are rejected (`script.lint`) |
| Meaningful transitions | `transition` per shot with a reason; shots still start exactly on their beat | Default is a cut |
| Pictures are checked | `qa.py`, as above | Unchecked pictures say so; a person approves every picture |
| Loudness | Voice and music levelled first, music ducked under the voice (sidechain, ratio 6), two-pass `loudnorm` to -14 LUFS, true peak -1 dB | Measured and reported in `report.json` |

The vision check reduces bad pictures; it does not guarantee good ones. A person still looks at every shot.
