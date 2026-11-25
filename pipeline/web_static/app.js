'use strict';
const $ = s => document.querySelector(s);
let films = [], S = null, L = null, options = null, jobWas = false, lastJob = null, dirty = false;
const RATIOS = ['9x16', '16x9'], RATIO_NAME = { '9x16': 'vertical', '16x9': 'wide' };
const GPU_MIN = 20;

/* Build elements from data only: text is never parsed as HTML. */
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'class') e.className = v;
    else if (k in e && k !== 'list' && k !== 'form') e[k] = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) if (c !== null && c !== undefined && c !== false) e.append(c);
  return e;
}
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const d = await r.json().catch(() => ({ error: 'The studio did not answer.' }));
  if (!r.ok) throw new Error(d.error || 'Something went wrong.');
  return d;
}
let toastTimer;
function toast(t) { const e = $('#toast'); e.textContent = t; e.classList.add('on'); clearTimeout(toastTimer); toastTimer = setTimeout(() => e.classList.remove('on'), 6000); }
function ask(title, text, yes) {
  $('#ask-title').textContent = title; $('#ask-text').textContent = text; $('#ask-yes').textContent = yes;
  const d = $('#ask'); d.returnValue = ''; d.showModal();
  return new Promise(ok => d.addEventListener('close', () => ok(d.returnValue === 'yes'), { once: true }));
}
const id = () => S.storyboard.id, main = () => S.storyboard.language;
const clock = t => new Date(t).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
const count = (f) => S.rows.filter(f).length;
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;

/* ---- actions ---- */
async function run(action, body = {}, cost) {
  if (dirty && !await ask('You have unsaved edits', 'They are not used until you save them. Continue with the saved version?', 'Continue')) return;
  if (cost && !await ask(cost.title, cost.text, cost.yes)) return;
  try { await api(`/api/film/${id()}/run`, { action, ...body }); jobWas = true; await poll(); } catch (e) {
    if (/not been collected/.test(e.message) && await ask('Earlier job not collected', e.message, 'Send again')) return run(action, { ...body, replace: true });
    toast(e.message);
  }
}
async function edit(body, done = 'Saved') {
  try { await api(`/api/film/${id()}/edit`, body); dirty = false; toast(done); await load(id()); draw(); return true; } catch (e) { toast(e.message); return false; }
}
function voiceCost(rows) {
  const n = rows.reduce((a, r) => a + r.voice.calls, 0), model = S.storyboard.voices[main()].model || S.storyboard.models.tts;
  const u = L.tts[model];
  const left = u && u.blocked ? `${model} has reached today's limit. Backup models are tried; if they are full too, nothing is lost and you can try again after ${clock(L.tts_reset)}.` : `The free limit is about ${L.tts_free} a day for each voice model. ${model} has made ${u ? u.used : 0} today.`;
  return { title: `Make ${plural(rows.length, 'line')}?`, text: `This uses ${plural(n, 'voice call')}. ${left}`, yes: 'Make voices' };
}
function pictureCost(n, what, checked = true) {
  const each = 167, left = Math.max(0, L.flux_free - L.flux_used);
  return { title: `Draw ${what}?`, text: `About ${n * each} units for ${plural(n, 'picture')} (an estimate${checked ? '; a picture that fails its check is redrawn up to twice more' : ''}). About ${left} of ${L.flux_free} units are left until ${clock(L.flux_reset)}.${checked ? ' Each check also uses one story-text call.' : ''}`, yes: 'Draw' };
}
const gpuCost = n => ({ title: `Send ${plural(n, 'clip')} to the GPU?`, text: `About ${(n * GPU_MIN / 60).toFixed(1)} hours of GPU time (${GPU_MIN} minutes a clip, plus waiting in the queue). About ${(L.gpu_free_h - L.gpu_used_h).toFixed(1)} of ${L.gpu_free_h} free hours are left this week, by our own log.`, yes: 'Send to GPU' });

