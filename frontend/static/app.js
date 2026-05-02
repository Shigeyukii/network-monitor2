// ============================================================
// API helpers
// ============================================================
const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async del(path) {
    const r = await fetch(path, { method: "DELETE" });
    if (!r.ok && r.status !== 204) throw new Error(await r.text());
  },
};

// ============================================================
// Toast
// ============================================================
function toast(msg, type = "success") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ============================================================
// Utilities
// ============================================================
function fmtBps(bps) {
  if (bps === null || bps === undefined) return "—";
  if (bps >= 1e9) return (bps / 1e9).toFixed(2) + " Gbps";
  if (bps >= 1e6) return (bps / 1e6).toFixed(2) + " Mbps";
  if (bps >= 1e3) return (bps / 1e3).toFixed(1) + " Kbps";
  return bps.toFixed(0) + " bps";
}

function fmtRtt(ms) {
  if (ms === null || ms === undefined) return "—";
  return ms.toFixed(1) + " ms";
}

function fmtTime(ts) {
  if (!ts) return "—";
  const d = new Date(ts.replace(" ", "T"));
  return d.toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function statusLabel(ping) {
  if (!ping) return "unknown";
  return ping.status ? "up" : "down";
}

function statusText(ping) {
  if (!ping) return "不明";
  return ping.status ? "UP" : "DOWN";
}

// ============================================================
// App state
// ============================================================
const state = {
  view: "dashboard",      // "dashboard" | "detail" | "settings"
  devices: [],
  groups: [],
  summary: {},
  activeGroupId: null,    // null=すべて, -1=未グループ, N=グループID
  detail: { device: null, hours: 24, ifIndex: null },
  charts: {},
  refreshTimer: null,
  detailTimer: null,
};

function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
  state.view = name;
}

// ============================================================
// Dashboard
// ============================================================
async function loadDashboard() {
  try {
    const [devices, groups, summary] = await Promise.all([
      api.get("/api/devices"),
      api.get("/api/groups"),
      api.get("/api/metrics/summary"),
    ]);
    state.devices = devices;
    state.groups  = groups;
    state.summary = summary;
    renderSummary(summary);
    renderGroupTabs();
    renderDeviceGrid(filteredDevices());
  } catch (e) {
    toast("デバイス一覧の取得に失敗しました: " + e.message, "error");
  }
}

function renderSummary(s) {
  document.getElementById("sum-total").textContent   = s.total;
  document.getElementById("sum-up").textContent      = s.up;
  document.getElementById("sum-down").textContent    = s.down;
  document.getElementById("sum-unknown").textContent = s.unknown;
}

function filteredDevices() {
  if (state.activeGroupId === null) return state.devices;
  if (state.activeGroupId === -1)   return state.devices.filter(d => !d.group_id);
  return state.devices.filter(d => d.group_id === state.activeGroupId);
}

function renderGroupTabs() {
  const container = document.getElementById("group-tabs");
  const allCount = state.devices.length;
  const ungrouped = state.devices.filter(d => !d.group_id).length;

  const tabs = [
    { id: null, label: "すべて", color: null, count: allCount },
    ...state.groups.map(g => ({ id: g.id, label: g.name, color: g.color, count: g.device_count })),
  ];
  if (ungrouped > 0) {
    tabs.push({ id: -1, label: "未グループ", color: "#8b949e", count: ungrouped });
  }

  container.innerHTML = tabs.map(t => {
    const isActive = state.activeGroupId === t.id;
    const dotHtml  = t.color ? `<span class="tab-dot" style="background:${t.color}"></span>` : "";
    const style    = isActive && t.color ? `background:${t.color}` :
                     isActive            ? `background:var(--accent)` : "";
    return `<button class="group-tab ${isActive ? "active" : ""}" style="${style}"
              onclick="setGroupFilter(${t.id === null ? "null" : t.id})">
              ${dotHtml}${esc(t.label)}
              <span class="tab-count">${t.count}</span>
            </button>`;
  }).join("");
}

function setGroupFilter(id) {
  state.activeGroupId = id;
  renderGroupTabs();
  renderDeviceGrid(filteredDevices());
}

