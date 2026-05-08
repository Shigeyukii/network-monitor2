/**
 * NetworkMap — 星座風ネットワークマップ Canvas レンダラー
 */
const NetworkMap = (() => {
  // ---- 定数 ----
  const BG_STAR_COUNT  = 220;
  const NODE_R_BASE    = 6;
  const NODE_R_MAX     = 16;
  const DRAG_THRESHOLD = 4;   // px: これ以上動いたらドラッグとみなす

  // ---- 状態 ----
  let canvas, ctx;
  let nodes = [], edges = [], bgStars = [];
  let time = 0;
  let rafId = null;
  let dpr   = 1;

  // インタラクション
  let dragging     = null;   // { node, startX, startY, moved }
  let hovering     = null;
  let edgeMode     = false;
  let edgeStart    = null;   // 接続モード時の起点ノード

  // コールバック
  let cbNodeClick    = null;
  let cbPositionSave = null;
  let cbEdgeCreate   = null;
  let cbEdgeMode     = null;  // (active) => 表示を更新

  // ---- 公開 API ----
  function init(canvasEl, callbacks = {}) {
    canvas           = canvasEl;
    ctx              = canvas.getContext("2d");
    cbNodeClick      = callbacks.onNodeClick      || null;
    cbPositionSave   = callbacks.onPositionSave   || null;
    cbEdgeCreate     = callbacks.onEdgeCreate     || null;
    cbEdgeMode       = callbacks.onEdgeModeChange || null;

    generateBgStars();
    setupResize();
    setupEvents();
  }

  function setData(data) {
    nodes = (data.nodes  || []).map(n => ({...n}));
    edges =  data.edges  || [];
  }

  function setEdgeMode(active) {
    edgeMode  = active;
    edgeStart = null;
    canvas.style.cursor = active ? "crosshair" : "default";
  }

  function startAnimation() {
    if (rafId) return;
    function loop(t) {
      time = t / 1000;
      syncSize();
      render();
      rafId = requestAnimationFrame(loop);
    }
    rafId = requestAnimationFrame(loop);
  }

  function stopAnimation() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
  }

  // ---- サイズ同期 ----
  function syncSize() {
    dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    // ゼロサイズの場合は更新しない（非表示状態でキャンバスがリセットされるのを防ぐ）
    if (w === 0 || h === 0) return;
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width  = w * dpr;
      canvas.height = h * dpr;
    }
  }

  function setupResize() {
    new ResizeObserver(() => { if (rafId) syncSize(); }).observe(canvas);
  }

  // ---- 座標変換 ----
  function toAbs(node) {
    return { x: node.x * canvas.width, y: node.y * canvas.height };
  }
  function toRel(cx, cy) {
    return { x: cx / canvas.width, y: cy / canvas.height };
  }
  function clientToCanvas(e) {
    const r  = canvas.getBoundingClientRect();
    return {
      x: (e.clientX - r.left) * dpr,
      y: (e.clientY - r.top)  * dpr,
    };
  }
  function hitTest(cx, cy) {
    const thresh = 22 * dpr;
    for (const n of nodes) {
      const a = toAbs(n);
      if (Math.hypot(cx - a.x, cy - a.y) < thresh) return n;
    }
    return null;
  }

  // ---- イベント ----
  function setupEvents() {
    canvas.addEventListener("mousedown",  onDown);
    canvas.addEventListener("mousemove",  onMove);
    canvas.addEventListener("mouseup",    onUp);
    canvas.addEventListener("mouseleave", () => { hovering = null; });
    canvas.addEventListener("touchstart", e => onDown(e.touches[0]), { passive: true });
    canvas.addEventListener("touchmove",  e => { onMove(e.touches[0]); e.preventDefault(); }, { passive: false });
    canvas.addEventListener("touchend",   e => onUp(e.changedTouches[0]));
  }

  function onDown(e) {
    const { x, y } = clientToCanvas(e);
    const node = hitTest(x, y);
    if (!node) return;

    if (edgeMode) {
      if (!edgeStart) {
        edgeStart = node;
        if (cbEdgeMode) cbEdgeMode(node);
      } else if (edgeStart.device_id !== node.device_id) {
        if (cbEdgeCreate) cbEdgeCreate(edgeStart.device_id, node.device_id);
        edgeStart = null;
        if (cbEdgeMode) cbEdgeMode(null);
      } else {
        edgeStart = null;
        if (cbEdgeMode) cbEdgeMode(null);
      }
      return;
    }

    dragging = { node, startX: x, startY: y, moved: false };
    canvas.style.cursor = "grabbing";
  }

  function onMove(e) {
    const { x, y } = clientToCanvas(e);
    if (dragging) {
      const dx = x - dragging.startX;
      const dy = y - dragging.startY;
      if (!dragging.moved && Math.hypot(dx, dy) > DRAG_THRESHOLD * dpr) {
        dragging.moved = true;
      }
      if (dragging.moved) {
        const rel = toRel(x, y);
        dragging.node.x = Math.max(0.02, Math.min(0.98, rel.x));
        dragging.node.y = Math.max(0.04, Math.min(0.96, rel.y));
      }
    } else {
      hovering = hitTest(x, y);
      canvas.style.cursor = hovering ? "pointer" : (edgeMode ? "crosshair" : "default");
    }
  }

  function onUp(e) {
    if (!dragging) return;
    if (dragging.moved) {
      if (cbPositionSave) cbPositionSave(dragging.node.device_id, dragging.node.x, dragging.node.y);
    } else {
      if (cbNodeClick) cbNodeClick(dragging.node.device_id);
    }
    dragging = null;
    canvas.style.cursor = edgeMode ? "crosshair" : "default";
  }

  // ---- 背景星 ----
  function generateBgStars() {
    bgStars = Array.from({ length: BG_STAR_COUNT }, () => ({
      x:          Math.random(),
      y:          Math.random(),
      r:          Math.random() * 1.2 + 0.2,
      phase:      Math.random() * Math.PI * 2,
      speed:      Math.random() * 0.8 + 0.2,
      brightness: Math.random() * 0.5 + 0.2,
    }));
  }

  function drawBgStars() {
    const W = canvas.width, H = canvas.height;
    for (const s of bgStars) {
      const alpha = s.brightness * (0.6 + 0.4 * Math.sin(time * s.speed + s.phase));
      ctx.globalAlpha = alpha;
      ctx.fillStyle   = "#ffffff";
      ctx.beginPath();
      ctx.arc(s.x * W, s.y * H, s.r * dpr, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---- ノードのスタイル ----
  function nodeRadius(n) {
    let r = NODE_R_BASE * dpr;
    if (n.traffic_bps > 0) {
      const bonus = Math.min(7, Math.log10(Math.max(1, n.traffic_bps / 1e5)) * 2.2);
      r += bonus * dpr;
    }
    return Math.min(r, NODE_R_MAX * dpr);
  }

  function nodeColors(n) {
    if (n.status === "down")    return { fill: "#ff6b6b", glow: "#ff2222", core: "#ffaaaa" };
    if (n.status === "up") {
      if (n.traffic_bps > 5e6)  return { fill: "#f0dda0", glow: "#c8a832", core: "#fffaf0" };
      if (n.traffic_bps > 1e5)  return { fill: "#b8d4ff", glow: "#4488ff", core: "#ffffff" };
      return                           { fill: "#ddeeff", glow: "#6699ff", core: "#ffffff" };
    }
    return                             { fill: "#556677", glow: "#223344", core: "#889aaa" };
  }

  // ---- エッジ描画 ----
  function drawEdges() {
    const W = canvas.width, H = canvas.height;
    for (const e of edges) {
      const src = nodes.find(n => n.device_id === e.source_id);
      const tgt = nodes.find(n => n.device_id === e.target_id);
      if (!src || !tgt) continue;

      const x1 = src.x * W, y1 = src.y * H;
      const x2 = tgt.x * W, y2 = tgt.y * H;

      const anyDown  = src.status === "down"  || tgt.status === "down";
      const bothUp   = src.status === "up"    && tgt.status === "up";
      const maxTraff = Math.max(src.traffic_bps || 0, tgt.traffic_bps || 0);

      let color = anyDown ? "#ff4444" : bothUp ? "#7799ff" : "#445566";
      let alpha = anyDown ? 0.35 : bothUp ? 0.45 : 0.25;
      let lw    = 1 * dpr;

      if (maxTraff > 1e6) {
        const boost = Math.log10(maxTraff / 1e5) * 0.15;
        alpha = Math.min(0.85, alpha + boost);
        lw   += Math.min(3 * dpr, Math.log10(maxTraff / 1e5) * 0.8 * dpr);
        color = maxTraff > 5e6 ? "#e0c86a" : color;
      }

      // 流れるアニメーション（ダッシュオフセット）
      const dashLen  = 12 * dpr;
      const gapLen   = 8  * dpr;
      const dashSpeed = bothUp ? 20 * dpr : 0;
      const offset   = -(time * dashSpeed) % (dashLen + gapLen);

      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = color;
      ctx.lineWidth   = lw;
      ctx.shadowColor = color;
      ctx.shadowBlur  = 8 * dpr;
      ctx.setLineDash(bothUp && maxTraff > 0 ? [dashLen, gapLen] : []);
      ctx.lineDashOffset = offset;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
      ctx.restore();
    }
  }

  // ---- ノード描画 ----
  function drawNodes() {
    const W = canvas.width, H = canvas.height;
    for (const n of nodes) {
      const ax = n.x * W, ay = n.y * H;
      const r  = nodeRadius(n);
      const { fill, glow, core } = nodeColors(n);

      // デバイスごとに固有の瞬き位相
      const phase  = (n.device_id * 2.39996) % (Math.PI * 2);
      const speed  = 0.4 + (n.device_id % 7) * 0.08;
      const twink  = 1 + 0.18 * Math.sin(time * speed + phase);
      const tr     = r * twink;

      const isHover = hovering  && hovering.device_id  === n.device_id;
      const isStart = edgeStart && edgeStart.device_id === n.device_id;
      const glowR   = tr + (isHover ? 6 * dpr : 0);
      const glowB   = (20 + (n.traffic_bps || 0) / 2e6) * dpr;

      ctx.save();

      // 外側グロー
      ctx.shadowColor = glow;
      ctx.shadowBlur  = glowB;
      ctx.fillStyle   = fill;

      // 大きい星は4角星形、小さい星は丸
      if (tr > 8 * dpr) {
        drawSpike(ax, ay, tr, tr * 0.38);
      } else {
        ctx.beginPath();
        ctx.arc(ax, ay, glowR, 0, Math.PI * 2);
        ctx.fill();
      }

      // 中心輝点
      ctx.shadowBlur  = 0;
      ctx.globalAlpha = 0.9;
      ctx.fillStyle   = core;
      ctx.beginPath();
      ctx.arc(ax, ay, tr * 0.35, 0, Math.PI * 2);
      ctx.fill();

      // 接続モード選択リング
      if (isStart) {
        ctx.globalAlpha = 0.7;
        ctx.strokeStyle = "#00ff88";
        ctx.lineWidth   = 2 * dpr;
        ctx.shadowColor = "#00ff88";
        ctx.shadowBlur  = 12 * dpr;
        ctx.beginPath();
        ctx.arc(ax, ay, tr + 7 * dpr, 0, Math.PI * 2);
        ctx.stroke();
      }

      // ホバーリング
      if (isHover && !isStart) {
        ctx.globalAlpha = 0.5;
        ctx.strokeStyle = fill;
        ctx.lineWidth   = 1.5 * dpr;
        ctx.shadowColor = glow;
        ctx.shadowBlur  = 10 * dpr;
        ctx.beginPath();
        ctx.arc(ax, ay, tr + 5 * dpr, 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.restore();

      // ラベル
      ctx.save();
      ctx.font      = `${11 * dpr}px sans-serif`;
      ctx.fillStyle = n.status === "down" ? "#ff9999" : "#99bbdd";
      ctx.textAlign = "center";
      ctx.shadowColor = "#000000";
      ctx.shadowBlur  = 5 * dpr;
      ctx.fillText(n.name, ax, ay + tr + 14 * dpr);
      ctx.restore();
    }
  }

  // 4角星形
  function drawSpike(cx, cy, outer, inner) {
    const pts = 4;
    ctx.beginPath();
    for (let i = 0; i < pts * 2; i++) {
      const a = (i * Math.PI) / pts - Math.PI / 2;
      const r = i % 2 === 0 ? outer : inner;
      i === 0
        ? ctx.moveTo(cx + r * Math.cos(a), cy + r * Math.sin(a))
        : ctx.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a));
    }
    ctx.closePath();
    ctx.fill();
  }

  // ---- ツールチップ ----
  function drawTooltip() {
    const n = hovering;
    if (!n) return;
    const { x: ax, y: ay } = toAbs(n);
    const W = canvas.width, H = canvas.height;

    const lines = [n.name, n.ip_address];
    if (n.status === "up")      lines.push(`RTT: ${n.rtt ? n.rtt.toFixed(1) + " ms" : "—"}`);
    else if (n.status === "down") lines.push("⚠ DOWN");
    else                          lines.push("状態不明");
    if (n.traffic_bps > 0) {
      const bps = n.traffic_bps;
      const fmt = bps >= 1e9 ? (bps/1e9).toFixed(2)+" Gbps"
                : bps >= 1e6 ? (bps/1e6).toFixed(2)+" Mbps"
                : bps >= 1e3 ? (bps/1e3).toFixed(1)+" Kbps"
                :              bps.toFixed(0)+" bps";
      lines.push(`Traffic: ${fmt}`);
    }

    const pad  = 9 * dpr, lh = 16 * dpr;
    const boxW = 160 * dpr, boxH = lines.length * lh + pad * 2;
    let bx = ax + 16 * dpr, by = ay - boxH / 2;
    if (bx + boxW > W - 8) bx = ax - boxW - 16 * dpr;
    by = Math.max(4, Math.min(H - boxH - 4, by));

    ctx.save();
    ctx.globalAlpha = 0.92;
    ctx.fillStyle   = "rgba(8, 12, 36, 0.95)";
    ctx.strokeStyle = "#334477";
    ctx.lineWidth   = 1 * dpr;
    roundRect(bx, by, boxW, boxH, 7 * dpr);
    ctx.fill();
    ctx.stroke();

    lines.forEach((txt, i) => {
      ctx.globalAlpha = 1;
      ctx.font      = i === 0 ? `bold ${12*dpr}px sans-serif` : `${11*dpr}px sans-serif`;
      ctx.fillStyle = i === 0 ? "#cce0ff" : "#7799bb";
      ctx.textAlign = "left";
      ctx.fillText(txt, bx + pad, by + pad + 13 * dpr + i * lh);
    });
    ctx.restore();
  }

  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  // ---- メインレンダリング ----
  function render() {
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    // 夜空グラデーション背景
    const grad = ctx.createRadialGradient(W * 0.5, H * 0.4, 0, W * 0.5, H * 0.5, Math.max(W, H) * 0.75);
    grad.addColorStop(0, "#0b1035");
    grad.addColorStop(1, "#020510");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    drawBgStars();
    drawEdges();
    drawNodes();
    drawTooltip();
  }

  return { init, setData, setEdgeMode, startAnimation, stopAnimation };
})();
