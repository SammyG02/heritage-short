# Design

## Change of story, 25 Nov 2026 (before anything of the new story was generated)

The applicant replaced the invented sample "The Extra Cup" (kept below, and in `storyboards/the-extra-cup.json`) with their own family's story, "One Percent". The narration is the applicant's text. Amharic began as an agent's translation; the applicant corrected it in version 3.

- **Audience:** families and couples in Ethiopia and the diaspora who are waiting for something they have been told is unlikely. They watch vertically on a phone.
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

It happened in two steps on the evening of 25 November 2026, with friends in a voice chat, so the applicant could hear their reactions first hand. Names are not recorded: the applicant did not ask the friends for permission to name them.

**Step 1, the script (before any voice was made).** The applicant had not checked the agent's Amharic carefully, and sent the script to friends, who read it together with the applicant. Two of them found mistakes: words and phrases that were wrong or unnatural. The applicant rewrote the Amharic as a native speaker, line by line (storyboard version 3, saved at 19:31; the table below).

**Step 2, the radio cut (narration over placeholder music on a black screen; lines 11 and 12 shown as text because the free voice allowance had run out).** The voices were made at 19:38 to 19:42 and the radio cut at 19:44, and the applicant played it to the friends. Some words were still pronounced wrongly by the voice, for example "ተወለዱ" (*teweledu*, were born) heard as *teweldew* and "ጸለዩ" (*tseleyu*, they prayed) heard as *tsalay*; the applicant first blamed the voice model, which is part of why a second voice service was tried later (below). The listeners said the telling was good, and when told it was for a family story they thought it was cool. As reported to the agent at 00:05 on 26 November:

| Listener | What they said, as reported by the applicant |
|---|---|
| 1 | It was good |
| 2 | It is good, and not boring to listen to |
| 3 | They liked the narration and the storytelling style |
| 4 | The AI misses some things when it speaks Amharic |

These are the applicant's account, not recordings. Listeners' ages and exact Amharic wording are not recorded.

**What changed because of it:** the script was rewritten after the friends read it (step 1), and after hearing the radio cut line 10 was reworded twice (the siblings "came", then "were born"; 19:54 and 00:24). After the corrections the voice sounded natural to the applicant. Before and after, from the storyboard's history (`git show 94a371c:storyboard.json` and the current file):

| Line | Before (storyboard v2, 25 Nov 19:07) | After (in the film) |
|---|---|---|
| 1 | ባልና ሚስት ነበሩ። በወጣትነታቸው ተጋቡ፤ ልጅ እንደሚወልዱም እርግጠኛ ነበሩ። | ሁለት በወጣትነታቸው የተጋቡ ባልና ሚስት ነበሩ፤ ልጅ እንደሚወልዱም እርግጠኛ ነበሩ። |
| 2 | አንድ ዓመት አለፈ። ከዚያ ሁለት። ከዚያ አምስት። | ሆኖም አንድ ዓመት አለፈ። ከዚያም ሁለት። ከዚያም አምስት። |
| 4 | ከዚያ ሐኪሙ እውነቱን ነገራቸው፦ በኢትዮጵያ ዕድላቸው ከአንድ በመቶ በታች ነበር። | ከዚያም ሐኪሙ፦ በኢትዮጵያ የመውለድ ዕድላቸው ከአንድ በመቶ በታች መሆኑን ነገራቸው። |
| 5 | ብዙ ሰው እዚህ ያቆም ነበር። እነሱ ግን ጠየቁ፦ ሌላ የት እንሞክር? | ብዙ ሰው እዚህ ጋር ተስፋ ይቆርጥ ነበር። እነሱ ግን ጠየቁ፦ «ሌላ የት እንሞክር?» |
| 6 | መልሱ ሩቅ ነበር፤ እስራኤል። አዲስ ሐኪሞች፣ አዲስ ቋንቋ፣ ለዓመታት ያው ተስፋ። | መልሱ ሩቅ ነበር፤ እስራኤል። አዲስ ሃገር፣ አዲስ ሐኪሞች፣ አዲስ ቋንቋ፣ አራት አመት። |
| 10 | ከዚያ ታናሽ እህቴ፣ ከዚያም ታናሽ ወንድሜ መጡ። | ከዚያ ታናሽ እህቴ፣ ከዚያም ታናሽ ወንድሜ ተወለዱ። |
| 11 | ያ አንድ በመቶ እኔ ነበርኩ። ሁላችንም ነበርን። | ያ አንድ በመቶ እኔ ነበርኩ። ሁላችንም ነን። |

## Voice test: a second voice service, on a recommendation from Slack

**Why:** the free Gemini voice allowance (10 calls a day per model) ran out, and colleagues on the cohort's Slack recommended Addis AI for Amharic. **What was done:** Addis AI was added as a voice service, and all twelve lines were voiced with it in the night of 25 to 26 November (28 calls in `runs.jsonl`, `provider: addis-ai`). **What the applicant found:** it speaks several Ethiopian languages and can be paid in Ethiopian birr, but to the applicant the voice sounded unnatural and without emotion, "like a robot", unlike what the group had said. The applicant sent the new voice to the same friends, and they did not like it either. **What changed:** the film went back to Gemini TTS (lines 10 to 12 made on 26 Nov at 09:53 EAT). To live with its limit of 10 calls a day, the pipeline was changed so that one call can record every missing line at once and cut it into one file per shot (`narration.take`, `voice_take.split`, experiment 7).

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

**What was tested:** the cut with the invented pictures, the voices and the English subtitles, sent by the applicant to three friends on 26 November 2026. **What they said, as reported by the applicant** (three different people; names not recorded, as they were not asked):

| Viewer | What they said |
|---|---|
| 1 | It was great; she said she almost cried, although the story is not that sad |
| 2 | Liked it too |
| 3 | One picture felt off |

**What the applicant had missed:** happy that the whole film finally worked, the applicant had not noticed that the baby's fingers in shot 7 were wrong. **What changed:** shot 7 was redrawn (26 Nov 15:22 EAT) and its description rewritten (15:29 and 15:30); the earlier pictures are kept in `outputs/one-percent/keyframes/versions/`. The pipeline made this cheap because only that shot was drawn again.

**What it led to in the tool:** while fixing it the applicant found there was no way to choose which model draws a picture or to see how many free pictures were left, so the studio gained a Services page: choose the model for each service (voice, pictures, motion, writing), see what is left of each limit, and when it comes back.
