// ---------------------------------------------------------------
// SIS-UEMA Status — dashboard
// Lê docs/data/history.json (atualizado pelo GitHub Actions) e
// monta o painel: banner de status, uptime, linha do tempo e incidentes.
// ---------------------------------------------------------------

const HISTORY_URL = "data/history.json";

// Ícones (inline, estilo Lucide) — strings fixas e confiáveis, nunca dado externo.
const ICONS = {
  up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
  warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg>',
  down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>',
};

function fmtDateTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function timeAgo(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "agora mesmo";
  if (mins < 60) return `há ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `há ${hours}h`;
  const days = Math.round(hours / 24);
  return `há ${days}d`;
}

function uptimePercent(entries) {
  if (!entries.length) return null;
  const up = entries.filter((e) => e.status === "up").length;
  return (up / entries.length) * 100;
}

function entriesSince(history, hours) {
  const cutoff = Date.now() - hours * 3600 * 1000;
  return history.filter((e) => new Date(e.timestamp).getTime() >= cutoff);
}

function renderBanner(history) {
  const banner = document.getElementById("status-banner");
  const icon = document.getElementById("status-icon");
  const text = document.getElementById("status-text");
  const sub = document.getElementById("status-sub");
  const lastCheckEl = document.getElementById("last-check");
  const latencyEl = document.getElementById("latency");
  const httpEl = document.getElementById("http-code");

  if (!history.length) {
    text.textContent = "Sem dados ainda";
    sub.textContent = "O primeiro check aparece aqui em alguns minutos.";
    return;
  }

  const latest = history[history.length - 1];
  const isUp = latest.status === "up";
  const hasSslIssue = latest.error === "ssl_certificate_invalid";

  banner.classList.remove("state-up", "state-warn", "state-down");

  if (isUp && hasSslIssue) {
    banner.classList.add("state-warn");
    icon.innerHTML = ICONS.warn;
    text.textContent = "Online, com aviso";
    sub.textContent = "O site responde normalmente, mas o certificado SSL está com problema.";
  } else if (isUp) {
    banner.classList.add("state-up");
    icon.innerHTML = ICONS.up;
    text.textContent = "Tudo funcionando";
    sub.textContent = "O SIS-UEMA está respondendo normalmente.";
  } else {
    banner.classList.add("state-down");
    icon.innerHTML = ICONS.down;
    text.textContent = "Fora do ar";
    sub.textContent = "O SIS-UEMA não respondeu na última verificação.";
  }

  lastCheckEl.textContent = `${fmtDateTime(latest.timestamp)} (${timeAgo(latest.timestamp)})`;
  latencyEl.textContent = latest.latency_ms != null ? `${latest.latency_ms} ms` : "—";
  httpEl.textContent = latest.http_status != null ? latest.http_status : (latest.error || "—");
}

function renderUptimeRow(history) {
  const u24 = uptimePercent(entriesSince(history, 24));
  const u7d = uptimePercent(entriesSince(history, 24 * 7));
  const u30d = uptimePercent(entriesSince(history, 24 * 30));

  const fmt = (v) => (v == null ? "—" : `${v.toFixed(1)}%`);

  document.getElementById("uptime-24h").textContent = fmt(u24);
  document.getElementById("uptime-7d").textContent = fmt(u7d);
  document.getElementById("uptime-30d").textContent = fmt(u30d);
}

// Classifica uma entrada em up / warn / down / unknown para cor + legenda.
function classify(entry) {
  if (entry.status === "up") {
    return entry.error === "ssl_certificate_invalid" ? "warn" : "up";
  }
  if (entry.status === "down") return "down";
  return "unknown";
}

// Altura do "pico": queda = barra alta e cheia (como um incidente no
// Downdetector); no ar = barra baixa, com leve variação pela latência —
// assim o estado nunca depende só da cor.
function barHeightPercent(entry, maxLatency) {
  const cls = classify(entry);
  if (cls === "down") return 100;
  if (cls === "unknown") return 6;

  const latency = entry.latency_ms || 0;
  const ratio = maxLatency > 0 ? Math.min(latency / maxLatency, 1) : 0;
  const base = cls === "warn" ? 30 : 12;
  return Math.round(base + ratio * 40);
}

function renderTimeline(history) {
  const container = document.getElementById("heatmap");
  const tooltip = document.getElementById("chart-tooltip");
  const tooltipValue = document.getElementById("chart-tooltip-value");
  const tooltipMeta = document.getElementById("chart-tooltip-meta");
  container.innerHTML = "";

  // mostra as últimas ~120 verificações (cabe bem numa tela)
  const recent = history.slice(-120);

  if (!recent.length) {
    container.innerHTML = '<p style="color:var(--text-dim); font-size:13px;">Ainda não há verificações registradas. O primeiro check aparece aqui em alguns minutos.</p>';
    return;
  }

  const maxLatency = Math.max(
    ...recent.filter((e) => e.status === "up").map((e) => e.latency_ms || 0),
    1
  );

  const showTooltip = (bar, entry) => {
    const cls = classify(entry);
    const label = cls === "up" ? "no ar" : cls === "warn" ? "no ar (SSL c/ problema)" : cls === "down" ? "fora do ar" : "sem dado";
    tooltipValue.textContent = entry.latency_ms != null ? `${entry.latency_ms} ms` : label;
    tooltipMeta.textContent = `${fmtDateTime(entry.timestamp)} · ${label}`;
    const rect = bar.getBoundingClientRect();
    tooltip.style.left = `${rect.left + rect.width / 2}px`;
    tooltip.style.top = `${rect.top - 8}px`;
    tooltip.hidden = false;
  };
  const hideTooltip = () => { tooltip.hidden = true; };

  recent.forEach((entry) => {
    const bar = document.createElement("div");
    const cls = classify(entry);
    bar.className = `timeline-bar ${cls}`;
    bar.style.height = `${barHeightPercent(entry, maxLatency)}%`;
    bar.tabIndex = 0;
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", `${fmtDateTime(entry.timestamp)}, ${cls === "down" ? "fora do ar" : "no ar"}`);

    bar.addEventListener("pointerenter", () => showTooltip(bar, entry));
    bar.addEventListener("pointermove", () => showTooltip(bar, entry));
    bar.addEventListener("pointerleave", hideTooltip);
    bar.addEventListener("focus", () => showTooltip(bar, entry));
    bar.addEventListener("blur", hideTooltip);

    container.appendChild(bar);
  });
}

function renderIncidents(history) {
  const list = document.getElementById("incident-list");
  list.innerHTML = "";

  const incidents = [];
  let current = null;

  for (const entry of history) {
    if (entry.status === "down") {
      if (!current) {
        current = { start: entry.timestamp, end: entry.timestamp, count: 1 };
      } else {
        current.end = entry.timestamp;
        current.count += 1;
      }
    } else if (current) {
      incidents.push(current);
      current = null;
    }
  }
  if (current) incidents.push(current);

  const recentIncidents = incidents.slice(-8).reverse();

  if (!recentIncidents.length) {
    const li = document.createElement("li");
    li.className = "incident-empty";
    li.textContent = "Nenhum incidente registrado até agora. 🎉";
    list.appendChild(li);
    return;
  }

  recentIncidents.forEach((inc) => {
    const li = document.createElement("li");
    const durationMs = new Date(inc.end).getTime() - new Date(inc.start).getTime();
    const minutes = Math.max(Math.round(durationMs / 60000), 5); // check interval mínimo

    const left = document.createElement("span");
    left.className = "incident-time";
    left.textContent = fmtDateTime(inc.start);

    const right = document.createElement("span");
    right.className = "incident-duration";
    right.textContent = minutes < 60
      ? `~${minutes} min fora do ar`
      : `~${(minutes / 60).toFixed(1)}h fora do ar`;

    li.appendChild(left);
    li.appendChild(right);
    list.appendChild(li);
  });
}

function setRepoLink() {
  const link = document.getElementById("repo-link");
  // tenta inferir "usuario/repositorio" a partir da URL do GitHub Pages
  const host = window.location.hostname; // usuario.github.io
  const path = window.location.pathname.split("/").filter(Boolean); // [repo, ...]
  if (host.endsWith("github.io") && path.length) {
    const user = host.replace(".github.io", "");
    link.href = `https://github.com/${user}/${path[0]}`;
  } else {
    link.href = window.location.href;
  }
}

async function init() {
  setRepoLink();

  try {
    const res = await fetch(HISTORY_URL, { cache: "no-store" });
    const history = await res.json();

    renderBanner(history);
    renderUptimeRow(history);
    renderTimeline(history);
    renderIncidents(history);
  } catch (err) {
    document.getElementById("status-text").textContent = "Erro ao carregar dados";
    console.error("Falha ao carregar history.json:", err);
  }
}

init();
