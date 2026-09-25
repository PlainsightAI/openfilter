"""A page that reads each frame's own timings and compares them with the browser's clock.

The last leg of the chain, webvis to browser, is the one nobody can time from
inside the pipeline: by the time a frame is a JPEG on a socket, every filter has
already recorded its numbers and gone. Only the browser knows when the picture
actually arrived.

So the browser has to do the measuring, and for that it needs the frame's
numbers and the frame itself to arrive together. `<img src="/">` cannot do it:
it paints the pixels and drops everything else. This page fetches the multipart
stream itself, splits it, reads the COM segment out of each JPEG and draws the
picture on a canvas, so one instant has both the chain that came with the frame
and `Date.now()`.

No external anything: it is served by the filter it measures, and a page that
needed the network to load would measure the network too.
"""

__all__ = ['TIMINGS_PAGE']

TIMINGS_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>openfilter timings</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
         display: grid; grid-template-columns: minmax(0, 1fr) 6px var(--panel, 30rem);
         min-height: 100vh; }
  @media (max-width: 800px) { body { grid-template-columns: 1fr; } #split { display: none; } }
  canvas { width: 100%; height: auto; display: block; background: #111; }
  aside { padding: 1rem; overflow-x: hidden; }
  /* The table is wider than any sensible default, so the split is draggable rather than guessed:
     the reader gives the numbers the room they need and the picture keeps the rest. */
  #split { cursor: col-resize; background: rgba(128,128,128,.35); }
  #split:hover, #split.dragging { background: rgba(128,128,128,.7); }
  body.dragging { user-select: none; }
  h1 { font-size: 1rem; margin: 0 0 .75rem; }
  pre { margin: 0 0 .5rem; overflow-x: auto; font: inherit; }
  /* No horizontal scrolling inside the log: a column you have to drag a bar to see is a column
     you stop reading. Widen the panel instead, which is what the split handle is for. */
  #chain { max-height: 46vh; overflow-y: auto; overflow-x: hidden;
           border: 1px solid rgba(128,128,128,.35); padding: .5rem; }
  #chain pre { overflow: visible; width: max-content; margin: 0; }
  #chain .head { position: sticky; top: -.5rem; background: Canvas; padding-bottom: .15rem; }
  #chain .frame { border-top: 1px solid rgba(128,128,128,.25); padding-top: .25rem;
                  margin-top: .25rem; }
  .controls { display: flex; gap: 1rem; margin-bottom: .35rem; opacity: .8; }
  .controls label { display: flex; align-items: center; gap: .3rem; cursor: pointer; }
  h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .05em;
       opacity: .65; margin: 1.25rem 0 .35rem; font-weight: 600; }
  h2.src { color: var(--c); opacity: 1; }
  #zone { opacity: .7; }
  section { margin-bottom: .25rem; }
  .note { opacity: .65; margin-top: 1.25rem; }
  #live { margin-bottom: 1rem; }
  #live h2 { margin-top: 0; }
  .clock { font-size: 1.6rem; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
  .age { opacity: .65; }
  .age.stale { opacity: 1; font-weight: 700; }
</style>
<canvas id="view"></canvas>
<div id="split" title="drag to resize"></div>
<aside>
  <h1>frame timings</h1>
  <div id="live">
    <h2>browser clock <span id="zone"></span></h2>
    <div class="clock" id="clock">--:--:--.---</div>
    <div class="age" id="age">waiting for a frame</div>
  </div>
  <div class="controls">
    <label><input type="checkbox" id="follow" checked> follow</label>
    <label><input type="checkbox" id="newest"> newest on top</label>
  </div>
  <div id="chain"><pre class="head"></pre></div>
  <h2>served to this browser, last 200 frames</h2>
  <pre id="stats"></pre>
  <p class="note">The table is the frame's own, read out of its JPEG, in the same
  columns as the subject data. The last two rows are what no filter can record:
  when this browser received the frame, and how far that is from the read.</p>
</aside>
<script>
const canvas = document.getElementById('view');
const ctx = canvas.getContext('2d');
const chain = document.getElementById('chain');
const stats = document.getElementById('stats');
const deltas = [];
let lastTs = null;   // the read stamp of the frame on screen, for the age readout

const clock = t => new Date(t * 1000).toLocaleTimeString('en-GB', { hour12: false }) +
                   '.' + String(Math.floor((t % 1) * 1000)).padStart(3, '0');
const ms = v => (v >= 1000 ? (v / 1000).toFixed(2) + ' s' : Math.round(v) + ' ms');

const NL = String.fromCharCode(10);
const pad = (v, w, right) => right ? String(v).padStart(w) : String(v).padEnd(w);

// Same columns the terminal script prints from the subject data, so the two can be read side by
// side without converting anything. Raw epoch, not a clock, for the same reason.
// One block per frame, appended, so the panel reads like the log it mirrors: you watch the numbers
// move rather than watching one row rewrite itself. Older frames are dropped once there are more
// than KEEP of them, and the view follows the bottom unless the reader has scrolled up to look at
// something, which is the one time auto-scrolling is a nuisance.
const KEEP = 60;
const COLS = [4, 8, 19, 19, 10, 12];
const HEADER = ['ID', 'FILTER', 'TIME IN', 'TIME OUT', 'TOTAL MS', 'CLOCK'];
const at = t => new Date(t * 1000).toLocaleTimeString('en-GB', { hour12: false }) +
                '.' + String(Math.floor((t % 1) * 1000)).padStart(3, '0');
const line = cells => cells.map((cell, c) => pad(cell, COLS[c], c >= 2)).join('  ');

function render(t, browser) {
  const filters = t.filters || [];

  if (!filters.length) return 'no timings in this frame';

  const id = String(t.id != null ? t.id : '-');
  const total = ((filters[filters.length - 1].out - filters[0]['in']) * 1000).toFixed(3);
  const rows = filters.map(f =>
    line([id, String(f.name || '?'), f['in'].toFixed(6), f.out.toFixed(6), total, at(f['in'])]));

  if (t.served != null) {
    rows.push(line([id, 'served', t.served.toFixed(6), '', '', at(t.served)]));
  }

  rows.push(line([id, 'browser', browser.toFixed(6), '',
                  t.ts != null ? ((browser - t.ts) * 1000).toFixed(3) : '', at(browser)]));

  return rows.join(NL);
}

// `follow` off freezes the view where the reader left it while frames keep arriving, which is the
// only way to read a row that is three seconds old on a live stream. `newest on top` puts the
// arriving frame where the eye already is, so following needs no scrolling at all.
function append(text) {
  const follow = document.getElementById('follow').checked;
  const newest = document.getElementById('newest').checked;
  const head = chain.querySelector('.head');
  const block = document.createElement('pre');

  block.className = 'frame';
  block.textContent = text;

  if (newest) {
    head.after(block);
  } else {
    chain.appendChild(block);
  }

  const frames = chain.querySelectorAll('.frame');

  for (let i = KEEP; i < frames.length; i++) frames[newest ? i : frames.length - 1 - i].remove();
  if (follow) chain.scrollTop = newest ? 0 : chain.scrollHeight;
}

// The JPEG spec's COM segment (0xFFFE): walk the markers from SOI, skip the ones that carry no
// length, and stop at SOS, after which there are no more headers, only entropy-coded data.
function readComment(bytes) {
  let i = 2;
  while (i + 4 <= bytes.length && bytes[i] === 0xFF) {
    const marker = bytes[i + 1];
    if (marker === 0xD8 || marker === 0xD9 || (marker >= 0xD0 && marker <= 0xD7)) { i += 2; continue; }
    const len = (bytes[i + 2] << 8) | bytes[i + 3];
    if (marker === 0xFE) return new TextDecoder().decode(bytes.subarray(i + 4, i + 2 + len));
    if (marker === 0xDA) return null;
    i += 2 + len;
  }
  return null;
}

function show(bytes, arrived) {
  const raw = readComment(bytes);
  createImageBitmap(new Blob([bytes], { type: 'image/jpeg' })).then(bitmap => {
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    ctx.drawImage(bitmap, 0, 0);
    bitmap.close();
  });

  if (!raw) return;

  // A truncated or malformed payload must not take the page down with it: show() runs inside the
  // reader loop, so an uncaught throw here rejects run() and the picture freezes for good, with
  // the clock still ticking beside it. That is the exact symptom this page exists to tell apart
  // from a stalled pipeline.
  let t;
  try {
    t = JSON.parse(raw);
  } catch (err) {
    return;
  }

  const browser = arrived / 1000;
  lastTs = t.ts != null ? t.ts : null;

  append(render(t, browser));

  if (t.served != null) {
    deltas.push((browser - t.served) * 1000);
    if (deltas.length > 200) deltas.shift();
    const sorted = [...deltas].sort((a, b) => a - b);
    stats.textContent = [
      'samples  ' + deltas.length,
      'min      ' + ms(sorted[0]),
      'median   ' + ms(sorted[sorted.length >> 1]),
      'max      ' + ms(sorted[sorted.length - 1]),
    ].join('\\n');
  }
}

// Split the multipart stream by SOI/EOI rather than by the boundary string: the boundary is only
// a delimiter, while these two markers are the JPEG itself, so a part that arrives split across
// several reads still yields exactly one complete image.
async function run() {
  const reader = (await fetch(STREAM_URL)).body.getReader();
  let buffer = new Uint8Array(0);

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    const merged = new Uint8Array(buffer.length + value.length);
    merged.set(buffer);
    merged.set(value, buffer.length);
    buffer = merged;

    for (;;) {
      const start = indexOf(buffer, 0xFF, 0xD8, 0);
      if (start < 0) break;
      const end = indexOf(buffer, 0xFF, 0xD9, start + 2);
      if (end < 0) {
        if (start > 0) buffer = buffer.subarray(start);
        break;
      }
      show(buffer.subarray(start, end + 2), Date.now());
      buffer = buffer.subarray(end + 2);
    }
  }
}

