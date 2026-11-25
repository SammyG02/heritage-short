# Experiments

Each entry: hypothesis, the one thing changed, result. Image counts below come from the coding agent viewing contact sheets on 25 Nov 2026; the applicant has not yet confirmed them. Every call is in `runs.jsonl`.

**Done: 5. Target: at least 10.** Nothing is listed here until it has been run.

## 1. Negative wording in an image prompt

- **Hypothesis:** writing "cross-free" earrings keeps crosses out of the portrait.
- **Change:** "small silver cross-free round earrings" became "small plain round silver stud earrings". Same seeds 11, 22, 33, 44. (The shared style block also changed "no text, no lettering, no border" to "full-bleed painting reaching every edge", see 2.)
- **Result:** seeds 11 and 44 drew crosses with the negative wording; none of the four did afterwards. The hypothesis was wrong: naming the thing summoned it.
- **Decision:** prompts say what is present. The intake prompt in `pipeline/script.py` now carries this rule.

## 2. "No border" against "full-bleed"

- **Hypothesis:** saying "no border" prevents ragged paper edges.
- **Change:** the style block wording above, with the coffee-set subject also reworded (see 3), so this is not a clean single-variable test.
- **Result:** ragged paper edges were obvious in coffee-set seeds 11 and 44 and faint in others before; afterwards only small corners remain on 11 and 44. Better, not solved.
- **Decision:** keep "full-bleed"; choose seed 33, which has clean edges.

## 3. Naming a jebena against describing its shape

- **Hypothesis:** the model knows what a jebena is.
- **Change:** "one round black clay jebena coffee pot with a long neck and a side handle" became a description of a ball-shaped base, one tall slender tube neck, straw stopper and loop handle.
- **Result:** 0 of 4 pots looked like a jebena before (wide-mouthed teapots with spouts); 4 of 4 had the long neck afterwards.
- **Decision:** describe culturally specific objects by shape. Naming alone returned a generic teapot.

## 4. Leaving space for subtitles

- **Hypothesis:** asking for "calm empty space near the bottom" leaves room for captions.
- **Change:** vertical framing became "the painted scene continues down to the bottom edge". Some shot prompts changed in the same run.
- **Result:** before, the vertical images s04 and s07 ended in a flat painted band with the subject cut off; after, 0 of 11 vertical images did.
- **Decision:** let the picture fill the frame and give captions an outline instead.

## 5. Attaching a reference image to every shot

- **Hypothesis:** adding the coffee-set reference everywhere improves consistency.
- **Change:** removed it from s01 (house) and s06 (door), where no cup should appear. The s06 wording also changed.
- **Result:** with it, the coffee set appeared outdoors in front of the house in vertical s01, and blocked the door in both versions of s06. Without it, neither shot contained it.
- **Decision:** attach a reference only where its subject belongs. This is a limit on the brief's "condition every keyframe on the sheet" advice.

## Planned

Ken Burns against Wan on one shot; Wan 480p time and quality; motion-only against full-description prompts; three ACE-Step candidates; ducking settings; one-pass against two-pass loudness; style instruction against a different voice.
