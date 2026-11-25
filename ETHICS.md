# Consent, labelling and licences

## Consent

**Status: the applicant asked all four relatives; mother and father approved. Still locked until the details below are confirmed. Nothing of "One Percent" has been generated.** The pipeline refuses to call a model for it until `people.consent` in `storyboard.json` is `recorded` (`require_consent` in `pipeline/core/storyboard.py`, with a test).

"One Percent" is the applicant's true family story. It tells private medical history and quotes their mother.

- **Faces** are invented and drawn from text only. No photograph is used as input.
- **Voice** is a stock Gemini voice. No voice is cloned. It reads the mother's quoted words, so she must agree to them.
- **Siblings** are mentioned without names and seen only from behind.

| Person | How they appear | Agreed to the story, the public film and the words | When and how |
|---|---|---|---|
| Applicant (narrator in the story) | Told in first person, stock voice | Supplied the story, 25 Nov 2026 | Written instruction to the agent |
| Mother | Invented drawing; one quoted line | Agreed to the film; said it would be great to see it in animation style. **Quoted line, public posting and free-tier use: to confirm** | Reported by the applicant, 25 Nov 2026, about 19:15 EAT. How she was asked: **to confirm** |
| Father | Invented drawing | Approved; wants to see the final result. **Public posting and free-tier use: to confirm** | Same; how: **to confirm** |
| Sister, adult (22) | Mentioned, seen from behind | Asked for consent to this film. **Her answer: to confirm** | Same; how: **to confirm** |
| Brother, adult (20) | Mentioned, seen from behind | Asked for consent to this film. **His answer: to confirm** | Same; how: **to confirm** |

The earlier sample, "The Extra Cup", was invented: no real person was shown or voiced.

## Labelling

- An end card in both exports says the film was made with AI.
- The platform's AI disclosure will be switched on when posting.
- SynthID in Gemini audio is not deliberately removed or altered. Mixing and re-encoding happen as in any edit. File-level C2PA metadata may not survive FFmpeg, so the end card and platform label carry the disclosure.

## Private data

Google states that free-tier Gemini content is used to improve its products. For "The Extra Cup" only the invented story was sent. The narration of "One Percent" would be sent to Gemini TTS, so the consent above must cover that. It contains no names. Do not enter names, addresses or private family details.

## Licences

| Component | Licence or terms | Checked |
|---|---|---|
| Gemini 3.8 Flash and Flash TTS | Google API terms; free tier used to improve products | Pricing page, 25 Nov 2026 |
| FLUX.2 klein 4B on Workers AI | Weights Apache 2.0 per the brief; hosted use links to BFL terms | Cloudflare model listing, 25 Nov 2026 |
| Wan 2.2 TI2V-5B | Apache 2.0 | Model card, 25 Nov 2026 |
| ACE-Step 1.5 | MIT | Repository README, 25 Nov 2026 |
| Noto Sans Ethiopic | SIL Open Font License 1.1 | Bundled in assets/fonts with its licence |
| FFmpeg | LGPL/GPL by build; run as an external program | - |

Styles are described by their qualities. No living artist is named.
