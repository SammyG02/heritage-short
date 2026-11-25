'use strict';
const $ = s => document.querySelector(s);
const V = '9x16', W = '16x9', RATIOS = [V, W];
const CLIP_MIN = 20;
let films = [], S = null, L = null, J = { running: false }, at = 0, ratio = V, show = null, dirty = null, wasRunning = false, busy = false;
let face = null, heard = new Audio(), SV = null, svPick = {};

/* Elements are built from data only: text is never parsed as HTML. */
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'class') e.className = v;
    else if (k in e && !['list', 'form', 'style'].includes(k)) e[k] = v;
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
function toast(t) { const e = $('#toast'); e.textContent = t; e.classList.add('on'); clearTimeout(toastTimer); toastTimer = setTimeout(() => e.classList.remove('on'), 6500); }
/* A dialog resolves to the chosen value, or null. */
function dialog(title, body, choices) {
  const d = $('#ask');
  const form = h('form', { method: 'dialog', class: '' }, h('h2', {}, title), body, h('div', { class: 'ends' }, choices.map(([v, t, main]) => h('button', { type: main ? 'submit' : 'button', value: v, class: main ? 'go' : '', style: main ? 'width:auto;min-height:44px' : null, onclick: main ? null : () => d.close('') }, t))));
  form.method = 'dialog'; form.setAttribute('method', 'dialog');
  d.replaceChildren(form); d.returnValue = ''; d.showModal();
  return new Promise(ok => d.addEventListener('close', () => { d.replaceChildren(); ok(d.returnValue || null); }, { once: true }));
}
const ask = (title, text, yes) => dialog(title, h('p', {}, text), [['', 'Cancel'], ['yes', yes, true]]).then(v => v === 'yes');
const id = () => S.storyboard.id, lang = () => S.storyboard.language, shots = () => S.storyboard.shots;
const clock = t => new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
const ENGINE = { gemini: 'Google', addis: 'Addis AI', omnivoice: 'OmniVoice' }, DRAW = { cloudflare: 'Cloudflare', kaggle: 'Kaggle GPU' };
const n = (x, w) => `${x} ${w}${x === 1 ? '' : 's'}`;
const page = () => location.hash.split('/')[2] || 'script', home = () => !location.hash.split('/')[1];
const btn = (text, onclick, o = {}) => h('button', { type: 'button', class: o.go ? 'go' : '', disabled: o.off || (o.job && J.running), 'aria-pressed': o.on === undefined ? null : String(o.on), 'aria-label': o.label, onclick }, text);

/* ---------------- actions ---------------- */
async function reload() { if (home() || !S) return; [S, L] = await Promise.all([api('/api/film/' + (S ? id() : films[0].id)), api('/api/limits')]); }
async function edit(body, done) {
  if (busy) return false;
  busy = true;
  try { await api(`/api/film/${id()}/edit`, body); dirty = null; await reload(); draw(); if (done) toast(done); return true; } catch (e) { toast(e.message); return false; } finally { busy = false; }
}
async function run(action, body = {}) {
  if (!await settle()) return;
  try { await api(`/api/film/${id()}/run`, { action, ...body }); wasRunning = true; await poll(); } catch (e) {
    if (/not been collected/.test(e.message) && await ask('Earlier job not collected', e.message, 'Send again')) return run(action, { ...body, replace: true });
    toast(e.message);
  }
}
async function later(action, body, when) {
  if (!await ask(`Start at ${clock(when)}?`, `The free limit resets then. Keep this laptop awake and the studio open; closing it cancels this.`, 'Wait for it')) return;
  try { await api(`/api/film/${id()}/later`, { action, ...body }); await poll(); } catch (e) { toast(e.message); }
}
/* Unsaved words are saved before anything else happens. */
async function settle() {
  if (!dirty) return true;
  const d = dirty;
  return edit({ shots: { [d.id]: d.values } });
}
function play(url, onend) { heard.pause(); heard = new Audio(url); heard.onended = onend || null; heard.play().catch(() => toast('The browser blocked the sound. Press again.')); }
const picturesLeft = () => Math.max(0, L.flux_free - L.flux_used);
const units = (rows, x) => rows.reduce((a, r) => a + r['picture_' + x].cost, 0);
const spend = (count, total) => `Uses ${n(count, 'picture')}, about ${Math.max(1, Math.round(total / L.flux_free * 100))}% of today's limit`;

/* A job that failed on the GPU never reports "done", so there is always a way to check it or send it again. */
function sendAgain(action, body, fetchAction, what) {
  const kind = { motion_submit: 'motion', music_submit: 'music', pictures_submit: 'pictures' }[action];
  return h('div', { class: 'two' }, kind ? btn('Check progress', async () => { await run(kind + '_status'); }, { job: true }) : btn('Check progress', () => run(fetchAction), { job: true }),
    btn('Send again', async () => { if (await ask('Send it again?', `Only if the earlier job failed or was cancelled. ${what} Anything it finished but you have not collected is lost, so collect first.`, 'Send again')) run(action, { ...body, replace: true }); }, { job: true }));
}

/* ---------------- top bar ---------------- */
function topBar() {
  const t = S.storyboard.title;
  $('#top').replaceChildren(h('div', { class: 'where' }, h('a', { href: '#/' }, 'Films'), h('strong', {}, t[lang()] || Object.values(t)[0])), h('nav', { 'aria-label': 'Steps' }, [['script', 'Script'], ['cast', 'Cast'], ['shots', 'Shots'], ['film', 'Film']].map(([k, t]) => h('a', { href: `#/${id()}/${k}`, 'aria-current': page() === k ? 'page' : null }, t))), h('div', { class: 'end' }, page() !== 'film' && h('a', { class: 'btn preview', href: `#/${id()}/film` }, 'Preview'), h('a', { class: 'btn' + (page() === 'services' ? ' on' : ''), href: `#/${id()}/services`, 'aria-current': page() === 'services' ? 'page' : null }, 'Services')));
}

