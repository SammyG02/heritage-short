# Failures

What broke, what was tried, what fixed it. Times are EAT, 25 Nov 2026.

## Gemini 3.8 Flash overloaded (15:58 and 16:41)
- **Broke:** HTTP 503 "experiencing high demand" in the smoke test and again drafting a storyboard; one attempt ran 171 s before failing and another timed out at 180 s.
- **Tried:** three attempts with backoff, as built. All failed both times.
- **Fixed:** the script stage falls through to gemini-3.6-flash, then gemini-3.5-flash-lite. 3.6 succeeded in 38 s.

## Gemini TTS daily quota (16:41)
- **Broke:** HTTP 429, "10 requests per day on Free Tier", on the first English line after 12 successful calls. An 11-shot film in one language uses a full day's allowance.
- **Tried:** nothing on the same model; the code recognises a daily limit and does not waste retries on it.
- **Worked around:** a storyboard can set a TTS model per language. English uses gemini-3.8-flash-lite-tts, which completed all 11 lines.
- **Cost:** the two languages are not voiced by the same model, so they are not a fair quality comparison.

## All free TTS allowances used in one day (19:38 to 19:42)
- **Broke:** the new story's Amharic needed 14 calls (one per speaker turn). 3.8 Flash TTS was already used up; 3.8 Flash Lite TTS allowed one more line and then reported its own limit of 10 a day.
- **Tried:** gemini-3.1-flash-tts-preview (through generateContent, which returns raw PCM): 11 calls succeeded, then 429, "limit: 10" a day; also 3 a minute, which the retry waited out. gemini-2.5-flash-preview-tts reported its limit of 10 already exceeded although `runs.jsonl` has no earlier call to it, cause unknown. gemini-2.5-pro-preview-tts has a free limit of 0.
- **State:** 10 of 12 lines voiced (s01 by 3.8 Lite, s02 to s10 by 3.1). s11 and s12 wait for the reset, about 11:00 on 26 Nov. `radio --partial` shows them as text so the user test is not blocked.
- **Lesson:** 11 English test lines for the sample story cost the allowance the real film needed. Test on one line, not a whole film.

## TTS moved to a different API
- **Found:** gemini-3.8-flash-tts is documented on the Interactions API, not `generateContent`, and the documentation moved from ai.google.dev to aistudio.google.com.
- **Fixed:** built directly on Interactions. It returns a complete WAV file.

## Kaggle command-line tool would not start
- **Broke:** `ModuleNotFoundError: No module named 'six'` from a clean install of kaggle 2.2.5.
- **Fixed:** `six` added to requirements.txt.

## FFmpeg installed but not found
- **Broke:** winget reported FFmpeg installed, but it was not on PATH in the open shell.
- **Fixed:** `config.ffmpeg()` looks on PATH, then the winget folder, then falls back to the copy in the imageio-ffmpeg package.

## Truncated font
- **Broke:** the font download stopped at exactly 524,288 bytes of 1,143,168.
- **Noticed:** the suspiciously round size.
- **Fixed:** downloaded again and opened it with Pillow before use.

## Network drops
- **Broke:** one SSL end-of-file error during English line s04 (and one interrupted pip download).
- **Fixed:** the stage's retry succeeded on attempt 2.

## Culturally wrong objects
- **Broke:** all four first coffee pots were teapots. See experiment 3.
- **Still open:** wide s01 contains a fake signature; grass appears indoors in s11; wide s10 shows the hand on the pot instead of the cup. Waiting for the Cloudflare allowance to reset at 03:00.

## A network error mistaken for a failed GPU job (16:58 and 17:04)
- **Broke:** the watcher stopped, reporting Kaggle jobs as failed. Both were still queued.
- **Cause:** `status` searched the whole command output for the word "error", so a connection message matched.
- **Fixed:** only Kaggle's own status word is read; anything else is "unknown" and polling continues. A test covers it. `film --gpu` also stops waiting after four hours and uses the fallbacks.

