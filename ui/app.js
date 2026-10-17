"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const appToken = $('meta[name="app-token"]').content;
const content = $("#content");
const state = {
  data: null,
  page: "library",
  busy: false,
  refreshing: null,
  history: null,
  kind: "all",
  search: "",
  pageNumber: 1,
  browser: null,
  preview: null,
};
const names = {
  library: "All photos",
  folders: "Backup folders",
  activity: "Activity",
  settings: "Settings",
  help: "Help & about",
};
const icon = (name, small = false) =>
  `<svg class="icon${small ? " small" : ""}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
const number = (value) => Number(value || 0).toLocaleString();
const filename = (path) =>
  String(path).split(/[\\/]/).filter(Boolean).pop() || path;
const video = (path) => /\.(mp4|mov|mkv|avi|m4v|3gp|3g2|wmv|webm|mpg|mpeg|mts|m2ts|ts|flv|vob)$/i.test(path);
const badge = (label, kind = "") =>
  `<span class="badge ${kind}">${esc(label)}</span>`;
const size = (bytes) =>
  bytes == null
    ? ""
    : bytes < 1048576
      ? `${(bytes / 1024).toFixed(1)} KB`
      : `${(bytes / 1048576).toFixed(1)} MB`;

async function api(route, body) {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    route === "/api/account" ? 100000 : 25000,
  );
  try {
    const response = await fetch(route, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        "X-App-Token": appToken,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(
        result.error || "The app could not complete that action.",
      );
    return result;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error(
        "That is taking a while. Check your connection and try again.",
      );
    if (error instanceof TypeError)
      throw new Error(
        "The backup service is unavailable. Reopen the app to reconnect.",
      );
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
let toastTimer;
function toast(message, error = false) {
  $("#toast").textContent = message;
  $("#toast").classList.toggle("error", error);
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(
    () => {
      $("#toast").hidden = true;
    },
    error ? 8500 : 4200,
  );
}
async function mutate(route, body = {}) {
  if (state.busy) return false;
  state.busy = true;
  try {
    const result = await api(route, body);
    toast(result.message);
    return true;
  } catch (error) {
    toast(error.message, true);
    return false;
  } finally {
    state.busy = false;
    await refresh(true);
  }
}
function dateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) return esc(value);
  const time = parsed.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
  return parsed.toDateString() === new Date().toDateString()
    ? `Today, ${time}`
    : `${parsed.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}, ${time}`;
}
function syncButton(compact = false) {
  return `<button class="button ${state.data.running ? "secondary" : "primary"}${compact ? " compact" : ""}" data-action="sync" ${state.busy ? "disabled" : ""}>${icon(state.data.running ? "stop" : "play", true)}${state.data.running ? "Pause backup" : "Start backup"}</button>`;
}
function heading(title, description, action = "", count = null) {
  return `<div class="page-heading"><div><div class="heading-title"><h1>${esc(title)}</h1>${count === null ? "" : `<span class="count-pill">${number(count)}</span>`}</div><p>${esc(description)}</p></div>${action}</div>`;
}
function empty(title, description, symbol = "photo", action = "") {
  return `<div class="empty-library"><div class="empty-symbol">${icon(symbol)}</div><h3>${esc(title)}</h3><p>${esc(description)}</p>${action}</div>`;
}
function mobileLinks() {
  return '<div class="mobile-links"><a href="#settings">Settings</a><a href="#help">Help & about</a></div>';
}
function art() {
  return `<div class="setup-illustration" aria-hidden="true"><div class="setup-photo second"><svg viewBox="0 0 100 110" preserveAspectRatio="xMidYMid slice"><rect width="100" height="110" fill="#dce5df"/><circle cx="69" cy="28" r="14" fill="#f9efd1"/><path d="m-10 100 43-64 39 48 22-32 23 64H0Z" fill="#9aac9d"/><path d="m0 110 35-45 24 29 22-14 30 38" fill="#65836c"/></svg></div><div class="setup-photo"><svg viewBox="0 0 100 110" preserveAspectRatio="xMidYMid slice"><rect width="100" height="110" fill="#ece8d9"/><circle cx="30" cy="29" r="14" fill="#fcf7e4"/><path d="M0 68q28-22 65 0t35-4v46H0Z" fill="#bcc9ab"/><path d="M0 98q60-45 110-7v30H0Z" fill="#7da283"/><path d="m23 115 25-24-12-14 12-11" stroke="#e9dfbb" stroke-width="8" fill="none"/></svg></div><span class="check-seal">${icon("check")}</span></div>`;
}
function setupCard() {
  const d = state.data;
  if (d.account.connected && d.folders.length) return "";
  const steps = [
    {
      done: d.account.connected,
      label: "Connect Google Photos",
      action: "account",
    },
    {
      done: d.folders.length > 0,
      label: "Choose backup folders",
      action: "add-folder",
    },
    {
      done: d.running || d.stats.uploaded > 0,
      label: "Start your backup",
      action: "sync",
    },
  ];
  return `<section class="setup-card"><div class="setup-copy"><span class="eyebrow">A LITTLE LESS TO WORRY ABOUT</span><h2>Your memories, all together.</h2><p>Keep a copy of the photos and videos you love in Google Photos. Connect your account and choose a few folders to get started.</p><div class="setup-steps">${steps.map((step, index) => `<span class="setup-step${step.done ? " done" : ""}"><span class="step-dot">${step.done ? icon("check") : index + 1}</span>${step.done ? esc(step.label) : `<button class="text-button" data-action="${step.action}">${esc(step.label)}</button>`}</span>`).join("")}</div></div>${art()}</section>`;
}
function warnings() {
  const d = state.data;
  let html = "";
  const missing = d.requirements.find((item) => !item.ready);
  if (missing)
    html += `<div class="notice warning">${icon("info")}<span>${esc(missing.help)}</span><a class="text-button" href="#settings">View details</a></div>`;
  if (d.folders.some((folder) => !folder.available))
    html += `<div class="notice warning">${icon("folder")}<span>A backup folder is unavailable. Reconnect its drive or check folder permissions to continue.</span><a class="text-button" href="#folders">View folders</a></div>`;
  if (d.stats.legacy)
    html += `<div class="notice">${icon("info")}<span>${number(d.stats.legacy)} previous records are shown from your backend history. Open Google Photos to check their remote copies.</span><a href="#activity" class="text-button">View backup</a></div>`;
  if (d.history_error)
    html += `<div class="notice error">${icon("info")}<span>${esc(d.history_error)}</span></div>`;
  return html;
}
function libraryPage() {
  const d = state.data;
  return `${heading("Photos", "Backed up from this computer to Google Photos.", "", d.stats.uploaded)}<div class="library-toolbar"><div class="tabs" role="group" aria-label="Filter backed-up files">${[
    ["all", "All photos"],
    ["photos", "Photos"],
    ["videos", "Videos"],
  ]
    .map(
      ([kind, label]) =>
        `<button class="tab${state.kind === kind ? " active" : ""}" data-kind="${kind}" aria-pressed="${state.kind === kind}">${label}</button>`,
    )
    .join(
      "",
    )}</div><span class="view-hint">${icon("clock", true)}Recently backed up</span></div>${warnings()}${setupCard()}${d.account.connected && d.folders.length && !d.running && !d.stats.uploaded ? `<div class="notice">${icon("cloud")}<span>All set. Start backup to check your folders and copy your first photos.</span>${syncButton(true)}</div>` : ""}<div id="library-results">${libraryResults()}</div><div class="library-footnote">${icon("shield", true)}Your originals stay in place. Your backup stays in your Google account.</div>${mobileLinks()}`;
}
function libraryResults() {
  const history = state.history;
  if (!history)
    return '<div class="loading"><span class="spinner"></span>Loading your photos…</div>';
  if (history.error)
    return `<div class="notice error">${icon("info")}<span>${esc(history.error)}</span></div>`;
  if (!history.uploads.length) {
    if (state.search || state.kind !== "all")
      return empty(
        "No photos found",
        "Try another search or select All photos to see every backup.",
        "search",
      );
    return empty(
      state.data.running
        ? "Your photos are on their way"
        : "Your first backup starts here",
      state.data.running
        ? "The app is checking your selected folders. Confirmed backups will appear here as they finish."
        : "Choose the folders you want to keep safe. Photos and videos will appear here after Google confirms their backup.",
      "photo",
      !state.data.folders.length
        ? '<button class="button secondary" data-action="add-folder">Choose a folder' +
            icon("plus", true) +
            "</button>"
        : "",
    );
  }
  const groups = new Map();
  for (const file of history.uploads) {
    const parsed = new Date(file.uploaded_at.replace(" ", "T"));
    const key = !Number.isNaN(parsed.getTime())
      ? parsed.toDateString() === new Date().toDateString()
        ? "Today"
        : parsed.toLocaleDateString([], {
            month: "long",
            day: "numeric",
            year: "numeric",
          })
      : "Backed up";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(file);
  }
  let html = [...groups]
    .map(
      ([date, files]) =>
        `<h3 class="date-heading">${esc(date)}</h3><div class="photo-grid">${files.map((file) => `<button class="photo-card${video(file.path) ? " preview-unavailable" : ""}" data-preview="${esc(file.id)}" aria-label="Open ${esc(filename(file.path))}">${video(file.path) ? "" : `<img src="/api/media?id=${encodeURIComponent(file.id)}&thumbnail=1" alt="" loading="lazy">`}<span class="thumbnail-fallback">${icon(video(file.path) ? "video" : "photo")}<span>${esc(filename(file.path))}</span></span><span class="photo-status${file.confirmation ? "" : " unverified"}">${icon(file.confirmation ? "check" : "cloud")}</span>${video(file.path) ? `<span class="video-label">${icon("video", true)}VIDEO</span>` : ""}<span class="photo-name">${esc(filename(file.path))}</span></button>`).join("")}</div>`,
    )
    .join("");
  if (history.total > 25)
    html += `<div class="pagination"><span>${number((history.page - 1) * 25 + 1)}–${number(Math.min(history.page * 25, history.total))} of ${number(history.total)} files</span><div><button class="button secondary compact" data-page-number="${history.page - 1}" ${history.page <= 1 ? "disabled" : ""}>Previous</button><button class="button secondary compact" data-page-number="${history.page + 1}" ${history.page * 25 >= history.total ? "disabled" : ""}>Next</button></div></div>`;
  return html;
}
function foldersPage() {
  const d = state.data;
  const suggestions = d.suggestions.filter(
    (item) => !d.folders.some((folder) => folder.path === item.path),
  );
  return `${heading("Backup folders", "The places your memories come from.", '<button class="button primary" data-action="add-folder">' + icon("plus", true) + "Add folders</button>")}${warnings()}${suggestions.length ? `<div class="suggestions"><span>Familiar places</span>${suggestions.map((item) => `<button class="button secondary compact" data-suggest="${esc(item.path)}">${icon("folder", true)}${esc(item.name)}${icon("plus", true)}</button>`).join("")}</div>` : ""}${d.folders.length ? `<section class="panel folders-list">${d.folders.map((folder) => `<div class="folder-row"><span class="folder-icon">${icon("folder")}</span><div class="folder-info"><strong>${esc(folder.name)}</strong><p>${esc(folder.path)}</p></div>${badge(folder.available ? "Subfolders included" : "Drive unavailable", folder.available ? "" : "warning")}<button class="text-button danger" data-remove="${esc(folder.path)}" aria-label="Remove ${esc(folder.name)} from backup">Remove</button></div>`).join("")}</section>` : ""}<button class="folder-add" data-action="add-folder">${icon("plus")}Add a backup folder${icon("arrow", true)}</button><div class="info-card">${icon("shield")}<div><h3>A copy for peace of mind.</h3><p>Files are copied to Google Photos. Adding or removing folders safely pauses and resumes the worker. Removing a folder stops its future backups. The backend skips retries outside the selected folders. Your originals and completed backups stay in place.</p><div class="format-list">${d.formats.map((ext) => `<span>${ext}</span>`).join("")}</div></div></div>${mobileLinks()}`;
}
function activityPage() {
  const d = state.data;
  const failed = d.retries.filter((file) => file.state === "failed").length;
  const current = d.backup.current;
  const title = current
    ? "Backing up your memories"
    : d.running
      ? d.stats.pending
        ? "Checking your backup queue"
        : "Watching for new photos"
      : "Your backup is paused";
  const description = current
    ? `${current.name}${current.size ? " · " + size(current.size) : ""}`
    : d.running
      ? "New and changed files in your selected folders are checked automatically."
      : "Start backup whenever you’re ready. Saved progress and waiting files will be picked up again.";
  return `${heading("Backup activity", "A clear view of what’s safe and what needs another try.", '<button class="button secondary" data-action="refresh">' + icon("refresh", true) + "Refresh</button>")}${warnings()}<section class="backup-status"><span class="backup-status-icon">${current ? '<span class="spinner"></span>' : icon("cloud")}</span><div><h2>${esc(title)}</h2><p>${esc(description)}</p></div>${syncButton()}</section>${d.backup.error ? `<div class="notice warning">${icon("info")}<span>${esc(d.backup.error)}</span></div>` : ""}<div class="metrics"><section class="metric"><span>Files backed up</span><strong>${number(d.stats.verified)}</strong><small>${number(d.stats.today)} completed today</small></section><section class="metric"><span>Waiting or retrying</span><strong>${number(Math.max(0, d.stats.pending - failed))}</strong><small>Progress is saved locally</small></section><section class="metric"><span>Needs attention</span><strong>${number(failed)}</strong><small>${failed ? "Review and retry below" : "No failed backups"}</small></section></div><section class="panel"><div class="panel-heading"><div><h3>Backup queue</h3><p>Files settle before upload. Your backup script manages retries, up to three attempts.</p></div>${d.stats.pending ? '<button class="text-button" data-action="retry">Retry now' + icon("refresh", true) + "</button>" : badge("All clear", "success")}</div>${d.retries.length ? `<ul class="queue-list">${d.retries.map((file) => `<li><span class="file-icon">${icon(video(file.path) ? "video" : "photo")}</span><div class="file-info"><strong>${esc(filename(file.path))}</strong><p>${esc(file.error || "Waiting for the file to finish changing.")} ${file.attempts ? `Attempt ${file.attempts} of 3.` : ""}</p></div>${badge(file.state === "failed" ? "Needs attention" : file.state === "retrying" ? "Retrying" : "Waiting", file.state === "failed" ? "error" : file.state === "retrying" ? "warning" : "")}</li>`).join("")}</ul>` : empty("Nothing waiting in line", "New files and anything that needs another attempt will appear here.", "check")}</section><section class="panel"><div class="panel-heading"><h3>Recent events</h3><span class="view-hint">Saved on this computer</span></div>${
    d.logs.length
      ? `<ul class="event-list">${d.logs
          .slice(0, 70)
          .map(
            (log) =>
              `<li>${badge(log.level === "OK" ? "SUCCESS" : log.level, log.level === "OK" ? "success" : log.level === "ERROR" ? "error" : log.level === "WARN" ? "warning" : "")}<span class="event-message">${esc(log.message)}</span><time>${dateTime(log.timestamp)}</time></li>`,
          )
          .join("")}</ul>`
      : empty(
          "A quiet start",
          "Backup events will show up here once you get going.",
          "clock",
        )
  }</section>${mobileLinks()}`;
}
function settingsPage() {
  const d = state.data;
  return `${heading("Settings", "A few things to make this app your own.")}<section class="panel"><div class="panel-heading"><h3>Google Photos connection</h3>${badge(d.account.connected ? "Connected" : "Not connected", d.account.connected ? "success" : "")}</div><div class="setting-row"><div><h3>${esc(d.account.email || "Connect your Google account")}</h3><p>${esc(d.account.error || "Backups are tied to this account so switching accounts cannot silently reuse the wrong history.")}</p></div><button class="button secondary compact" data-action="account">${d.account.connected ? "Reconnect" : "Connect"}${icon("arrow", true)}</button></div></section><section class="panel"><div class="panel-heading"><h3>App preferences</h3></div><div class="setting-row"><div><h3 id="theme-label">Appearance</h3><p>A familiar light theme, a softer dark theme, or your system preference.</p></div><select id="theme-select" aria-labelledby="theme-label">${[
    ["system", "System"],
    ["light", "Light"],
    ["dark", "Dark"],
  ]
    .map(
      ([value, label]) =>
        `<option value="${value}" ${d.preferences.theme === value ? "selected" : ""}>${label}</option>`,
    )
    .join(
      "",
    )}</select></div><div class="setting-row"><div><h3 id="startup-label">Open when I sign in</h3><p id="startup-description">${window.desktop ? "Start the app quietly in the tray. Active backups resume automatically." : "Install the desktop app to manage automatic startup."}</p></div><input type="checkbox" id="startup-toggle" class="switch" aria-labelledby="startup-label" aria-describedby="startup-description" ${d.startup.enabled ? "checked" : ""} ${window.desktop ? "" : "disabled"}></div><div class="setting-row"><div><h3>Keep backing up in the background</h3><p>${window.desktop ? "Closing the window keeps the app in your system tray, when a tray is available. Use the tray menu to pause backup or quit completely." : "Keep the local service running to continue backing up when you close this browser."}</p></div>${icon("cloud")}</div></section><section class="panel"><div class="panel-heading"><h3>Local app data</h3>${badge(d.platform)}</div><div class="setting-row"><div><h3>Settings, credentials, and history</h3><p>Stored in your user profile, separate from the installation. Updating or uninstalling the app keeps this data and your photos.</p></div><button class="button secondary compact" data-action="data-folder" ${window.desktop ? "" : "disabled"}>Open folder${icon("folder", true)}</button></div><div class="setting-row"><div><h3>Bring your previous setup</h3><p>Before connecting an account, import gphotos.db and a portable gotohp.config from an older GoogleUnlimited folder. Originals are left in place.</p></div><button class="button secondary compact" data-action="import" ${window.desktop ? "" : "disabled"}>Import setup${icon("arrow", true)}</button></div></section><section class="panel"><div class="panel-heading"><h3>Backup components</h3></div>${d.requirements.map((item) => `<div class="requirement"><div>${esc(item.name)}${item.ready ? "" : `<p>${esc(item.help)}</p>`}</div>${badge(item.ready ? "Ready" : "Needs attention", item.ready ? "success" : "warning")}</div>`).join("")}</section><p class="about-note">GoogleUnlimited · Original UI informed by <a href="https://github.com/ente-io/ente" target="_blank" rel="noopener noreferrer">Ente Photos</a> · Uploads powered by <a href="https://github.com/xob0t/gotohp" target="_blank" rel="noopener noreferrer">gotohp</a></p>${mobileLinks()}`;
}
function helpPage() {
  return `${heading("Make room for your memories.", "A short guide to a backup that stays out of your way.")}<div class="about-grid"><section class="about-card"><span class="step-dot">1</span><h3>Connect your account</h3><p>Sign in to Google in the app window. If Google requires it, use the guided manual connection option.</p><button class="text-button" data-action="account">Connect Google Photos${icon("arrow", true)}</button></section><section class="about-card"><span class="step-dot">2</span><h3>Choose your folders</h3><p>Select the places your photos live. Supported files in subfolders are included automatically.</p><button class="text-button" data-action="add-folder">Choose backup folders${icon("arrow", true)}</button></section><section class="about-card"><span class="step-dot">3</span><h3>Let backup do its thing</h3><p>The app checks for stable new and changed files, confirms uploads, and keeps a retry queue.</p><button class="text-button" data-action="sync">${state.data.running ? "Pause backup" : "Start backup"}${icon("arrow", true)}</button></section></div><section class="panel"><div class="panel-heading"><h3>Good things to know</h3></div><div class="faq"><details><summary>Does the app need Python or a terminal?</summary><p>The installers include Python, SQLite, the upload engine, and the desktop runtime. Install and open GoogleUnlimited from your application menu. Source-code launchers remain available for development.</p></details><details><summary>Does backup keep running after I close the window?</summary><p>The desktop app stays in the system tray when a tray is available. Use the tray menu to pause or quit. Quitting stops the worker safely; an active backup resumes when you open the app again. The computer must be awake and connected to the internet.</p></details><details><summary>What does “backed up” mean?</summary><p>This library reads upload records written by your backup script. A checkmark means the backend saved a media key or duplicate record. The gallery shows local originals for those records. Open Google Photos to inspect the copies stored in your account.</p></details><details><summary>What if a file changes, moves, or fails?</summary><p>Changed files are checked again. Your backend uses file names, sizes, and content hashes to recognize duplicates. Files still being written wait until stable. The backend retries failed uploads up to three times. They stay visible in Activity and can be retried manually.</p></details><details><summary>What if an external drive is disconnected?</summary><p>Its folder is marked unavailable. Reconnect the drive and restart backup to make sure the backend watches it again. Completed history stays in place.</p></details><details><summary>Does removing a folder delete any photos?</summary><p>No. It stops future backups from that folder and prevents its queued files from uploading. Original files and confirmed Google Photos backups are kept. Uninstalling also keeps your photos and user-profile app data.</p></details><details><summary>Which file types can I back up?</summary><p>Common photos, camera RAW files, and videos are supported. The full list from your backend is shown on the Folders page. Preview support depends on the format and available codecs. A file can back up correctly even if its preview is unavailable.</p></details><details><summary>How does Google sign-in work?</summary><p>The gotohp client exchanges a Google Embedded Setup oauth_token cookie for a local credential. The desktop sign-in window detects this cookie automatically and clears its temporary browser session afterwards. If Google blocks the embedded window, use the manual browser instructions. Never share the cookie with anyone.</p></details></div></section><div class="info-card">${icon("info")}<div><h3>About this app</h3><p>The interface is informed by Ente’s open-source photo app. GoogleUnlimited is an independent client using gotohp and Google Photos. Storage treatment and service availability depend on Google and the upload engine. Your app data stays on this computer.</p></div></div><p class="about-note"><a href="https://photos.google.com" target="_blank" rel="noopener noreferrer">Open Google Photos</a> · <a href="#settings">App settings</a></p>${mobileLinks()}`;
}
function applyTheme() {
  if (!state.data) return;
  const choice = state.data.preferences.theme;
  document.documentElement.dataset.theme =
    choice === "system"
      ? matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : choice;
}
function updateShell() {
  const d = state.data;
  $("#library-count").textContent = number(d.stats.uploaded);
  $("#folder-count").textContent = number(d.folders.length);
  $("#account-avatar").textContent = d.account.email
    ? d.account.email[0].toUpperCase()
    : "G";
  $("#activity-attention").hidden = !d.retries.some(
    (file) => file.state === "failed",
  );
  const status = d.backup.error
    ? "Needs attention"
    : d.running
      ? d.backup.current
        ? "Backing up"
        : d.stats.pending
          ? "Checking files"
          : d.stats.uploaded
            ? "Up to date"
            : "Watching folders"
      : "Backup paused";
  $("#sync-pill").innerHTML =
    `<span class="status-dot${d.backup.error ? " warning" : d.running ? "" : " paused"}"></span><span>${status}</span>`;
  $("#summary-title").textContent = d.running
    ? "Backup is running"
    : "Your personal backup";
  $("#summary-description").textContent = d.account.connected
    ? "Your originals stay here. A copy stays in your Google account."
    : "Choose what matters. We’ll keep a copy.";
  $("#summary-total").textContent =
    `${number(d.stats.verified)} confirmed backups`;
  $("#backup-toggle").innerHTML =
    `${icon(d.running ? "stop" : "play", true)}${d.running ? "Pause backup" : "Start backup"}`;
  $("#backup-toggle").disabled = state.busy;
  $$("[data-page]").forEach((link) => {
    const selected = link.dataset.page === state.page;
    link.classList.toggle("active", selected);
    if (selected) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  document.title = `${names[state.page]} · GoogleUnlimited`;
  applyTheme();
}
function render() {
  if (!state.data) return;
  const scroll = $("#main").scrollTop;
  content.innerHTML = {
    library: libraryPage,
    folders: foldersPage,
    activity: activityPage,
    settings: settingsPage,
    help: helpPage,
  }[state.page]();
  content.setAttribute("aria-busy", "false");
  $("#main").scrollTop = scroll;
  updateShell();
}
async function refresh(force = false) {
  if (state.refreshing) {
    if (force) {
      await state.refreshing;
      return refresh(true);
    }
    return;
  }
  if (state.busy && !force) return;
  state.refreshing = (async () => {
    try {
      const result = await api("/api/status");
      const changed = JSON.stringify(result) !== JSON.stringify(state.data);
      state.data = result;
      $("#connection-error").hidden = true;
      updateShell();
      if (
        force ||
        content.querySelector(".loading") ||
        (changed &&
          !content.contains(document.activeElement) &&
          !content.querySelector("details[open]"))
      )
        render();
      if (state.page === "library") await loadLibrary(false);
    } catch (error) {
      $("#connection-error").hidden = false;
      if (!state.data) {
        content.innerHTML = empty(
          "Let’s reconnect",
          "Keep the app running and try again, or reopen GoogleUnlimited.",
          "refresh",
        );
        content.setAttribute("aria-busy", "false");
      }
    }
  })();
  try {
    await state.refreshing;
  } finally {
    state.refreshing = null;
  }
}
let libraryRequest = 0;
async function loadLibrary(loading = true) {
  const current = ++libraryRequest;
  if (loading && $("#library-results"))
    $("#library-results").innerHTML =
      '<div class="loading"><span class="spinner"></span>Loading your photos…</div>';
  try {
    const result = await api(
      "/api/history?" +
        new URLSearchParams({
          page: state.pageNumber,
          search: state.search,
          kind: state.kind,
        }),
    );
    if (current !== libraryRequest) return;
    const changed = JSON.stringify(result) !== JSON.stringify(state.history);
    state.history = result;
    if (
      state.page === "library" &&
      $("#library-results") &&
      (loading || changed || $("#library-results .loading"))
    )
      $("#library-results").innerHTML = libraryResults();
  } catch (error) {
    if (current === libraryRequest) toast(error.message, true);
  }
}
function navigate() {
  const hash = location.hash.slice(1);
  state.page = Object.hasOwn(names, hash) ? hash : "library";
  render();
  $("#main").scrollTop = 0;
  if (state.page === "library") loadLibrary();
}
function showAccount() {
  if (!state.data) return;
  if (state.data.running) {
    toast("Pause backup before reconnecting your Google account.", true);
    return;
  }
  $("#oauth-token").value = "";
  $("#account-error").hidden = true;
  $("#native-sign-in").hidden = !window.desktop;
  $("#manual-connection").open = !window.desktop;
  $("#account-connected").hidden = !state.data.account.connected;
  $("#account-connected").textContent = state.data.account.email
    ? `Connected as ${state.data.account.email}. Reconnect this same account to keep your backup history.`
    : "";
  $("#account-dialog").showModal();
}
async function chooseFolders() {
  if (state.busy) return;
  if (window.desktop) {
    try {
      const paths = await window.desktop.selectFolders();
      if (paths.length) await addFolders(paths);
    } catch (error) {
      toast(error.message, true);
    }
  } else {
    $("#folder-dialog").showModal();
    browse();
  }
}
async function addFolders(paths) {
  return mutate("/api/folders", {
    folders: [...state.data.folders.map((folder) => folder.path), ...paths],
  });
}
async function sync() {
  if (!state.data) return;
  if (!state.data.running && !state.data.account.connected)
    return showAccount();
  if (!state.data.running && !state.data.folders.length) {
    location.hash = "folders";
    toast("Choose a folder to back up first.");
    return;
  }
  return mutate(`/api/sync/${state.data.running ? "stop" : "start"}`);
}
let browseRequest = 0;
async function browse(path) {
  const current = ++browseRequest;
  state.browser = null;
  $("#choose-folder").disabled = true;
  $("#browse-error").hidden = true;
  $("#folder-browser").innerHTML =
    '<div class="browser-empty">Opening folder…</div>';
  try {
    const result = await api(
      "/api/browse" + (path ? "?" + new URLSearchParams({ path }) : ""),
    );
    if (current !== browseRequest) return;
    state.browser = result;
    $("#folder-path").value = result.path;
    $("#browse-up").disabled = result.path === result.parent;
    $("#choose-folder").disabled = false;
    $("#folder-browser").innerHTML = result.folders.length
      ? result.folders
          .map(
            (folder) =>
              `<button class="browser-folder" data-browse="${esc(folder.path)}">${icon("folder")}<span>${esc(folder.name)}</span>${icon("chevron", true)}</button>`,
          )
          .join("")
      : '<div class="browser-empty">No subfolders here. You can back up this folder.</div>';
  } catch (error) {
    if (current !== browseRequest) return;
    $("#browse-error").textContent = error.message;
    $("#browse-error").hidden = false;
    $("#folder-browser").innerHTML =
      '<div class="browser-empty">Choose another location or return to your home folder.</div>';
  }
}
function preview(identifier) {
  const file = state.history?.uploads.find((file) => file.id === identifier);
  if (!file) return;
  state.preview = identifier;
  $("#preview-title").textContent = filename(file.path);
  $("#preview-status").innerHTML = file.confirmation
    ? `${icon("check", true)}Backed up to Google Photos`
    : `${icon("clock", true)}Previous record · awaiting verification`;
  $("#preview-status").classList.toggle("success", Boolean(file.confirmation));
  $("#preview-meta").textContent =
    `${dateTime(file.uploaded_at)}${file.size ? " · " + size(file.size) : ""} · Local original`;
  const url = "/api/media?id=" + encodeURIComponent(identifier);
  $("#preview-media").innerHTML = video(file.path)
    ? `<video controls autoplay src="${url}"></video>`
    : `<img src="${url}" alt="${esc(filename(file.path))}">`;
  $("#reveal-file").hidden = !window.desktop;
  $("#preview-dialog").showModal();
}

document.addEventListener("click", async (event) => {
  const close = event.target.closest("[data-close]");
  if (close) {
    close.closest("dialog").close();
    return;
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "sync") await sync();
  if (action === "account") showAccount();
  if (action === "add-folder") await chooseFolders();
  if (action === "refresh") await refresh(true);
  if (action === "retry") await mutate("/api/retry");
  if (action === "data-folder" && window.desktop) {
    try {
      await window.desktop.openDataFolder();
    } catch (error) {
      toast(error.message, true);
    }
  }
  if (action === "import" && window.desktop) {
    try {
      const result = await window.desktop.importSetup();
      if (result) {
        toast(result.message);
        await refresh(true);
      }
    } catch (error) {
      toast(error.message, true);
    }
  }
  const suggestion = event.target.closest("[data-suggest]");
  if (suggestion) await addFolders([suggestion.dataset.suggest]);
  const remove = event.target.closest("[data-remove]");
  if (remove)
    await mutate("/api/folders", {
      folders: state.data.folders
        .map((folder) => folder.path)
        .filter((path) => path !== remove.dataset.remove),
    });
  const folder = event.target.closest("[data-browse]");
  if (folder) await browse(folder.dataset.browse);
  const filter = event.target.closest("[data-kind]");
  if (filter) {
    state.kind = filter.dataset.kind;
    state.pageNumber = 1;
    $$("[data-kind]").forEach((tab) => {
      const active = tab === filter;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-pressed", String(active));
    });
    await loadLibrary();
  }
  const page = event.target.closest("[data-page-number]");
  if (page) {
    state.pageNumber = Number(page.dataset.pageNumber);
    await loadLibrary();
  }
  const image = event.target.closest("[data-preview]");
  if (image) preview(image.dataset.preview);
});
let searchTimer;
$("#global-search").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.search = event.target.value.trim();
    state.pageNumber = 1;
    if (state.page !== "library") location.hash = "library";
    else loadLibrary(false);
  }, 220);
});
document.addEventListener("change", async (event) => {
  if (event.target.id === "theme-select")
    await mutate("/api/preferences", { theme: event.target.value });
  if (event.target.id === "startup-toggle" && window.desktop) {
    const checkbox = event.target;
    checkbox.disabled = true;
    try {
      const result = await window.desktop.setStartup(checkbox.checked);
      toast(result.message);
      await refresh(true);
    } catch (error) {
      checkbox.checked = !checkbox.checked;
      toast(error.message, true);
    } finally {
      if (checkbox.isConnected) checkbox.disabled = false;
    }
  }
});
$("#account-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy) return;
  state.busy = true;
  const button = $("#connect-button");
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span>Connecting…';
  $("#account-error").hidden = true;
  try {
    const result = await api("/api/account", {
      token: $("#oauth-token").value,
    });
    $("#oauth-token").value = "";
    $("#account-dialog").close();
    toast(result.message);
  } catch (error) {
    $("#account-error").textContent = error.message;
    $("#account-error").hidden = false;
  } finally {
    state.busy = false;
    button.disabled = false;
    button.innerHTML = "Connect account" + icon("arrow", true);
    await refresh(true);
  }
});
$("#native-connect").addEventListener("click", async () => {
  if (!window.desktop || state.busy) return;
  state.busy = true;
  const button = $("#native-connect");
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span>Waiting for Google sign-in…';
  $("#account-error").hidden = true;
  try {
    const result = await window.desktop.connectAccount();
    $("#account-dialog").close();
    toast(result.message);
  } catch (error) {
    $("#account-error").textContent = error.message;
    $("#account-error").hidden = false;
  } finally {
    state.busy = false;
    button.disabled = false;
    button.innerHTML = "Continue with Google" + icon("external", true);
    await refresh(true);
  }
});
for (const name of ["close", "cancel"])
  $("#account-dialog").addEventListener(name, () => {
    $("#oauth-token").value = "";
  });
$("#preview-dialog").addEventListener("close", () => {
  $("#preview-media").innerHTML = "";
  state.preview = null;
});
$("#reveal-file").addEventListener("click", async () => {
  try {
    if (state.preview && window.desktop)
      await window.desktop.revealFile(state.preview);
  } catch (error) {
    toast(error.message, true);
  }
});
$("#browse-form").addEventListener("submit", (event) => {
  event.preventDefault();
  browse($("#folder-path").value.trim());
});
$("#browse-up").addEventListener("click", () => {
  if (state.browser) browse(state.browser.parent);
});
$("#browse-home").addEventListener("click", () => browse());
$("#choose-folder").addEventListener("click", async () => {
  if (state.browser && (await addFolders([state.browser.path])))
    $("#folder-dialog").close();
});
$("#account-avatar").addEventListener("click", showAccount);
$("#sync-pill").addEventListener("click", () => {
  location.hash = "activity";
});
$("#reconnect").addEventListener("click", () => refresh(true));
document.addEventListener(
  "error",
  (event) => {
    if (event.target.matches?.(".photo-card img"))
      event.target.closest(".photo-card").classList.add("preview-unavailable");
    if (event.target.matches?.("#preview-media img, #preview-media video"))
      $("#preview-media").innerHTML =
        '<p class="preview-error">This original is unavailable or its format cannot be previewed. Open Google Photos to check the copy in your account.</p>';
  },
  true,
);
document.addEventListener("keydown", (event) => {
  if (
    event.key === "/" &&
    !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) &&
    !document.querySelector("dialog[open]")
  ) {
    event.preventDefault();
    $("#global-search").focus();
  }
});
matchMedia("(prefers-color-scheme: dark)").addEventListener(
  "change",
  applyTheme,
);
window.addEventListener("hashchange", navigate);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
state.page = Object.hasOwn(names, location.hash.slice(1))
  ? location.hash.slice(1)
  : "library";
if (window.desktop)
  window.desktop
    .getVersion()
    .then((version) => {
      $("#app-version").textContent = "v" + version;
    })
    .catch(() => {});
refresh();
setInterval(() => {
  if (!document.hidden && !document.querySelector("dialog[open]")) refresh();
}, 2000);