/* ---------------- script ---------------- */
function scriptPage() {
  const s = shots()[at], row = S.rows[at], todo = S.rows.filter(r => !r.voice.fresh), unread = S.rows.filter(r => !r.script_ok), unheard = S.rows.filter(r => r.voice.fresh && !r.voice_ok);
  const field = (key, label, value, rows) => h('label', {}, label, h(rows ? 'textarea' : 'input', { rows, value: value || '', id: 'f-' + key, oninput: () => { dirty = { id: s.id, values: values() }; foot(); } }));
  const values = () => { const v = { narration: { [lang()]: $('#f-main').value }, emotion: $('#f-emotion').value }; if (lang() !== 'en') v.narration.en = $('#f-en').value; return v; };
  const problems = S.problems.filter(x => x.startsWith(s.id)).map(x => x.slice(5));
  const footer = h('div', { class: 'foot' });
  function foot() {
    const over = S.length > 90 || S.length < 60, kids = [h('div', { class: 'between' }, h('span', {}, 'Film length'), h('span', { class: over ? 'bad' : 'soft' }, `${S.length} s, limit 60 to 90`)), h('div', { class: 'meter' }, h('div', { class: over ? 'over' : '', style: `width:${Math.min(100, S.length / 90 * 100)}%` }))];
    const voice = h('div', { class: 'between mid' }, h('span', { class: 'soft' }, ENGINE[S.engine]), btn('Change voice', () => voiceSettings()), h('a', { class: 'btn', href: `#/${id()}/services` }, 'Service'));
    if (dirty) kids.push(btn('Save', () => edit({ shots: { [s.id]: values() } }, 'Saved'), { go: true }));
    else if (S.locked) kids.push(btn('Record consent', consent, { go: true }), h('p', {}, 'This is a true story. Nothing is made before consent.'));
    else if (S.problems.length) { const k = shots().findIndex(x => S.problems[0].startsWith(x.id)); kids.push(btn(`Fix line ${k + 1}`, () => { at = k; draw(); }, { go: true }), h('p', {}, S.problems[0].slice(5))); }
    else if (over) kids.push(btn(S.length > 90 ? 'Shorten the script' : 'Lengthen the script', () => $('#f-main').focus(), { go: true }), h('p', {}, 'A film must be 60 to 90 seconds'));
    else if (unread.length) kids.push(btn(`Approve ${n(unread.length, 'line')}`, () => edit({ approve: { script: unread.map(r => r.id) } }), { go: true }), h('p', {}, 'Read every line first. Voices come next.'));
    else if (todo.length) kids.push(...makeVoices(todo));
    else if (unheard.length) kids.push(btn(`Approve ${n(unheard.length, 'voice')}`, () => edit({ approve: { voice: unheard.map(r => r.id) } }), { go: true }), h('p', {}, 'Listen to each one first. Pictures come next.'));
    else kids.push(h('a', { class: 'btn go', href: `#/${id()}/cast` }, 'Choose the cast'));
    footer.replaceChildren(...kids.slice(0, 2), voice, ...kids.slice(2));
  }
  foot();
  return h('div', { class: 'split' },
    h('div', { class: 'lines' }, shots().map((x, i) => { const r = S.rows[i]; return h('button', { type: 'button', 'aria-current': i === at ? 'true' : null, onclick: () => go(i) }, h('i', {}, i + 1), h('em', {}, x.narration[lang()]), h('small', {}, r.voice.fresh ? (r.voice_ok ? '✓ ' : '') + r.voice.seconds + ' s' : 'No voice')); })),
    h('div', { class: 'side' }, h('div', { class: 'head' }, h('h1', {}, `Line ${at + 1}`), row.voice.fresh ? btn('Play', () => play(row.voice.url)) : null, row.voice.fresh ? btn(row.voice_ok ? 'Approved' : 'Approve', () => edit({ approve: { voice: [s.id] }, value: !row.voice_ok }), { on: row.voice_ok }) : null),
      field('main', lang() === 'am' ? 'Amharic' : 'English', s.narration[lang()], 4), lang() !== 'en' && field('en', 'Subtitle', s.narration.en, 3), field('emotion', 'Emotion', s.emotion),
      problems.length ? h('p', { class: 'bad' }, problems.join('\n')) : null,
      row.voice.fresh && !row.voice_ok ? btn('Say it again', async () => { if (await ask('Say this line again?', `The current voice is replaced. ${S.engine === 'gemini' ? 'Uses 1 or 2 voice calls.' : ''}`, 'Say it again')) run('voice', { shots: [s.id], force: true }); }, { job: true }) : null,
      footer));
}
function makeVoices(todo) {
  const label = `Make ${n(todo.length, 'missing voice')}`;
  if (S.engine === 'omnivoice') {
    const g = S.gpu_jobs.voice;
    return g && !g.fetched ? [btn('Collect voices', () => run('voice_fetch'), { go: true, job: true }), sendAgain('voice_submit', {}, 'voice_fetch', 'It uses GPU time again.'), h('p', {}, 'Sent to the Kaggle GPU')] : [btn(label, async () => { if (await ask('Use OmniVoice?', 'Last resort: neutral tone, no emotion, quality untested. It runs on your free GPU hours.', 'Send')) run('voice_submit'); }, { go: true, job: true }), h('p', {}, 'Runs on your GPU hours')];
  }
  if (S.engine === 'addis') return [btn(label, async () => { if (await ask('Make the voices?', `About ${Math.max(1, Math.round(S.length * todo.length / S.rows.length / 60 * 10) / 10)} minutes of speech from your Addis AI credit. Services shows what is left.`, 'Make voices')) run('voice'); }, { go: true, job: true, off: !S.addis_key }), h('p', {}, S.addis_key ? 'Uses your Addis AI credit' : 'Add ADDIS_API_KEY to .env, then restart')];
  const models = [...new Set([S.storyboard.voices[lang()].model || S.storyboard.models.tts, ...(S.storyboard.models.tts_fallbacks || [])])];
  const free = models.reduce((a, m) => a + (L.tts[m] ? (L.tts[m].blocked ? 0 : Math.max(0, L.tts_free - L.tts[m].used)) : L.tts_free), 0);
  if (free < S.voice_calls) return [btn(`${label} at ${clock(L.tts_reset)}`, () => later('voice', {}, L.tts_reset), { go: true }), h('p', {}, 'No free calls left today')];
  return [btn(label, async () => { if (await ask('Make the voices?', `${S.voice_calls === 1 ? 'One call' : n(S.voice_calls, 'call')} if all goes well. If the recording cannot be cut safely, it uses a few more. About ${free} are free today.`, 'Make voices')) run('voice'); }, { go: true, job: true }), h('p', {}, `Uses ${n(S.voice_calls, 'call')}, about ${free} free today`)];
}
/* Choose the people who speak. The service itself is chosen on the Services page. Resolves true when something was saved. */
async function voiceSettings(engine, model) {
  if (!await settle()) return false;
  engine = engine || S.engine;
  const v = S.storyboard.voices[lang()], chars = Object.keys(v.characters || {});
  const slots = h('div', { class: 'stack' }), note = h('p', {});
  let picks = {};
  async function fill() {
    const e = engine; picks = {}; slots.replaceChildren(); note.textContent = '';
    if (e === 'omnivoice') { note.textContent = 'Neutral tone and no choice of voice. The base model is listed as non-commercial. Never tested here.'; for (const c of ['narrator', ...chars]) picks[c] = { value: c }; return; }
    let list = [];
    try { list = await api(e === 'gemini' ? '/api/voices/gemini' : '/api/voices/addis/' + lang()); } catch (err) { note.textContent = /ADDIS_API_KEY/.test(err.message) ? 'Add ADDIS_API_KEY to the .env file, then restart the studio.' : err.message; }
    if (e === 'addis' && list.length) note.textContent = 'Choosing a voice plays its sample. Samples are free.';
    for (const c of ['narrator', ...chars]) {
      const now = c === 'narrator' ? v.voice : v.characters[c].voice;
      const known = list.some(x => x.id === now), start = c === 'narrator' ? Math.max(0, list.findIndex(x => /^(male|man)$/.test(x.gender))) : Math.max(0, list.findIndex(x => /^(female|woman)$/.test(x.gender)));
      picks[c] = list.length ? h('select', {}, !known && e === S.engine ? h('option', { value: now }, now) : null, list.map((x, k) => h('option', { value: x.id, selected: x.id === now || (!known && e !== S.engine && k === start) }, x.name + (x.gender ? `, ${{ male: 'man', female: 'woman' }[x.gender] || x.gender}` : '') + (x.about ? `: ${x.about}` : '')))) : h('input', { value: e === S.engine ? now : '', placeholder: e === 'addis' ? 'Voice id, for example am-hamen' : '' });
      const p = picks[c], url = () => `/api/voices/addis/${lang()}/${p.value}`;
      if (e === 'addis' && list.length) {
        const b = btn('Play', () => { if (!heard.paused && heard.src.endsWith(url())) heard.pause(); else hear(); }, { label: `Hear the ${c} voice` });
        const hear = () => { play(url()); const now = heard, done = () => { if (heard === now) b.textContent = 'Play'; }; document.querySelectorAll('#ask .hear').forEach(x => { x.textContent = 'Play'; }); b.textContent = 'Stop'; now.onpause = done; now.onended = done; now.onerror = () => { done(); toast('This sample could not be loaded.'); }; };
        b.classList.add('hear');
        p.onchange = () => { if (list.find(x => x.id === p.value && x.sample)) hear(); };
        slots.append(h('div', { class: 'pick' }, h('label', {}, c[0].toUpperCase() + c.slice(1), p), b));
      } else slots.append(h('label', {}, c[0].toUpperCase() + c.slice(1), p));
    }
  }
  fill();
  const agreed = h('textarea', { rows: 3, placeholder: 'My mother and father agreed in person on 26 November that the story may go to Addis AI.' }), needs = engine === 'addis' && S.true_story && !S.addis_agreed;
  const choice = await dialog(`Voices by ${ENGINE[engine]}`, [slots, note, needs ? h('label', {}, 'Addis AI may train on what it is sent. Who in this true story agreed to that, when and how?', agreed) : null].filter(Boolean), [['', 'Cancel'], ['yes', 'Use these voices', true]]);
  heard.pause();
  if (choice !== 'yes') return false;
  const body = { engine, narrator: picks.narrator.value, characters: Object.fromEntries(chars.map(c => [c, picks[c].value])), ...(model ? { model } : {}), ...(needs ? { agreed: agreed.value } : {}) };
  if (!body.narrator) { toast('Choose a voice for the narrator.'); return false; }
  const made = S.rows.filter(r => r.voice.fresh).length;
  const people = body.narrator === v.voice && chars.every(c => body.characters[c] === v.characters[c].voice);
  if (engine === S.engine && people && !model) return false;
  if (made && engine === S.engine && !people && !await ask('Change the voice?', `${n(made, 'finished line')} will need making again, and pictures wait until the new voices are approved.`, 'Change')) return false;
  return edit({ voice: body }, 'Voice changed');
}
async function consent() {
  const box = h('textarea', { rows: 4, placeholder: 'My mother agreed in person on 25 November to the story, the public film and her quoted line.' });
  if (await dialog('Consent', [h('p', {}, 'Who agreed, when, how, and to what? Use roles, not names. Write only what people really said.'), box], [['', 'Cancel'], ['yes', 'Record', true]]) === 'yes') edit({ consent: box.value }, 'Consent recorded');
}