## Kaggle GPU queue
- **Broke:** both T4 jobs were still queued about 45 minutes after submission, with 0 of 30 GPU hours used.
- **Worked around:** the film is already complete with Ken Burns moves and a placeholder score; clips replace them when they arrive.

## Wan 2.2 out of memory on a T4 (17:53)
- **Broke:** the first Wan job (one clip, s01 vertical, 480x832, 121 frames) failed before the first step: `CUDA out of memory`, 13.93 GiB allocated by PyTorch on GPU 0 of 14.56 GiB. Loading had taken 309 s.
- **Layout at the time:** fp16 transformer and a float32 VAE both on GPU 0; a second float32 VAE on GPU 1 for decoding.
- **Not tried yet:** moving the encoding VAE off GPU 0 or encoding first and freeing it, fewer frames, CPU or group offload, a quantised transformer, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.
- **Tried, 18:45:** the VAE (encoding and decoding) moved to GPU 1 so the transformer has GPU 0 alone, plus `expandable_segments:True`. Both were changed at once, so which one mattered is not separated.
- **Fixed:** two clips completed (19:35): peak 12.5 GB, 832 and 827 s denoising, 1,175 and 1,171 s in total each.
- **New limit:** about 20 GPU minutes per 5 s clip at 480p, so 24 clips is roughly 8 hours in one session.

## A Wan clip that broke the body (19:35)
- **Broke:** in `s03_9x16` the woman's head folds backwards until her face is hidden, and the camera moves although the prompt asked for a fixed one.
- **Likely cause, not isolated:** several actions in one prompt (lift head, breathe, move arms and hands, pour). The single-face clip in the same job held together.
- **Response:** "One Percent" motion prompts cut to one small movement each, to be tested.
- **Queue:** both jobs started at 17:47, a little over an hour after submission.

## Ten defects that 70 passing tests missed (code review, 23:00)
- **Found:** a review of the code, not a test or a run. Among them: redrawing one format made the other format's approved picture out of date; the one-call voice asked for long pauses inside lines as well as between them; an approval survived a new, unheard recording; changing a face left its older version with the old face; a saved picture could be overwritten; the proofreader and the drafting of a true story did not wait for consent.
- **Tried:** 21 tests written first. 15 failed before the fixes; the others guard behaviour that had to stay.
- **Fixed:** all ten. Cache keys and cached items of four storyboards (306 items, 132 cached) were the same before and after, so no finished work has to be made again.
- **Lesson:** the earlier tests checked each feature alone. The defects were where two features meet.

## The older mother became a different person (23:29)
- **Broke:** both options drawn from the approved young face came back with much paler skin, deep wrinkles and grey hair, about 75 instead of 50. The father, from the same kind of prompt, kept his skin tone.
- **Likely cause, not isolated:** "in her fifties", "silver hairs" and "smile lines" together.
- **Changed:** the prompt names the skin tone and face first and asks for one small change. New drafts get the same wording from code, and older versions are made only when the script shows one. Not redrawn yet: the daily picture allowance was used up (about 10,100 of 10,000 by our estimate).

## Our own story was inside the tool
- **Found by the applicant:** a new film copied its defaults (voice style, music and video settings) from this repository's storyboard, and new stories and their call logs were saved inside the repository.
- **Fixed:** neutral `pipeline/defaults.json`; personal films and logs in `my-films/`, ignored by Git. A test searches the code for words of our story.

## Addis AI refused every line, and our test said it worked (26 Nov, 01:22)
- **Broke:** the first real call (one neutral word) came back `HTTP 422 CLIENT_REQUEST_ID_REQUIRED`. The code had only ever been tested with a stand-in for the service, which accepted anything.
- **Fixed:** each line now sends one id, the same on every retry, so a retry cannot be charged twice. The second call returned real audio and cost 0.04 Birr.
- **Lesson:** the studio now offers a service only after it has really produced something.