function renderDeviceGrid(devices) {
  const grid = document.getElementById("device-grid");
  if (devices.length === 0) {
    const isEmpty = state.devices.length === 0;
    grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
      <div class="icon">📡</div>
      <p>${isEmpty ? "監視デバイスがまだ登録されていません" : "このグループにはデバイスがありません"}</p>
      ${isEmpty ? `<button class="btn btn-primary" onclick="openAddDevice()">＋ デバイスを追加</button>` : ""}
    </div>`;
    return;
  }
  grid.innerHTML = devices.map(d => {
    const st  = statusLabel(d.latest_ping);
    const rtt = d.latest_ping ? fmtRtt(d.latest_ping.response_time) : "—";
    const ts  = d.latest_ping ? fmtTime(d.latest_ping.timestamp) : "未確認";
    const groupBadge = d.group
      ? `<span class="group-badge"><span class="dot" style="background:${d.group.color}"></span>${esc(d.group.name)}</span>`
      : "";
    return `<div class="device-card status-${st}" onclick="openDetail(${d.id})">
      <div class="card-top">
        <div>
          <div class="device-name">${esc(d.name)}</div>
          <div class="device-ip">${esc(d.ip_address)}</div>
        </div>
        <span class="status-badge ${st}">${statusText(d.latest_ping)}</span>
      </div>
      <div class="device-meta">
        <span class="rtt">RTT: ${rtt}</span>
        ${d.snmp_enabled ? `<span>📊 SNMP</span>` : ""}
      </div>
      ${groupBadge}
      <div style="font-size:11px;color:var(--muted);margin-top:6px">${ts}</div>
    </div>`;
  }).join("");
}

function esc(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ============================================================
// Detail view
// ============================================================
async function openDetail(deviceId) {
  clearInterval(state.detailTimer);
  destroyCharts();
  state.detail.device = state.devices.find(d => d.id === deviceId) || { id: deviceId };
  state.detail.hours = 24;
  state.detail.ifIndex = null;
  showView("detail");
  await refreshDetail();
  state.detailTimer = setInterval(refreshDetail, 60_000);
}

async function refreshDetail() {
  const id = state.detail.device.id;
  try {
    const [device, pingData, portData] = await Promise.all([
      api.get(`/api/devices/${id}`),
      api.get(`/api/metrics/ping/${id}?hours=${state.detail.hours}`),
      api.get(`/api/devices/${id}/ports`),
    ]);
    state.detail.device = device;
    renderDetailHeader(device);
    renderDeviceInfo(device);
    renderPingChart(pingData);
    renderUptimeBar(pingData);
    renderPortTable(portData, id);

    if (device.snmp_enabled) {
      document.getElementById("traffic-section").style.display = "";
      const ifIdx = state.detail.ifIndex ? `&if_index=${state.detail.ifIndex}` : "";
      const trafficData = await api.get(`/api/metrics/traffic/${id}?hours=${state.detail.hours}${ifIdx}`);
      renderIfaceSelector(trafficData, device.id);
      renderTrafficChart(trafficData);
    } else {
      document.getElementById("traffic-section").style.display = "none";
    }
  } catch (e) {
    toast("詳細データ取得失敗: " + e.message, "error");
  }
}

function renderDetailHeader(d) {
  const st = statusLabel(d.latest_ping);
  document.getElementById("detail-title").textContent = d.name;
  document.getElementById("detail-ip").textContent    = d.ip_address;
  const badge = document.getElementById("detail-status");
  badge.className = `status-badge ${st}`;
  badge.textContent = statusText(d.latest_ping);
  document.getElementById("btn-edit-device").onclick   = () => openEditDevice(d.id);
  document.getElementById("btn-delete-device").onclick = () => confirmDelete(d.id, d.name);
}

function renderDeviceInfo(d) {
  const rtt = d.latest_ping ? fmtRtt(d.latest_ping.response_time) : "—";
  const ts  = d.latest_ping ? fmtTime(d.latest_ping.timestamp) : "未確認";
  document.getElementById("info-ip").textContent        = d.ip_address;
  document.getElementById("info-rtt").textContent       = rtt;
  document.getElementById("info-lastcheck").textContent = ts;
  document.getElementById("info-interval").textContent  = d.ping_interval + " 秒";
  document.getElementById("info-snmp").textContent      = d.snmp_enabled
    ? `有効 (${d.snmp_community} / ${d.snmp_version})`
    : "無効";
}

function renderUptimeBar(pingData) {
  const bar = document.getElementById("uptime-bar");
  if (pingData.length === 0) { bar.innerHTML = ""; return; }
  const BUCKETS = 48;
  const total = pingData.length;
  const size  = Math.max(1, Math.ceil(total / BUCKETS));
  const segs  = [];
  for (let i = 0; i < total; i += size) {
    const slice = pingData.slice(i, i + size);
    const up = slice.filter(p => p.status).length;
    segs.push(up / slice.length >= 0.5 ? "up" : "down");
  }
  const upCount = pingData.filter(p => p.status).length;
  const pct = total > 0 ? ((upCount / total) * 100).toFixed(1) : "—";
  document.getElementById("uptime-pct").textContent = `稼働率: ${pct}%`;
  bar.innerHTML = segs.map(s => `<div class="uptime-seg ${s}" title="${s}"></div>`).join("");
}

// ---- Ping chart ----
function renderPingChart(data) {
  destroyChart("ping");
  const ctx = document.getElementById("ping-chart").getContext("2d");
  const labels  = data.map(p => new Date(p.timestamp.replace(" ", "T")));
  const values  = data.map(p => p.status ? p.response_time : null);
  const colors  = data.map(p => p.status ? "rgba(63,185,80,0.9)" : "rgba(248,81,73,0.9)");

  state.charts.ping = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "応答時間 (ms)",
        data: values,
        borderColor: "rgba(88,166,255,0.8)",
        backgroundColor: "rgba(88,166,255,0.1)",
        pointBackgroundColor: colors,
        pointRadius: data.length > 200 ? 2 : 4,
        pointBorderWidth: 0,
        tension: 0.3,
        fill: true,
        spanGaps: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          type: "time",
          time: { tooltipFormat: "MM/dd HH:mm:ss", displayFormats: { hour: "HH:mm", minute: "HH:mm" } },
          ticks: { color: "#8b949e", maxTicksLimit: 8 },
          grid: { color: "rgba(48,54,61,0.6)" },
        },
        y: {
          beginAtZero: true,
          ticks: { color: "#8b949e" },
          grid: { color: "rgba(48,54,61,0.6)" },
          title: { display: true, text: "ms", color: "#8b949e" },
        },
      },
    },
  });
}

// ---- Traffic chart ----
function renderIfaceSelector(trafficData, deviceId) {
  const sel = document.getElementById("iface-select");
  const current = state.detail.ifIndex;
  sel.innerHTML = '<option value="">全インターフェース</option>' +
    trafficData.map(i => `<option value="${i.if_index}" ${i.if_index == current ? "selected" : ""}>${esc(i.if_name || "if" + i.if_index)}</option>`).join("");
  sel.onchange = () => {
    state.detail.ifIndex = sel.value ? parseInt(sel.value) : null;
    refreshDetail();
  };
}

function renderTrafficChart(trafficData) {
  destroyChart("traffic");
  if (!trafficData || trafficData.length === 0) return;

  // Use first interface if none selected, or the selected one
  const iface = state.detail.ifIndex
    ? trafficData.find(i => i.if_index === state.detail.ifIndex)
    : trafficData[0];
  if (!iface || iface.data.length === 0) {
    document.getElementById("no-traffic-msg").style.display = "";
    return;
  }
  document.getElementById("no-traffic-msg").style.display = "none";

  const ctx = document.getElementById("traffic-chart").getContext("2d");
  const labels  = iface.data.map(r => new Date(r.timestamp.replace(" ", "T")));
  const inData  = iface.data.map(r => r.in_bps);
  const outData = iface.data.map(r => r.out_bps);

  state.charts.traffic = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "受信 (In)",
          data: inData,
          borderColor: "rgba(88,166,255,0.9)",
          backgroundColor: "rgba(88,166,255,0.15)",
          pointRadius: inData.length > 200 ? 1 : 3,
          pointBorderWidth: 0,
          tension: 0.3,
          fill: true,
        },
        {
          label: "送信 (Out)",
          data: outData,
          borderColor: "rgba(63,185,80,0.9)",
          backgroundColor: "rgba(63,185,80,0.15)",
          pointRadius: outData.length > 200 ? 1 : 3,
          pointBorderWidth: 0,
          tension: 0.3,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#8b949e" } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${fmtBps(ctx.raw)}`,
          },
        },
      },
      scales: {
        x: {
          type: "time",
          time: { tooltipFormat: "MM/dd HH:mm:ss", displayFormats: { hour: "HH:mm", minute: "HH:mm" } },
          ticks: { color: "#8b949e", maxTicksLimit: 8 },
          grid: { color: "rgba(48,54,61,0.6)" },
        },
        y: {
          beginAtZero: true,
          ticks: {
            color: "#8b949e",
            callback: v => fmtBps(v),
          },
          grid: { color: "rgba(48,54,61,0.6)" },
        },
      },
    },
  });
}

