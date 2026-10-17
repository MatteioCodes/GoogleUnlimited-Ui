const {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  nativeImage,
  session,
  shell,
  Tray,
} = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs/promises");
const path = require("node:path");
const readline = require("node:readline");
const crypto = require("node:crypto");

app.setName("GoogleUnlimited");
if (process.platform === "win32")
  app.setAppUserModelId("io.googleunlimited.desktop");
const root = path.resolve(__dirname, "..");
const dataDirectory =
  process.env.GOOGLE_UNLIMITED_DATA_DIR || app.getPath("userData");
require("node:fs").mkdirSync(dataDirectory, { recursive: true, mode: 0o700 });
app.setPath("userData", dataDirectory);
let mainWindow,
  tray,
  backend,
  address,
  apiToken,
  quitting = false,
  closing = false;

if (!app.requestSingleInstanceLock()) app.exit(0);

function trusted(event) {
  if (
    !mainWindow ||
    event.sender.id !== mainWindow.webContents.id ||
    !event.senderFrame.url.startsWith(`${address}/`)
  ) {
    throw new Error("This action is only available in the app window.");
  }
}

async function request(route, body) {
  const response = await fetch(address + route, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "X-App-Token": apiToken,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(route === "/api/account" ? 100000 : 20000),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error || "The app could not complete that action.");
  return result;
}

async function startBackend() {
  let executable, args;
  if (app.isPackaged) {
    const service = path.join(process.resourcesPath, "service");
    executable =
      process.platform === "win32"
        ? path.join(service, "python.exe")
        : path.join(service, "python", "bin", "python3");
    args = ["-u", path.join(service, "dashboard.py")];
  } else {
    executable =
      process.env.GOOGLE_UNLIMITED_PYTHON ||
      (process.platform === "win32" ? "python" : "python3");
    args = ["-u", path.join(root, "dashboard.py")];
  }
  const resources = app.isPackaged ? process.resourcesPath : root;
  const engine = app.isPackaged
    ? path.join(
        resources,
        "upload",
        process.platform === "win32" ? "gotohp-cli.exe" : "gotohp-cli",
      )
    : process.env.GOOGLE_UNLIMITED_ENGINE ||
      path.join(
        root,
        process.platform === "win32"
          ? "gotohp-cli-x64.exe"
          : "gotohp-cli_amd64",
      );
  args.push(
    "--port",
    "0",
    "--desktop",
    "--no-browser",
    "--data-dir",
    dataDirectory,
    "--asset-dir",
    path.join(resources, "ui"),
    "--engine",
    engine,
  );
  backend = spawn(executable, args, {
    windowsHide: true,
    stdio: ["pipe", "pipe", "pipe"],
    cwd: dataDirectory,
  });
  const child = backend;
  // Consume diagnostics without persisting account data or printing child output.
  child.stderr.on("data", () => {});
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      child.kill();
      reject(
        new Error(
          "The backup service did not start. Reinstall the app if this continues.",
        ),
      );
    }, 30000);
    const lines = readline.createInterface({ input: child.stdout });
    lines.on("line", (line) => {
      try {
        const ready = JSON.parse(line);
        if (ready.ready && Number.isInteger(ready.port)) {
          clearTimeout(timer);
          resolve(ready.port);
        }
      } catch {}
    });
    child.once("error", () => {
      clearTimeout(timer);
      reject(new Error("The included backup service could not be opened."));
    });
    child.once("exit", () => {
      clearTimeout(timer);
      reject(new Error("The backup service exited during startup."));
    });
  });
  address = `http://127.0.0.1:${port}`;
  const html = await (await fetch(address)).text();
  const match = html.match(/name="app-token"\s+content="([^"]+)"/);
  if (!match)
    throw new Error("The app could not connect to its local backup service.");
  apiToken = match[1];
  child.once("exit", () => {
    if (!quitting) {
      dialog.showErrorBox(
        "Backup service stopped",
        "Backup has stopped. Reopen GoogleUnlimited to resume from your saved progress.",
      );
      showWindow();
    }
  });
}

function allowedExternal(url) {
  try {
    const parsed = new URL(url);
    return (
      parsed.protocol === "https:" &&
      [
        "photos.google.com",
        "accounts.google.com",
        "github.com",
        "www.python.org",
      ].includes(parsed.hostname)
    );
  } catch {
    return false;
  }
}

