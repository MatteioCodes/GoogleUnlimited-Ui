/*
 * electron-builder 26.15.3 has a pure JS NSIS uninstaller reader, but only
 * selects it automatically on macOS. Use that same reader for Linux builds.
 * Native Windows builds use the normal builder path. No product code is patched.
 */
const path = require("node:path");
const { build, Platform, Arch } = require("electron-builder");

if (process.platform === "linux") {
  const version = require("app-builder-lib/package.json").version;
  if (version !== "26.15.3")
    throw new Error(
      "Review the NSIS cross-build adapter when upgrading electron-builder.",
    );
  const { WineVmManager } = require("app-builder-lib/out/vm/WineVm");
  const {
    UninstallerReader,
  } = require("app-builder-lib/out/targets/nsis/nsisUtil");
  WineVmManager.prototype.exec = async function (file, args, options) {
    if (
      args.length ||
      options?.env?.__COMPAT_LAYER !== "RunAsInvoker" ||
      !file.endsWith(".exe")
    ) {
      throw new Error(
        "Unexpected Windows helper invocation during NSIS cross-build.",
      );
    }
    const destination = path.join(
      path.dirname(file),
      `${path.basename(file, "exe")}__uninstaller.exe`,
    );
    await UninstallerReader.exec(file, destination);
    console.log(
      "Generated NSIS uninstaller with electron-builder’s binary reader.",
    );
  };
}

build({
  targets: Platform.WINDOWS.createTarget(["nsis"], Arch.x64),
  publish: "never",
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