function destroyChart(name) {
  if (state.charts[name]) {
    state.charts[name].destroy();
    delete state.charts[name];
  }
}
function destroyCharts() {
  Object.keys(state.charts).forEach(destroyChart);
}

// ============================================================
// Add / Edit device modal
// ============================================================
function populateGroupSelect(selectedGroupId) {
  const sel = document.getElementById("field-group-id");
  sel.innerHTML = '<option value="">未グループ</option>' +
    state.groups.map(g =>
      `<option value="${g.id}" ${g.id === selectedGroupId ? "selected" : ""}>${esc(g.name)}</option>`
    ).join("");
}

function openAddDevice() {
  const modal = document.getElementById("device-modal");
  document.getElementById("modal-title").textContent  = "デバイスを追加";
  document.getElementById("modal-submit").textContent = "追加";
  document.getElementById("device-form").reset();
  document.getElementById("device-id").value = "";
  populateGroupSelect(null);
  toggleSnmpFields();
  modal.style.display = "flex";
}

async function openEditDevice(id) {
  try {
    const d = await api.get(`/api/devices/${id}`);
    const modal = document.getElementById("device-modal");
    document.getElementById("modal-title").textContent  = "デバイスを編集";
    document.getElementById("modal-submit").textContent = "保存";
    document.getElementById("device-id").value            = d.id;
    document.getElementById("field-name").value           = d.name;
    document.getElementById("field-ip").value             = d.ip_address;
    document.getElementById("field-ping-interval").value  = d.ping_interval;
    populateGroupSelect(d.group_id || null);
    document.getElementById("field-snmp-enabled").checked = !!d.snmp_enabled;
    document.getElementById("field-community").value      = d.snmp_community;
    document.getElementById("field-port").value           = d.snmp_port;
    document.getElementById("field-version").value        = d.snmp_version;
    toggleSnmpFields();
    modal.style.display = "flex";
  } catch (e) {
    toast("デバイス情報取得失敗: " + e.message, "error");
  }
}