/* ---- pieces ---- */
const tag = (text, kind) => h('span', { class: 'tag ' + (kind || '') }, text);
function state(a, made = 'ready', none = 'not made') { return a.fresh ? tag(made, 'ok') : a.url ? tag('out of date', 'warn') : tag(none); }
function btn(text, onclick, o = {}) { return h('button', { type: 'button', class: (o.quiet ? 'quiet ' : '') + (o.tiny ? 'btn tiny' : ''), disabled: o.disabled || (o.job !== false && lastJob && lastJob.running), title: o.title, onclick }, text); }
function head(title, text, ...more) { return [h('h1', {}, title), text && h('p', { class: 'soft' }, text), ...more]; }
function lockNote() { return S.locked && h('div', { class: 'note' }, h('b', {}, 'Locked. '), 'This is a true story, so nothing can be made until consent is recorded on the ', h('a', { href: `#/${id()}/story` }, 'Story page'), '.'); }
const line = s => s.narration[main()];

/* ---- pages ---- */
const STEPS = [
  ['story', 'Story', () => [`${S.rows.length} shots`, !S.locked]],
  ['characters', 'Characters', () => { const r = Object.values(S.references); const n = r.filter(x => x.decided).length; return [`${n}/${r.length}`, n === r.length]; }],
  ['voice', 'Voice', () => { const n = count(r => r.voice.fresh); return [`${n}/${S.rows.length}`, n === S.rows.length]; }],
  ['pictures', 'Pictures', () => { const n = RATIOS.reduce((a, x) => a + count(r => r['picture_' + x].fresh), 0); return [`${n}/${S.rows.length * 2}`, n === S.rows.length * 2]; }],
  ['motion', 'Motion', () => { const n = RATIOS.reduce((a, x) => a + count(r => r['clip_' + x].fresh), 0); return [`${n}/${S.rows.length * 2}`, n === S.rows.length * 2]; }],
  ['music', 'Music', () => [S.storyboard.music.reason === 'Not chosen yet' ? 'choose' : 'chosen', S.storyboard.music.reason !== 'Not chosen yet']],
  ['film', 'Film', () => [S.film['9x16'] ? 'made' : 'not made', !!S.film['9x16']]],
  ['feedback', 'Audience', () => [plural(S.feedback.length, 'note'), S.feedback.length >= 6]],
  ['limits', 'Limits', () => ['', false]]];

function nextStep() {
  if (S.locked) return ['Record consent', 'story'];
  if (Object.values(S.references).some(r => !r.decided && !r.from)) return ['Choose your characters', 'characters'];
  if (Object.values(S.references).some(r => !r.decided)) return ['Draw and choose the older characters', 'characters'];
  if (S.rows.some(r => !r.voice.fresh)) return ['Finish the voices', 'voice'];
  if (S.rows.some(r => RATIOS.some(x => !r['picture_' + x].fresh))) return ['Draw the pictures', 'pictures'];
  if (S.rows.some(r => !r['clip_9x16'].fresh)) return ['Add motion, or go on with slow camera moves', 'motion'];
  return ['Build the film', 'film'];
}

