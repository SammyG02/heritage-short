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

## Decision: two keyframes per shot

Each shot has its own vertical and horizontal picture rather than one picture cropped twice. It doubles image calls but keeps faces and hands whole in both. The cost is that the two versions are not identical.
