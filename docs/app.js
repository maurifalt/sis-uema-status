// ---------------------------------------------------------------
// SIS-UEMA Status — dashboard
// Lê docs/data/history.json (atualizado pelo GitHub Actions) e
// monta o painel: status atual, uptime, heatmap e incidentes.
// ---------------------------------------------------------------

const HISTORY_URL = "data/history.json";

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

function renderHero(history) {
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");
  const lastCheckEl = document.getElementById("last-check");
  const latencyEl = document.getElementById("latency");
  const httpEl = document.getElementById("http-code");

  if (!history.length) {
    text.textContent = "Sem dados ainda";
    return;
  }

  const latest = history[history.length - 1];
  const isUp = latest.status === "up";
  const hasSslIssue = latest.error === "ssl_certificate_invalid";

  dot.classList.add(isUp ? "up" : "down");
  if (isUp && hasSslIssue) {
    text.textContent = "Online (certificado SSL com problema)";
    text.style.color = "var(--amber)";
    dot.style.background = "var(--amber)";
  } else {
    text.textContent = isUp ? "Online" : "Fora do ar";
    text.style.color = isUp ? "var(--up)" : "var(--down)";
  }

  lastCheckEl.textContent = `${fmtDateTime(latest.timestamp)} (${timeAgo(latest.timestamp)})`;
  latencyEl.textContent = latest.latency_ms != null ? `${latest.latency_ms} ms` : "—";
  httpEl.textContent = latest.http_status != null ? latest.http_status : (latest.error || "—");
}

function renderPulseLine(history) {
  const line = document.getElementById("pulse-line");
  const recent = history.slice(-40);
  if (!recent.length) return;

  const w = 400;
  const h = 60;
  const step = w / Math.max(recent.length - 1, 1);

  const points = recent.map((e, i) => {
    const x = i * step;
    // "batimento": sobe em up, cai em down, com um pequeno padrão de pulso
    const base = h / 2;
    const isUp = e.status === "up";
    const amp = isUp ? 14 : 20;
    const wobble = i % 4 === 0 ? amp : amp * 0.25;
    const y = isUp ? base - wobble : base + wobble;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  line.setAttribute("points", points.join(" "));

  const latest = recent[recent.length - 1];
  line.style.stroke = latest.status === "up" ? "var(--up)" : "var(--down)";
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

function renderHeatmap(history) {
  const container = document.getElementById("heatmap");
  container.innerHTML = "";

  // mostra as últimas ~120 verificações (cabe bem numa tela)
  const recent = history.slice(-120);

  recent.forEach((entry) => {
    const bar = document.createElement("div");
    const status = entry.status === "up" ? "up" : entry.status === "down" ? "down" : "unknown";
    bar.className = `heatmap-bar ${status}`;
    const label = status === "up" ? "no ar" : "fora do ar";
    bar.title = `${fmtDateTime(entry.timestamp)} · ${label}` +
      (entry.latency_ms != null ? ` · ${entry.latency_ms}ms` : "");
    container.appendChild(bar);
  });

  if (!recent.length) {
    container.innerHTML = '<p style="color:var(--text-dim); font-size:13px;">Ainda não há verificações registradas. O primeiro check aparece aqui em alguns minutos.</p>';
  }
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

    renderHero(history);
    renderPulseLine(history);
    renderUptimeRow(history);
    renderHeatmap(history);
    renderIncidents(history);
  } catch (err) {
    document.getElementById("status-text").textContent = "Erro ao carregar dados";
    console.error("Falha ao carregar history.json:", err);
  }
}

init();