const pages = {
  story() {
    const sb = S.storyboard, [t, to] = nextStep();
    const box = sb.shots.map((s, i) => {
      const fields = {};
      const f = (k, label, value, rows = 2) => { fields[k] = h('textarea', { rows, value: value || '', oninput: () => { dirty = true; } }); return h('label', { class: 'f' }, label, fields[k]); };
      const kinds = ['cut', 'fade', 'dissolve', 'fadeblack', 'fadewhite', 'smoothleft', 'smoothright', 'smoothup', 'circleopen'];
      const tr = h('select', { onchange: () => { dirty = true; } }, kinds.map(k => h('option', { value: k, selected: (s.transition || { type: 'cut' }).type === k }, k)));
      const why = h('input', { value: (s.transition || {}).reason || '', oninput: () => { dirty = true; } });
      const langs = Object.keys(sb.voices);
      const form = h('div', {},
        langs.map(l => f('n_' + l, l === 'am' ? 'Amharic narration' : 'English (also the subtitle)', s.narration[l])),
        f('emotion', 'What the characters feel', s.emotion, 1), f('image_prompt', 'Picture (English works best)', s.image_prompt, 3), f('motion_prompt', 'Movement: one small action', s.motion_prompt, 2),
        h('div', { class: 'row gap' }, h('label', { class: 'f' }, 'Arrives by', tr), h('label', { class: 'f', style: 'flex:1' }, 'Because', why)),
        h('div', { class: 'row gap' }, btn('Save shot', () => edit({ shots: { [s.id]: { narration: Object.fromEntries(langs.map(l => [l, fields['n_' + l].value])), emotion: fields.emotion.value, image_prompt: fields.image_prompt.value, motion_prompt: fields.motion_prompt.value, transition: { type: tr.value, reason: why.value } } } }, 'Saved. Only what changed will need remaking.')), h('span', { class: 'soft small' }, 'Saving uses no limits.')));
      return h('div', { class: 'shot' }, h('div', { class: 'n' }, i + 1), h('div', {}, h('div', { class: 'am' }, line(s)), h('p', { class: 'soft small' }, s.narration.en), h('p', { class: 'soft small' }, `${s.reason}. ${s.emotion || ''}`), h('details', {}, h('summary', {}, 'Edit'), form)), h('div', {}, s.quote_voice && tag('quote: ' + s.quote_voice)));
    });
    const consent = h('textarea', { rows: 4, placeholder: 'For example: My mother agreed in person on 25 November to the story, the public film and her quoted line. Use roles, not names.' });
    const people = sb.people;
    return [head(Object.values(sb.title).join(' / '), sb.logline),
      h('div', { class: 'panel row' }, h('div', {}, h('b', {}, 'Next: '), t), h('a', { class: 'btn right', href: `#/${id()}/${to}` }, 'Go')),
      h('p', { class: 'soft small' }, `For: ${sb.audience}. Feeling at the end: ${sb.intent}.`),
      people.based_on_real_people && (S.locked ? h('div', { class: 'note' }, h('h2', {}, 'Consent'), h('p', {}, 'This film tells a true story. Write who agreed, when, how, and to what. Only record what people really said.'), consent, h('div', { class: 'row gap' }, btn('Record consent', () => edit({ consent: consent.value }, 'Consent recorded'))))
        : h('p', { class: 'small' }, tag('consent recorded', 'ok'), ' ', people.consent_record || 'Details are in ETHICS.md.')),
      h('div', { class: 'gap' }, box)];
  },
  characters() {
    return [head('Characters', 'Choose one face for each person. Every shot is drawn from the face you choose, so they stay the same.'), lockNote(),
      Object.entries(S.references).map(([name, r]) => {
        const made = r.options.filter(o => o.url), parent = r.from && S.references[r.from], wait = parent && !parent.decided;
        const missing = r.options.filter(o => !o.fresh).length;
        return h('section', { class: 'panel' }, h('div', { class: 'row' }, h('h2', {}, name.replace(/_/g, ' ')), r.decided ? tag('chosen', 'ok') : tag('not chosen'), h('span', { class: 'soft small' }, r.shots.length ? `in shots ${r.shots.map(x => +x.slice(1)).join(', ')}` : ''),
          missing > 0 && h('span', { class: 'right' }, btn(`Draw ${plural(missing, 'option')}`, () => run('references', { name }, pictureCost(missing, 'options', false)), { disabled: wait || S.locked }))),
          h('p', { class: 'soft small' }, r.from ? `Drawn from the ${r.from} you choose, so it is the same person. ` : '', r.look), wait && h('p', { class: 'small' }, `Choose the ${r.from} first.`),
          made.length ? h('div', { class: 'cast' }, r.options.filter(o => o.url).map(o => h('button', { type: 'button', class: 'choice', 'aria-pressed': String(r.decided && r.chosen === o.seed), onclick: async () => {
            const used = r.shots.length; if (r.decided && r.chosen !== o.seed && !await ask('Change this character?', `Pictures already drawn in ${plural(used, 'shot')} will need drawing again.`, 'Change')) return;
            edit({ references: { [name]: { seed: o.seed } } }, 'Chosen');
          } }, h('img', { src: o.url, alt: `${name} option ${o.seed}`, loading: 'lazy' }), h('span', {}, `Option ${o.seed}`, o.fresh ? '' : ' (out of date)')))) : h('p', { class: 'soft' }, 'No options drawn yet.'));
      })];
  },
  voice() {
    const todo = S.rows.filter(r => !r.voice.fresh);
    return [head('Voice', 'Listen to each line. Changing one line only remakes that line.'), lockNote(),
      h('div', { class: 'row gap' }, btn(todo.length ? `Make ${plural(todo.length, 'missing line')}` : 'All lines are ready', () => run('voice', {}, voiceCost(todo)), { disabled: !todo.length || S.locked }), btn('Build radio cut', () => run('radio'), { quiet: true, disabled: !S.rows.some(r => r.voice.url) }), h('span', { class: 'soft small' }, 'The radio cut uses no limits. Lines without a voice appear as text.')),
      S.radio_latest && h('div', { class: 'panel' }, h('h2', {}, 'Radio cut'), h('p', { class: 'soft small' }, 'Latest cut built here or on the command line. Build again after changes.'), h('video', { src: S.radio_latest, controls: true, style: 'width:100%;max-width:560px;height:64px;background:#000;border-radius:8px' })),
      h('div', { class: 'gap' }, S.storyboard.shots.map((s, i) => { const v = S.rows[i].voice; return h('div', { class: 'shot' }, h('div', { class: 'n' }, i + 1), h('div', {}, h('div', { class: 'am' }, line(s)), h('p', { class: 'small soft' }, s.narration.en), v.url && h('audio', { src: v.url, controls: true, preload: 'none' })), h('div', { class: 'row' }, state(v), v.seconds && h('span', { class: 'small soft' }, `${v.seconds} s`), v.model && h('span', { class: 'small soft' }, v.model), btn(v.url ? 'Say again' : 'Make', () => run('voice', { shots: [s.id], force: true }, voiceCost([S.rows[i]])), { quiet: true, tiny: true, disabled: S.locked }))); }))];
  },
  pictures() {
    const left = RATIOS.reduce((a, x) => a + count(r => !r['picture_' + x].fresh), 0);
    return [head('Pictures', 'Each picture is checked for the same face, right emotion, hands and style. Look at every one yourself too.'), lockNote(),
      h('div', { class: 'row gap' }, btn(left ? `Draw ${plural(left, 'missing picture')}` : 'All pictures are ready', () => run('pictures', {}, pictureCost(left, 'every missing picture')), { disabled: !left || S.locked }),
        RATIOS.map(x => { const n = count(r => !r['picture_' + x].fresh); return n > 0 && btn(`Only ${RATIO_NAME[x]} (${n})`, () => run('pictures', { ratios: [x] }, pictureCost(n, RATIO_NAME[x] + ' pictures')), { quiet: true, disabled: S.locked }); })),
      h('div', { class: 'grid' }, S.storyboard.shots.map((s, i) => {
        const r = S.rows[i];
        const qa = RATIOS.map(x => [x, r['picture_' + x].qa]).filter(q => q[1]);
        return h('article', { class: 'tile' }, h('div', { class: 'pair' }, RATIOS.map(x => h('div', { class: 'frame' }, r['picture_' + x].url ? h('a', { href: r['picture_' + x].url, target: '_blank' }, h('img', { src: r['picture_' + x].url, alt: `Shot ${i + 1}, ${RATIO_NAME[x]}`, loading: 'lazy' })) : RATIO_NAME[x]))),
          h('div', { class: 'body' }, h('div', { class: 'row' }, h('h3', {}, `Shot ${i + 1}`), RATIOS.map(x => state(r['picture_' + x], RATIO_NAME[x] + ' ready', RATIO_NAME[x] + ' not made'))),
            h('p', { class: 'small' }, line(s)), h('p', { class: 'small soft' }, s.emotion),
            qa.map(([x, q]) => { const c = q.tries && q.tries.find(t => t.seed === q.seed_used); return h('p', { class: 'small' }, tag(`${RATIO_NAME[x]}: ${q.status}`, q.status === 'passed' ? 'ok' : 'warn'), c && c.check && c.check.problem !== 'none' ? ' ' + c.check.problem : ''); }),
            h('div', { class: 'row' }, RATIOS.map(x => !r['picture_' + x].fresh && btn(`Draw ${RATIO_NAME[x]}`, () => run('pictures', { shots: [s.id], ratios: [x] }, pictureCost(1, 'this picture')), { tiny: true, quiet: true, disabled: S.locked })),
              RATIOS.every(x => r['picture_' + x].fresh) && btn('New version', async () => { if (await ask('Draw a new version?', 'Both formats of this shot get a new seed and are drawn again (2 pictures). The current ones are replaced.', 'Draw again') && await edit({ shots: { [s.id]: { seed: s.seed + 1000 } } }, 'New seed saved')) run('pictures', { shots: [s.id] }); }, { tiny: true, quiet: true, disabled: S.locked }))));
      }))];
  },
  motion() {
    const g = S.gpu_jobs.wan, ready = x => S.rows.filter(r => r['picture_' + x].fresh && !r['clip_' + x].fresh);
    return [head('Motion', 'Pictures become 5-second moving clips on a free GPU. A shot without a clip gets a slow camera move, so the film is never blocked.'), lockNote(),
      h('div', { class: 'panel' }, h('h2', {}, 'GPU job'), g ? h('p', {}, `${plural(g.items, 'clip')} sent ${clock(g.submitted * 1000)}. `, g.fetched ? tag('collected', 'ok') : tag('not collected yet', 'warn')) : h('p', { class: 'soft' }, 'Nothing has been sent.'),
        h('div', { class: 'row gap' }, RATIOS.map(x => btn(`Send ${RATIO_NAME[x]} clips (${ready(x).length})`, () => run('motion_submit', { ratios: [x], shots: ready(x).map(r => r.id) }, gpuCost(ready(x).length)), { disabled: !ready(x).length || S.locked })), btn('Check progress', () => run('motion_status'), { quiet: true, disabled: !g }), btn('Collect finished clips', () => run('motion_fetch'), { quiet: true, disabled: !g })),
        h('p', { class: 'small soft' }, 'Checking and collecting use no limits. You can close this page while the GPU works. A job cannot be cancelled from here; use the Kaggle website.')),
      h('div', { class: 'grid' }, S.storyboard.shots.map((s, i) => { const r = S.rows[i]; return h('article', { class: 'tile' }, h('div', { class: 'pair' }, RATIOS.map(x => { const c = r['clip_' + x], k = r['picture_' + x]; return h('div', { class: 'frame' }, c.url ? h('video', { src: c.url, controls: true, loop: true, muted: true, preload: 'metadata' }) : k.url ? h('img', { src: k.url, alt: '' }) : RATIO_NAME[x]); })),
        h('div', { class: 'body' }, h('div', { class: 'row' }, h('h3', {}, `Shot ${i + 1}`), RATIOS.map(x => state(r['clip_' + x], RATIO_NAME[x] + ' moving', RATIO_NAME[x] + ' camera move'))), h('p', { class: 'small' }, s.motion_prompt),
          h('div', { class: 'row' }, RATIOS.map(x => r['picture_' + x].fresh && !r['clip_' + x].fresh && btn(`Send ${RATIO_NAME[x]}`, () => run('motion_submit', { ratios: [x], shots: [s.id] }, gpuCost(1)), { tiny: true, quiet: true, disabled: S.locked }))))); }))];
  },
  music() {
    const m = S.storyboard.music, why = h('input', { value: m.reason === 'Not chosen yet' ? '' : m.reason, placeholder: 'Why this one? One sentence, in your words' });
    const need = S.scores.filter(x => !x.fresh).length, g = S.gpu_jobs.music;
    return [head('Music', m.caption), h('label', { class: 'f' }, 'Reason', why),
      S.scores.map(x => h('div', { class: 'panel' }, h('div', { class: 'row' }, h('h2', {}, `Score ${x.seed}`), m.chosen_seed === x.seed && m.reason !== 'Not chosen yet' ? tag('chosen', 'ok') : state(x), h('span', { class: 'right' }, btn('Use this score', () => why.value.trim() ? edit({ music: { seed: x.seed, reason: why.value.trim() } }, 'Score chosen') : (toast('Write one sentence about why first.'), why.focus()), { tiny: true, disabled: !x.fresh }))), x.url && h('audio', { src: x.url, controls: true, preload: 'none' }))),
      (need > 0 || g) && h('div', { class: 'row' }, need > 0 && btn(`Send ${plural(need, 'score')} to the GPU`, () => run('music_submit', {}, { title: 'Send music to the GPU?', text: 'The three scores took about 6 minutes of GPU time last time, plus the queue.', yes: 'Send' }), { disabled: S.locked }), g && btn('Check progress', () => run('music_status'), { quiet: true }), g && btn('Collect music', () => run('music_fetch'), { quiet: true }))];
  },
  film() {
    const gaps = count(r => !r.voice.fresh) + RATIOS.reduce((a, x) => a + count(r => !r['picture_' + x].fresh), 0), rep = S.report;
    return [head('Film', 'Editing uses your own computer and no limits. It takes about 15 to 30 minutes on this laptop.'),
      h('div', { class: 'row gap' }, btn('Build the film', () => run('build'), { disabled: gaps > 0 || S.locked }), gaps > 0 && h('span', { class: 'soft' }, `${plural(gaps, 'voice or picture')} still missing.`)),
      RATIOS.some(x => S.film[x]) && h('div', { class: 'films gap' }, RATIOS.map(x => S.film[x] && h('div', {}, h('h2', {}, x === '9x16' ? 'Vertical' : 'Wide'), h('video', { src: S.film[x], controls: true, preload: 'metadata' }), h('a', { class: 'small', href: S.film[x], download: `${id()}_${x}.mp4` }, 'Download')))),
      rep && h('div', { class: 'panel' }, h('h2', {}, 'Checks'), h('p', {}, `${rep.seconds} seconds, music: ${rep.music}, moving shots: ${Object.entries(rep.wan_shots).map(([k, v]) => `${v} ${RATIO_NAME[k]}`).join(', ')}.`), rep.files.map(f => h('p', { class: 'small' }, `${f.file}: ${f.lufs} LUFS, peak ${f.true_peak_db} dB. `, f.problems.length ? tag(f.problems.join(', '), 'bad') : tag('passes', 'ok'))), h('p', { class: 'small soft' }, 'This shows the last build. Build again after any change.'))];
  },
  feedback() {
    const test = h('select', {}, h('option', { value: 'radio cut' }, 'Test 1: radio cut'), h('option', { value: 'near-final cut' }, 'Test 2: near-final cut'));
    const who = h('input', { placeholder: 'Friend, 24, did not know the story' }), words = h('textarea', { rows: 4, placeholder: 'Their exact words, good and bad' }), change = h('textarea', { rows: 2, placeholder: 'What you will change because of this (can stay empty)' });
    return [head('Audience', 'Show it to at least three people at each stage. Write what they really said.'),
      h('div', { class: 'panel' }, h('p', { class: 'small soft' }, 'Ask: What was it about? When did you realise who the baby was? What did you feel most? What was confusing or wrong? How do you feel at the end?'), h('label', { class: 'f' }, 'Which cut', test), h('label', { class: 'f' }, 'Who (no names)', who), h('label', { class: 'f' }, 'What they said', words), h('label', { class: 'f' }, 'What will change', change),
        h('div', { class: 'row gap' }, btn('Add note', async () => { try { await api(`/api/film/${id()}/feedback`, { test: test.value, who: who.value, words: words.value, change: change.value }); toast('Added'); await load(id()); draw(); } catch (e) { toast(e.message); } }, { job: false }))),
      S.feedback.slice().reverse().map(f => h('div', { class: 'panel' }, h('div', { class: 'row' }, h('b', {}, f.who), tag(f.test), h('span', { class: 'soft small' }, clock(f.ts))), h('blockquote', {}, f.words), f.change && h('p', { class: 'small' }, h('b', {}, 'Change: '), f.change)))];
  },
  limits() {
    const bar = (name, used, total, text, blocked) => h('div', { class: 'panel' }, h('div', { class: 'row' }, h('h2', {}, name), blocked && tag('limit reached', 'bad'), h('span', { class: 'right soft' }, text)), h('div', { class: 'bar' }, h('i', { class: blocked || used >= total ? 'full' : '', style: `width:${Math.min(100, blocked ? 100 : used / total * 100)}%` })));
    const models = [...new Set([S.storyboard.voices[main()].model || S.storyboard.models.tts, ...(S.storyboard.models.tts_fallbacks || []), ...Object.keys(L.tts)])];
    return [head('Limits', 'Counted from this project\'s own log, so use elsewhere on the same accounts is not included.'),
      h('h3', { class: 'gap' }, `Voice, resets ${clock(L.tts_reset)}`), models.map(m => { const u = L.tts[m] || { used: 0, blocked: false }; return bar(m, u.used, L.tts_free, `${u.used} made today, limit about ${L.tts_free}`, u.blocked); }),
      h('h3', { class: 'gap' }, `Pictures, reset ${clock(L.flux_reset)}`), bar('FLUX on Cloudflare', L.flux_used, L.flux_free, `about ${L.flux_used} of ${L.flux_free} units (estimate)`),
      h('h3', { class: 'gap' }, 'Motion and music'), bar('Kaggle GPU', L.gpu_used_h, L.gpu_free_h, `about ${L.gpu_used_h} of ${L.gpu_free_h} hours this week`),
      h('p', { class: 'soft small' }, 'The free text model also writes and checks stories; its daily limit is not known. Editing is free and unlimited.')];
  }
};