## 26 November 2026 (times EAT)

### Cloudflare said "used up" while the studio showed 98% left (08:22)
- **Broke:** a picture was refused with "you have used up your daily free allocation of 10,000 neurons". The studio counted from midnight UTC; Cloudflare counts the last 24 hours (experiment 11).
- **Tried:** the applicant created a second Cloudflare account and a new Gemini key to carry on drawing that morning. The studio still showed the old account's usage, because it counted every call in one log.
- **Fixed:** the studio counts a rolling 24 hours, believes the service's own refusal, and counts each account separately (each call records a short one-way fingerprint of the account, never the key).

### Cloudflare's safety filter blocked a harmless picture (08:12)
- **Broke:** one of two "older mother" faces came back HTTP 400 "Your output has been flagged". The other, with the same words and another seed, was fine.
- **Fixed:** a blocked picture is tried again with another seed, up to three times; only then does the studio ask for different words.

### The picture checker waited on an overloaded model (09:00 to 10:00)
- **Broke:** drawing 11 pictures took over 30 minutes; most of it was the check waiting on gemini-3.8-flash (40 of 41 checks failed). The status line said "Google is busy", and the applicant stopped a run that was working.
- **Fixed:** 3.6 Flash is asked first (experiment 12), and the status line now shows progress ("Picture 4 of 11") and says a slow check is normal.

### The one-call voice recording could not be cut (09:53)
- **Broke:** one recording of three lines was refused by the cutter, so the same three lines were made again one by one: four calls of the day's ten, not one.
- **Fixed:** the cutter also uses each line's length when pauses tie (experiment 15). The paid recording was kept and used to test the fix.

### WaveSpeed: refused clips, an unexplained charge, and a page left open (14:50 to 15:45)
- **Broke:** four clips were sent at once; WaveSpeed refused two ("Concurrency limit reached. Your plan allows up to 2 running"). The balance fell by $0.26 for two clips listed at $0.13 (experiment 14). And a page opened before the shots were switched to WaveSpeed still said "Animate 2 shots"; pressing it animated everything the server held, not the two shown.
- **Fixed:** at most two at once, and a refused submit (never created, never charged) waits and is sent again. The real balance is read before every batch. Paid clips are made one named shot at a time, after a confirmation that shows the price; the server refuses anything else.

### A budget check that blocked every edit (15:50)
- **Broke:** with every shot set to WaveSpeed, the planned total ($1.26) passed the money left ($0.74), and the check refused any edit to any shot, even "Redraw" or switching a shot back to the free GPU.
- **Fixed:** only a change that adds paid clips past the money left is refused. A test covers redraw, switching away, and adding.

### Kaggle did not answer after an upload (16:00)
- **Broke:** sending one clip to Kaggle failed: the upload finished, then "Connection to api.kaggle.com timed out" when creating the dataset version. Nothing had started on Kaggle.
- **Fixed:** Kaggle commands are tried again after 20 and 40 s on a connection error, and a final failure says in plain words that nothing was started.

### Pictures that were wrong and nearly shipped
- **Broke:** the baby's fingers in shot 7 were wrong, and the applicant missed it; a viewer in user test 2 said a picture felt off. Shot 11 showed four children where the story has three. The "older mother" came out about 60 rather than about 40.
- **Fixed:** shot 7 redrawn and its description rewritten (15:22 to 15:30). The studio gained ways to fix the rest without touching other shots: edit or add a character (so the siblings can be fixed characters), more faces to choose from, and a downloadable draft of the whole film to watch before building it.

### The services page reloaded itself without end (about 08:45)
- **Broke:** with room left on the new account, the picture "reset" time was "now", so every 20-second check looked like a reset that had just passed and reloaded the page.
- **Fixed:** the reset time is always in the future, and a countdown can reload the page only once.