function toggleSnmpFields() {
  const enabled = document.getElementById("field-snmp-enabled").checked;
  document.getElementById("snmp-fields").classList.toggle("visible", enabled);
}

function closeDeviceModal() {
  document.getElementById("device-modal").style.display = "none";
}

async function submitDeviceForm(e) {
  e.preventDefault();
  const id = document.getElementById("device-id").value;
  const groupVal = document.getElementById("field-group-id").value;
  const body = {
    name:           document.getElementById("field-name").value.trim(),
    ip_address:     document.getElementById("field-ip").value.trim(),
    ping_interval:  parseInt(document.getElementById("field-ping-interval").value) || 60,
    group_id:       groupVal ? parseInt(groupVal) : null,
    snmp_enabled:   document.getElementById("field-snmp-enabled").checked,
    snmp_community: document.getElementById("field-community").value.trim() || "public",
    snmp_port:      parseInt(document.getElementById("field-port").value) || 161,
    snmp_version:   document.getElementById("field-version").value,
  };
  try {
    if (id) {
      await api.put(`/api/devices/${id}`, body);
      toast("デバイスを更新しました");
    } else {
      await api.post("/api/devices", body);
      toast("デバイスを追加しました");
    }
    closeDeviceModal();
    await loadDashboard();
    if (id && state.view === "detail" && state.detail.device?.id === parseInt(id)) {
      await refreshDetail();
    }
  } catch (e) {
    toast("保存失敗: " + e.message, "error");
  }
}

async function confirmDelete(id, name) {
  if (!confirm(`「${name}」を削除しますか？\n関連する全データも削除されます。`)) return;
  try {
    await api.del(`/api/devices/${id}`);
    toast(`「${name}」を削除しました`);
    clearInterval(state.detailTimer);
    showView("dashboard");
    await loadDashboard();
  } catch (e) {
    toast("削除失敗: " + e.message, "error");
  }
}