async function newFilm() {
  options = options || await api('/api/options');
  const story = h('textarea', { rows: 8 }), theme = h('select', {}, Object.entries(options.themes).map(([k, v]) => h('option', { value: k }, v))), audience = h('input', { placeholder: 'My cousins abroad' }), intent = h('input', { placeholder: 'Close to home' }), real = h('input', { type: 'checkbox' });
  const lang = h('select', {}, Object.entries(options.languages).map(([k, v]) => h('option', { value: k }, v)), options.soon.map(x => h('option', { disabled: true }, x + ' (coming soon)')));
  const go = h('button', { type: 'button', onclick: async () => {
    if (!await ask('Write the storyboard?', 'This sends your story to Google\'s free text model, which may learn from it, and uses one or more story-text calls. No voice or picture is made.', 'Write it')) return;
    go.disabled = true; go.textContent = 'Writing, up to a few minutes...';
    try { const r = await api('/api/draft', { story: story.value, language: lang.value, theme: theme.value, audience: audience.value, intent: intent.value, true_story: real.checked }); await listFilms(); location.hash = `#/${r.id}/story`; } catch (e) { toast(e.message); go.disabled = false; go.textContent = 'Write my storyboard'; }
  } }, 'Write my storyboard');
  $('#steps').replaceChildren();
  $('#view').replaceChildren(...[head('Tell your story', 'Write it the way you would tell it. Leave out names and private details.'), h('div', { class: 'panel' }, h('label', { class: 'f' }, 'Your story', story), h('label', { class: 'f' }, 'Narration language', lang), h('label', { class: 'f' }, 'Theme', theme), h('label', { class: 'f' }, 'Who is it for?', audience), h('label', { class: 'f' }, 'What should they feel at the end?', intent), h('p', { class: 'gap' }, h('label', {}, real, ' This is a true story about real people. I will get their consent before anything is made.')), h('div', { class: 'gap' }, go))].flat());
}

