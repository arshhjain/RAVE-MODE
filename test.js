
window.onerror = function(msg, url, line, col, error) { alert(msg + ' at ' + line + ':' + col); };
// ── Drag interceptors ──────────────────────────────────────────────────
['knob-section', 'palette-section', 'settings', 'track-info'].forEach(id => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener('mousedown',  e => e.stopPropagation());
  el.addEventListener('touchstart', e => e.stopPropagation());
});

// ── Spotify-style marquee ──────────────────────────────────────────────
// Behaviour:
//   1. Pause at start (1.4s)
//   2. Scroll left at constant speed until end of text is visible
//   3. Pause at end (1.4s)
//   4. Jump instantly back to start, repeat
//
// Driven by a single rAF loop with a state machine — no CSS animation,
// no fighting between transform and animation properties.

// ── Spotify-style marquee ──────────────────────────────────────────────
const MQ_SPEED    = 40;
const MQ_PAUSE_MS = 1400;

let mqRAF      = null;
let mqState    = 'idle';
let mqX        = 0;
let mqTimer    = 0;
let mqOverflow = 0;
let mqLast     = 0;

function mqStop() {
  if (mqRAF) { cancelAnimationFrame(mqRAF); mqRAF = null; }
  mqState = 'idle';
}

function mqSetTrack(track) {
  mqStop();
  const el = document.getElementById('title-text');
  const wr = document.getElementById('title-wrap');

  wr.style.webkitMaskImage = 'none';
  wr.style.maskImage       = 'none';
  el.style.transition      = 'none';
  el.style.transform       = 'translateX(0)';
  el.textContent           = track;

  requestAnimationFrame(() => requestAnimationFrame(() => {
    const overflow = el.scrollWidth - wr.clientWidth;

    if (overflow <= 2) {
      wr.style.textAlign       = 'center';
      wr.style.webkitMaskImage = '';
      wr.style.maskImage       = '';
      return;
    }

    wr.style.textAlign       = 'left';
    wr.style.webkitMaskImage = 'linear-gradient(to right, transparent 0%, black 4%, black 96%, transparent 100%)';
    wr.style.maskImage       = 'linear-gradient(to right, transparent 0%, black 4%, black 96%, transparent 100%)';

    mqOverflow = overflow;
  mqX        = mqOverflow / 2;   // ← start offset to the right by half overflow
  mqTimer    = MQ_PAUSE_MS;
  mqState    = 'pause-start';
  mqLast     = performance.now();
  mqRAF      = requestAnimationFrame(mqTick);

  }));
}

function mqTick(now) {
  const dt = Math.min(now - mqLast, 50);
  mqLast   = now;
  const el = document.getElementById('title-text');

  switch (mqState) {

    case 'pause-start':
      mqTimer -= dt;
      if (mqTimer <= 0) mqState = 'scroll-fwd';
      break;

case 'scroll-fwd':
  mqX -= MQ_SPEED * (dt / 1000);
  if (mqX <= -(mqOverflow / 2)) {   // ← end at half overflow left
    mqX     = -(mqOverflow / 2);
    el.style.transform = `translateX(${mqX.toFixed(2)}px)`;
    mqState = 'pause-end';
    mqTimer = MQ_PAUSE_MS;
    mqRAF   = requestAnimationFrame(mqTick);
    return;
  }
  el.style.transform = `translateX(${mqX.toFixed(2)}px)`;
  break;

case 'scroll-back':
  mqX += MQ_SPEED * (dt / 1000);
  if (mqX >= mqOverflow / 2) {      // ← return to start offset, not 0
    mqX     = mqOverflow / 2;
    el.style.transform = `translateX(${mqX.toFixed(2)}px)`;
    mqState = 'pause-start';
    mqTimer = MQ_PAUSE_MS;
    mqRAF   = requestAnimationFrame(mqTick);
    return;
  }
  el.style.transform = `translateX(${mqX.toFixed(2)}px)`;
  break;

    case 'pause-end':
      mqTimer -= dt;
      if (mqTimer <= 0) mqState = 'scroll-back';
      break;

    case 'scroll-back':
      mqX += MQ_SPEED * (dt / 1000);
      if (mqX >= 0) {
        mqX     = 0;
        el.style.transform = 'translateX(0)';
        mqState = 'pause-start';
        mqTimer = MQ_PAUSE_MS;
        mqRAF   = requestAnimationFrame(mqTick);
        return;
      }
      el.style.transform = `translateX(${mqX.toFixed(2)}px)`;
      break;
  }

  mqRAF = requestAnimationFrame(mqTick);
}

