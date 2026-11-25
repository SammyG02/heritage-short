# Handoff

Written Wed 25 Nov 2026, about 18:05 EAT, for the next agent. State is as of then; re-check anything time-sensitive.

**Hard deadline: Thu 26 Nov 2026, 23:59 EAT, both submissions.** The plan aims for 21:00.

Read in this order: this file, [TODO.md](TODO.md), [PLAN.md](PLAN.md), [ARCHITECTURE.md](ARCHITECTURE.md), [FAILURES.md](FAILURES.md). TODO ticks are slightly behind; this file is newer. PLAN's schedule is the original one and we are behind it.

## 1. What this is

The 10 Academy challenge "AI-Content Generation: The Heritage Short" (B2W0). Build a 60-90 s film about a story that matters to the applicant's family, and the code pipeline that makes it. The user is the applicant.

- Brief (PDF, 23 pages): `C:\Users\samue\.t3\userdata\attachments\14dc22e5-bc95-4b58-aac2-05edd55a8388-c003621a-4937-48f8-81cc-6377bea40f43-pdf.pdf`
- The same brief as text, easier to search: `C:\Users\samue\.t3\userdata\attachments\14dc22e5-bc95-4b58-aac2-05edd55a8388-ddd658b5-ba46-40b4-b767-bcd8eafaf5b8-txt.txt`. I compared it with the PDF and found no new requirements.
- Claude Code memory: `C:\Users\samue\.claude\projects\C--Users-samue--t3-projects-tenx-ai-content-creation\memory\` (brief, rubric, stack, evidence honesty, decisions). Another kind of agent should read those files directly. The decisions file predates the build; this file supersedes it.

## 2. What the user asked for, in order

1. Read everything in the brief, make a plan and to-do list, save the important requirements to memory. **Done.**
2. Consider the platform text for anything extra. **Done, nothing new.**
3. A platform that accepts a story, offers languages (Amharic, English and others) and asks the theme. **No real people seen; invented characters.** The user would sign up for whatever is needed. **Built; gaps in section 5.**
4. Include `.gitignore` and `.env`. **Done.**
5. Asked what the Kaggle key was. Answer: `KAGGLE_API_TOKEN` is enough; `KAGGLE_KEY` and `HF_TOKEN` stay empty. Phone verification showed "Verified".
6. "Use a sample story for now, Amharic and English for now, others coming soon. Go, start building." **Done.**
7. Asked whether the assignment was finished. Answer: no, about 40% (my estimate).
8. README so anyone can understand the project, run it locally and get their own film. **Done**, except `<repository address>`.
9. This handoff.

The user's typing is informal and they want plain explanations.

## 3. Permissions and limits that came up

- The user said go and build. Local commits were made under the approved plan, which dates audience and consent before generation.
- **Publishing to GitHub is not authorised.** I asked twice to create a public repository on `SammyG02`; no answer yet. There is no remote. Work is on branch `build/heritage-short`; `master` holds only the initial commit.
- The user has not approved paid models. I did not call Nano Banana, Omni or Lyria, although the key lists them.
- The user put keys in `.env` and it must stay uncommitted. Do not print its values.
- From the brief: the public post must be written by the applicant, and an AI interview checks their understanding. So viewer feedback, consent, experiments and failures must be real. Leave blanks rather than invent them.
- From the brief: a real person shown or voiced without a consent record in ETHICS.md scores the film **zero**.
- Choices I made, not user rules: stock voice only, painted look, branch name, Lite TTS for new stories, two keyframes per shot, the sample story itself.

## 4. What exists and works

Sample film "The Extra Cup" (ትርፍ ሲኒ), 11 shots, 74.7 s, Amharic, `outputs/extra-cup/film/am/film_9x16.mp4` and `film_16x9.mp4`. Measured -14.24 LUFS, -1.46 dB true peak, 24 fps. It still uses Ken Burns moves and the **placeholder music made in code**.

Radio cuts: `outputs/extra-cup/film/am/radio_cut.mp4` (74.7 s) and `film/en/radio_cut.mp4` (77.2 s). A full English film has not been rendered.

| Checked | Result |
|---|---|
| Offline tests | 16 pass |
| Clean clone, no keys | Rebuilt both MP4s with identical SHA-256 prefixes, 0 model calls, 14 min 40 s (4 min in a later run) |
| Fresh venv from requirements.txt | Works, about 1 minute |
| FFmpeg not on PATH | Bundled copy works |
| Story intake | Drafted a valid bilingual storyboard (`storyboards/the-half-blanket-11251645.json`), called from code |
| Web page | Form, review, approve, build, play: works using the cached sample. Rejects foreign Origin/Host and path traversal |
| `start.bat` | First and second run work, tested with Notepad, browser and pause removed |
| Secrets | No key value found in the working files outside `.env`; an earlier scan of Git history was also clean. Rescan before publishing |

Last commit before this file: `b8d1a4b`. `runs.jsonl` has 100 lines. Clean working tree then; no background jobs or servers running.

## 5. Not tested or known wrong

- **Wan video has never worked.** The first job (s01 vertical) ran out of memory on a T4 before step 1. See FAILURES.md for the layout and untried ideas. Worker: `pipeline/kaggle_jobs/wan_worker.py`. Simplest first try: encode the first frame with the VAE, then free it from GPU 0 before loading the transformer, or keep the only VAE on GPU 1. The pipeline class runs both on one device, so this needs code. Test one clip before all 22.
- **ACE-Step worked**: `outputs/extra-cup/music/score_101.wav`, `_202`, `_303` (90 s each). Nobody has listened. `chosen_seed` is 101 only by default, with reason "Not chosen yet". The next `film` run will use 101 automatically.
- **GPU seconds in runs.jsonl double count:** `loaded` and `done` rows are job totals that include the clip rows. Do not simply sum `gpu_s`.
- A brand-new story through to a finished film has not been run. Nor have Mac, Linux, `film --gpu`, or the interactive `new` prompts.
- **The Amharic was written by an agent** and no native speaker has checked text or audio.
- The grandmother and coffee-set references (seed 33 each) were chosen by the agent and await approval.
- Picture flaws seen: wide s01 has a fake signature; s11 has grass indoors; wide s10 has the hand on the pot, not the cup. Image contact sheets were inspected by the agent.
- Radio cut and audio have only been measured, not heard.
- COSTS.md prices two models at another model's rate (stated there) and has no GPU price. Its FLUX neuron figure is an estimate.
- EXPERIMENTS.md has 5 of at least 10. Entries 2, 4 and 5 changed more than one thing and say so.
- ETHICS.md says the story is an invented sample. Update it if the story changes.
- Git history holds about 161 MB and `outputs/` is 254 MB. No file seen is over GitHub's 100 MB limit (largest are about 30 MB), but check before pushing.
- `HANDOFF.md`, `PLAN.md` and `TODO.md` would become public with the repository. Decide with the user. HANDOFF.md contains local paths.

## 6. Limits found

| Service | Finding |
|---|---|
| Gemini 3.8 Flash TTS | Error said 10 requests a day; 12 succeeded first. At 16:41 EAT it said retry in 18h18m, about 11:00 Thursday |
| Gemini 3.8 Flash Lite TTS | 11 English lines succeeded today; limit unknown. Set per language with `voices.<lang>.model` |
| Gemini 3.8 Flash text | 503 overloaded twice; falls back to 3.6, then 3.5 Lite |
| Cloudflare FLUX | 10,000 neurons a day, resets 03:00 EAT; about 85% used today by estimate. A new 9-11 shot film needs roughly 4,000 |
| Kaggle | 30 GPU hours a week, unused at the start; today's jobs waited over an hour in the queue |

Amharic line changes before 11:00 Thursday need the Lite model. Adding `voices.am.model` makes **all 11** Amharic lines stale, so decide deliberately.

## 7. What is left

**Waiting on the user (asked, not answered)**
1. Keep this story, and say why it matters to their family, or send their own. Everything else depends on it.
2. Check the Amharic; approve the look; choose one of the three scores with a reason.
3. User test 1: play the Amharic radio cut to at least three people and collect their words. The plan had this for tonight.
4. Permission for a public GitHub repository.
5. Whether 10 Academy gave a frontier key; where videos will be hosted; whether the submission forms ask for anything extra.

**Agent work**
1. Fix Wan's memory use and test one clip.
2. Apply test 1 to the storyboard (bump `version`) and record it in DESIGN.md.
3. Rebuild with the chosen score; fix the flawed keyframes after 03:00.
4. At least five more real experiments: Ken Burns against Wan, 480p time, score candidates, ducking, one-pass against two-pass loudness, style against voice.
5. Near-final cut, then user test 2 (three people), recorded and applied.
6. Ceiling: have a non-coder use the web page and record where they get stuck.
7. Report (30 points of assignment 1, not started): what and for whom, what the audience said, hardest problem, one suggested practice that beat instinct and one that did not, ceiling, what next. A candidate for "did not", with evidence in experiment 5: attaching the reference sheet to every keyframe.
8. Refresh README, COSTS, TODO; secret scan; clean-clone run; publish once allowed; put the real address in the README.
9. Rehearse the live demo: edit one narration line, run `status`, then `film`, show the single new line in `runs.jsonl`. It spends one TTS call.

**User only:** write and publish the post with the AI label on; record the walkthrough (5 minutes at most: architecture, one hard decision, one shot regenerated); check links while logged out; submit both assignments; AI interview.

**Grading.** A1: engineering 20, documentation 10, design 10, experiments 10, troubleshooting 10, measurement 5, consent 5, report 30 (three parts of 10). A2: film 50, walkthrough 30, post 20.

## 8. Running it

```powershell
cd C:\Users\samue\.t3\projects\tenx-ai-content-creation
.venv\Scripts\python -m pipeline status      # what is stale; calls no model
.venv\Scripts\python -m pipeline film        # build
.venv\Scripts\python -m pipeline web         # http://localhost:8765, or double-click start.bat
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pipeline gpu submit wan --ratio 9x16 --shot s01
.venv\Scripts\python -m pipeline gpu status wan
.venv\Scripts\python -m pipeline gpu fetch wan
```

Kaggle jobs are private: `heritage-short-wan`, `heritage-short-music`, dataset `heritage-short-jobs`. Submitting again pushes a new version and overwrites `outputs/extra-cup/jobs/wan.json`, so fetch first.

Long scripts sent through the Bash tool here failed with a quoting error. Write files with the file tool instead. The laptop has 8 GB of memory and no NVIDIA GPU.

## 9. Suggested first message to the next agent

> Read HANDOFF.md, then TODO.md and FAILURES.md. Tell me what you need from me, and start by fixing the Wan out-of-memory problem with a one-clip test.
