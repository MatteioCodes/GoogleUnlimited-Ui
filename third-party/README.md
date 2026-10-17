# Source references and bundled software

The desktop interface uses original application code and assets, with navigation,
gallery layout, folder-watch controls, and theme behavior informed by Ente Photos.
The reference is Ente's AGPL-3.0 source at commit
`5249a8c432411b46ea03d11819f2a029ea447e41`:

- https://github.com/ente-io/ente/blob/5249a8c432411b46ea03d11819f2a029ea447e41/web/apps/photos/src/components/gallery/PhotosNavigationShell.tsx
- https://github.com/ente-io/ente/blob/5249a8c432411b46ea03d11819f2a029ea447e41/web/apps/photos/src/components/sidebar/WatchFolder.tsx
- https://github.com/ente-io/ente/blob/5249a8c432411b46ea03d11819f2a029ea447e41/web/apps/photos/src/components/sidebar/theme.ts

Ente source and brand assets are not included in this application. GoogleUnlimited
is an independent Google Photos client and does not use Ente's storage service.

The upload engine is gotohp by xob0t, licensed under MIT. Its license is included
in `gotohp-LICENSE.txt`. Installers also bundle Electron, CPython, Pillow, and their
runtime dependencies; their licenses are included with the packaged resources.

Linux installers additionally include the Ubuntu 22.04 builds of sqlite3,
libsqlite3, inotify-tools, libinotifytools, readline, and libtinfo. Exact download
URLs, versions, and SHA-256 checksums are in `scripts/runtime-lock.json`.
Copyright notices and license texts are in `service/backend/tools/licenses`.
Corresponding inotify-tools and readline source archives, distribution patches,
and build metadata accompany the binaries in `service/backend/tools/sources`.
These tools run as separate processes; they are used by the original Bash backend.

Windows installers include the repository's PSSQLite module, used by the original
PowerShell backend. Windows PowerShell 5.1 is supplied by Windows 10/11.