// ============================================================
// Group management modal
// ============================================================

const GROUP_COLORS = [
  "#58a6ff", "#3fb950", "#d29922", "#f85149",
  "#bc8cff", "#ff7b72", "#39d353", "#8b949e",
];

function openGroupModal() {
  renderColorPicker("#58a6ff");
  renderGroupList();
  document.getElementById("group-modal").style.display = "flex";
}

function closeGroupModal() {
  document.getElementById("group-modal").style.display = "none";
}

function renderColorPicker(selected) {
  document.getElementById("new-group-color").value = selected;
  document.getElementById("color-picker").innerHTML = GROUP_COLORS.map(c =>
    `<span class="color-swatch ${c === selected ? "selected" : ""}"
           style="background:${c}" title="${c}"
           onclick="selectColor('${c}')"></span>`
  ).join("");
}

function selectColor(color) {
  document.getElementById("new-group-color").value = color;
  renderColorPicker(color);
}

function renderGroupList() {
  const el = document.getElementById("group-list");
  if (state.groups.length === 0) {
    el.innerHTML = `<p style="color:var(--muted);font-size:13px">グループはまだありません</p>`;
    return;
  }
  el.innerHTML = state.groups.map(g => `
    <div class="group-list-item" id="group-item-${g.id}">
      <span class="group-color-dot" style="background:${g.color}"></span>
      <span class="group-name">${esc(g.name)}</span>
      <span class="group-meta">${g.device_count} 台</span>
      <button class="btn btn-sm" onclick="startEditGroup(${g.id}, '${esc(g.name)}', '${g.color}')">編集</button>
      <button class="btn btn-sm btn-danger" onclick="deleteGroup(${g.id}, '${esc(g.name)}')">削除</button>
    </div>
  `).join("");
}

function startEditGroup(id, name, color) {
  const item = document.getElementById(`group-item-${id}`);
  item.innerHTML = `
    <span class="group-color-dot" style="background:${color}"></span>
    <input class="group-edit-input" id="edit-name-${id}" value="${esc(name)}">
    <button class="btn btn-sm btn-primary" onclick="submitEditGroup(${id}, '${color}')">保存</button>
    <button class="btn btn-sm" onclick="renderGroupList()">キャンセル</button>
  `;
}

async function submitEditGroup(id, color) {
  const name = document.getElementById(`edit-name-${id}`).value.trim();
  if (!name) return;
  try {
    await api.put(`/api/groups/${id}`, { name, color });
    await reloadGroups();
    toast("グループを更新しました");
  } catch (e) {
    toast("更新失敗: " + e.message, "error");
  }
}

async function deleteGroup(id, name) {
  if (!confirm(`「${name}」を削除しますか？\n所属デバイスは未グループになります。`)) return;
  try {
    await api.del(`/api/groups/${id}`);
    await reloadGroups();
    if (state.activeGroupId === id) state.activeGroupId = null;
    toast(`「${name}」を削除しました`);
  } catch (e) {
    toast("削除失敗: " + e.message, "error");
  }
}

async function submitAddGroup(e) {
  e.preventDefault();
  const name  = document.getElementById("new-group-name").value.trim();
  const color = document.getElementById("new-group-color").value;
  if (!name) return;
  try {
    await api.post("/api/groups", { name, color });
    document.getElementById("new-group-name").value = "";
    renderColorPicker("#58a6ff");
    await reloadGroups();
    toast(`「${name}」を追加しました`);
  } catch (e) {
    toast("追加失敗: " + e.message, "error");
  }
}

async function reloadGroups() {
  state.groups = await api.get("/api/groups");
  state.devices = await api.get("/api/devices");
  renderGroupList();
  renderGroupTabs();
  renderDeviceGrid(filteredDevices());
}

// ============================================================
// Port management (in detail view)
// ============================================================

