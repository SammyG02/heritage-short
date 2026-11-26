# Heritage Short

**Tell a story in a few sentences. Get back a short animated film.**

You write a story and choose a language and a theme. The program writes a storyboard for you to check, then makes the pictures and the voice, adds music and English subtitles, and gives you a 60-90 second video in two shapes: vertical for phones and wide for TV or YouTube.

It runs on your own computer, needs no graphics card, and uses free services. One optional service is paid.

> **The film in this repository** is *One Percent* (አንድ በመቶ), the author's true family story, told in Amharic with English subtitles: 12 shots, 88.8 seconds, vertical 1080x1920 and wide 1920x1080, -14.2 LUFS. Three shots are moving clips (Wan 2.2), chosen where movement matters; nine are slow camera moves over painted pictures, the fallback the brief suggests when GPU time runs short. The wide version is the vertical film over a blurred copy of itself, so both shapes show exactly the same frames and no picture or clip was paid for twice ([why](ARCHITECTURE.md#one-film-two-shapes)). The score is one of three ACE-Step candidates, chosen by ear. Every face is invented; the family's consent is in [ETHICS.md](ETHICS.md). An earlier invented film, *The Extra Cup*, is in `outputs/extra-cup/`.

**Contents:** [What happens](#what-happens) · [Install](#1-install) · [Rebuild the film](#2-rebuild-the-film-no-keys-needed) · [Get keys](#3-get-your-free-keys) · [Make your film](#4-make-your-own-film) · [Change it](#5-change-something) · [Costs](#what-it-costs) · [Problems](#if-something-goes-wrong) · [For developers](#for-developers)

## What happens

```text
Your story (and, for a true story, who agreed to what)
   |  an AI writes a plan of 8-12 shots
   v
Storyboard   <-- you read it, fix the words, and approve it
   |
   +-- voice      one recording per shot (Gemini; Addis AI optional)
   +-- cast       a face for each character, chosen by you, used in every shot
   +-- pictures   one per shot, checked automatically, approved by you
   +-- movement   a slow camera move, or an AI video clip for the shots you choose
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

Open a terminal (Windows: PowerShell. Mac or Linux: Terminal) and download the project:

```bash
git clone https://github.com/SammyG02/heritage-short.git
cd heritage-short
```

It is about 240 MB, because the film's pictures, voices, clips and score are kept in it so that it can be rebuilt without any AI call.

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

## 2. Rebuild the film (no keys needed)

```powershell
.venv\Scripts\python -m pipeline film
```

(`make film` does the same.) This rebuilds *One Percent* from `storyboard.json` and the saved pictures, voices, clips and score, **without calling any AI service**: every one of them is in the repository with a record of the inputs that made it. On our 8 GB laptop a fresh clone with no keys did it in about 7 minutes, and both videos were byte-for-byte the same as the originals. The videos appear here:

```text
outputs/one-percent/film/am/film_9x16.mp4    vertical
outputs/one-percent/film/am/film_16x9.mp4    wide
outputs/one-percent/film/am/report.json      length, size, loudness, and any problem found
```

## 3. Get your free keys

A key is a password that lets the program use a service. Two are needed to make a new film. No payment card is required.

| Service | Used for | How to get it |
|---|---|---|
| **Google Gemini** | Storyboard, voice, picture checks | Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in, create an API key, copy it |
| **Cloudflare** | Pictures | Sign up at [dash.cloudflare.com](https://dash.cloudflare.com). Open **Workers AI** and choose its REST API option. Create a Workers AI API token, and copy the **token** and the **account ID** |
| **Kaggle** (optional, free) | AI video clips and AI music on a free GPU | Sign up at [kaggle.com](https://www.kaggle.com), verify your phone in **Settings**, then create a token in the **API Tokens** tab |
| **WaveSpeed** (optional, **paid**) | AI video clips in about a minute instead of twenty | [wavespeed.ai](https://wavespeed.ai), add credit, create an API key. About $0.05 to $0.16 a clip |
| **Addis AI** (optional, paid in Birr) | Another Amharic and English voice | [addisassistant.com](https://addisassistant.com) |
| **Groq** (optional, free) | Another model for writing and picture checks | [console.groq.com](https://console.groq.com) |

Copy the file `.env.example` and name the copy `.env`:

```powershell
copy .env.example .env
```

(Mac or Linux: `cp .env.example .env`.) Open `.env` in any text editor and paste each key straight after its `=`, with no spaces or quotes. Leave the optional ones empty if you do not use them: a service without its key is simply not offered.

Git ignores `.env`, so it is not uploaded. **Never share it or show it in a screenshot or video.** If a key leaks, delete it on the service's website and make a new one.

Check that the keys work:

```powershell
.venv\Scripts\python -m pipeline smoke
```

You want `ok` beside Gemini text, Gemini TTS and Cloudflare. Each check makes one real call and counts toward your daily allowance.

## 4. Make your own film

### The easy way: in your browser

**Windows:** double-click **`start.bat`**. **Mac or Linux:** run `./start.sh`. These also do steps 1 and 3 for you, up to pasting the keys. On Mac or Linux, then open <http://localhost:8765>.

Or start it yourself and open <http://localhost:8765>:

```powershell
.venv\Scripts\python -m pipeline web
```

The studio opens on your films. Press **New film**, write your story, choose the language, narrator and theme. If it really happened to real people, tick that box: you then record **who agreed, person by person** (their story told, drawn as a character, their words quoted, their photo used; when and how), and **which AI services** they agreed to. Nothing is sent anywhere until that is filled in, and a service left unticked is never called.

Each film then has five tabs:

1. **Story:** your story, and the consent record. Add to it or withdraw it at any time; withdrawing locks the film.
2. **Script:** read and change every line, hear each voice, approve it.
3. **Cast:** two faces for each character; choose one, ask for more, edit a character's description, add or remove one. A face is invented from text, or, only with that person's recorded yes, drawn from a photo.
4. **Shots:** draw, check, redraw and approve each picture. Under **Motion**, choose for each shot: a free camera move, a clip from the free Kaggle GPU, or a paid WaveSpeed clip. Watch each clip, approve it or animate it again.
5. **Film:** play a quick preview, **download a draft video** of what exists now (about two minutes, free), and **build the final film** once everything is approved.

**Services** (top right) shows every voice, picture, motion and writing service, what is left of each free limit and when it comes back, and lets you choose. A progress bar shows what each job is doing and roughly how long is left. Nothing runs until you press a button, and any button that uses a free limit or money says how much first.

**Your films are yours.** Every story you make, with its characters, pictures, voices, music and call log, is saved in `my-films/` on your computer (or the folder named by `HERITAGE_FILMS`). Git ignores it. The film in `storyboard.json` belongs to this repository's author; the studio shows it only if `SHOW_REPO_FILM=1` is in `.env`.

Press **Stop** at any time; finished parts are kept. Leave the terminal window open while it works. The page is only reachable from your own computer.

### In the terminal

```powershell
.venv\Scripts\python -m pipeline new
```

It asks the same questions, saves a draft in `storyboards/`, and prints its name. Open and edit that file, then:

```powershell
.venv\Scripts\python -m pipeline -s storyboards\your-story.json film
```

### Before you start

- **Leave out real names and private details.** Your text goes to AI services, and free tiers may use it to improve their products.
- **Real people need their own yes.** For a true story, ask each person first, in person or by phone, and record what they agreed to. Faces are invented unless a person agreed to their photo being used; the photo stays on your computer and out of Git.
- **You are publishing AI content.** Keep the end card, and switch on the AI label where you post it.

## 5. Change something

Open your storyboard file, change it, and run the same `film` command again. To see first what would be remade:

```powershell
.venv\Scripts\python -m pipeline status
```

| To change | Edit | What is made again |
|---|---|---|
| What the voice says | `narration` in that shot | One voice recording. English is also the subtitle text |
| A picture | `image_prompt` in that shot | That shot's picture (the wide film is made from it) |
| How the character looks | `look` or `chosen_seed` under `references` | Every picture of that character |
| The camera move | `ken_burns`: in, out, left, right, up, down | No AI calls |

Picture tip: describe what **is** there. Writing "no cross" put crosses in our pictures.

### Moving clips and music

With Kaggle set up, add `--gpu` to send the missing clips and scores to Kaggle's free GPU:

```powershell
.venv\Scripts\python -m pipeline film --gpu
```

Kaggle's free queue can be long, and a clip takes about 20 minutes. The program waits up to four hours, then finishes with camera moves and simple music. Run it again later to pick up what is ready (`gpu fetch wan`, `gpu fetch music`, then `film`).

With a WaveSpeed key, `python -m pipeline motion --shot s05` makes one paid clip in about a minute. In the studio, choose WaveSpeed under Motion for a shot and press **Animate this shot**.

## What it costs

Making *One Percent* cost **no money**. Everything ran inside free limits, plus two free sign-up credits: **$0.34** of WaveSpeed's $1.00 (three clips) and **9.50 Birr** of Addis AI's 500 Birr (voices tried and not used). What we found on 25 and 26 November 2026:

| Service | Free limit | Roughly enough for |
|---|---|---|
| Gemini voice | 10 calls a day for each model; one call can record a whole script | One film a day |
| Cloudflare pictures | 10,000 neurons, counted over the last 24 hours | About 59 pictures, two films |
| Kaggle | 30 GPU hours a week | About 80 clips |
| WaveSpeed | Paid after its free $1.00 sign-up credit: about $0.05 to $0.16 a clip | |

Details, measured latency and GPU minutes: [COSTS.md](COSTS.md).

## If something goes wrong

Nothing already made is lost. Fix the cause and run the same command again; it continues where it stopped.

| You see | Do this |
|---|---|
| `python` is not recognized | Reinstall Python and tick "Add Python to PATH", then open a new terminal |
| `No module named pipeline` | Run the command from inside the project folder |
| `GEMINI_API_KEY is not set` | Check that the file is named `.env` (not `.env.txt`) and the key is pasted and saved |
| `HTTP 401` or `403` | The key is wrong or lacks permission. Make a new one |
| `HTTP 429` ... per day, or "used up" | The free allowance is used. The studio shows when it comes back and can start the job then by itself |
| `HTTP 503` high demand | The service is busy. The program already retried and tried another model; wait and run again |
| `Storyboard is not valid` | Read the lines below it; each names the part to fix |
| `The film would be ... s` | Must be 60-90 s. Shorten the narration if too long, raise `duration_s` if too short |
| "have not agreed to ..." | For a true story, that service is not ticked on the Story tab. Tick it only if the people agreed |
| Port 8765 already in use | The studio is already running in another window. Close that one |
| Kaggle stays `queued` | Normal on the free tier. Run without `--gpu` |

## Languages

Narration in Amharic and English. Afaan Oromo, Tigrinya and Somali are listed as coming soon and have not been tested. Subtitles are always English.

## For developers

| Command (after `python -m pipeline`) | Does |
|---|---|
| `film [--gpu] [--review]` | Every stage, both formats. `--review` stops wherever a person has not approved |
| `-l en film` | English narration instead of the main language |
| `-s FILE ...` | Use another storyboard |
| `web` | The studio |
| `new` | Draft a storyboard in the terminal |
| `validate`, `status` | Check the storyboard; show what is stale |
| `narration`, `references`, `keyframes`, `radio` | One stage; `--shot s03` or `--name mother` for one item, `--force` to make it again |
| `approve script\|voice\|picture` | Approve from the terminal |
| `gpu submit\|status\|fetch wan\|music` | Kaggle jobs |
| `motion --shot s05` | One paid WaveSpeed clip |
| `preview`, `assemble` | A quick draft video, or the final edit from what exists; neither calls a model |
| `smoke` | Call each provider once |

Run the offline tests with `.venv\Scripts\python -m pytest` (182 tests, no network).

| Path | Contents |
|---|---|
| `storyboard.json` | The film's contract; all stages read only this |
| `schema/` | Storyboard rules, checked before every run |
| `pipeline/` | One file per stage; shared code in `core/`, GPU workers in `kaggle_jobs/`, the studio in `web.py` and `web_static/` |
| `outputs/` | Everything generated, each with a record of its inputs |
| `runs.jsonl` | One line per AI call, including failures |
| `storyboards/` | Other storyboards: the earlier sample and test drafts |

More: [DESIGN](DESIGN.md) (audience and user tests), [ARCHITECTURE](ARCHITECTURE.md), [EXPERIMENTS](EXPERIMENTS.md), [FAILURES](FAILURES.md), [COSTS](COSTS.md), [ETHICS](ETHICS.md).