// ── WebSocket ──────────────────────────────────────────────────────────
let ws         = null;
let cache      = { knobs: {} };
let lastTrack  = null;
let cfgSeeded  = false;
let activeDrags = 0;

function wsSend(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function connectWS() {
  const host = window.location.hostname;
  const url  = `ws://${host}:7373/ws`;
  try { ws = new WebSocket(url); }
  catch(e) { setTimeout(connectWS, 600); return; }
  ws.onopen    = () => {}
  ws.onmessage = e => onFrame(JSON.parse(e.data));
  ws.onerror   = () => {};
  ws.onclose   = () => {
    {}
    setTimeout(connectWS, 600);
  };
}
connectWS();

document.getElementById('min-btn').onclick   = () => wsSend({type:'window', action:'minimize'});
document.getElementById('close-btn').onclick = () => wsSend({type:'window', action:'close'});
document.getElementById('hb-btn').onclick    = toggleSettings;

// ── Log scale helpers ──────────────────────────────────────────────────
const logToActual = (n,mn,mx) => { mn=Math.max(mn,1e-9); return mn*Math.pow(mx/mn,n); };
const actualToNorm= (a,mn,mx) => { mn=Math.max(mn,1e-9); a=Math.max(a,mn); return Math.log(a/mn)/Math.log(mx/mn); };
const normDisp    = n => Math.max(1,Math.min(100,Math.round(n*99)+1));

// ── Knob definitions ───────────────────────────────────────────────────
const MAIN_K = [
  {
    key: 'sensitivity', label: 'Sensitivity', mn: .1, mx: 2.5, log: 0,
    tip: {
      desc: 'Overall audio reactivity.',
      high: 'Flashes to quiet sounds & whispers',
      low: 'Only hits on loud prominent beats'
    },
    fmt: (v,mn,mx)=>Math.round(1 + ((v-0.1)/(2.5-0.1))*9).toString()
  },
  {
    key: 'brightness', label: 'Ambient', mn: .01, mx: 1.0, log: 1,
    tip: {
      desc: 'Resting background ambient glow.',
      high: 'Bright room-filling ambient floor',
      low: 'Near-black darkness between beats'
    },
    fmt: (v,mn,mx)=>Math.round(1 + ((v-0.01)/(1.0-0.01))*9).toString()
  },
  {
    key: 'responsiveness', label: 'Responsiveness', mn: 0, mx: 0.60, log: 0,
    tip: {
      desc: 'Reaction speed of the lights.',
      high: 'Fast, snappy, instant flickers',
      low: 'Smooth, floating, relaxed fades'
    },
    fmt: (v,mn,mx)=>Math.round(1 + ((v-0)/(0.60-0))*9).toString()
  }
];
const DYN_K = [
  {
    key: 'responsiveness', label: 'Response', mn: 0.0, mx: 0.60, log: 0,
    tip: {
      desc: 'Envelope attack & fade speed.',
      high: 'Snappy, energetic party tempo',
      low: 'Calm, slow-breathing lounge tempo'
    }
  },
  {
    key: 'attack_gamma', label: 'Attack Curve', mn: 1.0, mx: 2.5, log: 0,
    tip: {
      desc: 'How beats bloom from darkness.',
      high: 'Soft analog swell (gentle on eyes)',
      low: 'Instant, punchy strobe hits'
    }
  },
  {
    key: 'decay_gamma', label: 'Decay Curve', mn: 0.8, mx: 2.5, log: 0,
    tip: {
      desc: 'How beats fade back to black.',
      high: 'Quick fade that cleanly settles',
      low: 'Long, lingering sustained light'
    }
  },
];
const BASS_K = [
  {
    key: 'bass_intensity', label: 'Bass Drive', mn: .01, mx: .30, log: 1,
    tip: {
      desc: 'Kick drum & 808 blast power.',
      high: 'Huge, room-shaking bass flashes',
      low: 'Subtle, restrained bass thump'
    }
  },
  {
    key: 'bass_width', label: 'Bass Width', mn: 2, mx: 0, log: 0, dyn: () => (cache.knobs.led_count || 108) * .8,
    tip: {
      desc: 'Physical spread of bass pulses.',
      high: 'Expands across the entire strip',
      low: 'Tight, punchy center blast'
    }
  },
];
const TREBLE_K = [
  {
    key: 'treble_intensity', label: 'Treble Drive', mn: .10, mx: 2.0, log: 1,
    tip: {
      desc: 'Brightness of hi-hats & vocals.',
      high: 'Crisp, piercing sparkles on highs',
      low: 'Mellow, gentle high notes'
    }
  },
  {
    key: 'treble_sens', label: 'Treble Sens', mn: .5, mx: 3.0, log: 0,
    tip: {
      desc: 'Treble volume relative to bass.',
      high: 'Highs punch through heavy bass',
      low: 'Bass dominates the lighting'
    }
  },
  {
    key: 'treble_width', label: 'Treble Width', mn: 2, mx: 0, log: 0, dyn: () => (cache.knobs.led_count || 108) * .5,
    tip: {
      desc: 'Physical size of treble flashes.',
      high: 'Wide, sweeping light bursts',
      low: 'Sharp, pinpoint sparks'
    }
  },
  {
    key: 'treble_zone', label: 'Treble Zone', mn: 0, mx: 0, log: 0, dyn: () => (cache.knobs.led_count || 108) * .4, isInt: 1,
    tip: {
      desc: 'Where treble sparks ignite.',
      high: 'Sparks move inward toward center',
      low: 'Sparks stay at outer strip edges'
    }
  },
];

// ── Knob arc SVG ───────────────────────────────────────────────────────
const S=220, SPAN=260, CX=32, CY=32, R=24;
function pt(deg){ const r=(deg-90)*Math.PI/180; return [CX+R*Math.cos(r), CY+R*Math.sin(r)]; }
function arc(norm){
  const sw=Math.max(.001, SPAN*norm);
  const [x1,y1]=pt(S), [x2,y2]=pt(S+sw);
  return `M${x1} ${y1} A${R} ${R} 0 ${sw>180?1:0} 1 ${x2} ${y2}`;
}

// ── Build knob ─────────────────────────────────────────────────────────
function buildKnob(d, container){
  const w=document.createElement('div'); w.className='knob-wrap';
  w.innerHTML=`
    <div class="knob-label">${d.label}</div>
    <div class="knob-ring"><svg viewBox="0 0 64 64">
      <path d="M${pt(S)[0]} ${pt(S)[1]} A${R} ${R} 0 1 1 ${pt(S+SPAN)[0]} ${pt(S+SPAN)[1]}"
            fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="5" stroke-linecap="round"/>
      <path class="fg" d="${arc(.01)}" fill="none" stroke="#00f0ff" stroke-width="5" stroke-linecap="round"/>
    </svg></div>
    <div class="knob-value">—</div>`;
  container.appendChild(w);

  w.addEventListener('mouseenter', () => {
    if (dragging || activeDrags > 0) return;
    showGlobalTip(w, d.tip);
  });
  w.addEventListener('mouseleave', hideGlobalTip);

  const fg=w.querySelector('.fg'), vl=w.querySelector('.knob-value');
  const getMax=()=>d.dyn?d.dyn():d.mx;
  let dragging=false, dn=0;
  let lastUserTouch=0;
  let lastSendTime=0;

  function refresh(knobs){
    if (dragging) return;
    // Suppress echo frames from server while or immediately after user adjusted knob
    if (performance.now() - lastUserTouch < 500) return;
    const a=knobs[d.key]; if(a==null)return;
    const mx=getMax();
    const n=d.log?actualToNorm(a,d.mn,mx):(a-d.mn)/(mx-d.mn||1);
    fg.setAttribute('d', arc(n));
    vl.textContent = Math.round(n * 100) + "%";
  }

  w.onpointerdown=e=>{
    hideGlobalTip();
    e.stopPropagation(); e.preventDefault();
    dragging=true; activeDrags++;
    lastUserTouch=performance.now();
    w.setPointerCapture(e.pointerId);
    const a=cache.knobs[d.key]??d.mn, mx=getMax();
    dn=d.log?actualToNorm(a,d.mn,mx):(a-d.mn)/(mx-d.mn||1);
  };

  w.onpointermove=e=>{
    if(!dragging)return;
    lastUserTouch=performance.now();
    dn=Math.max(0,Math.min(1, dn-e.movementY/150));
    const mx=getMax();
    let val=d.log?logToActual(dn,d.mn,mx):d.mn+dn*(mx-d.mn);
    if(d.isInt) val=Math.round(val);
    fg.setAttribute('d', arc(dn));
    vl.textContent = Math.round(dn * 100) + "%";
    if(cache.knobs) cache.knobs[d.key]=val;

    const now=performance.now();
    if(now - lastSendTime > 28){
      wsSend({type:'knob', key:d.key, value:val});
      lastSendTime=now;
    }
  };

  const endDrag=()=>{
    if(!dragging) return;
    dragging=false; activeDrags=Math.max(0,activeDrags-1);
    hideGlobalTip();
    lastUserTouch=performance.now();
    const mx=getMax();
    let val=d.log?logToActual(dn,d.mn,mx):d.mn+dn*(mx-d.mn);
    if(d.isInt) val=Math.round(val);
    wsSend({type:'knob', key:d.key, value:val});
  };

  w.onpointerup    = endDrag;
  w.onpointercancel= endDrag;

  w.addEventListener('wheel', e => {
    e.preventDefault();
    hideGlobalTip();
    lastUserTouch = performance.now();
    
    const a = cache.knobs[d.key] ?? d.mn;
    const mx = getMax();
    let currentDn = d.log ? actualToNorm(a, d.mn, mx) : (a - d.mn) / (mx - d.mn || 1);
    
    currentDn = Math.max(0, Math.min(1, currentDn - e.deltaY / 1500));
    
    let val = d.log ? logToActual(currentDn, d.mn, mx) : d.mn + currentDn * (mx - d.mn);
    if(d.isInt) val = Math.round(val);
    
    fg.setAttribute('d', arc(currentDn));
    vl.textContent = Math.round(currentDn * 100) + "%";
    
    if(cache.knobs) cache.knobs[d.key] = val;
    
    const now = performance.now();
    if(now - lastSendTime > 28) {
      wsSend({type:'knob', key:d.key, value:val});
      lastSendTime = now;
    }
    
    clearTimeout(w._wheelTimer);
    w._wheelTimer = setTimeout(() => {
      wsSend({type:'knob', key:d.key, value:val});
    }, 50);
  }, { passive: false });

  return {refresh};
}

const mainW   = MAIN_K.map(k => buildKnob(k, document.getElementById('main-knobs')));

// ── Vibe Slider & Power Toggle ──────────────────────────────────────
const vibeVals = [0.08, 0.19, 0.68, 1.0];
document.getElementById('vibe-slider').addEventListener('input', e => {
  const v = vibeVals[e.target.value];
  wsSend({type:'knob', key:'saturation', value:v});
});
document.getElementById('power-toggle').addEventListener('change', e => {
  wsSend({type:'knob', key:'power', value:e.target.checked});
});

// ── Inactive Auto-Dimming ──────────────────────────────────────────
let inactiveTimer = null;
const appEl = document.getElementById('app');
function resetInactiveTimer() {
  appEl.classList.remove('inactive');
  clearTimeout(inactiveTimer);
  inactiveTimer = setTimeout(() => {
    appEl.classList.add('inactive');
  }, 2500);
}
window.addEventListener('mousemove', resetInactiveTimer);
window.addEventListener('mousedown', resetInactiveTimer);
window.addEventListener('keydown', resetInactiveTimer);
resetInactiveTimer();

const dynW    = DYN_K.map(k => buildKnob(k, document.getElementById('knobs-dynamics')));
const bassW   = BASS_K.map(k => buildKnob(k, document.getElementById('knobs-bass')));
const trebleW = TREBLE_K.map(k => buildKnob(k, document.getElementById('knobs-treble')));
const allAdvW = [...dynW, ...bassW, ...trebleW];

// ── Fluid Background Canvas ───────────────────────────────────────────
const fluidEl = document.getElementById('fluid-bg');
const fluidCtx = fluidEl.getContext('2d');
let fluidTime = 0;

function resizeFluid() {
  fluidEl.width = window.innerWidth;
  fluidEl.height = window.innerHeight;
}
window.addEventListener('resize', resizeFluid);
resizeFluid();

function boostSaturation(r, g, b, factor) {
  r/=255; g/=255; b/=255;
  const max=Math.max(r,g,b), min=Math.min(r,g,b), d=max-min;
  let h=0, s=max===0?0:d/max, v=max;
  if(d!==0){
    if     (max===r) h=((g-b)/d)%6;
    else if(max===g) h=(b-r)/d+2;
    else             h=(r-g)/d+4;
    h/=6; if(h<0) h+=1;
  }
  if (factor <= 1.0) {
    s = s * Math.max(0, factor);
  } else {
    s = Math.min(1.0, s + (1.0 - s) * (factor - 1.0) * 0.85);
  }
  const i=Math.floor(h*6), f=h*6-i,
        p=v*(1-s), q=v*(1-f*s), t=v*(1-(1-f)*s);
  let ro,go,bo;
  switch(i%6){
    case 0:ro=v;go=t;bo=p;break; case 1:ro=q;go=v;bo=p;break;
    case 2:ro=p;go=v;bo=t;break; case 3:ro=p;go=q;bo=v;break;
    case 4:ro=t;go=p;bo=v;break; case 5:ro=v;go=p;bo=q;break;
  }
  return [ro*255, go*255, bo*255];
}

function p3(r, g, b, a=1) {
  return `rgba(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)}, ${a.toFixed(3)})`;
}

function drawFluid(pal, bass, treble) {
  if (!pal || !pal.length) return;
  const W = fluidEl.width, H = fluidEl.height;
  fluidCtx.clearRect(0,0,W,H);

  const sat     = cache.knobs ? (cache.knobs.saturation ?? 1.0) : 1.0;
  const bgLevel = cache.knobs ? (cache.knobs.brightness ?? 0.15) : 0.15;
  const boosted = pal.map(([r,g,b]) => boostSaturation(r, g, b, sat));

  fluidTime += 0.005 + (bass * 0.02);

  // Background ambient (pal[0])
  fluidCtx.fillStyle = p3(...boosted[0], 0.2 + bgLevel * 0.5);
  fluidCtx.fillRect(0, 0, W, H);

  fluidCtx.globalCompositeOperation = 'screen';

  // Multiple Bass Blobs
  const bScale = 1.0 + (bass * 1.5);
  for (let i = 0; i < 4; i++) {
      const phase = i * Math.PI / 2;
      const bX = W * 0.5 + Math.sin(fluidTime * (0.8 + i*0.1) + phase) * (W * 0.4);
      const bY = H * 0.5 + Math.cos(fluidTime * (0.6 + i*0.1) - phase) * (H * 0.4);
      const bRadius = (Math.min(W, H) * (0.3 + i*0.05)) * bScale;
      
      const bgRad = fluidCtx.createRadialGradient(bX, bY, 0, bX, bY, bRadius);
      bgRad.addColorStop(0, p3(...boosted[1], 0.4));
      bgRad.addColorStop(1, p3(...boosted[1], 0));
      fluidCtx.fillStyle = bgRad;
      fluidCtx.beginPath(); fluidCtx.arc(bX, bY, bRadius, 0, Math.PI*2); fluidCtx.fill();
  }

  // Multiple Treble Blobs
  const tScale = 0.8 + (treble * 2.0);
  for (let i = 0; i < 5; i++) {
      const phase = i * Math.PI * 0.4;
      const tX = W * 0.5 + Math.cos(fluidTime * (1.4 + i*0.2) + phase) * (W * 0.45) + (Math.random() - 0.5) * treble * 150;
      const tY = H * 0.5 + Math.sin(fluidTime * (1.7 + i*0.2) - phase) * (H * 0.45) + (Math.random() - 0.5) * treble * 150;
      const tRadius = (Math.min(W, H) * (0.2 + i*0.05)) * tScale;
      
      const tgRad = fluidCtx.createRadialGradient(tX, tY, 0, tX, tY, tRadius);
      tgRad.addColorStop(0, p3(...boosted[2], 0.5));
      tgRad.addColorStop(1, p3(...boosted[2], 0));
      fluidCtx.fillStyle = tgRad;
      fluidCtx.beginPath(); fluidCtx.arc(tX, tY, tRadius, 0, Math.PI*2); fluidCtx.fill();
  }

  fluidCtx.globalCompositeOperation = 'source-over';
}

// ── Segment Manager ────────────────────────────────────────────────────
const SEG_COLORS = [
  '#00f0ff', '#ff007f', '#a855f7', '#00dfd8', '#f59e0b', '#10b981', '#6366f1', '#ec4899'
];

let localSegments = null;
let localSegmentMode = 'independent';
let segmentsSeeded = false;

function setSegmentMode(mode) {
  localSegmentMode = mode;
  ['indep', 'overlay', 'cont'].forEach(m => {
    const id = `btn-mode-${m}`;
    const btn = document.getElementById(id);
    if (!btn) return;
    const match = (m === 'indep' && mode === 'independent') ||
                  (m === 'overlay' && mode === 'overlay') ||
                  (m === 'cont' && mode === 'continuous');
    btn.classList.toggle('active', match);
  });
  wsSend({ type: 'set_segment_mode', mode: mode });
}

function renderMinimap() {
  const minimap = document.getElementById('seg-minimap');
  const coverageStat = document.getElementById('seg-coverage-stat');
  if (!minimap || !localSegments) return;

  const totalLeds = parseInt(document.getElementById('cfg-leds')?.value) || (cache.knobs ? cache.knobs.led_count : 197) || 197;
  minimap.innerHTML = '';
  let mappedCount = 0;

  localSegments.forEach((seg, idx) => {
    const start = parseInt(seg[0]);
    const stop = parseInt(seg[1]);
    const validStart = isNaN(start) ? 0 : Math.max(0, start);
    const validStop = isNaN(stop) ? validStart : Math.max(validStart, stop);
    const len = Math.max(0, validStop - validStart);
    mappedCount += len;
    const color = SEG_COLORS[idx % SEG_COLORS.length];

    const block = document.createElement('div');
    block.className = 'seg-minimap-block';
    const pct = totalLeds > 0 ? (len / totalLeds) * 100 : 0;
    block.style.width = `${pct}%`;
    block.style.background = color;
    block.title = `Segment ${idx}: ${validStart} - ${validStop} (${len} LEDs)`;
    if (pct > 7) block.textContent = `S${idx}`;
    minimap.appendChild(block);

    const badge = document.getElementById(`seg-badge-${idx}`);
    if (badge) badge.textContent = `${len} LEDs`;
  });

  if (coverageStat) {
    coverageStat.textContent = `${mappedCount} / ${totalLeds} LEDs`;
    coverageStat.style.color = mappedCount === totalLeds ? 'var(--accent)' : '#ffaa00';
  }
}

function buildSegmentCards() {
  const container = document.getElementById('seg-cards');
  if (!container || !localSegments) return;

  const count = localSegments.length || 1;
  const segItem = document.getElementById('acc-segments');

  const totalLeds = parseInt(document.getElementById('cfg-leds')?.value) || (cache.knobs ? cache.knobs.led_count : 197) || 197;
  container.innerHTML = '';

  localSegments.forEach((seg, idx) => {
    const start = seg[0];
    const stop = seg[1];
    const len = Math.max(0, (parseInt(stop) || 0) - (parseInt(start) || 0));
    const color = SEG_COLORS[idx % SEG_COLORS.length];

    const card = document.createElement('div');
    card.className = 'seg-card';
    card.id = `seg-card-${idx}`;
    card.innerHTML = `
      <div class="seg-card-header">
        <div class="seg-card-title">
          <span class="seg-dot" style="background:${color};box-shadow:0 0 8px ${color}"></span>
          <span>Segment ${idx}</span>
          <span class="seg-badge" id="seg-badge-${idx}">${len} LEDs</span>
        </div>
        ${localSegments.length > 1 ? `<button class="seg-del-btn" title="Remove Segment" onclick="removeSegment(${idx})">&times;</button>` : ''}
      </div>
      <div class="seg-inputs-row">
        <div class="seg-input-group">
          <span class="seg-input-label">Start</span>
          <input class="seg-num-input" id="seg-in-start-${idx}" type="number" min="0" max="${totalLeds}" value="${start}"
                 oninput="onSegmentInput(${idx}, 'start', this.value)"
                 onblur="onSegmentBlur(${idx}, 'start', this.value)"/>
        </div>
        <div class="seg-input-group">
          <span class="seg-input-label">Stop</span>
          <input class="seg-num-input" id="seg-in-stop-${idx}" type="number" min="0" max="${totalLeds}" value="${stop}"
                 oninput="onSegmentInput(${idx}, 'stop', this.value)"
                 onblur="onSegmentBlur(${idx}, 'stop', this.value)"/>
        </div>
      </div>
    `;
    container.appendChild(card);
  });

  renderMinimap();
}

function onSegmentInput(idx, field, val) {
  if (!localSegments || !localSegments[idx]) return;
  if (val === '') {
    localSegments[idx][field === 'start' ? 0 : 1] = '';
  } else {
    localSegments[idx][field === 'start' ? 0 : 1] = parseInt(val);
  }
  renderMinimap();
}

function onSegmentBlur(idx, field, val) {
  if (!localSegments || !localSegments[idx]) return;
  const totalLeds = parseInt(document.getElementById('cfg-leds')?.value) || (cache.knobs ? cache.knobs.led_count : 197) || 197;
  let num = parseInt(val);
  if (isNaN(num)) {
    num = field === 'start' ? 0 : totalLeds;
  }
  num = Math.max(0, Math.min(totalLeds, num));
  localSegments[idx][field === 'start' ? 0 : 1] = num;

  const inputEl = document.getElementById(`seg-in-${field}-${idx}`);
  if (inputEl) inputEl.value = num;

  renderMinimap();
}

function addSegment() {
  if (!localSegments) localSegments = [];
  const totalLeds = parseInt(document.getElementById('cfg-leds')?.value) || (cache.knobs ? cache.knobs.led_count : 197) || 197;
  const lastStop = localSegments.length > 0 ? (parseInt(localSegments[localSegments.length - 1][1]) || 0) : 0;
  const newStop = Math.min(totalLeds, lastStop + 30);
  localSegments.push([lastStop, Math.max(lastStop + 1, newStop)]);
  buildSegmentCards();
}

function removeSegment(idx) {
  if (!localSegments || localSegments.length <= 1) return;
  localSegments.splice(idx, 1);
  buildSegmentCards();
}

function saveSegments() {
  if (!localSegments || !localSegments.length) return;
  const totalLeds = parseInt(document.getElementById('cfg-leds')?.value) || (cache.knobs ? cache.knobs.led_count : 197) || 197;

  const sanitized = localSegments.map(seg => {
    let st = parseInt(seg[0]);
    let en = parseInt(seg[1]);
    if (isNaN(st)) st = 0;
    if (isNaN(en)) en = totalLeds;
    st = Math.max(0, Math.min(totalLeds, st));
    en = Math.max(st + 1, Math.min(totalLeds, en));
    return [st, en];
  });

  localSegments = sanitized;
  buildSegmentCards();

  wsSend({ type: 'set_segments', segments: sanitized });
  wsSend({ type: 'set_segment_mode', mode: localSegmentMode });

  const btn = document.getElementById('seg-save-btn');
  if (btn) {
    const orig = btn.textContent;
    btn.textContent = 'Applied ✓';
    setTimeout(() => { btn.textContent = orig; }, 1200);
  }
}

// ── Configure ─────────────────────────────────────────────────────────
function applyCfg(){
  const ip  =document.getElementById('cfg-ip').value.trim();
  const leds=parseInt(document.getElementById('cfg-leds').value);
  if(ip)           wsSend({type:'knob',key:'wled_ip',  value:ip});
  if(!isNaN(leds)) wsSend({type:'knob',key:'led_count',value:leds});
}

// ── Frame handler ──────────────────────────────────────────────────────
function onFrame(data){
  if(activeDrags === 0){
    cache = data;
  } else {
    cache.bass    = data.bass;
    cache.treble  = data.treble;
    cache.palette = data.palette;
    cache.art     = data.art;
    cache.track   = data.track;
  }

  if(data.track && data.track !== lastTrack){
    lastTrack = data.track;
    mqSetTrack(data.track);
  }
  
  if (data.art) {
      document.getElementById('album-cover').src = `data:image/jpeg;base64,${data.art}`;
  }

  mainW.forEach(w=>w.refresh(data.knobs));
  
  if (data.knobs) {
      document.getElementById('power-toggle').checked = data.knobs.power !== false;
      const sat = data.knobs.saturation;
      let val = 2; // Accurate default
      if (sat <= 0.2) val = 0;
      else if (sat <= 0.5) val = 1;
      else if (sat <= 0.8) val = 2;
      else val = 3;
      document.getElementById('vibe-slider').value = val;
  }
  allAdvW.forEach(w =>w.refresh(data.knobs));

  if(!cfgSeeded && data.knobs && data.knobs.wled_ip){
    document.getElementById('cfg-ip').value  =data.knobs.wled_ip;
    document.getElementById('cfg-leds').value=data.knobs.led_count;
    cfgSeeded=true;
  }

  if (data.knobs && data.knobs.led_count) {
    const wledStat = document.getElementById('acc-wled-stat');
    if (wledStat) wledStat.textContent = `${data.knobs.led_count} LEDs`;
  }

  if (!segmentsSeeded && data.segments && data.segments.length) {
    localSegments = JSON.parse(JSON.stringify(data.segments));
    localSegmentMode = data.segment_mode || 'independent';
    setSegmentMode(localSegmentMode);
    buildSegmentCards();
    segmentsSeeded = true;
  }

  if (data.segment_mode) {
    const segStat = document.getElementById('acc-seg-stat');
    if (segStat) segStat.textContent = data.segment_mode.charAt(0).toUpperCase() + data.segment_mode.slice(1);
  }

  drawFluid(data.palette, data.bass, data.treble);
}

// ── Accordion toggle & hover-expand ────────────────────────────────────
let accHoverTimer = null;

function openAccordion(el) {
  if (!el || el.classList.contains('open')) return;
  document.querySelectorAll('.acc-item').forEach(item => {
    if (item !== el) item.classList.remove('open');
  });
  el.classList.add('open');
  setTimeout(() => {
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, 100);
}

function toggleAccordion(id) {
  const el = document.getElementById(id);
  if (!el) return;
  if (el.classList.contains('open')) {
    el.classList.remove('open');
  } else {
    openAccordion(el);
  }
}

function setupAccordionHover() {
  document.querySelectorAll('.acc-item').forEach(item => {
    item.addEventListener('mouseenter', () => {
      // Do not collapse or switch if the user is dragging a knob or focused on an input
      if (activeDrags > 0) return;
      const activeEl = document.activeElement;
      if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'BUTTON') && activeEl.closest('.acc-item')) {
        return;
      }

      clearTimeout(accHoverTimer);
      accHoverTimer = setTimeout(() => {
        if (activeDrags > 0) return;
        openAccordion(item);
      }, 90);
    });

    item.addEventListener('mouseleave', () => {
      clearTimeout(accHoverTimer);
    });
  });
}
setupAccordionHover();