function renderPortTable(ports, deviceId) {
  const tbody = document.getElementById("port-table-body");
  const empty = document.getElementById("port-empty");

  if (ports.length === 0) {
    tbody.innerHTML = "";
    empty.style.display = "";
    return;
  }
  empty.style.display = "none";
  tbody.innerHTML = ports.map(p => {
    const st  = p.latest ? (p.latest.status ? "up" : "down") : "unknown";
    const rtt = p.latest?.response_time ? fmtRtt(p.latest.response_time) : "—";
    const ts  = p.latest ? fmtTime(p.latest.timestamp) : "未確認";
    const stText = st === "up" ? "OPEN" : st === "down" ? "CLOSED" : "不明";
    return `<tr>
      <td><span class="port-num">${p.port}</span></td>
      <td>${esc(p.label || "—")}</td>
      <td><span class="status-badge ${st}">${stText}</span></td>
      <td>${rtt}</td>
      <td style="font-size:11px;color:var(--muted)">${ts}</td>
      <td><button class="btn btn-sm btn-danger"
            onclick="removePort(${deviceId}, ${p.port})">削除</button></td>
    </tr>`;
  }).join("");
}

async function removePort(deviceId, port) {
  if (!confirm(`ポート ${port} の監視を削除しますか？`)) return;
  try {
    await api.del(`/api/devices/${deviceId}/ports/${port}`);
    toast(`ポート ${port} を削除しました`);
    refreshDetail();
  } catch (e) {
    toast("削除失敗: " + e.message, "error");
  }
}

async function submitAddPort(e) {
  e.preventDefault();
  const deviceId = state.detail.device.id;
  const port  = parseInt(document.getElementById("new-port-num").value);
  const label = document.getElementById("new-port-label").value.trim();
  if (!port) return;
  try {
    await api.post(`/api/devices/${deviceId}/ports`, { port, label });
    document.getElementById("new-port-num").value   = "";
    document.getElementById("new-port-label").value = "";
    toast(`ポート ${port} を追加しました`);
    refreshDetail();
  } catch (e) {
    toast("追加失敗: " + e.message, "error");
  }
}

// ============================================================
// Report view
// ============================================================

async function openReport() {
  showView("report");
  try {
    const data = await api.get("/api/reports/uptime");
    renderReportTable(data);
  } catch (e) {
    toast("レポート取得失敗: " + e.message, "error");
  }
}

function fmtUptime(u) {
  if (!u || u.pct === null) return `<span class="uptime-pct nodata">—</span>`;
  const cls = u.pct >= 99 ? "high" : u.pct >= 95 ? "mid" : "low";
  return `<span class="uptime-pct ${cls}">${u.pct}%</span>`;
}

function renderReportTable(data) {
  const tbody  = document.getElementById("report-tbody");
  const empty  = document.getElementById("report-empty");
  const table  = document.getElementById("report-table");

  if (data.length === 0) {
    table.style.display = "none";
    empty.style.display = "";
    return;
  }
  table.style.display = "";
  empty.style.display = "none";

  tbody.innerHTML = data.map(r => {
    const st = statusLabel(r.latest_ping);
    const groupBadge = r.group
      ? `<span class="group-badge"><span class="dot" style="background:${r.group.color}"></span>${esc(r.group.name)}</span>`
      : `<span style="color:var(--muted);font-size:12px">未グループ</span>`;
    return `<tr>
      <td style="font-weight:600">${esc(r.name)}</td>
      <td style="font-family:monospace;font-size:12px">${esc(r.ip_address)}</td>
      <td>${groupBadge}</td>
      <td><span class="status-badge ${st}">${statusText(r.latest_ping)}</span></td>
      <td>${fmtUptime(r.uptimes["1h"])}</td>
      <td>${fmtUptime(r.uptimes["24h"])}</td>
      <td>${fmtUptime(r.uptimes["7d"])}</td>
      <td>${fmtUptime(r.uptimes["30d"])}</td>
    </tr>`;
  }).join("");
}

// ============================================================
// Alert panel
// ============================================================

function openAlertPanel() {
  document.getElementById("alert-overlay").style.display = "block";
  document.getElementById("alert-panel").classList.add("open");
  loadAlerts();
}

function closeAlertPanel() {
  document.getElementById("alert-overlay").style.display = "none";
  document.getElementById("alert-panel").classList.remove("open");
}

async function loadAlerts() {
  try {
    const alerts = await api.get("/api/alerts?limit=100");
    renderAlertList(alerts);
  } catch (e) {
    toast("アラート取得失敗: " + e.message, "error");
  }
}