/* ---------------- cast ---------------- */
function castPage() {
  const people = Object.entries(S.references).filter(([, r]) => !r.from || S.references[r.from].decided);
  if (!people.length) return h('div', { class: 'empty' }, h('h1', {}, 'No cast needed'), h('p', {}, 'This story has no recurring person or object.'));
  const all = people.flatMap(([name, r]) => r.options.filter(o => o.fresh).map(o => ({ name, ...o })));
  const chosen = all.find(o => face && o.name === face.name && o.seed === face.seed) || all.find(o => S.references[o.name].decided && S.references[o.name].chosen === o.seed) || all[0];
  const next = people.find(([, r]) => r.options.some(o => !o.fresh)), undecided = people.find(([, r]) => !r.decided && r.options.some(o => o.fresh));
  let footer;
  if (S.locked) footer = [btn('Record consent', consent, { go: true })];
  else if (next) {
    const [name, r] = next, count = r.options.filter(o => !o.fresh).length, need = count * 110;
    footer = need > picturesLeft() ? [btn(`Draw ${name.replace(/_/g, ' ')} at ${clock(L.flux_reset)}`, () => later('references', { name }, L.flux_reset), { go: true }), h('p', {}, 'Not enough left today')]
      : [btn(`Draw ${n(count, 'face')} for ${name.replace(/_/g, ' ')}`, () => run('references', { name }), { go: true, job: true }), h('p', {}, spend(count, count * 110))];
  } else if (undecided) footer = [h('p', {}, `Choose a face for ${undecided[0].replace(/_/g, ' ')}`)];
  else footer = [h('a', { class: 'btn go', href: `#/${id()}/shots` }, 'Go to shots')];
  return h('div', { class: 'split' },
    h('div', { class: 'stage' }, h('div', { class: 'frame square' }, chosen ? h('img', { src: chosen.url, alt: chosen.name }) : 'Not drawn yet')),
    h('div', { class: 'side' }, h('div', { class: 'people' }, people.map(([name, r]) => h('section', {}, h('h2', {}, name.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase())), r.options.some(o => o.fresh) ? h('div', { class: 'faces' }, r.options.filter(o => o.fresh).map(o => h('button', { type: 'button', class: 'face', 'aria-label': `${name} ${o.seed}`, 'aria-pressed': String(r.decided && r.chosen === o.seed), onclick: () => pickFace(name, r, o) }, h('img', { src: o.url, alt: '' })))) : h('p', { class: 'soft' }, 'Not drawn yet')))), h('div', { class: 'foot' }, footer)));
}
async function pickFace(name, r, o) {
  face = { name, seed: o.seed };
  if (r.decided && r.chosen === o.seed) return draw();
  const drawn = S.rows.filter(x => r.shots.includes(x.id) && RATIOS.some(k => x['picture_' + k].fresh)).length;
  const older = Object.entries(S.references).filter(([, x]) => x.from === name && x.options.some(o => o.url)).length;
  if (r.decided && (drawn || older) && !await ask('Change this face?', [drawn && `${n(drawn, 'shot')} will need drawing again.`, older && 'The older version will need drawing and choosing again too.'].filter(Boolean).join(' '), 'Change')) return;
  edit({ references: { [name]: { seed: o.seed } } });
}