function showWindow() {
  if (!address) return;
  if (!mainWindow) return createWindow();
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 780,
    minHeight: 620,
    title: "GoogleUnlimited",
    backgroundColor: "#f4f4f4",
    icon: path.join(__dirname, "assets", "icon.png"),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.webContents.session.setPermissionRequestHandler(
    (_contents, _permission, callback) => callback(false),
  );
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (allowedExternal(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(`${address}/`)) event.preventDefault();
  });
  mainWindow.on("close", (event) => {
    if (!quitting && tray) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
    if (!quitting && !tray) app.quit();
  });
  await mainWindow.loadURL(address);
  if (!process.argv.includes("--background") || !tray) mainWindow.show();
}

function createTray() {
  try {
    const image = nativeImage
      .createFromPath(path.join(__dirname, "assets", "icon.png"))
      .resize({ width: 24, height: 24 });
    tray = new Tray(image);
    tray.setToolTip("GoogleUnlimited");
    tray.on("click", showWindow);
    tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: "Open GoogleUnlimited", click: showWindow },
        {
          label: "Resume backup",
          click: () =>
            request("/api/sync/start", {}).catch((error) =>
              dialog.showErrorBox("Backup needs attention", error.message),
            ),
        },
        {
          label: "Pause backup",
          click: () => request("/api/sync/stop", {}).catch(() => {}),
        },
        { type: "separator" },
        { label: "Quit GoogleUnlimited", click: () => app.quit() },
      ]),
    );
  } catch {
    tray = null;
  }
}

async function setStartup(enabled) {
  if (typeof enabled !== "boolean")
    throw new Error("Choose a valid startup setting.");
  if (process.platform === "win32") {
    app.setLoginItemSettings({
      name: "GoogleUnlimited",
      openAtLogin: enabled,
      args: ["--background"],
    });
    if (app.getLoginItemSettings().openAtLogin !== enabled)
      throw new Error("Windows could not update automatic startup.");
  } else {
    const config =
      process.env.XDG_CONFIG_HOME || path.join(app.getPath("home"), ".config");
    const target = path.join(config, "autostart", "googleunlimited.desktop");
    if (enabled) {
      await fs.mkdir(path.dirname(target), { recursive: true });
      const executable = process.env.APPIMAGE || process.execPath;
      const escaped = executable
        .replace(/([\\"`$])/g, "\\$1")
        .replaceAll("%", "%%");
      await fs.writeFile(
        target,
        `[Desktop Entry]\nType=Application\nName=GoogleUnlimited\nExec="${escaped}" --background\nTryExec=${executable}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n`,
        { mode: 0o600 },
      );
    } else {
      await fs.rm(target, { force: true });
    }
  }
  return request("/api/startup", { enabled });
}

async function reconcileStartup() {
  let enabled = false;
  if (process.platform === "win32") {
    enabled = app.getLoginItemSettings().openAtLogin;
  } else {
    const config =
      process.env.XDG_CONFIG_HOME || path.join(app.getPath("home"), ".config");
    try {
      const entry = await fs.readFile(
        path.join(config, "autostart", "googleunlimited.desktop"),
        "utf8",
      );
      enabled = entry.includes(
        `TryExec=${process.env.APPIMAGE || process.execPath}\n`,
      );
    } catch {}
  }
  await request("/api/startup", { enabled });
}

async function connectAccount() {
  const partition = session.fromPartition(
    `google-sign-in-${crypto.randomUUID()}`,
  );
  const signIn = new BrowserWindow({
    parent: mainWindow,
    width: 560,
    height: 760,
    title: "Connect Google Photos",
    webPreferences: {
      session: partition,
      sandbox: true,
      nodeIntegration: false,
      contextIsolation: true,
    },
  });
  const userAgent = partition
    .getUserAgent()
    .replace(/\sGoogleUnlimited\/\S+/g, "")
    .replace(/\sElectron\/\S+/g, "");
  partition.setUserAgent(userAgent);
  return new Promise((resolve, reject) => {
    let exchanging = false,
      complete = false;
    const cleanup = async () => {
      partition.cookies.removeListener("changed", changed);
      await partition.clearStorageData().catch(() => {});
    };
    const changed = async (_event, cookie, _cause, removed) => {
      if (
        removed ||
        exchanging ||
        cookie.name !== "oauth_token" ||
        ![
          "accounts.google.com",
          ".accounts.google.com",
          ".google.com",
        ].includes(cookie.domain)
      )
        return;
      exchanging = true;
      try {
        const result = await request("/api/account", { token: cookie.value });
        complete = true;
        resolve(result);
      } catch (error) {
        complete = true;
        reject(error);
      } finally {
        await cleanup();
        if (!signIn.isDestroyed()) signIn.close();
      }
    };
    partition.cookies.on("changed", changed);
    partition.setPermissionRequestHandler((_contents, _permission, callback) =>
      callback(false),
    );
    signIn.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    signIn.webContents.on("will-navigate", (event, url) => {
      try {
        const parsed = new URL(url);
        if (
          parsed.protocol !== "https:" ||
          !(
            parsed.hostname === "google.com" ||
            parsed.hostname.endsWith(".google.com")
          )
        )
          event.preventDefault();
      } catch {
        event.preventDefault();
      }
    });
    signIn.once("closed", async () => {
      await cleanup();
      if (!complete)
        reject(
          new Error(
            "Sign-in closed. You can try again or use the manual connection option.",
          ),
        );
    });
    signIn.loadURL("https://accounts.google.com/EmbeddedSetup").catch(() => {
      complete = true;
      reject(
        new Error(
          "Google sign-in could not open. Check your connection or use the manual option.",
        ),
      );
      if (!signIn.isDestroyed()) signIn.close();
    });
  });
}

function registerHandlers() {
  const handle = (name, callback) =>
    ipcMain.handle(name, async (event, ...args) => {
      trusted(event);
      return callback(...args);
    });
  handle("folders:select", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "Choose backup folders",
      properties: ["openDirectory", "multiSelections"],
    });
    return result.canceled ? [] : result.filePaths;
  });
  handle("account:connect", connectAccount);
  handle("startup:set", setStartup);
  handle("data:open", () => shell.openPath(dataDirectory));
  handle("external:open", (url) => {
    if (!allowedExternal(url)) throw new Error("This link is unavailable.");
    return shell.openExternal(url);
  });
  handle("app:version", () => app.getVersion());
  handle("file:reveal", async (identifier) => {
    if (typeof identifier !== "string" || identifier.length > 12000)
      throw new Error("Choose a file from the library.");
    await request(`/api/media-check?id=${encodeURIComponent(identifier)}`);
    shell.showItemInFolder(
      Buffer.from(identifier, "base64url").toString("utf8"),
    );
  });
  handle("setup:import", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "Choose your previous GoogleUnlimited app folder",
      properties: ["openDirectory"],
    });
    if (result.canceled) return null;
    return request("/api/import", { folder: result.filePaths[0] });
  });
}

