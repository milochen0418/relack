"""The chat page's own script and styles.

The composer boxes are uncontrolled textareas (a server-controlled `value`
breaks IME composition), so typing help runs here: Enter sends and
Shift+Enter adds a line (never while an IME is composing), the formatting
buttons, @ autocomplete, emoji insertion, and paste / drag-and-drop uploads
(handed to the hidden Reflex upload zones). It also shows desktop
notifications, plays the alert sound, keeps the unread count in the tab title,
keeps message lists scrolled to the newest message, and passes requests back
to the server through the hidden `#relack-bridge` input.
"""

CLIENT_JS = r"""
(function () {
  if (window.__relackRuntime) return;
  const R = (window.__relackRuntime = {});

  // ---------- helpers ----------
  const composerSel = 'textarea[data-relack-composer]';
  function root() { return document.querySelector('[data-relack-me]'); }
  function targetComposer(el) {
    const t = el.dataset.relackTarget;
    if (t) return document.querySelector('textarea[data-relack-composer="' + t + '"]');
    const form = el.closest('form');
    return form ? form.querySelector(composerSel) : null;
  }
  function autosize(ta) {
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, Math.round(window.innerHeight * 0.4)) + 'px';
  }
  function insertText(ta, text) {
    ta.focus();
    let ok = false;
    try { ok = document.execCommand('insertText', false, text); } catch (e) { ok = false; }
    if (!ok) {
      ta.setRangeText(text, ta.selectionStart, ta.selectionEnd, 'end');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
    autosize(ta);
  }
  function bridge(payload) {
    const el = document.getElementById('relack-bridge');
    if (!el) return;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(el, JSON.stringify(Object.assign({ t: Date.now() }, payload)));
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }
  window.relackBridge = bridge;
  function insideCodeBlock(ta) {
    return ((ta.value.slice(0, ta.selectionStart).match(/```/g) || []).length % 2) === 1;
  }

  // ---------- formatting ----------
  function wrap(ta, before, after, placeholder) {
    const s = ta.selectionStart, e = ta.selectionEnd;
    const sel = ta.value.slice(s, e) || placeholder;
    insertText(ta, before + sel + after);
    ta.setSelectionRange(s + before.length, s + before.length + sel.length);
  }
  function prefixLines(ta, prefix) {
    const v = ta.value, s = ta.selectionStart, e = ta.selectionEnd;
    const start = v.lastIndexOf('\n', s - 1) + 1;
    let end = v.indexOf('\n', e);
    if (end < 0) end = v.length;
    const lines = v.slice(start, end).split('\n');
    ta.setSelectionRange(start, end);
    insertText(ta, lines.map((l, i) => prefix(i) + l).join('\n'));
  }
  const FORMATS = {
    bold: ta => wrap(ta, '**', '**', 'bold'),
    italic: ta => wrap(ta, '_', '_', 'italic'),
    strike: ta => wrap(ta, '~~', '~~', 'strikethrough'),
    code: ta => wrap(ta, '`', '`', 'code'),
    codeblock: ta => {
      const s = ta.selectionStart;
      const nl = s > 0 && ta.value[s - 1] !== '\n' ? '\n' : '';
      wrap(ta, nl + '```\n', '\n```', 'code');
    },
    quote: ta => prefixLines(ta, () => '> '),
    ul: ta => prefixLines(ta, () => '- '),
    ol: ta => prefixLines(ta, i => (i + 1) + '. '),
    link: ta => {
      const s = ta.selectionStart, e = ta.selectionEnd;
      const text = ta.value.slice(s, e) || 'link';
      insertText(ta, '[' + text + '](https://)');
      const at = s + text.length + 3;
      ta.setSelectionRange(at, at + 8);
    },
  };

  // ---------- @ mentions ----------
  const SPECIAL = [
    { u: 'here', n: 'here', hint: 'Notify everyone in this room' },
    { u: 'channel', n: 'channel', hint: 'Notify everyone in this room' },
    { u: 'everyone', n: 'everyone', hint: 'Notify everyone in this room' },
  ];
  let mention = null; // {ta, start, items, index, box}
  function closeMention() {
    if (mention && mention.box) mention.box.remove();
    mention = null;
  }
  function people(ta) {
    try { return JSON.parse(ta.closest('form').dataset.mentions || '[]'); } catch (e) { return []; }
  }
  function updateMention(ta) {
    const pos = ta.selectionStart;
    if (pos !== ta.selectionEnd) return closeMention();
    const before = ta.value.slice(0, pos);
    const m = before.match(/(^|[^A-Za-z0-9_])@([^@\n]{0,40})$/);
    if (!m || insideCodeBlock(ta)) return closeMention();
    const query = m[2].toLowerCase();
    const r = root();
    const me = r ? r.dataset.relackMe : '';
    const all = people(ta);
    const hit = p => !query || p.n.toLowerCase().startsWith(query) || p.u.toLowerCase().startsWith(query) ||
      p.n.toLowerCase().includes(' ' + query);
    let items = all.filter(p => p.u !== me && hit(p)).slice(0, 8);
    items = items.concat(SPECIAL.filter(hit)).slice(0, 8);
    if (!items.length) return closeMention();
    const counts = {};
    all.forEach(p => { const k = p.n.toLowerCase(); counts[k] = (counts[k] || 0) + 1; });
    items.forEach(p => { p.insert = p.hint ? p.u : (counts[p.n.toLowerCase()] > 1 ? p.u : p.n); });
    const start = pos - m[2].length - 1;
    const index = mention && mention.ta === ta ? Math.min(mention.index, items.length - 1) : 0;
    if (!mention || mention.ta !== ta) {
      closeMention();
      const box = document.createElement('div');
      box.className = 'relack-mention-pop';
      box.setAttribute('role', 'listbox');
      box.setAttribute('aria-label', 'Mention someone');
      ta.closest('form').appendChild(box);
      mention = { ta, box };
    }
    Object.assign(mention, { start, items, index });
    renderMention();
  }
  function renderMention() {
    const { box, items, index } = mention;
    box.innerHTML = '';
    items.forEach((p, i) => {
      const row = document.createElement('div');
      row.className = 'relack-mention-item' + (i === index ? ' active' : '');
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', i === index ? 'true' : 'false');
      if (p.hint) {
        row.innerHTML = '<span class="relack-mention-at">@</span>';
      } else {
        const img = document.createElement('img');
        img.src = 'https://api.dicebear.com/9.x/notionists/svg?seed=' + encodeURIComponent(p.s || p.u);
        img.alt = '';
        row.appendChild(img);
      }
      const name = document.createElement('span');
      name.className = 'relack-mention-name';
      name.textContent = p.hint ? '@' + p.n : p.n;
      row.appendChild(name);
      const sub = document.createElement('span');
      sub.className = 'relack-mention-sub';
      sub.textContent = p.hint || (p.u !== p.n ? p.u : '');
      row.appendChild(sub);
      row.addEventListener('mousedown', e => { e.preventDefault(); pickMention(i); });
      box.appendChild(row);
    });
  }
  function pickMention(i) {
    const { ta, start, items } = mention;
    const p = items[i];
    ta.focus();
    ta.setSelectionRange(start, ta.selectionStart);
    closeMention();
    insertText(ta, '@' + p.insert + ' ');
  }

  // ---------- uploads ----------
  function upload(zoneId, files) {
    const input = document.querySelector('#' + zoneId + ' input[type=file]');
    if (!input || !files.length) return;
    const dt = new DataTransfer();
    files.forEach(f => dt.items.add(f));
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function pastedName(f) {
    if (f.name && !/^image\.(png|jpe?g|gif|webp)$/i.test(f.name)) return f;
    const d = new Date(), p = n => String(n).padStart(2, '0');
    const ext = ((f.type.split('/')[1] || 'png').replace('jpeg', 'jpg')).split('+')[0];
    const name = 'Pasted image ' + d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
      p(d.getHours()) + '.' + p(d.getMinutes()) + '.' + p(d.getSeconds()) + '.' + ext;
    return new File([f], name, { type: f.type });
  }

  // ---------- notifications ----------
  let audio = null;
  function unlockAudio() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === 'suspended') audio.resume();
    } catch (e) {}
  }
  function ding() {
    try {
      unlockAudio();
      if (!audio) return;
      const t = audio.currentTime;
      [[880, 0], [1320, 0.13]].forEach(([freq, delay]) => {
        const osc = audio.createOscillator(), gain = audio.createGain();
        osc.type = 'sine';
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, t + delay);
        gain.gain.exponentialRampToValueAtTime(0.18, t + delay + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + delay + 0.35);
        osc.connect(gain).connect(audio.destination);
        osc.start(t + delay);
        osc.stop(t + delay + 0.4);
      });
      R.dings = (R.dings || 0) + 1;
    } catch (e) {}
  }
  function inFront() { return document.visibilityState === 'visible' && document.hasFocus(); }
  window.relackNotify = function (items) {
    const r = root();
    if (!r) return;
    const room = r.dataset.relackRoom || '', thread = r.dataset.relackThread || '';
    let sound = false;
    for (const it of items) {
      // Already on screen: the message is in the room or thread this tab shows.
      if (inFront() && ((it.room === room && !it.parent) || (it.parent && it.parent === thread))) continue;
      const key = 'relack_notified_' + it.id;
      try {
        if (localStorage.getItem(key)) continue; // another tab of this browser has shown it
        localStorage.setItem(key, String(Date.now()));
      } catch (e) {}
      sound = true;
      R.shown = (R.shown || []).concat([it]);
      if (!inFront() && r.dataset.relackDesktop !== 'off' && 'Notification' in window &&
          Notification.permission === 'granted') {
        try {
          const n = new Notification(it.title, {
            body: it.body,
            tag: it.id,
            icon: 'https://api.dicebear.com/9.x/notionists/png?seed=' + encodeURIComponent(it.seed || ''),
          });
          n.onclick = () => {
            window.focus();
            bridge({ op: 'jump', room: it.room, id: it.id, parent: it.parent });
            n.close();
          };
        } catch (e) {}
      }
    }
    if (sound && r.dataset.relackSound !== 'off') ding();
  };
  try {
    const cutoff = Date.now() - 2 * 86400000;
    Object.keys(localStorage)
      .filter(k => k.startsWith('relack_notified_') && Number(localStorage.getItem(k)) < cutoff)
      .forEach(k => localStorage.removeItem(k));
  } catch (e) {}

  // ---------- unread count in the title, instant refresh on new messages ----------
  function updateTitle() {
    const el = document.getElementById('relack-unread-total');
    const n = el ? parseInt(el.textContent || '0', 10) || 0 : 0;
    const base = document.title.replace(/^\(\d+\)\s*/, '');
    const want = n > 0 ? '(' + n + ') ' + base : base;
    if (document.title !== want) document.title = want;
  }
  let syncTimer = null;
  function syncSoon() {
    clearTimeout(syncTimer);
    syncTimer = setTimeout(() => {
      const el = document.getElementById(inFront() ? 'unread-sync-visible' : 'unread-sync-hidden');
      if (el) el.click();
    }, 150);
  }
  document.addEventListener('visibilitychange', syncSoon);
  window.addEventListener('focus', syncSoon);

  // ---------- message lists stay at the newest message ----------
  function setupScroller(el) {
    if (!el || el.__relackScroll) return;
    el.__relackScroll = true;
    el.style.overflowAnchor = 'none';
    let atBottom = true, lastHeight = el.scrollHeight, lastTop = el.scrollTop, room = el.dataset.room;
    el.addEventListener('scroll', () => {
      atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      lastTop = el.scrollTop;
      lastHeight = el.scrollHeight;
    }, { passive: true });
    const follow = () => {
      if (el.dataset.room !== room) { room = el.dataset.room; atBottom = true; }
      const h = el.scrollHeight;
      if (el.__relackPrepend) {
        el.__relackPrepend = false;
        el.scrollTop = lastTop + (h - lastHeight);
      } else if (atBottom) {
        el.scrollTop = h;
      }
      lastHeight = el.scrollHeight;
      lastTop = el.scrollTop;
    };
    new MutationObserver(follow).observe(el, {
      childList: true, subtree: true, attributes: true, attributeFilter: ['data-room'],
    });
    el.addEventListener('load', () => { if (atBottom) el.scrollTop = el.scrollHeight; }, true);
    el.scrollTop = el.scrollHeight;
  }
  window.relackScrollTo = function (id, tries) {
    tries = tries || 0;
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ block: 'center' });
      return;
    }
    if (tries < 40) setTimeout(() => window.relackScrollTo(id, tries + 1), 100);
  };

  new MutationObserver(records => {
    let activity = false, total = false, history = false;
    for (const rec of records) {
      const el = rec.target.nodeType === 3 ? rec.target.parentElement : rec.target;
      if (!el) continue;
      if (el.id === 'relack-activity') activity = true;
      else if (el.id === 'relack-unread-total') total = true;
      else if (el.id === 'relack-history-rev') history = true;
    }
    if (activity) syncSoon();
    if (total) updateTitle();
    if (history) {
      const btn = document.getElementById('relack-refresh-older');
      if (btn) btn.click();
    }
    setupScroller(document.getElementById('relack-messages'));
    setupScroller(document.getElementById('relack-thread-messages'));
  }).observe(document.body, { subtree: true, childList: true, characterData: true });
  setInterval(updateTitle, 2000);

  // ---------- picture viewer ----------
  function closeViewer() {
    const box = document.querySelector('.relack-viewer');
    if (box) box.remove();
  }
  function openViewer(src, name) {
    closeViewer();
    const box = document.createElement('div');
    box.className = 'relack-viewer';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', name);
    const img = document.createElement('img');
    img.src = src;
    img.alt = name;
    const bar = document.createElement('div');
    bar.className = 'relack-viewer-bar';
    const title = document.createElement('span');
    title.textContent = name;
    const download = document.createElement('a');
    download.href = src;
    download.download = name;
    download.textContent = 'Download';
    const close = document.createElement('button');
    close.type = 'button';
    close.textContent = 'Close';
    bar.append(title, download, close);
    box.append(img, bar);
    box.addEventListener('click', e => { if (e.target === box || e.target === close) closeViewer(); });
    document.body.appendChild(box);
  }

  // ---------- events ----------
  document.addEventListener('keydown', e => {
    const t = e.target;
    if (!t || !t.matches) return;
    if (e.key === 'Escape' && document.querySelector('.relack-viewer') && !t.matches(composerSel)) {
      closeViewer();
      return;
    }
    if (t.matches('input[data-relack-search]') && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) {
      e.preventDefault();
      return;
    }
    if (!t.matches(composerSel)) return;
    if (e.isComposing || e.keyCode === 229) return;
    if (mention && mention.ta === t) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const n = mention.items.length;
        mention.index = (mention.index + (e.key === 'ArrowDown' ? 1 : n - 1)) % n;
        renderMention();
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); pickMention(mention.index); return; }
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeMention(); return; }
    }
    if ((e.metaKey || e.ctrlKey) && !e.altKey) {
      const k = e.key.toLowerCase();
      const fmt = k === 'b' ? 'bold' : k === 'i' ? 'italic' : (e.shiftKey && k === 'x') ? 'strike' : '';
      if (fmt) { e.preventDefault(); FORMATS[fmt](t); return; }
    }
    if (e.key === 'Escape' && document.querySelector('.relack-viewer')) {
      e.preventDefault();
      closeViewer();
      return;
    }
    if (e.key === 'Escape' && t.dataset.relackComposer === 'edit') {
      e.preventDefault();
      const cancel = t.closest('form').querySelector('[data-relack-cancel]');
      if (cancel) cancel.click();
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey) {
      if (insideCodeBlock(t)) return; // Enter adds a line inside ``` blocks
      e.preventDefault();
      const form = t.closest('form');
      if (!t.value.trim() && !form.querySelector('[data-relack-pending]') && t.dataset.relackComposer !== 'edit') return;
      closeMention();
      form.requestSubmit();
    }
  }, true);

  document.addEventListener('input', e => {
    const t = e.target;
    if (t && t.matches && t.matches(composerSel)) { autosize(t); updateMention(t); }
  }, true);
  document.addEventListener('focusin', e => {
    const t = e.target;
    if (t && t.matches && t.matches('textarea[data-relack-composer="edit"]') && !t.__relackPlaced) {
      t.__relackPlaced = true;
      t.setSelectionRange(t.value.length, t.value.length);
      autosize(t);
    }
  }, true);
  document.addEventListener('focusout', e => {
    if (mention && e.target === mention.ta) setTimeout(closeMention, 150);
  }, true);
  document.addEventListener('reset', e => {
    const ta = e.target.querySelector && e.target.querySelector(composerSel);
    if (ta) setTimeout(() => autosize(ta), 0);
    closeMention();
  }, true);
  document.addEventListener('pointerdown', unlockAudio, { once: true, capture: true });

  document.addEventListener('click', e => {
    const t = e.target;
    if (!t || !t.closest) return;
    const fmt = t.closest('[data-relack-fmt]');
    if (fmt) {
      e.preventDefault();
      const ta = targetComposer(fmt);
      if (ta && FORMATS[fmt.dataset.relackFmt]) FORMATS[fmt.dataset.relackFmt](ta);
      return;
    }
    const emoji = t.closest('[data-relack-emoji]');
    if (emoji) {
      const ta = targetComposer(emoji);
      if (ta) insertText(ta, emoji.dataset.relackEmoji);
      return;
    }
    const picture = t.closest('img[data-relack-image]');
    if (picture) {
      e.preventDefault();
      openViewer(picture.currentSrc || picture.src, picture.dataset.relackImage);
      return;
    }
    const attach = t.closest('[data-relack-attach]');
    if (attach) {
      e.preventDefault();
      const input = document.querySelector('#' + attach.dataset.relackAttach + ' input[type=file]');
      if (input) input.click();
      return;
    }
    if (t.closest('[data-relack-older]')) {
      const list = document.getElementById('relack-messages');
      if (list) list.__relackPrepend = true;
      return;
    }
    const link = t.closest('a[href^="#mention-"]');
    if (link) {
      e.preventDefault();
      e.stopPropagation();
      const user = decodeURIComponent(link.getAttribute('href').slice('#mention-'.length));
      if (!['here', 'channel', 'everyone'].includes(user)) bridge({ op: 'profile', user });
      return;
    }
    // Let the browser download: Reflex's router would take the click over.
    if (t.closest('a[download]')) e.stopImmediatePropagation();
  }, true);

  document.addEventListener('paste', e => {
    const t = e.target;
    if (!t || !t.matches || !t.matches(composerSel) || !t.dataset.relackUpload) return;
    const files = Array.from((e.clipboardData && e.clipboardData.files) || []);
    if (!files.length) return;
    const text = e.clipboardData.getData('text/plain');
    if (text && text.trim()) return; // e.g. cells copied from a spreadsheet: paste the text
    e.preventDefault();
    upload(t.dataset.relackUpload, files.map(pastedName));
  }, true);

  const dropZone = el => (el && el.closest ? el.closest('[data-relack-drop]') : null);
  const hasFiles = e => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files');
  document.addEventListener('dragover', e => {
    const zone = dropZone(e.target);
    if (!zone || !hasFiles(e)) return;
    e.preventDefault();
    zone.classList.add('relack-dragging');
  }, true);
  document.addEventListener('dragleave', e => {
    const zone = dropZone(e.target);
    if (zone && !zone.contains(e.relatedTarget)) zone.classList.remove('relack-dragging');
  }, true);
  document.addEventListener('drop', e => {
    document.querySelectorAll('.relack-dragging').forEach(n => n.classList.remove('relack-dragging'));
    const zone = dropZone(e.target);
    if (!zone || !hasFiles(e) || !e.dataTransfer.files.length) return;
    e.preventDefault();
    upload(zone.dataset.relackDrop, Array.from(e.dataTransfer.files));
  }, true);
})();
"""