function renderAlertList(alerts) {
  const el = document.getElementById("alert-list");
  if (alerts.length === 0) {
    el.innerHTML = `<div class="alert-empty"><div class="icon">🔕</div>アラートはありません</div>`;
    return;
  }
  el.innerHTML = alerts.map(a => {
    const isDown     = a.type === "down";
    const icon       = isDown ? "🔴" : "🟢";
    const msgClass   = isDown ? "down" : "recovery";
    const msgText    = isDown ? "障害検知 (DOWN)" : "復旧 (UP)";
    const unreadCls  = a.acknowledged ? "" : "unread";
    return `<div class="alert-item ${unreadCls}" id="alert-item-${a.id}">
      <span class="alert-icon">${icon}</span>
      <div class="alert-body">
        <div class="alert-device">${esc(a.device_name)} <span class="ip">${esc(a.device_ip_address)}</span></div>
        <div class="alert-msg ${msgClass}">${msgText}</div>
        <div class="alert-time">${fmtTime(a.timestamp)}</div>
      </div>
      ${!a.acknowledged
        ? `<button class="alert-ack-btn" title="既読にする" onclick="acknowledgeAlert(${a.id})">✓</button>`
        : ""}
    </div>`;
  }).join("");
}

async function acknowledgeAlert(id) {
  try {
    await api.put(`/api/alerts/${id}/acknowledge`);
    const item = document.getElementById(`alert-item-${id}`);
    if (item) {
      item.classList.remove("unread");
      item.querySelector(".alert-ack-btn")?.remove();
    }
    await refreshAlertBadge();
  } catch (e) {
    toast("既読化失敗: " + e.message, "error");
  }
}

async function acknowledgeAll() {
  try {
    await api.post("/api/alerts/acknowledge-all", {});
    await loadAlerts();
    await refreshAlertBadge();
    toast("すべて既読にしました");
  } catch (e) {
    toast("既読化失敗: " + e.message, "error");
  }
}

async function refreshAlertBadge() {
  try {
    const { count } = await api.get("/api/alerts/unread-count");
    const badge = document.getElementById("alert-badge");
    if (count > 0) {
      badge.textContent = count > 99 ? "99+" : count;
      badge.style.display = "flex";
    } else {
      badge.style.display = "none";
    }
  } catch (_) {}
}

function startAlertBadgeRefresh() {
  refreshAlertBadge();
  setInterval(refreshAlertBadge, 30_000);
}

// ============================================================
// Settings view
// ============================================================
async function openSettings() {
  showView("settings");
  try {
    const s = await api.get("/api/settings");
    document.getElementById("setting-ping-interval").value    = s.ping_interval ?? 60;
    document.getElementById("setting-snmp-interval").value    = s.snmp_interval ?? 60;
    document.getElementById("setting-teams-url").value        = s.teams_webhook_url ?? "";
    document.getElementById("setting-slack-url").value        = s.slack_webhook_url ?? "";
    document.getElementById("setting-notify-down").checked    = s.notify_on_down !== 0;
    document.getElementById("setting-notify-recovery").checked = s.notify_on_recovery !== 0;
  } catch (e) {
    toast("設定取得失敗: " + e.message, "error");
  }
}

async function saveSettings(e) {
  e.preventDefault();
  const body = {
    ping_interval:      parseInt(document.getElementById("setting-ping-interval").value),
    snmp_interval:      parseInt(document.getElementById("setting-snmp-interval").value),
    teams_webhook_url:  document.getElementById("setting-teams-url").value.trim(),
    slack_webhook_url:  document.getElementById("setting-slack-url").value.trim(),
    notify_on_down:     document.getElementById("setting-notify-down").checked    ? 1 : 0,
    notify_on_recovery: document.getElementById("setting-notify-recovery").checked ? 1 : 0,
  };
  try {
    await api.put("/api/settings", body);
    await api.post("/api/settings/reschedule", {});
    toast("設定を保存しました");
  } catch (e) {
    toast("設定保存失敗: " + e.message, "error");
  }
}

// ============================================================
// Import / Export
// ============================================================