/* ---------------- shots ---------------- */
function shotsPage() {
  const s = shots()[at], row = S.rows[at], pic = row['picture_' + ratio], clip = row['clip_' + ratio], name = `${s.id}_${ratio}`;
  const shown = show && pic.versions.some(v => v.name === show) ? pic.versions.find(v => v.name === show) : null;
  const media = shown ? h('img', { src: shown.url, alt: '' }) : clip.fresh ? h('video', { src: clip.url, autoplay: true, loop: true, muted: true, playsInline: true }) : pic.url ? h('img', { src: pic.url, alt: `Shot ${at + 1}` }) : 'Not drawn yet';
  const strip = shots().map((x, i) => { const p = S.rows[i]['picture_' + ratio]; return h('button', { type: 'button', 'aria-label': `Shot ${i + 1}`, 'aria-current': i === at ? 'true' : null, onclick: () => go(i) }, h('span', {}, p.url && h('img', { src: p.url, alt: '', loading: 'lazy' })), (p.ok && p.fresh ? '✓ ' : '') + (i + 1)); });
  const castReady = row.cast_ok;
  const drawOne = async () => {
    if (!castReady) return toast('Choose the cast for this shot first.');
    if (!row.voice_ok) return toast('Approve this shot’s voice first.');
    if (S.draw_with === 'kaggle') { const body = { shots: [s.id], ratios: [ratio] }; if (S.gpu_jobs.pictures && !S.gpu_jobs.pictures.fetched) return toast('Collect the pictures already on the GPU first.'); if (!await ask('Draw on the Kaggle GPU?', 'One picture, plus the queue and loading time. It comes back unchecked. Sending every missing picture together is much faster.', 'Send')) return; if (pic.fresh && !await edit({ shots: { [s.id]: { redraw: ratio } } })) return; return run('pictures_submit', body); }
    if (picturesLeft() < pic.cost) return toast(`No pictures left today. The limit resets at ${clock(L.flux_reset)}.`);
    if (pic.fresh) { if (await ask('Draw it again?', `Only the ${ratio === V ? 'vertical' : 'wide'} picture. The current one is kept in versions. ${spend(1, pic.cost)}.`, 'Redraw') && await edit({ shots: { [s.id]: { redraw: ratio } } })) run('pictures', { shots: [s.id], ratios: [ratio] }); } else run('pictures', { shots: [s.id], ratios: [ratio] });
  };
  const camera = s.motion === 'camera', motion = camera ? 'Free' : clip.fresh ? 'Moving' : S.gpu_jobs.wan && !S.gpu_jobs.wan.fetched ? 'On the GPU' : `About ${CLIP_MIN * 2} GPU minutes`;
  const setMotion = async m => { if ((s.motion || 'clip') === m) return; const drawn = S.storyboard.picture_size === 'light' && RATIOS.some(k => row['picture_' + k].fresh); if (!drawn || await ask('Change the motion?', 'This shot\u2019s picture must be drawn again: moving shots are drawn smaller than still ones.', 'Change')) edit({ shots: { [s.id]: { motion: m } } }); };
  const check = pic.qa && pic.fresh && pic.qa.tries && pic.qa.tries.length ? pic.qa.tries.find(t => t.seed === pic.qa.seed_used) : null;
  return [h('div', { class: 'split' },
    h('div', { class: 'stage' }, pic.versions.length ? h('div', { class: 'versions' }, pic.versions.slice().reverse().map(v => h('button', { type: 'button', 'aria-label': 'Earlier version', 'aria-current': show === v.name ? 'true' : null, onclick: () => { show = show === v.name ? null : v.name; draw(); } }, h('img', { src: v.url, alt: '' })))) : null, h('div', { class: 'frame' + (ratio === W ? ' wide' : '') }, media)),
    h('div', { class: 'side' }, h('div', { class: 'head' }, h('h1', {}, `Shot ${at + 1}`), btn(ratio === V ? 'Vertical' : 'Wide', () => { ratio = ratio === V ? W : V; show = null; draw(); }, { label: 'Switch format' }), pic.fresh ? btn(pic.ok ? 'Approved' : 'Approve', () => edit({ approve: { picture: [name] }, value: !pic.ok }), { on: pic.ok }) : null),
      h('div', { class: 'stack' }, h('div', { class: 'am' }, s.narration[lang()]), lang() !== 'en' && h('p', { class: 'soft' }, s.narration.en)),
      h('div', { class: 'rows' },
        h('div', {}, h('b', {}, 'Voice'), h('span', { class: 'soft' }, row.voice.fresh ? `${row.voice.seconds} s` : 'Not made'), row.voice.fresh ? btn('Play', () => play(row.voice.url)) : h('a', { class: 'btn', href: `#/${id()}/script` }, 'Script')),
        h('div', {}, h('b', {}, 'Picture'), h('span', { class: 'soft' }, shown ? 'Earlier version' : pic.fresh ? (pic.qa && /below/.test(pic.qa.status) ? 'Look closely' : 'Ready') : pic.url ? 'Out of date' : 'Not drawn'), shown ? btn('Use this', async () => { try { await api(`/api/film/${id()}/restore`, { shot: s.id, ratio, name: show }); show = null; await reload(); draw(); } catch (e) { toast(e.message); } }, { job: true }) : pic.ok && pic.fresh ? null : btn(pic.fresh ? 'Redraw' : 'Draw', drawOne, { job: true, off: S.locked })),
        h('div', { class: 'tall' }, h('div', { class: 'between' }, h('b', {}, 'Motion'), h('span', { class: 'soft' }, motion)), h('div', { class: 'seg', role: 'group', 'aria-label': 'Motion' }, btn('Camera move', () => setMotion('camera'), { on: camera, off: clip.fresh }), btn('Real movement', () => setMotion('clip'), { on: !camera, off: clip.fresh })))),
      check && check.check && check.check.problem && check.check.problem !== 'none' && /below/.test(pic.qa.status) ? h('p', { class: 'soft' }, check.check.problem) : null,
      h('div', { class: 'between' }, btn('Edit picture', editPicture)),
      h('div', { class: 'foot' }, shotsFoot()))), h('div', { class: 'strip' }, strip)];
}
async function editPicture() {
  const s = shots()[at], p = h('textarea', { rows: 5, value: s.image_prompt }), m = h('textarea', { rows: 2, value: s.motion_prompt });
  const kinds = { cut: 'Cut', dissolve: 'Dissolve', fadeblack: 'Through black', fadewhite: 'Through white', smoothleft: 'Slide left', smoothright: 'Slide right', smoothup: 'Slide up', circleopen: 'Circle' };
  const now = (s.transition || { type: 'cut' }), t = h('select', {}, Object.entries(kinds).map(([k, x]) => h('option', { value: k, selected: now.type === k }, x)));
  if (await dialog(`Shot ${at + 1}`, [h('label', {}, 'Picture', p), h('label', {}, 'Movement, one small action', m), h('label', {}, 'Arrives by', t)], [['', 'Cancel'], ['yes', 'Save', true]]) !== 'yes') return;
  const v = {};
  if (p.value !== s.image_prompt) v.image_prompt = p.value;
  if (m.value !== s.motion_prompt) v.motion_prompt = m.value;
  if (t.value !== now.type) v.transition = { type: t.value, reason: now.reason };
  if (Object.keys(v).length) edit({ shots: { [s.id]: v } }, 'Saved');
}
function shotsFoot() {
  const main = shotsNext(), g = S.gpu_jobs.wan;
  if (!g || g.fetched || S.locked) return main;
  /* A finished GPU job can always be collected, whatever the next step is. */
  return [...main, btn('Collect moving shots', () => run('motion_fetch'), { job: true }), sendAgain('motion_submit', { ratios: RATIOS }, 'motion_fetch', `It uses about ${S.plan.hours} GPU hours.`)];
}
function shotsNext() {
  if (S.locked) return [btn('Record consent', consent, { go: true })];
  const open = r => r.voice_ok && r.voice.fresh && r.cast_ok;
  for (const x of RATIOS) {
    const need = S.rows.filter(r => open(r) && !r['picture_' + x].fresh);
    if (need.length) {
      const body = { shots: need.map(r => r.id), ratios: [x] }, total = units(need, x), words = `${n(need.length, x === V ? 'vertical picture' : 'wide picture')}`;
      let left = picturesLeft(), fit = 0;
      for (const r of need) { left -= r['picture_' + x].cost; if (left >= 0) fit += 1; }
      const g = S.gpu_jobs.pictures;
      if (g && !g.fetched) return [btn('Collect pictures', () => run('pictures_fetch'), { go: true, job: true }), h('p', {}, `${n(g.items, 'picture')} on the GPU`), sendAgain('pictures_submit', body, 'pictures_fetch', 'It uses GPU time again.')];
      const by = h('div', { class: 'between mid' }, h('span', { class: 'soft' }, 'Draw with ' + DRAW[S.draw_with]), h('a', { class: 'btn', href: `#/${id()}/services` }, 'Change'));
      if (S.draw_with === 'kaggle') return [by, btn(`Draw ${words}`, async () => { if (await ask('Draw on the Kaggle GPU?', 'The same picture model, using your free GPU hours. It has not been tried here yet, and pictures come back unchecked.', 'Send')) run('pictures_submit', body); }, { go: true, job: true }), h('p', {}, 'Uses your GPU hours')];
      if (!fit) return [by, btn(`Draw ${words} at ${clock(L.flux_reset)}`, () => later('pictures', body, L.flux_reset), { go: true }), h('p', {}, 'Today\u2019s free pictures are used up')];
      return [by, btn(`Draw ${words}`, () => run('pictures', body), { go: true, job: true }), h('p', {}, fit < need.length ? `Free limit: ${fit} now, ${need.length - fit} after ${clock(L.flux_reset)}` : spend(need.length, total))];
    }
    const look = S.rows.filter(r => r['picture_' + x].fresh && !r['picture_' + x].ok);
    if (look.length) { const i = S.rows.indexOf(look[0]); return [i === at && ratio === x ? btn('Approve this shot', async () => { if (await edit({ approve: { picture: [`${look[0].id}_${x}`] } })) { const k = S.rows.findIndex(r => r['picture_' + x].fresh && !r['picture_' + x].ok); if (k >= 0) go(k); } }, { go: true }) : btn(`Check ${n(look.length, x === V ? 'vertical picture' : 'wide picture')}`, () => { ratio = x; go(i); }, { go: true }), h('p', {}, 'Same face, right emotion, good hands?')]; }
  }
  const g = S.gpu_jobs.wan;
  if (g && !g.fetched) return [h('p', {}, `${n(g.items, 'clip')} sent at ${clock(g.submitted * 1000)}, about ${CLIP_MIN} minutes each`)];
  if (S.plan.clips.length) return [btn(`Animate ${n(S.plan.clips.length, 'shot')}`, async () => { if (await ask('Send to the GPU?', `About ${S.plan.hours} of ${(L.gpu_free_h - L.gpu_used_h).toFixed(1)} GPU hours left this week, plus the queue.${S.plan.left_out ? ` ${n(S.plan.left_out, 'clip')} left for later so the limit is safe.` : ''}`, 'Send')) run('motion_submit', { ratios: RATIOS }); }, { go: true, job: true }), h('p', {}, `Uses ${S.plan.hours} GPU hours`)];
  if (S.rows.some(r => !r.cast_ok)) return [h('a', { class: 'btn go', href: `#/${id()}/cast` }, 'Finish the cast')];
  const wait = S.rows.filter(r => !open(r)).length;
  if (wait) return [h('a', { class: 'btn go', href: `#/${id()}/script` }, `${n(wait, 'shot')} waiting for a voice`)];
  return [h('a', { class: 'btn go', href: `#/${id()}/film` }, 'Go to film')];
}