CHAT_CSS = """
.relack-md { font-size: 0.875rem; line-height: 1.5; overflow-wrap: anywhere; }
.relack-md > :first-child { margin-top: 0; }
.relack-md > :last-child { margin-bottom: 0; }
.relack-md p { margin: 0.15rem 0; white-space: pre-wrap; }
.relack-md strong { font-weight: 700; }
.relack-md em { font-style: italic; }
.relack-md del { text-decoration: line-through; }
.relack-md a { text-decoration: underline; text-underline-offset: 2px; word-break: break-all; }
.relack-md code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.8em;
  background: rgba(15, 23, 42, 0.06); border: 1px solid rgba(15, 23, 42, 0.08); border-radius: 4px;
  padding: 0.05rem 0.3rem; color: #be185d;
}
.relack-md pre {
  margin: 0.35rem 0; padding: 0.6rem 0.75rem; border-radius: 0.5rem; background: #0f172a; color: #e2e8f0;
  overflow-x: auto; white-space: pre; font-size: 0.8rem; line-height: 1.45;
}
.relack-md pre code { background: none; border: 0; padding: 0; color: inherit; font-size: inherit; }
.relack-md blockquote { margin: 0.25rem 0; padding-left: 0.65rem; border-left: 3px solid rgba(100, 116, 139, 0.45); }
.relack-md ul { list-style: disc; padding-left: 1.25rem; margin: 0.2rem 0; }
.relack-md ol { list-style: decimal; padding-left: 1.4rem; margin: 0.2rem 0; }
.relack-md li { margin: 0.05rem 0; }
.relack-md table { border-collapse: collapse; margin: 0.3rem 0; font-size: 0.8rem; }
.relack-md th, .relack-md td { border: 1px solid rgba(100, 116, 139, 0.35); padding: 0.2rem 0.45rem; }
.relack-md a[href^="#mention-"] {
  text-decoration: none; font-weight: 600; color: #6d28d9; background: rgba(124, 58, 237, 0.12);
  border-radius: 4px; padding: 0 0.2rem; word-break: normal; cursor: pointer;
}
.relack-md a[href="#mention-here"], .relack-md a[href="#mention-channel"], .relack-md a[href="#mention-everyone"] {
  color: #92400e; background: #fef3c7;
}
.relack-mine .relack-md a { color: #fff; }
.relack-mine .relack-md code { background: rgba(255, 255, 255, 0.18); border-color: rgba(255, 255, 255, 0.25); color: #fff; }
.relack-mine .relack-md pre code { color: inherit; }
.relack-mine .relack-md blockquote { border-left-color: rgba(255, 255, 255, 0.6); }
.relack-mine .relack-md a[href^="#mention-"] { color: #fff; background: rgba(255, 255, 255, 0.22); }
.relack-highlight .relack-bubble { animation: relack-flash 2.6s ease-out; }
@keyframes relack-flash {
  0%, 45% { box-shadow: 0 0 0 3px #fbbf24; }
  100% { box-shadow: 0 0 0 3px rgba(251, 191, 36, 0); }
}
[data-relack-drop] { position: relative; }
[data-relack-drop].relack-dragging::after {
  content: "Drop files to share them"; position: absolute; inset: 8px; display: flex; align-items: center;
  justify-content: center; border: 2px dashed #7c3aed; border-radius: 1rem; background: rgba(245, 243, 255, 0.85);
  color: #6d28d9; font-weight: 600; z-index: 30; pointer-events: none;
}
.relack-viewer {
  position: fixed; inset: 0; z-index: 2000; background: rgba(15, 23, 42, 0.85); display: flex;
  flex-direction: column; align-items: center; justify-content: center; gap: 0.75rem; padding: 2rem;
}
.relack-viewer img { max-width: 92vw; max-height: 82vh; object-fit: contain; border-radius: 0.5rem; background: #fff; }
.relack-viewer-bar { display: flex; align-items: center; gap: 1rem; color: #e2e8f0; font-size: 0.875rem; }
.relack-viewer-bar a, .relack-viewer-bar button {
  color: #fff; background: rgba(255, 255, 255, 0.15); border-radius: 0.5rem; padding: 0.3rem 0.75rem; text-decoration: none;
}
.relack-viewer-bar a:hover, .relack-viewer-bar button:hover { background: rgba(255, 255, 255, 0.25); }
.relack-mention-pop {
  position: absolute; left: 0; bottom: calc(100% + 6px); width: min(22rem, 100%); max-height: 18rem; overflow-y: auto;
  background: #fff; border: 1px solid #e5e7eb; border-radius: 0.75rem; box-shadow: 0 12px 30px rgba(15, 23, 42, 0.15);
  padding: 0.25rem; z-index: 40;
}
.relack-mention-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.35rem 0.5rem; border-radius: 0.5rem; cursor: pointer; }
.relack-mention-item.active { background: #f5f3ff; }
.relack-mention-item img { width: 1.5rem; height: 1.5rem; border-radius: 9999px; background: #ede9fe; }
.relack-mention-at {
  width: 1.5rem; height: 1.5rem; border-radius: 9999px; background: #fef3c7; color: #92400e; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
}
.relack-mention-name { font-size: 0.875rem; font-weight: 600; color: #111827; white-space: nowrap; }
.relack-mention-sub { font-size: 0.75rem; color: #6b7280; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
"""
