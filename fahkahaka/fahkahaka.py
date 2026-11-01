#!/usr/bin/env python3
"""
fahkahaka - Windows tool that talks to a connected iPhone over USB and
forces MobileGestalt values (Siri AI keys, Dynamic Island, spoofed model).

Requires:
  - iTunes / Apple Devices installed (Apple Mobile Device Service = usbmuxd)
  - The iPhone trusted by this PC
  - A jailbroken device with SSH running (root@22, default password "alpine")

It edits the same gestalt cache file the Asteroid iOS app edits:
  /private/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/
      Library/Caches/com.apple.MobileGestalt.plist

A stock (non-jailbroken) iPhone cannot be written to from a PC - there is no
exploit that runs on the Windows side. This tool is honest about that.
"""

import os
import queue
import socket
import plistlib
import struct
import sys
import threading
import time
import traceback

import tkinter as tk
from tkinter import ttk, messagebox

try:
    import paramiko
except ImportError:
    paramiko = None

APP_NAME = "fahkahaka"
APP_VERSION = "1.0"
MUX_ADDR = ("127.0.0.1", 27015)

GESTALT_PATH = ("/private/var/containers/Shared/SystemGroup/"
                "systemgroup.com.apple.mobilegestaltcache/Library/Caches/"
                "com.apple.MobileGestalt.plist")

# ----------------------------------------------------------------- gestalt keys
# same hashes the Asteroid app uses
K_PRODUCT_TYPE        = "h9jDsbgj7xIVeIQ8S3/X3Q"   # ProductType
K_ARTWORK             = "oPeik/9e8lQWMszEjbPzng"   # ArtworkTraits
K_ISLAND              = "YlEtTtHlNesRBMal1CqRaA"   # DeviceSupportsDynamicIsland
K_GENMODEL            = "A62OafQ85EJAiiqKn4agtg"   # DeviceSupportsGenerativeModelSystems
K_REGION_CODE         = "h63QSdBCiT/z0WU6rdQv6Q"   # RegionCode
K_REGION_SYSCONFIG    = "yK+xavymRGZ3xWc1tb8XDg"   # RegionInfoFromSysconfig
K_BOARD               = "oYicEKzVTz4/CxxE05pEgQ"   # BoardConfig
K_PLATFORM            = "5pYKlGnYYBzGvAlIU8RjEQ"   # Platform
K_REGMODEL            = "97JDvERpVwO+GHtthIh7hA"   # RegModelNumber
K_INT_INSTALL         = "EqrsVvjcYDdxHBiQmGhAWw"   # apple-internal-install
K_INT_BUILD           = "LBJfwOEzExRxzlAnSuI7eg"   # InternalBuild
K_ACT_BUTTON          = "cT44WE1EohiwRzhsZ8xEsw"   # RingerButtonCapability (Action Button)
K_CAM_BUTTON          = "CwvKxM2cEogD3p+HYgaW0Q"   # CameraButtonCapability
K_GRAPHICS_TIER       = "oOV1jhJbdV3AddkcCg0AEA"   # apple-graphics-performance-tier
K_TOUCHID_SETTINGS    = "8Shl+AdVKo09f1Sldkb0kA"   # Touch ID Settings pane
K_LIVE_ACTIVITIES     = "e4ZSDal1Fg7QfCA7rlNmSQ"   # DeviceSupportsLiveActivities

# bool keys set by Siri AI activation (from Asteroid's mgSetSiriAIEnabled)
SIRI_AI_BOOL_KEYS = [
    "xOJfWykLmQCc8lKlzMlrLA",
    "K/R1GfGfCkXvEhaPS2Vrng",   # DeviceSupportsSiriUnderstandingOnDevice
    "waGD2UTpntjbDXD1r3oALQ",   # DeviceSupportsSiriHub
    "WXi7NQbOKnEX4vPQFeZAdQ",   # DeviceSupportsSiriBargeIn
    "PTQ+ABwag03BwO/CKvIK/A",   # DeviceSupportsSiriSpeaks
    "0AJUv/uYPsRiZNGpWJ7zfg",   # DeviceSupportsSiriSpokenMessages
]