/* ---------------- film ---------------- */
let final = false, player = null;
function filmPage() {
  const m = S.storyboard.music, gaps = S.rows.filter(r => !r.voice.fresh).length + RATIOS.reduce((a, x) => a + S.rows.filter(r => !r['picture_' + x].fresh).length, 0);
  const has = S.film[ratio], clips = S.rows.filter((r, i) => shots()[i].motion !== 'camera'), done = x => S.rows.filter(x).length;
  if (final && !has) final = false;
  const frame = h('div', { class: 'frame' + (ratio === W ? ' wide' : '') }), bar = h('div', { class: 'bar' });
  const left = h('div', { class: 'player' }, frame, bar);
  if (final) { frame.append(h('video', { src: has, controls: true, playsInline: true, style: 'object-fit:contain' })); bar.hidden = true; } else preview(frame, bar);
  return h('div', { class: 'split' }, left, h('div', { class: 'side' },
    h('div', { class: 'two' }, btn('Vertical', () => { ratio = V; draw(); }, { on: ratio === V }), btn('Wide', () => { ratio = W; draw(); }, { on: ratio === W })),
    has ? h('div', { class: 'two' }, btn('Preview', () => { final = false; draw(); }, { on: !final }), btn('Final film', () => { final = true; draw(); }, { on: final })) : null,
    h('h2', {}, 'Music'), h('div', { class: 'stack' }, S.scores.map((x, i) => h('div', { class: 'music' }, btn(x.url ? `Score ${i + 1}` : `Score ${i + 1}, not made`, () => chooseMusic(x), { on: m.chosen_seed === x.seed && m.reason !== 'Not chosen yet', off: !x.fresh }), x.url ? btn('Play', e => { if (!heard.paused && heard.src.includes('score_' + x.seed)) { heard.pause(); } else play(x.url); }, { label: `Play score ${i + 1}` }) : null)),
      S.scores.some(x => !x.url) ? (S.gpu_jobs.music && !S.gpu_jobs.music.fetched ? [btn('Collect music', () => run('music_fetch'), { job: true }), sendAgain('music_submit', {}, 'music_fetch', 'It uses about 6 GPU minutes again.')] : btn('Make music', async () => { if (await ask('Send music to the GPU?', 'About 6 GPU minutes, plus the queue.', 'Send')) run('music_submit'); }, { job: true, off: S.locked })) : null),
    h('div', { class: 'rows' }, [['Voices', done(r => r.voice.fresh), shots().length], ['Vertical pictures', done(r => r.picture_9x16.fresh), shots().length], ['Wide pictures', done(r => r.picture_16x9.fresh), shots().length], ['Moving shots', clips.filter(r => r.clip_9x16.fresh).length, clips.length]].map(([k, a, b]) => h('div', { style: 'min-height:44px' }, h('b', {}, k), h('span', { class: 'soft' }, `${a} of ${b}`)))),
    h('div', { class: 'foot' }, final ? h('a', { class: 'btn', href: has, download: `${id()}_${ratio}.mp4` }, 'Download this film') : null, btn('Build final film', () => run('build'), { go: true, job: true, off: gaps > 0 || S.locked }), h('p', {}, gaps ? `${n(gaps, 'part')} still missing` : 'Free, on your laptop, about 30 minutes'))));
}
async function chooseMusic(x) {
  const why = h('input', { value: '', placeholder: 'One sentence' });
  if (await dialog('Why this score?', [why], [['', 'Cancel'], ['yes', 'Use it', true]]) !== 'yes') return;
  if (!why.value.trim()) return toast('Write one sentence about why.');
  edit({ music: { seed: x.seed, reason: why.value.trim() } });
}
/* Plays what exists now, in the browser: pictures or clips, voices, subtitles and music. Nothing is rendered. */
function preview(frame, bar) {
  stopPreview();
  const p = player = { i: -1, voice: new Audio(), music: null, timer: 0, t0: 0, on: false };
  const len = i => Math.max(shots()[i].duration_s, (S.rows[i].voice.fresh ? S.rows[i].voice.seconds : 0) + 0.6), total = shots().reduce((a, _, i) => a + len(i), 0);
  const fill = h('div', { style: 'width:0' }), time = h('span', { class: 'soft' }), mm = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const icon = on => { const ns = 'http://www.w3.org/2000/svg', v = document.createElementNS(ns, 'svg'), d = document.createElementNS(ns, 'path'); v.setAttribute('width', 18); v.setAttribute('height', 18); v.setAttribute('viewBox', '0 0 18 18'); d.setAttribute('d', on ? 'M4 2H8V16H4ZM10 2H14V16H10Z' : 'M5 2 16 9 5 16Z'); d.setAttribute('fill', '#101010'); v.append(d); return v; };
  const toggle = h('button', { type: 'button', class: 'play', 'aria-label': 'Play preview', onclick: () => p.on ? halt() : start() }, icon(false));
  bar.replaceChildren(toggle, h('div', { class: 'meter' }, fill), time);
  time.textContent = `0:00 / ${mm(total)}`;
  function scene(i) {
    const s = shots()[i], r = S.rows[i], pic = r['picture_' + ratio], clip = r['clip_' + ratio];
    const el = clip.fresh ? h('video', { src: clip.url, autoplay: p.on, muted: true, loop: true, playsInline: true }) : pic.url ? h('img', { src: pic.url, alt: '', class: p.on ? 'drift' : '', style: `animation-duration:${len(i)}s` }) : h('span', {}, `Shot ${i + 1}`);
    frame.replaceChildren(el, h('div', { class: 'caption' }, h('span', {}, s.narration.en)));
  }
  function next() {
    if (!p.on || player !== p) return;
    p.i += 1;
    if (p.i >= shots().length) { halt(); p.i = -1; fill.style.width = '0'; return; }
    scene(p.i); p.t0 = performance.now();
    const r = S.rows[p.i];
    if (r.voice.fresh) { p.voice = new Audio(r.voice.url); p.voice.play().catch(() => {}); }
    p.timer = setTimeout(next, len(p.i) * 1000);
  }
  function start() {
    p.on = true; toggle.replaceChildren(icon(true)); toggle.setAttribute('aria-label', 'Pause preview'); heard.pause();
    const x = S.scores.find(x => x.seed === S.storyboard.music.chosen_seed && x.url);
    if (x) { if (!p.music) { p.music = new Audio(x.url); p.music.volume = 0.12; } p.music.play().catch(() => {}); }
    p.i = Math.max(-1, p.i - 1); next(); tick();
  }
  function halt() { p.on = false; clearTimeout(p.timer); p.voice.pause(); if (p.music) p.music.pause(); toggle.replaceChildren(icon(false)); toggle.setAttribute('aria-label', 'Play preview'); if (p.i >= 0 && p.i < shots().length) p.i = Math.max(0, p.i); }
  function tick() { if (player !== p || !p.on) return; let t = (performance.now() - p.t0) / 1000; for (let k = 0; k < p.i; k++) t += len(k); fill.style.width = `${Math.min(100, t / total * 100)}%`; time.textContent = `${mm(t)} / ${mm(total)}`; requestAnimationFrame(tick); }
  p.halt = halt; scene(0);
}
function stopPreview() { if (player) { player.halt(); player = null; } }

