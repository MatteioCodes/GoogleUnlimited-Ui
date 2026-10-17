/* Real Electron window, preload, native IPC and backup worker. Google is simulated. */
const { _electron: electron } = require("playwright");
const { expect } = require("@playwright/test");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

async function main() {
  const root = path.resolve(__dirname, "..");
  const temporary = await fs.mkdtemp(
    path.join(os.tmpdir(), "googleunlimited-desktop-"),
  );
  const data = path.join(temporary, "profile");
  const photos = path.join(temporary, "Family's photos");
  const uploader = path.join(temporary, "gotohp-cli");
  const screenshots =
    process.env.UI_SCREENSHOT_DIR || path.join(temporary, "screenshots");
  await fs.mkdir(photos, { recursive: true });
  await fs.mkdir(screenshots, { recursive: true });
  const python = execFileSync(
    process.platform === "win32" ? "python" : "python3",
    ["-c", "import sys; print(sys.executable)"],
    { encoding: "utf8" },
  ).trim();
  execFileSync(
    python,
    [
      "-c",
      "import runpy,sys; from pathlib import Path; runpy.run_path('tests/browser_smoke.py')['fixture_uploader'](Path(sys.argv[1]))",
      uploader,
    ],
    { cwd: root },
  );
  execFileSync(python, [
    "-c",
    "from PIL import Image; import sys; Image.new('RGB',(360,240),'#93b4a0').save(sys.argv[1])",
    path.join(photos, "A desktop memory.jpg"),
  ]);
  const packaged = process.env.PACKAGED_EXECUTABLE;
  if (packaged) {
    // A saved, simulated confirmation exercises the installed gallery and
    // bundled Pillow without contacting Google or connecting an account.
    execFileSync(python, ["-c", "import sys; from pathlib import Path; sys.path.insert(0,'tests'); from backend_fixtures import seed_upload; seed_upload(Path(sys.argv[1]),Path(sys.argv[2]))", data, path.join(photos,"A desktop memory.jpg")], { cwd: root });
  }
  const launch = () =>
    electron.launch({
      executablePath: packaged || require("electron"),
      args: ["--no-sandbox", ...(packaged ? [] : [root])],
      cwd: root,
      env: {
        ...process.env,
        GOOGLE_UNLIMITED_DATA_DIR: data,
        GOOGLE_UNLIMITED_ENGINE: uploader,
        GOOGLE_UNLIMITED_PYTHON: packaged
          ? "/no-system-python-required"
          : python,
        XDG_CONFIG_HOME: path.join(temporary, "config"),
      },
      timeout: 30000,
    });
  let instance;
  try {
    instance = await launch();
    let window = await instance.firstWindow();
    await expect(window.locator("h1")).toHaveText("Photos");
    const security = await window.evaluate(() => ({
      node: typeof require,
      bridge: typeof desktop,
    }));
    if (security.node !== "undefined" || security.bridge !== "object")
      throw new Error("Renderer isolation failed");
    await instance.evaluate(({ dialog }, photos) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [photos],
      });
    }, photos);
    await window.locator('[data-action="add-folder"]').first().click();
    await window.getByRole("link", { name: /Backup folders/ }).click();
    await expect(window.locator(".folder-row")).toHaveCount(1);
    await window
      .getByRole("link", { name: "Settings", exact: true })
      .first()
      .click();
    await expect(window.locator(".requirement .badge")).toHaveText([
      "Ready",
      "Ready",
      "Ready",
    ]);
    await window.locator("#theme-select").selectOption("dark");
    await expect(window.locator("html")).toHaveAttribute("data-theme", "dark");
    await window.reload();
    await expect(window.locator("html")).toHaveAttribute("data-theme", "dark");
    await window.locator("#startup-toggle").check();
    await expect(window.locator("#startup-toggle")).toBeChecked();
    if (!packaged) {
      // Replace only the external Google page with a real Electron cookie event.
      // Cookie capture, the native bridge, local HTTP, stdin and persistence run normally.
      await instance.evaluate(({ BrowserWindow }) => {
        const original = BrowserWindow.prototype.loadURL;
        BrowserWindow.prototype.loadURL = function (url, ...args) {
          if (url === "https://accounts.google.com/EmbeddedSetup") {
            this.webContents.session.cookies.set({
              url: "https://accounts.google.com",
              name: "oauth_token",
              value: "local-test-cookie",
              secure: true,
              httpOnly: true,
            });
            return Promise.resolve();
          }
          return original.call(this, url, ...args);
        };
      });
      await window.locator('[data-action="account"]').first().click();
      await expect(window.locator("#native-sign-in")).toBeVisible();
      await window.locator("#native-connect").click();
      await expect(window.locator("#account-dialog")).not.toBeVisible({
        timeout: 15000,
      });
      await expect(
        window.getByText("browser@example.test", { exact: true }),
      ).toBeVisible();
      if (await window.evaluate(() => localStorage.length))
        throw new Error("Unexpected browser credential storage");
      await window.locator("#backup-toggle").click();
      await expect(window.locator("#backup-toggle")).toHaveText("Pause backup");
      await window.getByRole("link", { name: /All photos/ }).click();
      await expect(window.locator(".photo-card")).toHaveCount(1, {
        timeout: 20000,
      });
      await window
        .getByRole("button", { name: "Open A desktop memory.jpg", exact: true })
        .click();
      await expect(window.locator("#preview-media img")).toHaveJSProperty(
        "naturalWidth",
        360,
      );
      await window.keyboard.press("Escape");
      await window.screenshot({
        path: path.join(screenshots, "desktop-native.png"),
      });
      await instance.close();
      instance = await launch();
      window = await instance.firstWindow();
      await expect(window.locator(".photo-card")).toHaveCount(1, {
        timeout: 15000,
      });
      await expect(window.locator("#backup-toggle")).toHaveText("Pause backup");
      await window.locator("#backup-toggle").click();
      await expect(window.locator("#backup-toggle")).toHaveText("Start backup");
    } else {
      await window.getByRole("link", { name: /All photos/ }).click();
      await expect(window.locator(".photo-card")).toHaveCount(1);
      await window.getByRole("button", { name: "Open A desktop memory.jpg", exact: true }).click();
      await expect(window.locator("#preview-media img")).toHaveJSProperty("naturalWidth", 360);
      await window.keyboard.press("Escape");
    }
    await window
      .getByRole("link", { name: "Settings", exact: true })
      .first()
      .click();
    await window.locator("#startup-toggle").uncheck();
    await expect(window.locator("#startup-toggle")).not.toBeChecked();
    const resources = await instance.evaluate(({ app }) => ({
      packaged: app.isPackaged,
      version: app.getVersion(),
    }));
    console.log(
      `${packaged ? "Packaged" : "Development"} desktop passed: isolated renderer, native folder selection, installed components, persistent theme, startup registration/removal${packaged ? ", gallery and image preview using the bundled runtime" : ", automatic cookie handoff, upload, preview and resume after quit"}.`,
      resources,
    );
  } finally {
    if (instance) await instance.close();
    await fs.rm(temporary, { recursive: true, force: true });
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