# spoof model -> RegModelNumber (board model string)
REG_MODELS = {
    "iPhone16,1": "A3083", "iPhone16,2": "A3084",
    "iPhone17,1": "A3083", "iPhone17,2": "A3084",
    "iPhone18,1": "A3256", "iPhone18,2": "A3257", "iPhone18,4": "A3260",
    "iPhone19,2": "A3472", "iPhone19,3": "A3473", "iPhone19,7": "A3716",
}

# ------------------------------------------------------------------ device list
DEVICES = [
    ("iPhone 11",            "iPhone12,1"),
    ("iPhone 11 Pro",        "iPhone12,2"),
    ("iPhone 11 Pro Max",    "iPhone12,5"),
    ("iPhone SE (2nd gen)",  "iPhone12,8"),
    ("iPhone 12 mini",       "iPhone13,1"),
    ("iPhone 12",            "iPhone13,2"),
    ("iPhone 12 Pro",        "iPhone13,3"),
    ("iPhone 12 Pro Max",    "iPhone13,4"),
    ("iPhone SE (3rd gen)",  "iPhone14,6"),
    ("iPhone 13 mini",       "iPhone14,4"),
    ("iPhone 13",            "iPhone14,5"),
    ("iPhone 13 Pro",        "iPhone14,2"),
    ("iPhone 13 Pro Max",    "iPhone14,3"),
    ("iPhone 14",            "iPhone14,7"),
    ("iPhone 14 Plus",       "iPhone14,8"),
    ("iPhone 14 Pro",        "iPhone15,2"),
    ("iPhone 14 Pro Max",    "iPhone15,3"),
    ("iPhone 15",            "iPhone15,9"),
    ("iPhone 15 Plus",       "iPhone15,10"),
    ("iPhone 15 Pro",        "iPhone16,1"),
    ("iPhone 15 Pro Max",    "iPhone16,2"),
    ("iPhone 16e",           "iPhone17,5"),
    ("iPhone 16",            "iPhone17,3"),
    ("iPhone 16 Plus",       "iPhone17,4"),
    ("iPhone 16 Pro",        "iPhone17,1"),
    ("iPhone 16 Pro Max",    "iPhone17,2"),
    ("iPhone 17",            "iPhone18,3"),
    ("iPhone Air",           "iPhone18,4"),
    ("iPhone 17 Pro",        "iPhone18,1"),
    ("iPhone 17 Pro Max",    "iPhone18,2"),
    ("iPhone 18 Pro",        "iPhone19,2"),
    ("iPhone 18 Pro Max",    "iPhone19,3"),
    ("iPhone 18 Pro Max (Global)", "iPhone19,7"),
]
DEFAULT_SPOOF = "iPhone19,3"

SMALL_ISLAND_SUBTYPE = 2436  # smallest island pill (iPhone X size)

# ------------------------------------------------------------------- usbmux raw
def _mux_socket():
    try:
        s = socket.create_connection(MUX_ADDR, 5)
        s.settimeout(20)
        return s
    except OSError:
        raise RuntimeError(
            "Could not reach Apple Mobile Device Service (usbmuxd) on port 27015.\n"
            "Install iTunes or the 'Apple Devices' app and plug the iPhone in.")

def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("usbmux connection closed")
        buf += chunk
    return buf

def _mux_send(sock, payload, tag=1):
    data = plistlib.dumps(payload, fmt=plistlib.FMT_BINARY)
    sock.sendall(struct.pack("<IIII", 16 + len(data), 1, 8, tag) + data)

def _mux_recv(sock):
    hdr = _recv_exact(sock, 16)
    length, _ver, typ, tag = struct.unpack("<IIII", hdr)
    body = _recv_exact(sock, length - 16)
    if typ != 8:
        raise RuntimeError("unexpected usbmux packet type %d" % typ)
    return plistlib.loads(body), tag

