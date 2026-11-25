# To do

**(You)** needs the applicant personally. Claude can build the rest with your review.
Rubric: A1 = codebase and report (100). A2 = film 50, walkthrough 30, post 20.

## 0. Unblock (Wednesday afternoon)
- [ ] (You) Choose the story, whose it is, and the narration language
- [ ] (You) Choose the audience and one ending feeling
- [x] (You) Decided: invented characters only, no real people shown
- [ ] Confirm stock TTS voice only and story does not identify a real person; otherwise get consent
- [ ] (You) Line up five testers for tonight and tomorrow afternoon
- [ ] (You) Gemini API key
- [ ] (You) Cloudflare account ID and Workers AI token
- [ ] (You) Phone-verified Kaggle account and API token
- [ ] (You) Confirm whether the frontier lane is available
- [ ] (You) Choose where the MP4s, walkthrough and post will be hosted
- [ ] Install FFmpeg; Python environment with pinned dependencies
- [ ] .gitignore, .env.example; verify live model names, limits and licences
- [ ] Smoke test each provider, logged to runs.jsonl

## 1. Story and radio cut
- [ ] DESIGN.md audience and intent, committed before generation
- [ ] ETHICS.md consent record, committed before generation
- [ ] JSON Schema and validator
- [ ] Shared core: hash cache, retries, logger, atomic writes, tests
- [ ] Story intake command: story, language, theme, audience, feeling -> draft storyboard
- [ ] storyboard.json v1: 8-12 shots, each with a reason
- [ ] (You) Edit and approve the script; check language and facts
- [ ] Narration per shot; measure durations; total film 60-90 s
- [ ] (You) Listen for pronunciation errors
- [ ] Radio cut with placeholder music
- [ ] (You) Test 1 with at least three people; collect their actual words
- [ ] Record test 1; commit storyboard v2 with visible changes

## 2. Pictures and music
- [ ] Reference candidates and style block; (You) approve the golden reference
- [ ] Keyframes for every shot; check faces, hands, cultural and period details
- [ ] Ken Burns for every shot (complete fallback film)
- [ ] Kaggle Wan worker, resumable; overnight batch at 480p
- [ ] Spotting list; three ACE-Step candidates; (You) choose with a reason
- [ ] Rough cut
- [ ] EXPERIMENTS.md and FAILURES.md kept current

## 3. Edit
- [ ] Cut to the music, duck, subtitles, loudness, end card, both exports
- [ ] Automatic check: 60-90 s, dimensions, 24 fps, about -14 LUFS, peak at or below -1 dB
- [ ] (You) Check on a phone speaker and headphones
- [ ] (You) Test 2 with at least three people
- [ ] Record test 2; apply changes; re-export
- [ ] Ceiling: story web form (if on schedule), tried by a non-coder

## 4. Documents and reproducibility
- [ ] README, ARCHITECTURE, COSTS
- [ ] At least ten real experiments; real failures; licence table complete
- [ ] Every model call in runs.jsonl
- [ ] Report: what and for whom, audience learning, hardest problem, practice that helped, practice that did not, ceiling, next
- [ ] (You) Revise the report in your own voice
- [ ] Secret scan including git history
- [ ] Fresh-clone run; edit one shot and prove only its dependents regenerate

## 5. Release and submit (target Thu 21:00, hard limit 23:59 EAT)
- [ ] Public GitHub repository
- [ ] Upload both MP4s
- [ ] (You) Write and publish the post with the AI label on
- [ ] (You) Record walkthrough, at most five minutes
- [ ] Open every link logged out
- [ ] (You) Submit Assignment 1: repository and report
- [ ] (You) Submit Assignment 2: vertical MP4, plus horizontal, walkthrough and post attachments
- [ ] (You) Reread logs and notes; take the AI interview
