# Heritage Short

**Tell a story in a few sentences. Get back a short animated film.**

You write a story and choose a language and a theme. The program writes a storyboard for you to check, then makes the pictures and the voice, adds music and English subtitles, and gives you a 60-90 second video in two shapes: vertical for phones and wide for TV or YouTube.

It runs on your own computer, needs no graphics card, and uses free services.

> **Status:** work in progress. The included film, *The Extra Cup* (ትርፍ ሲኒ), is an invented sample. AI video clips and AI music depend on Kaggle and have not completed a run yet; until then films use gently moving paintings and simple music made in code.

**Contents:** [What happens](#what-happens) · [Install](#1-install) · [See the sample](#2-see-the-sample-film-no-keys-needed) · [Get keys](#3-get-your-free-keys) · [Make your film](#4-make-your-own-film) · [Change it](#5-change-something) · [Problems](#if-something-goes-wrong) · [For developers](#for-developers)

## What happens

```text
Your story
   |  an AI writes a plan of 9-11 shots
   v
Storyboard   <-- you read it, fix the words, and approve it
   |
   +-- voice      one recording per shot
   +-- pictures   painted from the plan, with the same character throughout
   +-- movement   a slow camera move on each picture (or an AI video clip)
   +-- music      lowered automatically while the voice speaks
   v
Finished film   vertical + wide, English subtitles, "made with AI" end card
```

Everything about a film is kept in one file, its **storyboard**. Change one line there, run again, and only that part is made again.

## 1. Install

You need:

- **Python 3.11 or newer**: [python.org/downloads](https://www.python.org/downloads/). On Windows, tick "Add Python to PATH". (Developed and tested on Python 3.14, Windows 11.)
- **Git**: [git-scm.com](https://git-scm.com/downloads). Or use GitHub's green **Code** button, **Download ZIP**, and unzip it.
- About 2 GB of free disk space.

You do **not** need to install FFmpeg. If you have it, it is used; if not, a copy is installed with the other packages.

Open a terminal (Windows: PowerShell. Mac or Linux: Terminal) and download the project, using the address on its GitHub page:

```bash
git clone <repository address>
cd <the folder it created>
```

Then install its packages.

**Windows**

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

**Mac or Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

From here on, commands are written for Windows. On Mac or Linux, type `.venv/bin/python` instead of `.venv\Scripts\python`.

## 2. See the sample film (no keys needed)

```powershell
.venv\Scripts\python -m pipeline film
```

This rebuilds the sample from the saved pictures and voices, without calling any AI service. It took 4 to 15 minutes on an 8 GB laptop. The videos appear here:

```text
outputs/extra-cup/film/am/film_9x16.mp4    vertical
outputs/extra-cup/film/am/film_16x9.mp4    wide
```

## 3. Get your free keys

A key is a password that lets the program use a service. Two services are needed. No payment card is required.

| Service | Used for | How to get it |
|---|---|---|
| **Google Gemini** | Storyboard and voice | Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in, create an API key, copy it |
| **Cloudflare** | Pictures | Sign up at [dash.cloudflare.com](https://dash.cloudflare.com). Open **Workers AI** and choose its REST API option. Create a Workers AI API token, and copy the **token** and the **account ID** |
| **Kaggle** (optional) | AI video and AI music | Sign up at [kaggle.com](https://www.kaggle.com), verify your phone in **Settings**, then create a token in the **API Tokens** tab |

Copy the file `.env.example` and name the copy `.env`:

```powershell
copy .env.example .env
```

(Mac or Linux: `cp .env.example .env`.) Open `.env` in any text editor and paste each key straight after its `=`, with no spaces or quotes:

```text
GEMINI_API_KEY=paste_here
CLOUDFLARE_ACCOUNT_ID=paste_here
CLOUDFLARE_API_TOKEN=paste_here
```

Git ignores `.env`, so it is not uploaded. **Never share it or show it in a screenshot or video.** If a key leaks, delete it on the service's website and make a new one.

Check that the keys work:

```powershell
.venv\Scripts\python -m pipeline smoke
```

You want `ok` beside Gemini text, Gemini TTS and Cloudflare. `FAIL kaggle` is fine if you did not set it up. Each check makes one real call and counts toward your daily allowance.

## 4. Make your own film

### The easy way: in your browser

**Windows:** double-click **`start.bat`**. **Mac or Linux:** run `./start.sh`. These also do steps 1 and 3 for you, up to pasting the keys. On Mac or Linux, then open <http://localhost:8765>.

Or start it yourself and open <http://localhost:8765>:

```powershell
.venv\Scripts\python -m pipeline web
```

1. **Tell your story** in a few sentences. Choose Amharic or English, a theme, who it is for, and how they should feel at the end.
2. **Draft.** Wait for the storyboard. This can take a few minutes when Google is busy.
3. **Check every line** and change words that sound wrong. Check the Amharic especially. Pictures and voice are only made after you approve.
4. **Approve and make the film.** The page shows progress. Expect 15 to 30 minutes or more, depending on your computer and connection.
5. **Watch it** on the page. The files are in `outputs/<film name>/film/<language>/`.

Leave the terminal window open while it works. The page is only reachable from your own computer.

### In the terminal

```powershell
.venv\Scripts\python -m pipeline new
```

It asks the same questions, saves a draft in `storyboards/`, and prints its name. Open and edit that file, then:

```powershell
.venv\Scripts\python -m pipeline -s storyboards\your-story.json film
```

### Before you press approve

- **Leave out real names and private details.** Your text goes to free AI services, and Google says it may use free-tier text to improve its products.
- **Invented characters only.** The program has no way to upload photos or voices. If your story points to a real living person, ask their permission first.
- **You are publishing AI content.** Keep the end card, and switch on the AI label where you post it.

## 5. Change something

Open your storyboard file, change it, and run the same `film` command again. To see first what would be remade:

```powershell
.venv\Scripts\python -m pipeline -s storyboards\your-story.json status
```

| To change | Edit | What is made again |
|---|---|---|
| What the voice says | `narration` in that shot | One voice recording. English is also the subtitle text |
| A picture | `image_prompt` in that shot | That shot's two pictures |
| Try another version of a picture | `seed` in that shot | That shot's two pictures |
| How the character looks | `chosen_seed` under `references` (look in `outputs/<name>/references/` first) | Every picture of that character |
| The camera move | `ken_burns`: in, out, left, right, up, down | No AI calls |

Picture tip: describe what **is** there. Writing "no cross" put crosses in our pictures.

### Optional: AI video and music

With Kaggle set up, add `--gpu`:

```powershell
.venv\Scripts\python -m pipeline -s storyboards\your-story.json film --gpu
```

Kaggle's free queue can be long. The program waits up to four hours for each job, then finishes with the moving paintings and simple music. Run it again later to pick up what is ready:

```powershell
.venv\Scripts\python -m pipeline -s storyboards\your-story.json gpu fetch wan
.venv\Scripts\python -m pipeline -s storyboards\your-story.json gpu fetch music
.venv\Scripts\python -m pipeline -s storyboards\your-story.json film
```

## What it costs

Nothing, within free limits. We spent $0. What we found on 25 November 2026:

| Service | Free limit | Roughly enough for |
|---|---|---|
| Gemini voice, main model | 10 a day | Less than one 11-shot film |
| Gemini voice, Lite model (used for new stories) | Not published to us; 11 in one run worked | At least one film a day |
| Cloudflare pictures | 10,000 neurons a day, resets 00:00 UTC | About two films a day (estimate) |
| Kaggle | 30 GPU hours a week | Not measured yet |

Details: [COSTS.md](COSTS.md).

## If something goes wrong

Nothing already made is lost. Fix the cause and run the same command again; it continues where it stopped.

| You see | Do this |
|---|---|
| `python` is not recognized | Reinstall Python and tick "Add Python to PATH", then open a new terminal |
| `No module named pipeline` | Run the command from inside the project folder |
| `GEMINI_API_KEY is not set` | Check that the file is named `.env` (not `.env.txt`) and the key is pasted and saved |
| `HTTP 401` or `403` | The key is wrong or lacks permission. Make a new one |
| `HTTP 429` ... per day | Today's free allowance is used. Run again tomorrow |
| `HTTP 503` high demand | The service is busy. The program already retried; wait and run again |
| `Storyboard is not valid` | Read the lines below it; each names the part to fix |
| `The film would be ... s` | Must be 60-90 s. Shorten the narration if too long, raise `duration_s` if too short |
| Port 8765 already in use | The page is already running in another window. Close that one |
| Kaggle stays `queued` | Normal on the free tier. Run without `--gpu` |

## Languages

Narration in Amharic and English. Afaan Oromo, Tigrinya and Somali are coming soon. Subtitles are always English.

## For developers

| Command (after `python -m pipeline`) | Does |
|---|---|
| `film [--gpu]` | Every stage, both formats. `make film` does the same with whichever `python` is active |
| `-l en film` | English narration instead of the main language |
| `-s FILE ...` | Use another storyboard |
| `new`, `web` | Draft a storyboard |
| `validate`, `status` | Check the storyboard; show what is stale |
| `narration`, `references`, `keyframes`, `radio` | One stage |
| `gpu submit\|status\|fetch wan\|music` | Kaggle jobs |
| `smoke` | Call each provider once |

Run the offline tests with `.venv\Scripts\python -m pytest`.

| Path | Contents |
|---|---|
| `storyboard.json` | The film's contract; all stages read only this |
| `storyboards/` | Drafts made from your stories |
| `schema/` | Storyboard rules, checked before every run |
| `pipeline/` | One file per stage; shared code in `core/`, GPU workers in `kaggle_jobs/` |
| `outputs/` | Everything generated, with a record of the inputs |
| `runs.jsonl` | One line per AI call, including failures |

More: [DESIGN](DESIGN.md) (audience), [ARCHITECTURE](ARCHITECTURE.md), [EXPERIMENTS](EXPERIMENTS.md), [FAILURES](FAILURES.md), [COSTS](COSTS.md), [ETHICS](ETHICS.md).
