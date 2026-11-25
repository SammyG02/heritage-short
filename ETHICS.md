# Consent, labelling and licences

## Consent

**Status: mother, father, sister and brother all agreed, as reported by the applicant. Recorded before anything of the story was generated; voices, character pictures and one shot have been made since.** The pipeline refuses to call a model for it until `people.consent` in `storyboard.json` is `recorded` (`require_consent` in `pipeline/core/storyboard.py`, with a test).

"One Percent" is the applicant's true family story. It tells private medical history and quotes their mother.

- **Faces** are invented and drawn from text only. No photograph is used as input.
- **Voice** is a stock Gemini voice. No voice is cloned. The narrator is a male stock voice; a female stock voice reads the mother's quoted words, so she must agree to them. Neither imitates a real person.
- **Siblings** are mentioned without names and seen only from behind.

| Person | How they appear | Agreed to the story, the public film and the words | When and how |
|---|---|---|---|
| Applicant (narrator in the story) | Told in first person, stock voice | Supplied the story, 25 Nov 2026 | Written instruction to the agent |
| Mother | Invented drawing; one quoted line | Agreed to the film; said it would be great to see it in animation style. Agreed to public posting. Approved her quoted line (s09) and the question spoken by her character (s05), after the applicant told her about them | In person at home, as reported by the applicant on 25 Nov 2026 (about 19:15 and 19:30 EAT; the lines confirmed afterwards) |
| Father | Invented drawing | Approved; wants to see the final result. Agreed to public posting | Same |
| Sister, adult (22) | Mentioned, seen from behind | Said yes; agreed to public posting | Same |
| Brother, adult (20) | Mentioned, seen from behind | Said yes; agreed to public posting | Same |

**Addis AI (26 Nov 2026, recorded in the studio before the first line was sent at 01:32 EAT).** Addis AI's privacy policy says content may be used to train by default. The applicant wrote: "My Mother,father,brother and sister all agreed that i can use them as characters in my ai video and share data with addis AI and any other AI..." The studio refuses to send a true story to Addis AI without such a record (`people.addis_consent`).

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
| Gemini 3.1 Flash TTS preview | Google API terms, as above | Model page, 25 Nov 2026 |
| Addis AI Voices 2 (used for this film's Amharic voices from 26 Nov) | Its terms allow use in your own products, no resale. Its privacy policy says content may be used to train by default, so a true story needs fresh consent before choosing it | Terms and privacy pages, 25 Nov 2026 |
| Groq (optional, never used) | Terms not checked yet; check them before sending a true story | Model list only, 26 Nov 2026 |
| OmniVoice Amharic (optional last resort, not used) | Amharic card: Apache 2.0. Base model card: code Apache 2.0, weights CC-BY-NC. Treated as non-commercial. No recording of a person is used | Model cards, 25 Nov 2026 |
| Geist | SIL Open Font License 1.1 | Bundled in assets/fonts with its licence |
| Noto Sans Ethiopic | SIL Open Font License 1.1 | Bundled in assets/fonts with its licence |
| FFmpeg | LGPL/GPL by build; run as an external program | - |

Styles are described by their qualities. No living artist is named.
