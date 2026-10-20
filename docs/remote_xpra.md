# Running corgidrp GUI on a server, displayed on your Mac

The GUI runs where corgidrp and the data are. Two ways to see it on a laptop:

## xpra (recommended)

xpra starts a private virtual X server on the remote machine. The GUI draws into it at full
speed, and xpra streams compressed per-window updates to a client on your Mac, where each
window appears as a native window. Unlike plain X forwarding, drawing is not synchronous over
the link, Qt's bitmap-heavy repaints are compressed, and the session survives a dropped
connection: you can detach, close the laptop, and reattach later.

### Server (Linux)

1. Install xpra. Distribution packages lag; the project's own repositories are newer:
   https://github.com/Xpra-org/xpra/wiki/Download
2. Install the GUI in the environment where corgidrp imports, plus Qt's X11 client libraries
   (Debian/Ubuntu names):

        sudo apt install libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libgl1
        conda activate corgidrp
        pip install -e /path/to/corgidrp_gui

3. Check it starts headlessly:

        QT_QPA_PLATFORM=offscreen corgidrp-gui --version

### Client (macOS)

Install the xpra client from the project's DMG (or `brew install --cask xpra`). Client and
server should match on major version.

### Use

    # first time: start a session on the server and attach to it
    xpra start ssh://user@server/ --start="bash -lc 'conda activate corgidrp && corgidrp-gui'"

    # later, from any machine
    xpra attach ssh://user@server/

    # on the server
    xpra list
    xpra stop

Useful flags: `--desktop-scaling=1` or `--desktop-scaling=2` if windows come out tiny or huge
on a Retina display; `--keyboard-layout=us` if keys are mismatched; `--encoding=rgb` on a fast
campus link for the sharpest text.

### Known rough edges

- The macOS client is less polished than the Linux one; menu bars stay inside each window.
- Drag-and-drop in the Recipe Builder works but feedback lags slightly on slow links.
- Fonts render on the server, so the four themes look the same as locally.

## Plain X11 forwarding

    ssh -Y user@server
    conda activate corgidrp && corgidrp-gui

Works with XQuartz on the Mac and needs no extra software on the server beyond Qt's xcb
libraries, but every repaint crosses the network and the session dies with the SSH connection.
Fine for a quick look on a fast link; use xpra for real work.

## Why there is no "remote backend" in the app

Because the whole GUI runs on the server, every file it sees is local: the file dialogs, the
CalDB, the queue and the runner processes all work unchanged. A split GUI (local windows,
remote agent) would need its own file browser and a protocol; the code keeps one small
discipline from that design, a `Backend` interface for file and process access, so it remains
possible later without a rewrite.