def list_usb_devices():
    """Return [{'id', 'name', 'model', 'version', 'udid'}] via usbmux ListDevices."""
    s = _mux_socket()
    try:
        _mux_send(s, {
            "MessageType": "ListDevices",
            "ClientVersionString": APP_NAME + "-" + APP_VERSION,
            "ProgName": APP_NAME,
            "kLibUSBMuxVersion": 3,
        })
        msg, _ = _mux_recv(s)
    finally:
        s.close()
    out = []
    for d in msg.get("DeviceList", []):
        p = d.get("Properties", {}) or {}
        out.append({
            "id": d.get("DeviceID"),
            "name": p.get("DeviceName", "iPhone"),
            "model": p.get("ProductType", "unknown"),
            "version": p.get("ProductVersion", "?"),
            "udid": p.get("SerialNumber") or p.get("UDID") or str(d.get("DeviceID")),
        })
    return out

def open_device_port(dev_id, port):
    """Open a raw forwarded TCP connection to dev_id:port through usbmux."""
    s = _mux_socket()
    try:
        _mux_send(s, {
            "MessageType": "Connect",
            "DeviceID": dev_id,
            "PortNumber": socket.htons(port),
            "ClientVersionString": APP_NAME + "-" + APP_VERSION,
            "ProgName": APP_NAME,
            "kLibUSBMuxVersion": 3,
        })
        msg, _ = _mux_recv(s)
        num = msg.get("Number", msg.get("Result", 1))
        if num != 0:
            raise RuntimeError(
                "Device refused connection on port %d (code %s).\n"
                "If the phone is not jailbroken / SSH is not running, this tool "
                "cannot write anything - it needs root SSH on the device." % (port, num))
        s.settimeout(60)
        return s
    except Exception:
        s.close()
        raise

# ------------------------------------------------------------------------ ssh
class Device:
    def __init__(self, info, password, ssh_port=22, user="root"):
        self.info = info
        self.user = user
        self.password = password
        self.ssh_port = ssh_port
        self.transport = None
        self.sftp = None

    def connect(self):
        if paramiko is None:
            raise RuntimeError("paramiko is not installed (broken build).")
        sock = open_device_port(self.info["id"], self.ssh_port)
        try:
            t = paramiko.Transport(sock)
            t.start_client(timeout=20)
            t.auth_password(self.user, self.password)
        except Exception:
            sock.close()
            raise
        self.transport = t
        self.sftp = t.open_sftp()

    def close(self):
        try:
            if self.sftp:
                self.sftp.close()
            if self.transport:
                self.transport.close()
        except Exception:
            pass

    def run(self, cmd, timeout=60):
        chan = self.transport.open_session()
        chan.settimeout(timeout)
        chan.exec_command(cmd)
        out = chan.recv(65536).decode(errors="replace")
        err = chan.recv(65536).decode(errors="replace")
        while not chan.exit_status_ready():
            time.sleep(0.05)
        rc = chan.recv_exit_status()
        chan.close()
        return rc, out, err

    # ------------------------------------------------------------- gestalt io
    def read_gestalt(self):
        with self.sftp.open(GESTALT_PATH, "rb") as f:
            return plistlib.loads(f.read())

    def backup_gestalt(self, pl):
        data = plistlib.dumps(pl, fmt=plistlib.FMT_BINARY)
        with self.sftp.open("/var/tmp/fahkahaka-original.plist", "wb") as f:
            f.write(data)
        return data

    def write_gestalt(self, pl):
        data = plistlib.dumps(pl, fmt=plistlib.FMT_BINARY)
        tmp = "/var/tmp/fahkahaka-new.plist"
        with self.sftp.open(tmp, "wb") as f:
            f.write(data)
        st = self.sftp.stat(GESTALT_PATH)
        rc, _, err = self.run(
            "cp '%s' '%s' 2>/dev/null; "
            "mv '%s' '%s' && chown %d:%d '%s' && chmod %o '%s'" % (
                GESTALT_PATH, GESTALT_PATH + ".fahkahaka.bak",
                tmp, GESTALT_PATH,
                st.st_uid, st.st_gid, GESTALT_PATH,
                st.st_mode & 0o7777, GESTALT_PATH))
        if rc != 0:
            raise RuntimeError("failed to move gestalt into place: " + err.strip())

    def respring(self):
        self.run("if command -v sbreload >/dev/null 2>&1; then sbreload; "
                 "else killall -9 SpringBoard; fi", timeout=15)

# ------------------------------------------------------------------- mutation
def cache_extra(pl):
    return pl.setdefault("CacheExtra", {})

