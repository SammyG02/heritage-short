# Heritage Short

Turn a family story into a 60-90 second narrated, scored, subtitled film, in vertical and horizontal, from one JSON storyboard.

> Work in progress. The current film, "The Extra Cup" (ትርፍ ሲኒ), is an invented sample story.

## Run it

Needs Python 3.11 or newer. FFmpeg is used if installed; otherwise a bundled copy is used.

```bash
git clone <this repository>
cd tenx-ai-content-creation
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pipeline film
```

Generated pictures, voices and clips are committed with their cache records, so this rebuilds the film **without any keys or GPU**. `make film` does the same.

To change something, copy `.env.example` to `.env`, add your keys, edit `storyboard.json` and run the command again. Only what you changed is regenerated. `python -m pipeline status` shows what is stale first.

## Commands

| Command | Does |
|---|---|
| `python -m pipeline film` | Whole pipeline, both formats |
| `python -m pipeline film --gpu` | Also generates missing Wan clips and music on Kaggle, and waits |
| `python -m pipeline -l en film` | English narration instead of Amharic |
| `python -m pipeline new` | Draft a storyboard from your story, language and theme |
| `python -m pipeline web` | The same in a local web page |
| `python -m pipeline -s storyboards/x.json film` | Film another storyboard |
| `python -m pipeline radio` | Narration over placeholder music, for testing the story |
| `python -m pipeline gpu submit\|status\|fetch wan\|music` | Control Kaggle jobs by hand |
| `python -m pipeline smoke` | Call each provider once |
| `python -m pytest` | Offline tests |

Narration: Amharic and English. Afaan Oromo, Tigrinya and Somali are planned. Subtitles are English.

## Cost

No money spent. See [COSTS.md](COSTS.md).

## Read more

[DESIGN](DESIGN.md), [ARCHITECTURE](ARCHITECTURE.md), [EXPERIMENTS](EXPERIMENTS.md), [FAILURES](FAILURES.md), [ETHICS](ETHICS.md)