// ── Global Top-Layer Tooltip ───────────────────────────────────────────
const gTip = document.getElementById('global-tip');

function showGlobalTip(el, tipObj) {
  if (!gTip || !tipObj) return;
  if (typeof tipObj === 'string') {
    gTip.textContent = tipObj;
  } else {
    gTip.innerHTML = `
      <div class="tip-desc">${tipObj.desc}</div>
      <div class="tip-line"><span class="tip-tag hi">High &rarr;</span><span>${tipObj.high}</span></div>
      <div class="tip-line"><span class="tip-tag lo">Low &rarr;</span><span>${tipObj.low}</span></div>
    `;
  }
  const rect = el.getBoundingClientRect();
  const x = Math.round(rect.left + rect.width / 2);
  let y = rect.top - 8;
  if (y < 70) {
    gTip.style.top = `${Math.round(rect.bottom + 8)}px`;
    gTip.style.bottom = 'auto';
  } else {
    gTip.style.top = 'auto';
    gTip.style.bottom = `${Math.round(window.innerHeight - y)}px`;
  }
  const clampedX = Math.max(115, Math.min(window.innerWidth - 115, x));
  gTip.style.left = `${clampedX}px`;
  gTip.classList.add('visible');
}

function hideGlobalTip() {
  if (!gTip) return;
  gTip.classList.remove('visible');
}

window.addEventListener('scroll', hideGlobalTip, true);

// ── Settings toggle ────────────────────────────────────────────────────
function toggleSettings(){
  hideGlobalTip();
  const s=document.getElementById('settings');
  const open=s.classList.toggle('open');
  document.getElementById('hb-btn').classList.toggle('open',open);
}

// ── Resize ─────────────────────────────────────────────────────────────
function resize(){
  dotsEl.width  = dotsEl.offsetWidth;
  dotsEl.height = dotsEl.offsetHeight;
}
window.onresize=resize;
resize();