def apply_changes(pl, opts):
    """opts: dict with keys spoof(bool), product(str), siri(bool),
    island(bool), actions(bool). Returns list of human-readable actions."""
    done = []
    ce = cache_extra(pl)

    if opts["spoof"] or opts["siri"]:
        ce[K_PRODUCT_TYPE] = opts["product"]
        done.append("ProductType -> %s" % opts["product"])

    if opts["siri"]:
        ce[K_GENMODEL] = 1
        ce[K_PLATFORM] = "t8130"
        ce[K_BOARD] = "D83AP"
        ce[K_REGION_CODE] = "LL"
        ce[K_REGION_SYSCONFIG] = "LL/A"
        ce[K_REGMODEL] = REG_MODELS.get(opts["product"], "A3083")
        for k in SIRI_AI_BOOL_KEYS:
            ce[k] = 1
        ce.pop(K_INT_INSTALL, None)
        ce.pop(K_INT_BUILD, None)
        ce[K_LIVE_ACTIVITIES] = 1
        done.append("Siri AI eligibility keys set (region LL, board D83AP)")

    if opts["island"]:
        ce[K_ISLAND] = 1
        art = ce.setdefault(K_ARTWORK, {})
        art["ArtworkDeviceSubType"] = SMALL_ISLAND_SUBTYPE
        ce[K_LIVE_ACTIVITIES] = 1
        done.append("Dynamic Island enabled, small pill (subtype %d)" % SMALL_ISLAND_SUBTYPE)

    if opts["actions"]:
        ce[K_ACT_BUTTON] = 1
        ce[K_CAM_BUTTON] = 1
        ce[K_GRAPHICS_TIER] = 1
        ce[K_TOUCHID_SETTINGS] = 1
        done.append("3 Actions enabled (Action Button, Camera Control, Touch ID Settings)")

    return done

# ------------------------------------------------------------------- backup dir
def backup_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME, "backups")
    os.makedirs(d, exist_ok=True)
    return d

def save_local_backup(udid, data):
    p = os.path.join(backup_dir(), "%s-%d.plist" % (udid, int(time.time())))
    with open(p, "wb") as f:
        f.write(data)
    return p

def latest_local_backup(udid):
    d = backup_dir()
    cands = [os.path.join(d, x) for x in os.listdir(d)
             if x.startswith(udid + "-") and x.endswith(".plist")]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)