app.on("second-instance", showWindow);
app.on("activate", showWindow);
app.on("window-all-closed", () => {
  if (!tray) app.quit();
});
app.on("before-quit", (event) => {
  if (closing) return;
  event.preventDefault();
  quitting = true;
  closing = true;
  if (!backend || backend.exitCode !== null) return app.quit();
  const child = backend;
  const timer = setTimeout(() => {
    child.kill("SIGKILL");
    app.quit();
  }, 10000);
  child.once("exit", () => {
    clearTimeout(timer);
    app.quit();
  });
  child.stdin.end();
});

app.whenReady().then(async () => {
  try {
    await fs.mkdir(dataDirectory, { recursive: true, mode: 0o700 });
    await startBackend();
    await reconcileStartup();
    registerHandlers();
    Menu.setApplicationMenu(
      Menu.buildFromTemplate([
        {
          label: "GoogleUnlimited",
          submenu: [
            { label: "Open app", click: showWindow },
            { type: "separator" },
            { role: "quit" },
          ],
        },
        {
          label: "Edit",
          submenu: [
            { role: "undo" },
            { role: "redo" },
            { type: "separator" },
            { role: "cut" },
            { role: "copy" },
            { role: "paste" },
            { role: "selectAll" },
          ],
        },
        {
          label: "View",
          submenu: [
            { role: "reload" },
            { role: "resetZoom" },
            { role: "zoomIn" },
            { role: "zoomOut" },
            { role: "togglefullscreen" },
          ],
        },
      ]),
    );
    createTray();
    await createWindow();
  } catch (error) {
    dialog.showErrorBox("GoogleUnlimited could not start", error.message);
    app.quit();
  }
});