/* ---- shell ---- */
async function listFilms() {
  films = await api('/api/films');
  $('#films').replaceChildren(...films.map(f => h('option', { value: f.id }, Object.values(f.title).join(' / '))));
}
async function load(fid) { [S, L] = await Promise.all([api('/api/film/' + fid), api('/api/limits')]); }
function draw() {
  if (!S) return;
  const page = location.hash.split('/')[2] || 'story', y = window.scrollY;
  $('#films').value = id();
  $('#steps').replaceChildren(...STEPS.map(([k, name, f]) => { const [t, ok] = f(); return h('a', { href: `#/${id()}/${k}`, 'aria-current': k === page ? 'page' : null }, name, h('small', { class: ok ? 'ok' : '' }, t)); }));
  $('#view').replaceChildren(...(pages[page] || pages.story)().flat(Infinity).filter(Boolean));
  document.title = `${Object.values(S.storyboard.title).pop()} · Heritage Studio`;
  window.scrollTo(0, y);
}
async function route() {
  if (dirty && !await ask('Leave without saving?', 'Your edits on this page will be lost.', 'Leave')) return;
  dirty = false;
  const [, fid] = location.hash.split('/');
  try {
    if (fid === 'new') return await newFilm();
    const want = films.some(f => f.id === fid) ? fid : (films[0] || {}).id;
    if (!want) return await newFilm();
    if (!S || id() !== want) await load(want);
    draw(); window.scrollTo(0, 0); $('#view').focus({ preventScroll: true });
  } catch (e) { $('#view').replaceChildren(h('div', { class: 'note' }, e.message)); }
}
function dock(j) {
  const d = $('#dock'); if (!j.label || j.hidden) { d.hidden = true; return; }
  d.hidden = false;
  const open = d.querySelector('details') ? d.querySelector('details').open : j.running;
  const word = j.running ? `${j.label}... ${Math.floor(j.seconds / 60)}:${String(j.seconds % 60).padStart(2, '0')}` : j.stopped ? `${j.label}: stopped` : j.ok ? `${j.label}: finished` : `${j.label}: did not finish`;
  const last = (j.log.trim().split('\n').pop() || '').replace(/^ERROR: /, '').slice(0, 220);
  d.replaceChildren(h('div', { class: 'row' }, tag(j.running ? 'working' : j.ok ? 'done' : 'stopped', j.running ? 'warn' : j.ok ? 'ok' : 'bad'), h('b', {}, word), h('span', { class: 'soft small' }, last), h('span', { class: 'right row' }, j.running ? btn('Stop', async () => { await api('/api/job/stop', {}); poll(); }, { quiet: true, tiny: true, job: false, title: 'Finished parts are kept' }) : btn('Close', () => { lastJob.hidden = true; dock(lastJob); }, { quiet: true, tiny: true, job: false }))), h('details', { open }, h('summary', {}, 'Details'), h('pre', {}, j.log || '...')));
  const pre = d.querySelector('pre'); pre.scrollTop = pre.scrollHeight;
}
let timer;
async function poll() {
  clearTimeout(timer);
  try {
    const j = await api('/api/job'), was = jobWas, hid = lastJob && lastJob.hidden && !j.running;
    const changed = !lastJob || lastJob.running !== j.running;
    lastJob = { ...j, hidden: hid }; jobWas = j.running; dock(lastJob);
    if (was && !j.running) { if (S) await load(id()); if (!dirty) draw(); } else if (changed && S && !dirty) draw();
    timer = setTimeout(poll, j.running ? 2000 : 8000);
  } catch (e) { timer = setTimeout(poll, 8000); }
}
$('#films').addEventListener('change', e => { location.hash = `#/${e.target.value}/story`; });
window.addEventListener('hashchange', route);
window.addEventListener('beforeunload', e => { if (dirty) e.preventDefault(); });
(async () => { try { await listFilms(); await route(); poll(); } catch (e) { $('#view').replaceChildren(h('div', { class: 'note' }, e.message)); } })();