# ------------------------------------------------------------------------ gui
class App:
    def __init__(self, root):
        self.root = root
        self.logq = queue.Queue()
        self.devices = []

        root.title("%s v%s" % (APP_NAME, APP_VERSION))
        root.geometry("660x720")
        root.minsize(620, 680)

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#141418")
        style.configure("TLabel", background="#141418", foreground="#e8e8ea",
                        font=("Segoe UI", 10))
        style.configure("Hdr.TLabel", background="#141418", foreground="#ffffff",
                        font=("Segoe UI Semibold", 15))
        style.configure("Sub.TLabel", background="#141418", foreground="#8a8a93",
                        font=("Segoe UI", 9))
        style.configure("TCheckbutton", background="#141418", foreground="#e8e8ea",
                        font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=6)
        style.configure("TCombobox", padding=4)
        root.configure(background="#141418")

        main = ttk.Frame(root, padding=14)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="fahkahaka", style="Hdr.TLabel").pack(anchor="w")
        ttk.Label(main, text="Forces MobileGestalt on a connected, jailbroken iPhone "
                             "(USB). Same keys as the Asteroid app.",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 10))

        # --- device row
        devf = ttk.Frame(main)
        devf.pack(fill="x", pady=(0, 8))
        ttk.Label(devf, text="Device").pack(side="left")
        self.devvar = tk.StringVar()
        self.devbox = ttk.Combobox(devf, textvariable=self.devvar,
                                   state="readonly", width=48)
        self.devbox.pack(side="left", padx=8, fill="x", expand=True)
        ttk.Button(devf, text="Refresh", command=self.refresh_devices).pack(side="left")

        # --- spoof picker
        spf = ttk.Frame(main)
        spf.pack(fill="x", pady=(0, 8))
        ttk.Label(spf, text="Spoof as").pack(side="left")
        self.spoofvar = tk.StringVar()
        labels = ["%s  (%s)" % (n, p) for n, p in DEVICES]
        bylabel = {("%s  (%s)" % (n, p)): p for n, p in DEVICES}
        self.bylabel = bylabel
        self.spoofbox = ttk.Combobox(spf, textvariable=self.spoofvar,
                                     values=labels, state="readonly", width=48)
        for lbl, prod in bylabel.items():
            if prod == DEFAULT_SPOOF:
                self.spoofvar.set(lbl)
        self.spoofbox.pack(side="left", padx=8, fill="x", expand=True)

        # --- toggles
        self.v_spoof = tk.BooleanVar(value=True)
        self.v_siri = tk.BooleanVar(value=True)
        self.v_island = tk.BooleanVar(value=True)
        self.v_actions = tk.BooleanVar(value=True)
        ttk.Checkbutton(main, text="Spoof device model (18 Pro Max by default)",
                        variable=self.v_spoof).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(main, text="Siri AI (Apple Intelligence eligibility keys)",
                        variable=self.v_siri).pack(anchor="w", pady=(2, 0))
        ttk.Checkbutton(main, text="Small Dynamic Island",
                        variable=self.v_island).pack(anchor="w", pady=(2, 0))
        ttk.Checkbutton(main, text="3 Actions (Action Button + Camera Control + Touch ID)",
                        variable=self.v_actions).pack(anchor="w", pady=(2, 0))

        # --- ssh
        sf = ttk.Frame(main)
        sf.pack(fill="x", pady=(10, 4))
        ttk.Label(sf, text="SSH password").pack(side="left")
        self.pwvar = tk.StringVar(value="alpine")
        ttk.Entry(sf, textvariable=self.pwvar, show="*", width=24).pack(side="left", padx=8)
        ttk.Label(sf, text="port").pack(side="left")
        self.portvar = tk.StringVar(value="22")
        ttk.Entry(sf, textvariable=self.portvar, width=6).pack(side="left", padx=6)

        # --- buttons
        bf = ttk.Frame(main)
        bf.pack(fill="x", pady=10)
        ttk.Button(bf, text="Apply", command=lambda: self.job("apply")).pack(
            side="left", padx=(0, 6))
        ttk.Button(bf, text="Respring", command=lambda: self.job("respring")).pack(
            side="left", padx=6)
        ttk.Button(bf, text="Revert", command=lambda: self.job("revert")).pack(
            side="left", padx=6)
        ttk.Button(bf, text="Open backups", command=self.open_backups).pack(side="left", padx=6)

        # --- log
        ttk.Label(main, text="Log", style="Sub.TLabel").pack(anchor="w")
        self.log = tk.Text(main, height=16, bg="#0c0c0f", fg="#c8c8d0",
                           insertbackground="#c8c8d0", relief="flat",
                           font=("Consolas", 9), state="disabled",
                           highlightthickness=1, highlightbackground="#26262c")
        self.log.pack(fill="both", expand=True, pady=(4, 0))

        ttk.Label(main,
                  text="Honest limits: the phone must be jailbroken with SSH - a PC "
                       "cannot write gestalt on a stock iPhone. Siri AI keys only open "
                       "the eligibility gate; the on-device models still need A17 Pro+ "
                       "hardware to actually run.",
                  style="Sub.TLabel", wraplength=620).pack(anchor="w", pady=(8, 0))

        self.set_busy(False)
        self.refresh_devices()
        self.root.after(100, self.poll_log)

    # ------------------------------------------------------------- log helper
    def log_line(self, s):
        self.logq.put(s)

    def poll_log(self):
        try:
            while True:
                s = self.logq.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", s + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_log)

    def set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for w in (self.devbox, self.spoofbox):
            w.configure(state="disabled" if busy else
                        ("readonly" if w is self.spoofbox or True else "normal"))

    def open_backups(self):
        os.startfile(backup_dir())

    # ---------------------------------------------------------------- actions
    def refresh_devices(self):
        def work():
            try:
                devs = list_usb_devices()
            except Exception as e:
                self.log_line("[!] " + str(e))
                return
            self.devices = devs
            vals = ["%s  -  %s iOS %s  (%s)" % (d["name"], d["model"],
                                                d["version"], d["udid"][:8])
                    for d in devs]
            self.root.after(0, lambda: (self.devbox.configure(values=vals),
                                        self.devvar.set(vals[0] if vals else "")))
            if not devs:
                self.log_line("[!] No iPhone detected. Connect it, unlock it, and "
                              "tap Trust if asked.")
            else:
                self.log_line("[*] found %d device(s)" % len(devs))
        threading.Thread(target=work, daemon=True).start()

    def current_device(self):
        if not self.devices:
            return None
        idx = 0
        vals = self.devbox["values"]
        if vals:
            try:
                idx = list(vals).index(self.devvar.get())
            except ValueError:
                idx = 0
        return self.devices[min(idx, len(self.devices) - 1)]

    def job(self, kind):
        dev = self.current_device()
        if dev is None:
            messagebox.showerror(APP_NAME, "No iPhone detected. Plug one in and Refresh.")
            return
        opts = {
            "spoof": self.v_spoof.get(),
            "siri": self.v_siri.get(),
            "island": self.v_island.get(),
            "actions": self.v_actions.get(),
            "product": self.bylabel.get(self.spoofvar.get(), DEFAULT_SPOOF),
        }
        password = self.pwvar.get()
        try:
            port = int(self.portvar.get())
        except ValueError:
            port = 22
        threading.Thread(target=self._run_job, args=(kind, dev, opts, password, port),
                         daemon=True).start()

    def _run_job(self, kind, dev, opts, password, port):
        self.log_line("[*] %s on %s (%s)..." % (kind, dev["name"], dev["model"]))
        d = Device(dev, password, port)
        try:
            d.connect()
            self.log_line("[+] SSH connected (root@usb:%d)" % port)
        except Exception as e:
            self.log_line("[!] SSH failed: %s" % _friendly_ssh(e))
            return
        try:
            if kind == "respring":
                d.respring()
                self.log_line("[+] resprung")
                return
            if kind == "revert":
                path = latest_local_backup(dev["udid"])
                if path:
                    with open(path, "rb") as f:
                        data = f.read()
                    pl = plistlib.loads(data)
                else:
                    with d.sftp.open("/var/tmp/fahkahaka-original.plist", "rb") as f:
                        pl = plistlib.loads(f.read())
                d.write_gestalt(pl)
                d.respring()
                self.log_line("[+] reverted to backup and resprung")
                return
            # apply
            pl = d.read_gestalt()
            self.log_line("[+] read gestalt (%d top-level keys)" % len(pl))
            d.backup_gestalt(pl)
            save_local_backup(dev["udid"], plistlib.dumps(pl, fmt=plistlib.FMT_BINARY))
            for line in apply_changes(pl, opts):
                self.log_line("    -> " + line)
            d.write_gestalt(pl)
            self.log_line("[+] gestalt written")
            d.respring()
            self.log_line("[+] resprung - done. Reboot reverts unless you use the "
                          "Asteroid app's atomic write.")
        except Exception:
            self.log_line("[!] error:\n" + traceback.format_exc(limit=3))
        finally:
            d.close()

def _friendly_ssh(e):
    s = str(e)
    if "Authentication failed" in s:
        return ("authentication failed - wrong SSH password (default is 'alpine', "
                "change it in the field above if you set one on the device)")
    if "refused connection" in s or "Device refused" in s:
        return s + "\nStock devices have no SSH: jailbreak the phone first."
    return s

# ---------------------------------------------------------------------- entry
def probe_cli():
    try:
        for d in list_usb_devices():
            print("%s  %s  iOS %s  udid=%s" % (d["name"], d["model"],
                                               d["version"], d["udid"]))
    except Exception as e:
        print("error: %s" % e)
        return 1
    return 0

if __name__ == "__main__":
    if "--probe" in sys.argv:
        sys.exit(probe_cli())
    if paramiko is None:
        # still show a window so the user sees WHY instead of a vanishing console
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(APP_NAME, "paramiko missing from build - re-download the exe.")
        sys.exit(1)
    root = tk.Tk()
    App(root)
    root.mainloop()