function indexOf(bytes, a, b, from) {
  for (let i = from; i + 1 < bytes.length; i++) if (bytes[i] === a && bytes[i + 1] === b) return i;
  return -1;
}

// This clock runs on its own, not on frame arrivals, because the case worth catching is the one
// where frames stop: the picture freezes, every number in the table freezes with it, and only a
// clock that keeps moving shows that what you are looking at is no longer now.
// Every time on this page is rendered in the browser's zone, including the frame's own numbers,
// which the filter drew in the container's. Same instants, different clocks on screen, so both
// sides say which one they are.
document.getElementById('zone').textContent =
  '(' + new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' })
        .formatToParts(new Date()).find(p => p.type === 'timeZoneName').value + ')';

function tick() {
  const now = Date.now() / 1000;
  document.getElementById('clock').textContent = clock(now);

  const age = document.getElementById('age');
  if (lastTs === null) {
    age.textContent = 'waiting for a frame';
    age.className = 'age';
  } else {
    const behind = (now - lastTs) * 1000;
    age.textContent = 'frame is ' + ms(behind) + ' old';
    age.className = behind > 1000 ? 'age stale' : 'age';
  }
  requestAnimationFrame(tick);
}

chain.querySelector('.head').textContent = line(HEADER);

// Width survives a reload, because the first thing anyone does on this page is widen the panel and
// nobody wants to do it twice.
const saved = localStorage.getItem('panel');
if (saved) document.body.style.setProperty('--panel', saved);

document.getElementById('split').addEventListener('mousedown', down => {
  down.preventDefault();
  document.body.classList.add('dragging');

  const move = e => {
    const width = Math.min(Math.max(window.innerWidth - e.clientX, 240), window.innerWidth - 120);
    document.body.style.setProperty('--panel', width + 'px');
  };
  const up = () => {
    document.body.classList.remove('dragging');
    localStorage.setItem('panel', document.body.style.getPropertyValue('--panel'));
    removeEventListener('mousemove', move);
    removeEventListener('mouseup', up);
  };

  addEventListener('mousemove', move);
  addEventListener('mouseup', up);
});

const STREAM_URL = new URL(window.location.href).searchParams.get('topic') || '/';
tick();
run().catch(err => {
  document.getElementById('age').textContent = 'stream ended: ' + err;
  document.getElementById('age').className = 'age stale';
});
</script>
"""
