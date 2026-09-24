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
         display: grid; grid-template-columns: minmax(0, 1fr) 22rem; min-height: 100vh; }
  @media (max-width: 800px) { body { grid-template-columns: 1fr; } }
  canvas { width: 100%; height: auto; display: block; background: #111; }
  aside { padding: 1rem; border-left: 1px solid rgba(128,128,128,.35); }
  h1 { font-size: 1rem; margin: 0 0 .75rem; }
  table { width: 100%; border-collapse: collapse; }
  td { padding: .15rem 0; vertical-align: top; }
  td:last-child { text-align: right; white-space: nowrap; }
  tr.gap td { font-weight: 700; }
  .label { opacity: .65; }
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
<aside>
  <h1>frame timings</h1>
  <div id="live">
    <h2>system clock <span id="zone"></span></h2>
    <div class="clock" id="clock">--:--:--.---</div>
    <div class="age" id="age">waiting for a frame</div>
  </div>
  <div id="chain"></div>
  <h2>webvis &rarr; browser, last 200 frames</h2>
  <table id="stats"></table>
  <p class="note">The clock above is this machine's, running on its own. Every
  other number is the frame's own, read out of its JPEG and shown in this
  browser's zone; the blocks drawn on the picture use the container's.</p>
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

function rows(table, pairs) {
  table.innerHTML = pairs.map(([label, value, cls]) =>
    `<tr class="${cls || ''}"><td class="label">${label}</td><td>${value}</td></tr>`).join('');
}

function table(pairs) {
  return '<table>' + pairs.map(([label, value, cls]) =>
    `<tr class="${cls || ''}"><td class="label">${label}</td><td>${value}</td></tr>`).join('') +
    '</table>';
}

// The block colours the overlay draws, so a section in the panel and its block in the picture are
// recognisably the same filter.
const CORNER_COLORS = ['#00ff00', '#00ffff', '#ffbf00', '#ff00ff'];

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

  if (!raw) {
    chain.innerHTML = table([['no timings in this frame', 'set FILTER_TIMINGS=true']]);
    return;
  }

  const t = JSON.parse(raw);
  const browser = arrived / 1000;
  lastTs = t.ts != null ? t.ts : null;
  const filters = t.filters || [];
  let html = '';

  // One section per filter, in pipeline order, so the panel is read the same way the picture is:
  // who did what, and when. Anything that is not a filter's own number lives in its own section
  // below, rather than being mixed in where it would look like one.
  filters.forEach((f, i) => {
    const pairs = [];

    if (i === 0 && t.ts != null) pairs.push(['read (ts)', clock(t.ts)]);

    pairs.push(['in', clock(f['in'])]);
    pairs.push(['out', clock(f.out)]);
    pairs.push(['took', ms(f.duration_ms)]);

    if (i === filters.length - 1 && t.served != null) pairs.push(['served', clock(t.served)]);

    html += `<section><h2 class="src" style="--c:${CORNER_COLORS[i % 4]}">${f.name}</h2>` +
            table(pairs) + '</section>';
  });

  const gaps = [];

  if (t.ts != null && t.served != null) gaps.push(['inside the pipeline', ms((t.served - t.ts) * 1000)]);
  if (t.served != null) {
    const delta = (browser - t.served) * 1000;
    gaps.push(['served \u2192 this browser', ms(delta)]);
    deltas.push(delta);
    if (deltas.length > 200) deltas.shift();
    const sorted = [...deltas].sort((a, b) => a - b);
    rows(stats, [
      ['samples', deltas.length],
      ['min', ms(sorted[0])],
      ['median', ms(sorted[sorted.length >> 1])],
      ['max', ms(sorted[sorted.length - 1])],
    ]);
  }
  if (t.ts != null) gaps.push(['read \u2192 on screen', ms((browser - t.ts) * 1000), 'gap']);

  html += '<section><h2>gaps</h2>' + table(gaps) + '</section>';
  chain.innerHTML = html;
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

const STREAM_URL = new URL(window.location.href).searchParams.get('topic') || '/';
tick();
run();
</script>
"""
