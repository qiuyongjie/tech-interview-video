/* Anim Explainer Video v2 — deterministic Canvas runtime.
   Injected by scene-template.html; scene scripts define window.render(ctx, t, S). */
(function () {
  'use strict';

  var STYLE = window.__STYLE || {};
  var TIMELINE = window.__TIMELINE || { scenes: [] };
  var CFG = window.__RENDER_CONFIG || {};
  var sceneId = String(window.__SCENE_ID || '01');
  var scene = (TIMELINE.scenes || []).filter(function (s) { return String(s.id) === sceneId; })[0]
    || { duration: 10, cues: [] };

  var canvas = document.getElementById('stage');
  var W = Number(CFG.width || 1920);
  var H = Number(CFG.height || 1080);
  canvas.width = W;
  canvas.height = H;
  var ctx = canvas.getContext('2d', { alpha: false });

  var C = {
    bg: STYLE.bg || '#0B1020',
    surface: STYLE.surface || '#151D33',
    text: STYLE.text || '#E8EDF7',
    muted: STYLE.muted || '#8A94A8',
    entity: STYLE.entity || '#4CC9F0',
    focus: STYLE.focus || '#FFD166',
    relation: STYLE.relation || '#6B7A99',
    good: STYLE.good || '#06D6A0',
    bad: STYLE.bad || '#EF476F',
    assumption: STYLE.assumption || '#B388FF',
    quantity: STYLE.quantity || '#F6C85F'
  };
  var SANS = STYLE.font_sans || 'Microsoft YaHei';
  var MONO = STYLE.font_mono || 'Consolas';
  var MARGIN = Number(STYLE.margin || 96);
  var SAFE_BOTTOM = Number(STYLE.safe_bottom || 180);

  var boxes = [];
  var lastError = null;

  function clamp01(v) { return Math.max(0, Math.min(1, Number(v) || 0)); }
  function fontString(size, weight, mono) {
    return (weight || 400) + ' ' + size + 'px "' + (mono ? MONO : SANS) + '", sans-serif';
  }
  function roundedPath(x, y, w, h, r) {
    var rr = Math.max(0, Math.min(r || 0, Math.min(w, h) / 2));
    ctx.beginPath();
    if (ctx.roundRect) { ctx.roundRect(x, y, w, h, rr); return; }
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
  }
  function registerText(x, y, text, size, align, lines) {
    if (ctx.globalAlpha < 0.05) return;
    var width = 0;
    (lines || [text]).forEach(function (line) {
      width = Math.max(width, ctx.measureText(line).width);
    });
    var m = ctx.measureText(text);
    var asc = m.actualBoundingBoxAscent || size * 0.82;
    var desc = m.actualBoundingBoxDescent || size * 0.18;
    var left = align === 'center' ? x - width / 2 : (align === 'right' ? x - width : x);
    boxes.push({
      label: String(text).slice(0, 28),
      x: left, y: y - asc, w: width, h: (lines && lines.length ? (lines.length - 1) * size * 1.4 : 0) + asc + desc,
      size: size
    });
  }
  function wrapText(text, maxWidth) {
    var chars = String(text).split('');
    var lines = [];
    var current = '';
    for (var i = 0; i < chars.length; i++) {
      var next = current + chars[i];
      if (current && ctx.measureText(next).width > maxWidth) {
        lines.push(current);
        current = chars[i];
      } else {
        current = next;
      }
    }
    if (current) lines.push(current);
    return lines;
  }
  function mix(c1, c2, p) {
    function rgb(c) {
      var s = String(c).replace('#', '');
      if (s.length === 3) s = s[0] + s[0] + s[1] + s[1] + s[2] + s[2];
      var n = parseInt(s, 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }
    var a = rgb(c1), b = rgb(c2), q = clamp01(p);
    return 'rgb(' + Math.round(a[0] + (b[0] - a[0]) * q) + ',' +
      Math.round(a[1] + (b[1] - a[1]) * q) + ',' +
      Math.round(a[2] + (b[2] - a[2]) * q) + ')';
  }
  function rng(seed) {
    var a = Number(seed) >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  var ease = {
    linear: function (p) { return clamp01(p); },
    outCubic: function (p) { p = clamp01(p); return 1 - Math.pow(1 - p, 3); },
    inCubic: function (p) { p = clamp01(p); return p * p * p; },
    inOutCubic: function (p) {
      p = clamp01(p);
      return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
    },
    outBack: function (p) {
      p = clamp01(p);
      var c = 1.70158;
      return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2);
    },
    outExpo: function (p) { p = clamp01(p); return p >= 1 ? 1 : 1 - Math.pow(2, -10 * p); }
  };

  function drawLine(x1, y1, x2, y2, opts) {
    opts = opts || {};
    var p = opts.progress == null ? 1 : clamp01(opts.progress);
    var ex = x1 + (x2 - x1) * p, ey = y1 + (y2 - y1) * p;
    ctx.save();
    ctx.globalAlpha = opts.alpha == null ? 1 : clamp01(opts.alpha);
    ctx.strokeStyle = opts.color || C.relation;
    ctx.lineWidth = opts.width || 4;
    ctx.lineCap = 'round';
    if (opts.dash) ctx.setLineDash(opts.dash);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(ex, ey);
    ctx.stroke();
    if (opts.arrow && p > 0.01) {
      var ang = Math.atan2(ey - y1, ex - x1);
      var head = opts.head || 16;
      ctx.fillStyle = opts.color || C.relation;
      ctx.beginPath();
      ctx.moveTo(ex, ey);
      ctx.lineTo(ex - head * Math.cos(ang - 0.42), ey - head * Math.sin(ang - 0.42));
      ctx.lineTo(ex - head * Math.cos(ang + 0.42), ey - head * Math.sin(ang + 0.42));
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  function makeS(tNorm, timeSec) {
    var S = {
      W: W, H: H, C: C, style: STYLE,
      t: tNorm, time: timeSec, duration: scene.duration,
      cues: scene.cues || [],
      ease: ease,
      clamp: clamp01,
      clip: clamp01,
      lerp: function (a, b, p) { return a + (b - a) * clamp01(p); },
      seg: function (p, a, b) { return clamp01((clamp01(p) - a) / Math.max(1e-6, b - a)); },
      mix: mix,
      rng: rng,
      cue: function (id) {
        return (scene.cues || []).filter(function (c) { return String(c.id) === String(id); })[0] || null;
      },
      n: function (id) {
        var c = S.cue(id);
        if (!c || !c.duration) return 0;
        return clamp01((timeSec - c.start) / c.duration);
      },
      text: function (str, x, y, o) {
        o = o || {};
        var size = o.size || Number(STYLE.body_px) || 34;
        str = String(str);
        ctx.save();
        ctx.globalAlpha = o.alpha == null ? 1 : clamp01(o.alpha);
        ctx.font = fontString(size, o.weight || 400, !!o.mono);
        ctx.fillStyle = o.color || C.text;
        ctx.textAlign = o.align || 'left';
        ctx.textBaseline = o.baseline || 'alphabetic';
        var maxWidth = o.maxWidth || 0;
        if (maxWidth > 0 && ctx.measureText(str).width > maxWidth) {
          var lines = wrapText(str, maxWidth);
          var lh = size * 1.4;
          lines.forEach(function (line, i) { ctx.fillText(line, x, y + i * lh); });
          registerText(x, y, str, size, ctx.textAlign, lines);
        } else {
          ctx.fillText(str, x, y);
          registerText(x, y, str, size, ctx.textAlign, null);
        }
        ctx.restore();
      },
      rect: function (x, y, w, h, o) {
        o = o || {};
        ctx.save();
        ctx.globalAlpha = o.alpha == null ? 1 : clamp01(o.alpha);
        roundedPath(x, y, w, h, o.radius || 0);
        if (o.fill) { ctx.fillStyle = o.fill; ctx.fill(); }
        if (o.stroke) {
          ctx.strokeStyle = o.stroke;
          ctx.lineWidth = o.lineWidth || 2;
          ctx.stroke();
        }
        ctx.restore();
      },
      line: function (x1, y1, x2, y2, o) { drawLine(x1, y1, x2, y2, o); },
      arrow: function (x1, y1, x2, y2, o) {
        o = o || {};
        o.arrow = true;
        drawLine(x1, y1, x2, y2, o);
      },
      node: function (x, y, r, label, o) {
        o = o || {};
        var p = o.progress == null ? 1 : clamp01(o.progress);
        var color = o.color || C.entity;
        var rad = Math.max(1, r * (0.55 + 0.45 * ease.outCubic(p)));
        ctx.save();
        ctx.globalAlpha = p;
        ctx.beginPath();
        ctx.arc(x, y, rad, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = p * 0.18;
        ctx.fill();
        ctx.globalAlpha = p;
        ctx.lineWidth = o.lineWidth || 3;
        ctx.strokeStyle = color;
        ctx.stroke();
        ctx.restore();
        if (label != null && p > 0.25) {
          S.text(label, x, y + (o.size || 28) * 0.36, {
            size: o.size || 28, color: o.labelColor || C.text, align: 'center', alpha: p
          });
        }
      },
      panel: function (x, y, w, h, title, o) {
        o = o || {};
        var color = o.color || C.entity;
        S.rect(x, y, w, h, {
          fill: C.surface, stroke: color, lineWidth: 2, radius: 16,
          alpha: o.alpha == null ? 1 : o.alpha
        });
        if (title) {
          S.text(title, x + 28, y + 54, {
            size: o.titleSize || Number(STYLE.label_px) || 26, color: color, weight: 600
          });
        }
        (o.bodyLines || []).forEach(function (line, i) {
          S.text(line, x + 28, y + 100 + i * (o.bodySize || 30) * 1.5, {
            size: o.bodySize || 30, color: C.text, maxWidth: w - 56
          });
        });
      },
      code: function (lines, x, y, w, h, o) {
        o = o || {};
        S.rect(x, y, w, h, { fill: '#0D1426', stroke: C.relation, radius: 12 });
        if (o.title) S.text(o.title, x + 20, y + 40, { size: 24, color: C.muted });
        var size = o.size || 26;
        var top = y + (o.title ? 78 : 38);
        var hl = o.highlight || [];
        (lines || []).forEach(function (line, i) {
          var ly = top + i * size * 1.55;
          if (hl.indexOf(i) >= 0) {
            S.rect(x + 12, ly - size, w - 24, size * 1.35, { fill: C.focus, alpha: 0.16, radius: 6 });
          }
          S.text(line, x + 30, ly, { size: size, mono: true, color: C.text });
        });
      },
      chip: function (text, x, y, o) {
        o = o || {};
        var size = o.size || Number(STYLE.label_px) || 26;
        ctx.save();
        ctx.font = fontString(size, 500, false);
        var w = ctx.measureText(String(text)).width + 36;
        ctx.restore();
        var h = size + 22;
        S.rect(x, y, w, h, { fill: o.fill || C.surface, stroke: o.color || C.entity, radius: h / 2 });
        S.text(text, x + w / 2, y + h * 0.72, {
          size: size, color: o.color || C.text, align: 'center', weight: 500
        });
        return { x: x, y: y, w: w, h: h };
      },
      progressBar: function (x, y, w, h, p, o) {
        o = o || {};
        S.rect(x, y, w, h, { fill: C.surface, radius: h / 2 });
        var q = clamp01(p) * w;
        if (q > 1) S.rect(x, y, q, h, { fill: o.color || C.focus, radius: h / 2 });
      },
      stars: function (seed, count, alpha) {
        var r = rng(seed || 1);
        ctx.save();
        ctx.fillStyle = C.text;
        ctx.globalAlpha = alpha == null ? 0.12 : alpha;
        var dx = (timeSec * 7) % W, dy = (timeSec * 3) % H;
        for (var i = 0; i < (count || 60); i++) {
          var x = (r() * W + dx * (0.2 + r() * 0.5)) % W;
          var y = (r() * H + dy * (0.2 + r() * 0.4)) % H;
          var rad = 0.8 + r() * 1.8;
          ctx.beginPath();
          ctx.arc(x, y, rad, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }
    };
    return S;
  }

  function drawSubtitle(timeSec, S) {
    var cue = (scene.cues || []).filter(function (c) {
      return timeSec >= c.start && timeSec < c.end;
    })[0];
    if (!cue || !cue.text) return;
    var text = String(cue.text);
    var size = Number(STYLE.caption_px) || 30;
    ctx.save();
    ctx.font = fontString(size, 500, false);
    var maxW = W - 2 * MARGIN - 48;
    while (ctx.measureText(text).width > maxW && size > 24) {
      size -= 1;
      ctx.font = fontString(size, 500, false);
    }
    var tw = ctx.measureText(text).width;
    var bw = Math.min(maxW + 48, tw + 56);
    var bh = size + 30;
    var bx = (W - bw) / 2;
    var by = H - SAFE_BOTTOM + 24;
    S.rect(bx, by, bw, bh, { fill: C.surface, stroke: C.relation, lineWidth: 1, radius: 14, alpha: 0.95 });
    var baseY = by + bh * 0.72;
    var startX = (W - tw) / 2;
    ctx.font = fontString(size, 500, false);
    ctx.fillStyle = C.text;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(text, startX, baseY);

    // Karaoke highlight: overlay active words in focus color (no QA box registration).
    var cursor = 0;
    (cue.words || []).forEach(function (word) {
      var idx = text.indexOf(String(word.text || ''), cursor);
      if (idx < 0) return;
      cursor = idx + String(word.text).length;
      if (timeSec >= word.start && timeSec < word.end) {
        var prefix = text.slice(0, idx);
        var pw = ctx.measureText(prefix).width;
        ctx.fillStyle = C.focus;
        ctx.fillText(String(word.text), startX + pw, baseY);
      }
    });
    ctx.restore();
  }

  function drawMotionBackground(tp) {
    var scanX = ((tp * 1.25) % 1) * (W + 400) - 200;
    var grad = ctx.createLinearGradient(scanX - 170, 0, scanX + 170, 0);
    grad.addColorStop(0, 'rgba(120,110,90,0)');
    grad.addColorStop(0.5, 'rgba(120,110,90,0.045)');
    grad.addColorStop(1, 'rgba(120,110,90,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(scanX - 170, 0, 340, H);
    ctx.strokeStyle = 'rgba(120,110,90,0.06)';
    ctx.lineWidth = 1;
    for (var i = 0; i < 9; i++) {
      var y = (i * 130 + tp * 46) % H;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
    }
  }

  window.__installRuntime = function () {
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () { window.__READY = true; });
    } else {
      window.__READY = true;
    }
  };
  window.__debugBoxes = function () { return boxes.slice(); };
  window.__lastError = function () { return lastError; };

  window.__renderFrame = function (t) {
    try {
      boxes = [];
      lastError = null;
      var tp = clamp01(t);
      var timeSec = tp * (scene.duration || 10);
      var S = makeS(tp, timeSec);
      ctx.fillStyle = C.bg;
      ctx.fillRect(0, 0, W, H);
      ctx.save();
      var scale = 1.035 + 0.02 * Math.sin(tp * Math.PI * 2);
      var tx = 22 * Math.sin(tp * Math.PI * 2);
      var ty = 14 * Math.cos(tp * Math.PI * 1.3);
      ctx.translate(W / 2 + tx, H / 2 + ty);
      ctx.scale(scale, scale);
      ctx.translate(-W / 2, -H / 2);
      drawMotionBackground(tp);
      if (typeof window.render !== 'function') {
        throw new Error('scene script must define function render(ctx, t, S)');
      }
      window.render(ctx, tp, S);
      ctx.restore();
      drawSubtitle(timeSec, S);
      return { boxes: boxes.slice(), time: timeSec, error: null };
    } catch (err) {
      lastError = String((err && err.stack) || err);
      return { boxes: boxes.slice(), time: 0, error: lastError };
    }
  };
})();