/* ---------------- services ---------------- */
async function loadServices(fresh) {
  const want = id();
  if (!SV || SV.film !== want || fresh) { SV = null; svPick = {}; if (page() === 'services') draw(); }
  try { const d = await api(`/api/services/${want}${fresh ? '?fresh' : ''}`); if (S && id() === want) { SV = { ...d, film: want }; if (page() === 'services') draw(); } } catch (e) { toast(e.message); }
}
const when = t => { const d = new Date(t), day = d.toDateString() === new Date().toDateString() ? '' : d.toLocaleDateString([], { weekday: 'short' }) + ' '; return day + clock(t); };
const num = x => Number(x).toLocaleString('en-US', { maximumFractionDigits: 1 });
function left(o) {
  const m = o.meter;
  if (!m) return [h('span', { class: 'bar0' }), h('span', { class: 'left' })];
  const rest = m.full ? 0 : Math.max(0, m.limit - m.used), tip = `${num(m.used)} of ${num(m.limit)} ${m.unit} used${m.source === 'live' ? '' : ', counted here'}${m.reset ? `, resets ${when(m.reset)}` : ''}`;
  return [h('span', { class: 'bar0', title: tip }, h('span', { class: 'meter' }, h('div', { class: rest ? '' : 'over', style: `width:${rest ? Math.min(100, m.used / m.limit * 100) : 100}%` }))),
    h('span', { class: 'left', title: tip }, `${num(o.wait ? 0 : rest)} of ${num(m.limit)} ${m.unit} left`, m.reset ? h('small', {}, `${o.wait ? 'Free again' : 'Resets'} ${when(m.reset)}`) : null)];
}
/* What changes if this option is chosen, said before it happens. */
function consequence(g, o) {
  const done = S.rows.filter(r => r.voice.fresh).length;
  if (g.id === 'voice') {
    const engine = o.id.split(':')[0];
    if (engine === 'gemini' && S.engine === 'gemini') return done ? `${n(done, 'finished line')} stay as they are. The others use ${o.name}.` : `Every line uses ${o.name}.`;
    return `The whole film uses ${engine === 'gemini' ? o.name : ENGINE[engine]}.${done ? ` Your ${n(done, 'finished line')} are kept for if you switch back.` : ''}${engine === 'addis' && S.true_story && !S.addis_agreed ? ' Addis AI may train on it, so the people in this true story must agree first.' : ''}`;
  }
  if (g.id === 'pictures') return 'Finished pictures stay. New ones are drawn here.';
  if (g.id === 'motion') return `Every shot changes to ${o.name.toLowerCase()}. You can still change one shot at a time.${S.storyboard.picture_size === 'light' ? ' Pictures of the shots that change must be drawn again.' : ' Finished clips are kept.'}`;
  return 'Used for new scripts, proofreading and picture checks in every film.';
}
async function chooseService(g, o) {
  let ok = false;
  if (g.id === 'voice') { const [engine, model] = o.id.split(':'); ok = await voiceSettings(engine, model); }
  else if (g.id === 'writing') { try { await api('/api/settings', { writer: o.id }); ok = true; toast('Changed'); } catch (e) { toast(e.message); } }
  else ok = await edit({ services: { [g.id]: o.id } }, 'Changed');
  if (ok) { svPick = {}; loadServices(true); }
}
function servicesPage() {
  if (!SV || SV.film !== id()) return h('div', { class: 'empty' }, h('p', {}, 'Checking your limits'));
  const groups = SV.groups.map(g => {
    const cur = g.options.find(o => o.on), picked = svPick[g.id] ? g.options.find(o => o.id === svPick[g.id]) : null, changed = picked && picked !== cur, chosen = changed ? picked : cur;
    return h('section', { class: 'svc' }, h('h2', {}, g.title), h('div', {}, g.options.map(o => [
      h('button', { type: 'button', class: 'opt', 'aria-pressed': String(o === chosen), onclick: () => { svPick[g.id] = o.id; draw(); } }, h('i', { 'aria-hidden': 'true' }), h('span', { class: 'name' }, o.name, h('small', {}, o.note)), left(o)),
      changed && o === picked ? h('div', { class: 'note' }, h('span', {}, consequence(g, o)), btn('Cancel', () => { delete svPick[g.id]; draw(); }), btn('Switch', () => chooseService(g, o), { on: true, job: true })) : null])));
  });
  return h('div', { class: 'page' }, h('div', { class: 'inner' }, h('div', { class: 'head' }, h('h1', {}, 'Services'), btn('Refresh', () => loadServices(true))), groups));
}

