// Shared runtime for the FULL-study pages (PreflightBench-Live). pages_full/build.py inlines it into each page.
// Fresh code path from the pilot runtime, extended with: template variants (?v=), dialog kinds, slow load,
// near/away background motion, virtual (canvas) targets, and dialog/settled truth.
// All motion uses setTimeout/setInterval and Date.now(), so Playwright's clock controls it. No rAF.
(function () {
  const Q = new URLSearchParams(location.search);
  const seed = parseInt(Q.get('seed') || '1', 10);
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const bg = mulberry32(seed * 7919 + 1);       // background motion and content
  const ev = mulberry32(seed * 104729 + 7);     // seeded events only
  const P = {
    seed, Q, mulberry32,
    variant: parseInt(Q.get('v') || '0', 10),   // template variant: layout + theme
    motion: Q.get('motion') || 'med',
    rand: bg, evRand: ev,
    pick: (a, r = bg) => a[Math.floor(r() * a.length)],
    between: (lo, hi, r = bg) => lo + (hi - lo) * r(),
    level: (low, med, high) => ({ low, med, high, none: null }[Q.get('motion') || 'med']),
    t0: Date.now(),
    hooks: {},
    virtual: {},  // canvas targets: id -> {box: () => [x,y,w,h] | null, valid: () => bool}
  };
  window.P = P;

  // Fictional vocabulary only.
  const WORDS = ('aster bramble cobalt dune ember fennel glacier heron iris jasper kelp lark moss nettle opal ' +
    'plover quill reed sorrel tansy umbra vesper wren yucca zinnia beacon cinder drift ferry gable hollow ' +
    'inlet jetty knoll ledge mantle nook outpost prism ridge sable tarn').split(' ');
  P.words = (n, r = bg) => Array.from({ length: n }, () => P.pick(WORDS, r)).join(' ');
  P.sentence = (n, r = bg) => { const s = P.words(n, r); return s[0].toUpperCase() + s.slice(1) + '.'; };
  P.name = (r = bg) => P.pick(['Avery', 'Bo', 'Cass', 'Dev', 'Eli', 'Fen', 'Gray', 'Hollis', 'Indy', 'Jules', 'Kit', 'Lane', 'Mar', 'Noor', 'Oak', 'Pax'], r) +
    ' ' + P.pick(['Ashdown', 'Brightwater', 'Coldbrook', 'Dunmore', 'Elmsworth', 'Fairholt', 'Greyling', 'Hartwell'], r);

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  P.el = el;

  // ---------- themes (template variants) ----------
  // Four palettes x font stacks. Pages also change layout by P.variant; the palette only changes look.
  const THEMES = [
    { bg: '#f6f7f9', panel: '#ffffff', ink: '#1d232a', muted: '#66707a', accent: '#2e6bd9', line: '#dde2e8', font: '-apple-system, Helvetica, Arial, sans-serif' },
    { bg: '#fbf8f3', panel: '#fffdf9', ink: '#2a2420', muted: '#7a6f66', accent: '#b4552d', line: '#e8dfd3', font: 'Georgia, "Times New Roman", serif' },
    { bg: '#11161c', panel: '#1a222b', ink: '#e7ecf1', muted: '#93a1ae', accent: '#3fb68b', line: '#2a3540', font: 'Verdana, Geneva, sans-serif' },
    { bg: '#eef3ef', panel: '#f9fcfa', ink: '#1c2a22', muted: '#5f7368', accent: '#6b4fbb', line: '#d3dfd7', font: '"Trebuchet MS", Tahoma, sans-serif' },
  ];
  P.theme = THEMES[P.variant % THEMES.length];
  P.applyTheme = function () {
    const t = P.theme, s = document.documentElement.style;
    Object.entries(t).forEach(([k, v]) => s.setProperty('--' + k, v));
  };

  // ---------- targets ----------
  function target() {
    const id = window.__pfTarget || Q.get('target');
    return id ? document.querySelector(`[data-target-id="${id}"]`) : null;
  }
  P.target = target;
  function targetId() { return window.__pfTarget || Q.get('target'); }
  function blockOf(t) { return (P.hooks.blockOf && P.hooks.blockOf(t)) || t.closest('[data-block]') || t; }

  // ---------- events ----------
  function spacer(h, r) {
    const s = el('div', 'pf-inserted');
    s.style.cssText = `height:${h}px;box-sizing:border-box;background:var(--panel);border:1px solid var(--line);color:var(--muted);` +
      `border-radius:6px;margin:0 0 8px 0;padding:8px 12px;font-size:13px;overflow:hidden;grid-column:1/-1;`;
    s.textContent = P.pick(['Update available. ', 'Section expanded. ', 'New items below. ', 'Notice: '], r) + P.sentence(10, r);
    return s;
  }
  function doMoved(r) {
    const id = targetId();
    if (P.virtual[id] && P.hooks.moveVirtual) return P.hooks.moveVirtual(id, r);
    const t = target(); if (!t) return;
    const h = Math.round(P.between(10, 300, r));
    if (P.hooks.moveTarget) return P.hooks.moveTarget(t, h, r);
    const b = blockOf(t);
    b.parentNode.insertBefore(spacer(h, r), b);
  }
  function doLookalike(r) {
    const id = targetId();
    if (P.virtual[id] && P.hooks.lookalikeVirtual) return P.hooks.lookalikeVirtual(id, r);
    const t = target(); if (!t) return;
    const b = blockOf(t);
    const c = b.cloneNode(true);
    c.querySelectorAll('[data-target-id]').forEach(e => e.removeAttribute('data-target-id'));
    c.removeAttribute('data-target-id');
    c.querySelectorAll('[data-vary]').forEach(e => {
      const n = e.textContent.split(/\s+/).length;
      e.textContent = e.dataset.vary === 'num' ? String(Math.round(P.between(10, 999, r))) : P.sentence(Math.max(2, n), r);
    });
    // Mark the clone without touching its class when the clone IS the control (no block): truth compares
    // tag + text + className, so an extra class would hide an identical look-alike.
    if (b === t) c.dataset.pfLookalike = '1'; else c.classList.add('pf-lookalike');
    if (P.hooks.lookalike) return P.hooks.lookalike(t, b, c, r);
    b.parentNode.insertBefore(c, b);
  }
  // Dialog kinds: modal overlays that cover part of the page (label `dialog`).
  const DIALOGS = ['session_timeout', 'cookie_consent', 'styled_dialog'];
  function doDialog(r, kind) {
    kind = kind || P.pick(DIALOGS, r);
    let c = el('div', 'pf-cover pf-dialog');
    if (kind === 'cookie_consent') {
      const h = 120 + Math.round(r() * 50), bottom = r() < .5;
      c.style.cssText = `position:fixed;left:0;right:0;${bottom ? 'bottom' : 'top'}:0;height:${h}px;background:#1f2429;color:#f1f1f1;` +
        'z-index:900;padding:18px 36px;box-sizing:border-box;font:14px -apple-system,Arial,sans-serif;';
      c.append(el('div', null, 'We use cookies to keep you signed in and to measure traffic. ' + P.sentence(6, r)));
      const row = el('div'); row.style.marginTop = '10px';
      ['Accept all', 'Reject', 'Settings'].forEach(t => { const b = el('button', null, t); b.style.cssText = 'margin-right:8px;padding:6px 12px;font:inherit;'; row.append(b); });
      c.append(row);
    } else {
      c.style.cssText = 'position:fixed;inset:0;background:rgba(10,14,18,.5);z-index:900;display:flex;align-items:center;justify-content:center;';
      const d = el('div');
      if (kind === 'session_timeout') {
        d.style.cssText = 'background:#fff;color:#222;border-radius:8px;padding:24px 28px;width:400px;font:14px -apple-system,Arial,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.3);';
        d.append(el('h3', null, 'Your session is about to expire'), el('p', null, 'For your security you will be signed out in 2 minutes. ' + P.sentence(6, r)));
        const b = el('button', null, 'Stay signed in'); b.style.cssText = 'padding:7px 14px;font:inherit;'; d.append(b);
      } else {  // styled like the page: same palette and font
        d.style.cssText = 'background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:22px 26px;width:420px;font-family:var(--font);font-size:14px;';
        d.append(el('h3', null, P.pick(['Before you continue', 'Quick question', 'Something changed'], r)), el('p', null, P.sentence(14, r)));
        const b = el('button', null, P.pick(['Got it', 'Continue', 'OK'], r));
        b.style.cssText = 'padding:7px 14px;background:var(--accent);color:#fff;border:0;border-radius:6px;font:inherit;'; d.append(b);
      }
      c.append(d);
    }
    c.dataset.coverKind = kind;
    document.body.append(c);
  }
  // Non-dialog covers over the target: toast or popover (they cover the click but are not dialogs).
  function doCovered(r) {
    const id = targetId(), t = target();
    const bx = P.virtual[id] ? P.virtual[id].box() : (t && t.getBoundingClientRect() && (b => [b.left, b.top, b.width, b.height])(t.getBoundingClientRect()));
    if (!bx) return;
    const cx = bx[0] + bx[2] / 2, cy = bx[1] + bx[3] / 2;
    const kind = P.pick(['toast', 'popover'], r);
    const c = el('div', 'pf-cover');
    const w = kind === 'toast' ? 320 : 240, h = kind === 'toast' ? 56 : 110;
    const left = Math.max(0, Math.min(1280 - w, cx - w / 2 + (r() - .5) * (w * .5)));
    const top = Math.max(0, Math.min(800 - h, cy - h / 2 + (r() - .5) * (h * .5)));
    c.style.cssText = `position:fixed;left:${left}px;top:${top}px;width:${w}px;height:${h}px;z-index:900;box-sizing:border-box;` +
      'padding:12px 14px;border-radius:8px;font:13px -apple-system,Arial,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.18);' +
      (kind === 'toast' ? 'background:#2b3137;color:#fff;' : 'background:#fff;color:#222;border:1px solid #ccd;');
    c.textContent = kind === 'toast' ? 'Saved. ' + P.words(4, r) : 'Tip: ' + P.sentence(9, r);
    c.dataset.coverKind = kind;
    document.body.append(c);
  }
  function doGone(r) {
    const id = targetId();
    if (P.virtual[id] && P.hooks.goneVirtual) return P.hooks.goneVirtual(id, r);
    const t = target(); if (!t) return;
    const kind = P.pick(['removed', 'disabled', 'label'], r);
    if (kind === 'removed') t.remove();
    else if (kind === 'disabled') { t.disabled = true; t.dataset.pfDisabled = '1'; t.style.opacity = '0.4'; t.style.pointerEvents = 'none'; }
    else { t.textContent = t.dataset.alt || (t.textContent.trim() + 'd'); }
    document.documentElement.dataset.goneKind = kind;
  }
  // Slow load: the target's block is swapped for a loading skeleton, and comes back after `slow_ms`
  // (it may come back at a different height, so neighbours shift).
  function doSlowLoad(r) {
    const t = target(); if (!t) return;
    const b = blockOf(t);
    const sk = el('div', 'pf-skeleton');
    const rect = b.getBoundingClientRect();
    sk.style.cssText = `height:${Math.max(20, rect.height + Math.round(P.between(-10, 40, r)))}px;background:var(--line);border-radius:6px;margin:0 0 8px 0;`;
    const disp = b.style.display;
    b.style.display = 'none';
    b.parentNode.insertBefore(sk, b);
    const back = parseFloat(Q.get('slow_ms') || '3000');
    setTimeout(() => { sk.remove(); b.style.display = disp; }, back);
  }
  const EVENTS = { none: () => {}, moved: doMoved, moved_lookalike: doLookalike, covered: doCovered, gone: doGone,
    dialog: r => doDialog(r), slow_load: doSlowLoad };
  P.events = EVENTS;
  function schedule(name, at) {
    if (!name || name === 'none' || !(at >= 0)) return;
    setTimeout(() => { EVENTS[name](ev); document.documentElement.dataset['ev_' + name] = String(Date.now() - P.t0); }, at);
  }
  P.startEvents = function () {
    schedule(Q.get('event'), parseFloat(Q.get('event_at')));
    schedule(Q.get('event2'), parseFloat(Q.get('event2_at')));
  };

  // ---------- background motion near / away from the target (?bg=near|away) ----------
  // A spinner or a typing caret, placed within 20-60 px of the target ('near') or far from it ('away').
  P.startBgMotion = function () {
    const where = Q.get('bg'); if (!where || where === 'none') return;
    const r = mulberry32(seed * 31337 + 3);
    const id = targetId(), t = target();
    const bx = P.virtual[id] ? P.virtual[id].box() : (t ? (b => [b.left, b.top, b.width, b.height])(t.getBoundingClientRect()) : null);
    if (!bx) return;
    const kind = P.pick(['spinner', 'caret'], r);
    const s = el('div', 'pf-bgmotion');
    let x, y;
    if (where === 'near') {
      const side = P.pick(['l', 'r', 'u', 'd'], r), d = P.between(20, 60, r);
      x = side === 'l' ? bx[0] - d - 18 : side === 'r' ? bx[0] + bx[2] + d : bx[0] + bx[2] / 2;
      y = side === 'u' ? bx[1] - d - 18 : side === 'd' ? bx[1] + bx[3] + d : bx[1] + bx[3] / 2 - 9;
    } else {
      do { x = P.between(20, 1240, r); y = P.between(20, 760, r); } while (Math.abs(x - bx[0]) < 300 && Math.abs(y - bx[1]) < 200);
    }
    x = Math.max(2, Math.min(1260, x)); y = Math.max(2, Math.min(780, y));
    s.style.cssText = `position:fixed;left:${x}px;top:${y}px;width:18px;height:18px;z-index:850;pointer-events:none;`;
    document.body.append(s);
    let k = 0;
    if (kind === 'spinner') {
      s.style.border = '3px solid var(--line)'; s.style.borderTopColor = 'var(--accent)'; s.style.borderRadius = '50%'; s.style.boxSizing = 'border-box';
      setInterval(() => { s.style.transform = `rotate(${(k += 30) % 360}deg)`; }, 50);
    } else {
      s.style.width = '2px'; s.style.background = 'var(--ink)';
      setInterval(() => { s.style.visibility = (k++ % 2) ? 'hidden' : 'visible'; }, 530);
    }
    document.documentElement.dataset.bgKind = kind;
  };

  // ---------- last action (worked set) ----------
  // Page defines P.action = {id, smallSel?, smallLabel, panelText}. Outcome from ?outcome=.
  P.wireAction = function () {
    const cfg = P.action; if (!cfg) return;
    const btn = document.querySelector(`[data-action-id="${cfg.id}"]`); if (!btn) return;
    btn.dataset.label = btn.textContent;
    btn.addEventListener('click', () => {
      const o = Q.get('outcome') || 'success_clear';
      if (o === 'success_clear') {
        const p = el('div', 'pf-panel');
        const b = btn.getBoundingClientRect();
        const top = Math.min(800 - 130, b.bottom + 10), left = Math.max(10, Math.min(1280 - 360, b.left - 120));
        p.style.cssText = `position:fixed;left:${left}px;top:${top}px;width:340px;height:110px;background:var(--panel);` +
          'border:2px solid var(--accent);border-radius:10px;padding:16px 18px;box-sizing:border-box;color:var(--ink);font-size:15px;z-index:800;font-family:var(--font);';
        p.append(el('div', null, cfg.panelText), el('div', null, P.sentence(5)));
        document.body.append(p);
      } else if (o === 'success_small') {
        const e = cfg.smallSel ? document.querySelector(cfg.smallSel) : btn;
        e.textContent = cfg.smallLabel;
      } else if (o === 'failed_error') {
        const t = el('div', 'pf-error', cfg.errorText || "Couldn't complete that. Try again.");
        t.style.cssText = 'position:fixed;right:24px;bottom:24px;background:#b3261e;color:#fff;padding:12px 16px;border-radius:8px;font-size:14px;z-index:950;';
        document.body.append(t);
        setTimeout(() => t.remove(), 3000);
      } // failed_silent: nothing
    });
  };

  // ---------- truth, read by the generator ----------
  function validDom(t) {
    return !!(t && t.isConnected && !t.disabled && !t.dataset.pfDisabled && t.offsetParent !== null &&
      (t.dataset.label == null || t.textContent === t.dataset.label));
  }
  function topCover(x, y) {
    const e = document.elementFromPoint(x, y);
    return e && e.closest('.pf-cover, .pf-panel, .pf-skeleton') ? e : null;
  }
  function hits(id, t, x, y) {
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return false;
    const v = P.virtual[id];
    if (v) {  // canvas target: inside its render-state box, and the canvas itself is what is on top
      const b = v.box(); if (!b || !v.valid()) return false;
      if (!(x >= b[0] && x < b[0] + b[2] && y >= b[1] && y < b[1] + b[3])) return false;
      const e = document.elementFromPoint(x, y);
      return !!(e && e.tagName === 'CANVAS' && (!v.canvas || e === v.canvas));
    }
    const e = document.elementFromPoint(x, y);
    return !!(e && (e === t || t.contains(e)));
  }
  function dialogVisible() {
    return Array.from(document.querySelectorAll('.pf-dialog')).some(d => { const b = d.getBoundingClientRect(); return b.width > 0 && b.height > 0; });
  }
  window.__truth = function (px, py) {
    const id = targetId(), v = P.virtual[id], t = v ? null : target();
    const ok = v ? v.valid() : validDom(t);
    const out = { go_ok: ok && hits(id, t, px, py), target_exists: ok, target_box: null, hit_mask: null,
      covered: false, lookalike_boxes: [], center_hit: false, dialog: dialogVisible(),
      overlay: !!document.querySelector('.pf-cover'), click_on_cover: !!topCover(px, py) };
    const b = v ? v.box() : (t && t.isConnected && t.offsetParent !== null ? (r => [r.left, r.top, r.width, r.height])(t.getBoundingClientRect()) : null);
    if (b) {
      out.target_box = b;
      const cx = b[0] + b[2] / 2, cy = b[1] + b[3] / 2;
      out.center_hit = ok && hits(id, t, cx, cy);
      const inView = cx >= 0 && cy >= 0 && cx < innerWidth && cy < innerHeight;
      out.covered = ok && inView && !out.center_hit;
      const mask = [];
      for (let y = Math.ceil(b[1] / 4) * 4; y < b[1] + b[3]; y += 4)
        for (let x = Math.ceil(b[0] / 4) * 4; x < b[0] + b[2]; x += 4)
          if (ok && hits(id, t, x, y)) mask.push([x, y]);
      out.hit_mask = mask;
      if (t) {
        const sig = e => e.tagName + '|' + e.textContent.trim() + '|' + e.className;
        const s = sig(t);
        document.querySelectorAll(t.tagName).forEach(e => {
          if (e === t || sig(e) !== s) return;
          const r = e.getBoundingClientRect();
          if (r.width > 0 && r.bottom > 0 && r.top < innerHeight) out.lookalike_boxes.push([r.left, r.top, r.width, r.height]);
        });
      } else if (P.hooks.virtualLookalikes) out.lookalike_boxes = P.hooks.virtualLookalikes(id);
      out.unique = out.lookalike_boxes.length === 0;
    }
    out.correct_action = out.go_ok ? 'go' : (out.target_exists && out.center_hit ? 'reaim' : 'replan');
    return out;
  };
  window.__targets = () => {
    const dom = Array.from(document.querySelectorAll('[data-target-id]')).filter(e => e.offsetParent !== null).map(e => {
      const b = e.getBoundingClientRect();
      return { id: e.dataset.targetId, box: [b.left, b.top, b.width, b.height] };
    });
    const virt = Object.entries(P.virtual).map(([id, v]) => ({ id, box: v.box() })).filter(o => o.box);
    return dom.concat(virt);
  };
  window.__actionBox = () => {
    const b = document.querySelector('[data-action-id]'); if (!b) return null;
    const r = b.getBoundingClientRect(); return [r.left, r.top, r.width, r.height];
  };

  document.addEventListener('DOMContentLoaded', () => {
    P.applyTheme();
    if (P.init) P.init();
    document.querySelectorAll('[data-target-id]').forEach(e => { if (e.dataset.label == null) e.dataset.label = e.textContent; });
    P.wireAction();
    P.startEvents();
    // background motion starts after targets exist; the generator sets the target before load via ?target=
    setTimeout(() => P.startBgMotion(), 0);
  });
})();
