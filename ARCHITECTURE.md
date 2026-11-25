# Architecture

```text
story + language + theme --> script.py (or web.py) --> storyboard JSON --> a person edits and approves
                                                            |
                                            validated before every run
                                                            |
   narration.py --> one WAV per shot ----------------------+--> timeline (voice length, snapped to the beat)
   keyframes.py --> references --> one PNG per shot/ratio --+--> shots.py --> Wan clip, or Ken Burns
   gpu.py (Kaggle) --> Wan clips, ACE-Step scores ----------+--> music.py --> chosen score, or placeholder
                                                            |
                                                       assemble.py --> film_9x16.mp4, film_16x9.mp4, report.json
```

## Contract

`storyboard.json` is the only thing stages share. Prompts, seeds, models, voices, mix settings and music cues live there, not in code. `schema/storyboard.schema.json` checks shape; `core/storyboard.py` checks what a schema cannot: unique ids, narration in every language, known references, chosen seeds, and a 60-90 s plan. Each shot must state a `reason`. `people.real_people` must be false.

| Stage | Reads | Writes under `outputs/<id>/` |
|---|---|---|
| narration | narration text, voice | `narration/<lang>/<shot>.wav` |
| keyframes | prompts, seed, chosen references | `references/`, `keyframes/<shot>_<ratio>.png` |
| shots | keyframe, motion prompt, timeline | `shots/wan/` (model), `shots/cut/` (rebuilt locally, not committed) |
| music | caption, bpm, key, seeds | `music/score_<seed>.wav` |
| assemble | all of the above | `film/<lang>/` |

## Caching

Each model output has a `.meta.json` with a SHA-256 key over its exact inputs (model, prompt, seed, parameters, and the content hash of any image it depends on) and a hash of the file. A file is reused only if both match. So:

- a changed narration line regenerates one WAV;
- a changed image prompt regenerates that shot's two images (one per format), and makes its Wan clips stale;
- a changed reference image regenerates every keyframe that uses it, and nothing else;
- a damaged or hand-edited file is regenerated.

`tests/test_contract.py` proves the first two without network access. Writes go to a temporary file and are then renamed, so an interrupted run never leaves a half-written output.

## Failure handling

- Hosted calls: three attempts with exponential backoff and jitter, honouring the server's suggested wait. Client errors and daily quotas are not retried.
- Script: falls through a list of text models.
- Wan: if no clip matches the current keyframe and prompt, the shot uses Ken Burns. A stale clip is never used.
- Music: a placeholder synthesised in code is used until a matching score exists.
- Kaggle: workers save each result as it finishes; `gpu fetch` imports what succeeded and logs each result once.
- Assembly measures the finished files (length, size, frame rate, loudness, true peak) and writes any problem to `report.json`.

## Logging

Every attempt, including failures, is one line in `runs.jsonl`: run id, stage, item, provider, model, parameters, seed, attempt, status, latency, GPU seconds, cost, list-price equivalent. Secret values are replaced before writing.

## Services are choices

`services.py` lists a service only if its key is set, it has already produced something here (from the call log) and its limit is known; `GET /api/services/<film>` calls no model. Limits come from the service when it answers (Addis AI credit, Kaggle GPU hours, Groq's response headers), otherwise they are counted from the logs. Google reports no limits, so a daily limit is known only once one of its refusals states it. Cloudflare's use is counted by us, because the token in use is not allowed to read it. A service not proven yet (OmniVoice, pictures on Kaggle) can be tried from the command line and appears once it has worked.

- Voice and picture service: per film, in the storyboard. A film uses one voice service. Changing the Google model pins finished lines to the model that made them, so only new lines change.
- New films start with Addis AI when its key is present. A true story starts with Google, because Addis AI may train on what it is sent; choosing Addis AI needs `people.addis_consent`.
- Writing model (scripts, proofreading, picture checks): per person, in `my-films/settings.json`. Groq can be chosen here only: the models it lists do not draw pictures or speak Amharic. Never called so far; tested with a stand-in.

## Decision: two keyframes per shot

Each shot has its own vertical and horizontal picture rather than one picture cropped twice. It doubles image calls but keeps faces and hands whole in both. The cost is that the two versions are not identical.

## Quality rules every film gets

| Promise | How it is kept | If it fails |
|---|---|---|
| Same characters throughout | One approved reference image per character; a locked `look` sentence added to every prompt that shows them; older versions are drawn `from` the approved one | Changing the chosen image makes exactly that character's shots stale |
| Emotion fits the moment | `emotion` per shot goes into the picture and motion prompts; `voice_emotion` into the voice style | New drafts without an emotion are rejected (`script.lint`) |
| Meaningful transitions | `transition` per shot with a reason; shots still start exactly on their beat | Default is a cut |
| Pictures are checked | `qa.py`: a vision model scores identity, emotion, content, anatomy and style; below 7 is redrawn with another seed, at most 3 tries, best kept | No vision model available: kept and marked `unchecked`, never `passed` |
| Voices | The person chooses the service and model on the Services page. Each service keeps its own files, so switching back loses nothing. A film made before that choice may still list `models.tts_fallbacks`, tried in order; the model used is stored beside the file | All exhausted: the run stops and resumes later; no half-voiced film is exported |
| Motion | Wan clip | Slow camera move on the same picture |
| Music | Chosen ACE-Step score | Placeholder made in code |

The vision check reduces bad pictures; it does not guarantee good ones. A person still approves references and looks at every shot.