/* ---------------- new film ---------------- */
const creating = () => location.hash === '#/new';
const newFilm = () => { location.hash = '#/new'; };
/* Kept while the studio is open, so going back or an error never loses the story. */
let story = { story: '', language: '', theme: '', audience: '', intent: '', narrator: 'man', true_story: false, consent: '' }, writing = false;
async function goNew() {
  if (dirty && !await settle()) return;
  heard.pause(); stopPreview(); S = null; SV = null;
  const o = await api('/api/options');
  if (creating()) drawNew(o);
}
function drawNew(o) {
  document.title = 'New film | Heritage Studio';
  $('#top').replaceChildren(h('div', { class: 'where' }, h('a', { href: '#/' }, 'Films'), h('strong', {}, 'New film')), h('nav'), h('div'));
  story.language = story.language || Object.keys(o.languages)[0]; story.theme = story.theme || Object.keys(o.themes)[0];
  const keep = (k, e) => { e.addEventListener('input', () => { story[k] = e.type === 'checkbox' ? e.checked : e.value; ready(); }); return e; };
  const list = (k, rows) => keep(k, h('select', {}, rows.map(([v, x]) => h('option', { value: v, selected: story[k] === v }, x))));
  const words = () => story.story.trim().split(/\s+/).filter(Boolean).length;
  const count = h('span', { class: 'soft' }), agreed = h('label', { hidden: !story.true_story }, 'Who agreed, when, how and to what? Roles, not names', keep('consent', h('textarea', { rows: 3, value: story.consent, placeholder: 'My mother agreed in person on 25 November to the story and the public film.' })));
  const write = btn('Write the script', async () => {
    writing = true; ready();
    try {
      const r = await api('/api/draft', story);
      Object.assign(story, { story: '', audience: '', intent: '', true_story: false, consent: '' });
      films = await api('/api/films');
      if (creating()) location.hash = `#/${r.id}/script`; else toast('Your new script is ready.');
    } catch (e) { toast(e.message); } finally { writing = false; if (creating()) drawNew(o); }
  }, { go: true }), hint = h('p');
  function ready() {
    const few = words() < 12, who = story.true_story && story.consent.trim().split(/\s+/).filter(Boolean).length < 8;
    agreed.hidden = !story.true_story;
    count.textContent = `${words()} words`;
    write.disabled = writing || few || who;
    write.textContent = writing ? 'Writing the script' : 'Write the script';
    hint.textContent = writing ? 'This can take a few minutes. You can leave this page.' : few ? 'Tell the story in a few sentences first' : who ? 'Write who agreed, in one sentence' : 'You read and change every line before anything is made';
  }
  $('#view').replaceChildren(h('div', { class: 'split new' },
    h('div', { class: 'tell' }, h('div', { class: 'between mid' }, h('h1', {}, 'Your story'), count), keep('story', h('textarea', { value: story.story, 'aria-label': 'Your story', placeholder: 'Tell it as you would tell a friend. What happened, to whom, and what changed?' })),
      h('p', { class: 'soft' }, `Leave out names and private details: the story goes to ${o.writer}\u2019s free text model${o.writer === 'Google' ? ', which may learn from it' : ''}.`)),
    h('div', { class: 'side' }, h('div', { class: 'two' }, h('label', {}, 'Language', list('language', Object.entries(o.languages))), h('label', {}, 'Narrator', list('narrator', [['man', 'A man'], ['woman', 'A woman']]))),
      h('label', {}, 'Theme', list('theme', Object.entries(o.themes).map(([k, v]) => [k, v.split(':')[0]]))),
      h('label', {}, 'Who is it for?', keep('audience', h('input', { value: story.audience, placeholder: 'My cousins abroad' }))), h('label', {}, 'What should they feel?', keep('intent', h('input', { value: story.intent, placeholder: 'Close to home' }))),
      h('label', { class: 'row' }, keep('true_story', h('input', { type: 'checkbox', checked: story.true_story })), 'It is about real people'), agreed,
      h('div', { class: 'foot' }, write, hint))));
  ready();
}