function initImportExport() {
  document.getElementById("import-file-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const resultEl = document.getElementById("import-result");
    resultEl.style.display = "";
    resultEl.style.color   = "var(--muted)";
    resultEl.textContent   = "読み込み中...";

    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const result = await api.post("/api/import", data);

      resultEl.style.color = "var(--green)";
      resultEl.innerHTML =
        `✅ インポート完了<br>` +
        `グループ: ${result.groups_created} 件追加 / ${result.groups_skipped} 件スキップ<br>` +
        `デバイス: ${result.devices_created} 件追加 / ${result.devices_skipped} 件スキップ<br>` +
        `ポート設定: ${result.ports_created} 件追加`;

      // ダッシュボードのデバイス一覧を更新
      await loadDashboard();
      toast(`デバイス ${result.devices_created} 件をインポートしました`);
    } catch (e) {
      resultEl.style.color = "var(--red)";
      resultEl.textContent = "❌ インポート失敗: " + e.message;
      toast("インポート失敗: " + e.message, "error");
    }

    // ファイル選択をリセット（同じファイルを再選択できるよう）
    e.target.value = "";
  });
}

async function testNotify(target) {
  const url = document.getElementById(
    target === "teams" ? "setting-teams-url" : "setting-slack-url"
  ).value.trim();
  if (!url) {
    toast("URL を入力してください", "error");
    return;
  }
  try {
    const result = await api.post("/api/settings/test-notify", { target, url });
    if (result.ok) {
      toast(`${target === "teams" ? "Teams" : "Slack"} へテスト送信しました`);
    } else {
      toast(`送信失敗: ${result.detail || "不明なエラー"}`, "error");
    }
  } catch (e) {
    toast("テスト送信失敗: " + e.message, "error");
  }
}

// ============================================================
// Hours selector in detail
// ============================================================
function setDetailHours(hours) {
  state.detail.hours = hours;
  document.querySelectorAll(".hours-btn").forEach(b => {
    b.classList.toggle("active", parseInt(b.dataset.hours) === hours);
  });
  refreshDetail();
}

// ============================================================
// Auto-refresh
// ============================================================
function startDashboardRefresh() {
  clearInterval(state.refreshTimer);
  state.refreshTimer = setInterval(() => {
    if (state.view === "dashboard") loadDashboard();
  }, 30_000);
}

// ============================================================
// Init
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  // Nav
  document.getElementById("nav-home").addEventListener("click", () => {
    clearInterval(state.detailTimer);
    showView("dashboard");
    loadDashboard();
  });
  document.getElementById("btn-add-device").addEventListener("click", openAddDevice);
  document.getElementById("btn-settings").addEventListener("click", openSettings);
  document.getElementById("btn-manage-groups").addEventListener("click", openGroupModal);
  document.getElementById("btn-report").addEventListener("click", openReport);
  document.getElementById("btn-report-back").addEventListener("click", () => {
    showView("dashboard");
    loadDashboard();
  });

  // Port form in detail view
  document.getElementById("port-add-form").addEventListener("submit", submitAddPort);

  // Group modal
  document.getElementById("group-modal-close").addEventListener("click", closeGroupModal);
  document.getElementById("group-modal").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeGroupModal();
  });
  document.getElementById("group-add-form").addEventListener("submit", submitAddGroup);

  // Device form
  document.getElementById("device-form").addEventListener("submit", submitDeviceForm);
  document.getElementById("field-snmp-enabled").addEventListener("change", toggleSnmpFields);
  document.getElementById("modal-cancel").addEventListener("click", closeDeviceModal);
  document.getElementById("device-modal").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeDeviceModal();
  });

  // Settings form
  document.getElementById("settings-form").addEventListener("submit", saveSettings);
  document.getElementById("btn-settings-back").addEventListener("click", () => {
    showView("dashboard");
    loadDashboard();
  });

  // Detail back
  document.getElementById("btn-detail-back").addEventListener("click", () => {
    clearInterval(state.detailTimer);
    destroyCharts();
    showView("dashboard");
    loadDashboard();
  });

  // Hours buttons
  document.querySelectorAll(".hours-btn").forEach(b => {
    b.addEventListener("click", () => setDetailHours(parseInt(b.dataset.hours)));
  });

  // Alert panel
  document.getElementById("btn-alerts").addEventListener("click", openAlertPanel);
  document.getElementById("btn-ack-all").addEventListener("click", acknowledgeAll);

  // Import / Export
  initImportExport();

  // Initial load
  showView("dashboard");
  loadDashboard();
  startDashboardRefresh();
  startAlertBadgeRefresh();
});
