# Design

## Change of story, 25 Nov 2026 (before anything of the new story was generated)

The applicant replaced the invented sample "The Extra Cup" (kept below, and in `storyboards/the-extra-cup.json`) with their own family's story, "One Percent". The narration is the applicant's text. Amharic began as an agent's translation; the applicant corrected it in version 3.

- **Audience (draft, applicant to confirm):** families and couples in Ethiopia and the diaspora who are waiting for something they have been told is unlikely. They watch vertically on a phone.
- **Intent:** feel that a small chance is still a chance, and want to keep trying.
- **Shape:** a husband and wife we do not know, an empty doorstep, a long wait, a birth. Only then "That baby was me." The peak is the mother's own line, on her face. The doorstep returns full.

### Storyboard version 2: the applicant's review (25 Nov 2026, before any generation; not a user test)

- Removed the opening "number" shot: it spoiled the suspense. The film now starts with a husband and wife.
- Removed all coffee imagery and the "same two cups" line: the applicant does not want it.
- Removed "They tried again".
- "My mother and father" and "my parents" became "they" until the reveal, so the narrator's identity stays hidden. Added the reveal shot, s08.
- **Motion:** the applicant asked for people who move and speak rather than still pictures, so motion prompts ask for lips, heads, hands and breath. Narration is voice-over; mouths are not lip-synced.
- **Every shot's reason** is in its `reason` field.

- **Style:** the applicant's mother, asked for consent, said she would like to see it as animation. An agent first read that as 2D; the applicant corrected it: she means 3D painted animation. The style block now says so.
- **Script version 3:** the applicant rewrote the Amharic themselves as a native speaker (agent fixes: one stray comma, "4" spelled out for the voice, quote marks around the question). The English subtitles were updated to match.
- **Voices:** the narrator is a man, like the applicant. Quoted words are spoken in a woman's stock voice.

## User test 1: radio cut of "One Percent"

**When:** night of 25-26 November 2026, reported by the applicant at 00:05. **What they heard:** the Amharic radio cut: lines 1 to 10 voiced, lines 11 and 12 shown as text because the free voice allowance had run out, over placeholder music.

The applicant passed on these reactions in English. They are the applicant's short account, not recordings, and each listener's age, connection to the story and wording in Amharic are not recorded yet.

| Listener | What they said, as reported |
|---|---|
| 1 | It was good |
| 2 | It is good, and not boring to listen to |
| 3 | They liked the narration and the storytelling style |
| 4 | The AI misses some things when it speaks Amharic |

**What we learned:** the telling holds attention, so its order and its male narrator stay. The weak point is pronunciation, not the story. Nobody was asked, or nobody said, whether the reveal in shot 8 surprised them: that stays an open question for test 2.

**What will change:** the wrong words have to be named before a line is changed. The applicant will ask listener 4 which lines. Each named line is respelled in `storyboard.json` and said again before its shot is animated.

**What we did in the wrong order:** shot 1 was drawn at 23:31, before these reactions arrived. The other pictures were held back.

**Already changed by the applicant after hearing the same cut:** line 10 was reworded (the parents' children "were born" rather than "came").

## First version: the sample story

Written before any image, voice, music or video was generated.

> **Status: sample story.** "The Extra Cup" is an invented story used to build and test the pipeline. The applicant has not yet replaced it or adopted it as their own. No user test has been run yet.

## Audience

Young Ethiopians living away from the home they grew up in, and the parents and relatives who would receive the film from them. They watch on a phone, vertically, probably inside a Telegram or WhatsApp family chat, often without headphones.

## Intent

When it ends, the viewer should feel that home is a habit of welcome they can carry with them, and want to call someone.

**How might we** help someone far from home feel close to the person who taught them to welcome others?

## Story

A grandmother always sets out one more coffee cup than there are people. It is for "the one still on the road". One rainy night a stranger arrives, and the cup is his. Years later her grandchild, far from home, still sets out one extra cup.

## Why this shape

- One main character and one returning object (the cup) keep visual consistency achievable.
- Hands, cups, rain and steam carry the feeling, so few shots depend on a face.
- Painted, not photographic: invented people should not be mistaken for real ones.
- The last line turns to the viewer.

Each shot's reason is in its `reason` field in `storyboard.json`.

## User test 2: near-final cut

Not run yet. Needs at least three people from the audience.