/* ---------------- home ---------------- */
const STEP = { script: 'Script', cast: 'Cast', shots: 'Shots', film: 'Film' };
let cards = [];
async function goHome() {
  if (dirty && !await settle()) return;
  heard.pause(); stopPreview(); S = null; SV = null;
  [cards, films] = await Promise.all([api('/api/home'), api('/api/films')]);
  if (home()) drawHome();
}
function drawHome() {
  stopPreview();
  document.title = 'Heritage Studio';
  $('#top').replaceChildren(h('div', {}, h('strong', { class: 'brand' }, 'Heritage Studio')), h('nav'), h('div', { class: 'end' }, cards.length ? h('button', { type: 'button', class: 'white', onclick: newFilm }, 'New film') : null));
  if (!cards.length) { $('#view').replaceChildren(h('div', { class: 'empty' }, h('h1', {}, 'Make your first film'), h('p', {}, 'Tell a story. Everything you make stays on this computer.'), btn('New film', newFilm, { go: true }))); return; }
  $('#view').replaceChildren(h('div', { class: 'page' }, h('div', { class: 'inner wide' }, h('h1', {}, 'Your films'), h('div', { class: 'cards' }, cards.map(c => h('a', { class: 'card', href: `#/${c.id}/${c.step}` },
    h('div', { class: 'poster' }, c.poster ? h('img', { src: c.poster, alt: '' }) : null),
    h('div', { class: 'about' }, h('h2', {}, c.title), c.english && c.english !== c.title ? h('span', { class: 'soft' }, c.english) : null,
      h('div', { class: 'stats' }, c.done.filter(d => d[2]).map(([k, a, b]) => h('div', {}, h('div', { class: 'between' }, h('span', { class: 'soft' }, k), h('span', {}, `${a} of ${b}`)), h('div', { class: 'meter' }, h('div', { style: `width:${a / b * 100}%` }))))),
      h('span', { class: 'next' }, c.step === 'film' ? (c.film ? 'Watch the film' : 'Build the film') : `Continue: ${STEP[c.step]}`))))))));
}
/* ---------------- shell ---------------- */
async function go(i) { if (i === at && page() !== 'shots') return; if (!await settle()) return; at = i; show = null; draw(); const a = document.querySelector('.strip [aria-current],.lines [aria-current]'); if (a) a.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
function draw() {
  if (creating()) return;
  if (home()) return drawHome();
  if (!S) return;
  stopPreview();
  at = Math.min(at, shots().length - 1);
  const keep = document.querySelector('.lines') ? document.querySelector('.lines').scrollTop : 0, side = document.querySelector('.side') ? document.querySelector('.side').scrollTop : 0, down = document.querySelector('.page') ? document.querySelector('.page').scrollTop : 0;
  topBar();
  const made = { script: scriptPage, cast: castPage, shots: shotsPage, film: filmPage, services: servicesPage }[page()] || scriptPage;
  $('#view').replaceChildren(...[made()].flat());
  if (document.querySelector('.lines')) document.querySelector('.lines').scrollTop = keep;
  if (document.querySelector('.side')) document.querySelector('.side').scrollTop = side;
  if (document.querySelector('.page')) document.querySelector('.page').scrollTop = down;
  document.title = `${Object.values(S.storyboard.title).pop()} | Heritage Studio`;
}
async function route() {
  if (home()) return goHome();
  if (creating()) return goNew();
  const want = location.hash.split('/')[1];
  if (!films.some(f => f.id === want)) { location.hash = '#/'; return; }
  if (dirty && !await settle()) return;
  if (!S || id() !== want) { [S, L] = await Promise.all([api('/api/film/' + want), api('/api/limits')]); at = 0; face = null; show = null; }
  heard.pause(); draw(); window.scrollTo(0, 0);
  if (page() === 'services') loadServices();
}
function work() {
  const w = $('#work'), p = J.planned;
  if (J.running) { w.hidden = false; const lines = J.log.trim().split('\n').map(x => x.trim()), last = /high demand|retrying|unavailable/.test(lines.slice(-4).join(' ')) ? 'Google is busy, trying again' : (lines.pop() || ''); w.replaceChildren(h('strong', {}, J.label), h('p', { class: 'soft' }, last), h('span', { class: 'soft' }, `${Math.floor(J.seconds / 60)}:${String(J.seconds % 60).padStart(2, '0')}`), btn('Details', details), btn('Stop', async () => { await api('/api/job/stop', {}); poll(); })); }
  else if (J.label && !J.seen && !J.ok) { w.hidden = false; const why = (J.log.trim().split('\n').find(x => /ERROR|Not enough|Stopped/.test(x)) || J.log.trim().split('\n').pop() || '').replace('ERROR: ', ''); w.replaceChildren(h('strong', { class: 'bad' }, J.stopped ? 'Stopped' : 'Did not finish'), h('p', { class: 'soft', title: why }, why), btn('Details', details), btn('Close', () => { J.seen = true; work(); })); }
  else if (p && p.length) { w.hidden = false; w.replaceChildren(h('strong', {}, p.map(x => `${x.label} at ${clock(x.at)}`).join(', ')), h('p', { class: 'soft' }, 'Keep the laptop awake and the studio open.'), btn('Cancel', async () => { await api('/api/plan/cancel', {}); poll(); })); }
  else w.hidden = true;
}
const details = () => dialog(J.label, h('pre', {}, J.log || 'Nothing yet'), [['', 'Close']]);
let timer;
async function poll() {
  clearTimeout(timer);
  try {
    const j = await api('/api/job');
    j.seen = J.seen && J.label === j.label && J.started === j.started && !j.running;
    const change = J.running !== j.running;
    J = j;
    if (wasRunning && !j.running) { await reload(); if (home()) goHome(); else if (!dirty && !(player && player.on)) draw(); if (j.ok) toast(`${j.label}: done`); } else if (change && S && !dirty && !(player && player.on)) draw();
    wasRunning = j.running; work();
  } catch (e) { /* the studio may be restarting */ }
  timer = setTimeout(poll, J.running ? 2000 : 8000);
}
window.addEventListener('hashchange', () => route().catch(e => toast(e.message)));
window.addEventListener('beforeunload', e => { if (dirty) e.preventDefault(); });
(async () => {
  try { films = await api('/api/films'); await route(); poll(); } catch (e) { $('#view').replaceChildren(h('div', { class: 'empty' }, h('h1', {}, 'The studio could not start'), h('p', {}, e.message))); }
})();
