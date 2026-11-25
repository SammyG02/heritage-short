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
- **Worked around for now:** Ken Burns.
- **Queue:** both jobs started at 17:47, a little over an hour after submission.
