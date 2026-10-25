import time
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

BG = "#15131D"
SURFACE = "#211D2E"
RAISED = "#2C2740"
TEXT = "#ECE9F7"
MUTED = "#9A94B3"
ACCENT = "#7C6CFF"
DANGER = "#FF5D6C"


class VideoTile(ctk.CTkFrame):
    def __init__(self, master, name, is_self=False):
        super().__init__(master, fg_color=SURFACE, corner_radius=14)
        self.name = name
        self.is_self = is_self
        self.mic = True
        self.cam = True
        self.last_img = None
        self.avatar_cache = {}
        self.img_label = ctk.CTkLabel(self, text="", fg_color="transparent")
        self.img_label.place(relx=0.5, rely=0.5, anchor="center")
        self.badge = ctk.CTkLabel(
            self,
            text=self.badge_text(),
            fg_color=RAISED,
            text_color=TEXT,
            corner_radius=8,
            padx=10,
            pady=4,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.badge.place(relx=0.03, rely=0.94, anchor="sw")
        self.show_avatar(320, 240)

    def badge_text(self):
        title = "You" if self.is_self else self.name
        return f"{title} · muted" if not self.mic else title

    def set_state(self, mic, cam):
        self.mic = mic
        self.cam = cam
        self.badge.configure(
            text=self.badge_text(), text_color=DANGER if not mic else TEXT
        )
        if not cam:
            self.last_img = None
            w, h = self.target_box()
            self.show_avatar(w, h)

    def target_box(self):
        w = max(160, self.winfo_width() - 12)
        h = max(120, self.winfo_height() - 12)
        if w / h > 4 / 3:
            w = int(h * 4 / 3)
        else:
            h = int(w * 3 / 4)
        return max(120, w), max(90, h)

    def show_avatar(self, w, h):
        key = (w, h, self.name)
        if key not in self.avatar_cache:
            img = Image.new("RGB", (w, h), (33, 29, 46))
            draw = ImageDraw.Draw(img)
            r = min(w, h) // 4
            cx, cy = w // 2, h // 2
            draw.ellipse(
                (cx - r, cy - r, cx + r, cy + r), fill=(44, 39, 64)
            )
            initial = (self.name[:1] or "?").upper()
            font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), initial, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                (cx - tw // 2, cy - th // 2),
                initial,
                fill=(236, 233, 247),
                font=font,
            )
            self.avatar_cache[key] = ctk.CTkImage(
                light_image=img, dark_image=img, size=(w, h)
            )
        self.img_label.configure(image=self.avatar_cache[key])

    def update_frame(self, pil_img):
        if not self.cam:
            return
        self.last_img = pil_img
        w, h = self.target_box()
        resized = pil_img.resize((w, h), Image.Resampling.BILINEAR)
        cimg = ctk.CTkImage(light_image=resized, dark_image=resized, size=(w, h))
        self.img_label.configure(image=cimg)
        self.img_label.image = cimg


class HomeScreen(ctk.CTkFrame):
    def __init__(self, master, on_create, on_join):
        super().__init__(master, fg_color=BG)
        self.on_create = on_create
        self.on_join = on_join
        box = ctk.CTkFrame(self, fg_color="transparent")
        box.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(
            box,
            text="MeetLite",
            text_color=TEXT,
            font=ctk.CTkFont(size=34, weight="bold"),
        ).pack(pady=(0, 4))
        ctk.CTkLabel(
            box,
            text="Video meetings with a code and a PIN.",
            text_color=MUTED,
            font=ctk.CTkFont(size=14),
        ).pack(pady=(0, 22))
        top = ctk.CTkFrame(box, fg_color=SURFACE, corner_radius=14)
        top.pack(fill="x", pady=(0, 16), ipadx=16, ipady=12)
        top.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(top, text="Your name", text_color=MUTED).grid(
            row=0, column=0, sticky="w", padx=14, pady=(8, 2)
        )
        ctk.CTkLabel(top, text="Server address", text_color=MUTED).grid(
            row=0, column=1, sticky="w", padx=14, pady=(8, 2)
        )
        self.name_entry = ctk.CTkEntry(
            top, width=240, height=38, fg_color=RAISED, text_color=TEXT
        )
        self.name_entry.insert(0, "Alex")
        self.name_entry.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        self.host_entry = ctk.CTkEntry(
            top, width=240, height=38, fg_color=RAISED, text_color=TEXT
        )
        self.host_entry.insert(0, "127.0.0.1")
        self.host_entry.grid(row=1, column=1, padx=14, pady=(0, 10), sticky="ew")
        cards = ctk.CTkFrame(box, fg_color="transparent")
        cards.pack(fill="x")
        cards.grid_columnconfigure((0, 1), weight=1)
        left = ctk.CTkFrame(cards, fg_color=SURFACE, corner_radius=16)
        left.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        ctk.CTkLabel(
            left,
            text="Start a meeting",
            text_color=TEXT,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(20, 8))
        ctk.CTkLabel(
            left,
            text="Create a fresh room and share\nthe 6-character code and PIN.",
            text_color=MUTED,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 36))
        self.create_btn = ctk.CTkButton(
            left,
            text="Create meeting",
            fg_color=ACCENT,
            hover_color="#6756EB",
            text_color=TEXT,
            height=42,
            corner_radius=12,
            command=self.submit_create,
        )
        self.create_btn.pack(fill="x", padx=20, pady=(0, 20))
        right = ctk.CTkFrame(cards, fg_color=SURFACE, corner_radius=16)
        right.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        ctk.CTkLabel(
            right,
            text="Join a meeting",
            text_color=TEXT,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(20, 12))
        self.code_var = ctk.StringVar()
        self.code_var.trace_add("write", self.clean_code)
        self.code_entry = ctk.CTkEntry(
            right,
            textvariable=self.code_var,
            placeholder_text="6-character code",
            height=38,
            fg_color=RAISED,
            text_color=TEXT,
        )
        self.code_entry.pack(fill="x", padx=20, pady=(0, 10))
        self.pin_var = ctk.StringVar()
        self.pin_var.trace_add("write", self.clean_pin)
        self.pin_entry = ctk.CTkEntry(
            right,
            textvariable=self.pin_var,
            placeholder_text="4-digit PIN",
            show="*",
            height=38,
            fg_color=RAISED,
            text_color=TEXT,
        )
        self.pin_entry.pack(fill="x", padx=20, pady=(0, 14))
        self.join_btn = ctk.CTkButton(
            right,
            text="Join",
            fg_color=ACCENT,
            hover_color="#6756EB",
            text_color=TEXT,
            height=42,
            corner_radius=12,
            command=self.submit_join,
        )
        self.join_btn.pack(fill="x", padx=20, pady=(0, 20))
        self.status_lbl = ctk.CTkLabel(
            box, text="", text_color=DANGER, font=ctk.CTkFont(size=13)
        )
        self.status_lbl.pack(pady=(16, 0))

    def clean_code(self, *_):
        v = self.code_var.get().upper()[:6]
        if v != self.code_var.get():
            self.code_var.set(v)

    def clean_pin(self, *_):
        v = "".join(ch for ch in self.pin_var.get() if ch.isdigit())[:4]
        if v != self.pin_var.get():
            self.pin_var.set(v)

    def set_busy(self, busy, message="", is_error=False):
        state = "disabled" if busy else "normal"
        self.create_btn.configure(state=state)
        self.join_btn.configure(state=state)
        self.status_lbl.configure(
            text=message, text_color=DANGER if is_error else MUTED
        )

    def submit_create(self):
        name = self.name_entry.get().strip() or "Guest"
        host = self.host_entry.get().strip() or "127.0.0.1"
        self.on_create(host, name)

    def submit_join(self):
        name = self.name_entry.get().strip() or "Guest"
        host = self.host_entry.get().strip() or "127.0.0.1"
        code = self.code_var.get().strip().upper()
        pin = self.pin_var.get().strip()
        if len(code) != 6 or len(pin) != 4:
            self.set_busy(False, "Enter a 6-character code and 4-digit PIN", True)
            return
        self.on_join(host, name, code, pin)


class MeetingScreen(ctk.CTkFrame):
    def __init__(self, master, on_leave):
        super().__init__(master, fg_color=BG)
        self.on_leave = on_leave
        self.net = None
        self.host = ""
        self.tiles = {}
        self.last_tx = 0
        self.last_rx = 0
        self.last_stat_t = time.time()
        top = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14, height=54)
        top.pack(fill="x", padx=18, pady=(16, 10))
        self.info_lbl = ctk.CTkLabel(
            top,
            text="",
            text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.info_lbl.pack(side="left", padx=16, pady=12)
        self.copy_btn = ctk.CTkButton(
            top,
            text="Copy invite",
            fg_color=RAISED,
            hover_color=ACCENT,
            text_color=TEXT,
            width=110,
            height=32,
            corner_radius=10,
            command=self.copy_invite,
        )
        self.copy_btn.pack(side="left", padx=6, pady=12)
        self.stats_lbl = ctk.CTkLabel(
            top,
            text="Ping 0 ms · Up 0 kbps · Down 0 kbps",
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        )
        self.stats_lbl.pack(side="right", padx=16, pady=12)
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True, padx=18, pady=4)
        bar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=16)
        bar.pack(pady=(8, 18), padx=18)
        self.mic_btn = ctk.CTkButton(
            bar,
            text="Mute",
            fg_color=RAISED,
            hover_color=ACCENT,
            text_color=TEXT,
            width=120,
            height=40,
            corner_radius=12,
            command=self.toggle_mic,
        )
        self.mic_btn.pack(side="left", padx=10, pady=10)
        self.cam_btn = ctk.CTkButton(
            bar,
            text="Stop video",
            fg_color=RAISED,
            hover_color=ACCENT,
            text_color=TEXT,
            width=120,
            height=40,
            corner_radius=12,
            command=self.toggle_cam,
        )
        self.cam_btn.pack(side="left", padx=10, pady=10)
        self.leave_btn = ctk.CTkButton(
            bar,
            text="Leave",
            fg_color=DANGER,
            hover_color="#D94857",
            text_color=TEXT,
            width=110,
            height=40,
            corner_radius=12,
            command=lambda: self.on_leave(None),
        )
        self.leave_btn.pack(side="left", padx=10, pady=10)

    def attach(self, net, host, joined_info):
        self.net = net
        self.host = host
        for t in self.tiles.values():
            t.destroy()
        self.tiles.clear()
        self.info_lbl.configure(text=f"Code: {net.code}   ·   PIN: {net.pin}")
        self.mic_btn.configure(text="Mute", fg_color=RAISED)
        self.cam_btn.configure(text="Stop video", fg_color=RAISED)
        self.add_tile(net.id, "You", True, True, True)
        for p in joined_info.get("peers", []):
            self.add_tile(p["id"], p["name"], False, p["mic"], p["cam"])
        self.last_tx = net.tx
        self.last_rx = net.rx
        self.last_stat_t = time.time()
        self.poll_events()
        self.refresh_stats()

    def add_tile(self, pid, name, is_self, mic, cam):
        if pid in self.tiles:
            return
        tile = VideoTile(self.grid_frame, name, is_self=is_self)
        tile.set_state(mic, cam)
        self.tiles[pid] = tile
        self.relayout()

    def remove_tile(self, pid):
        tile = self.tiles.pop(pid, None)
        if tile:
            tile.destroy()
            self.relayout()

    def relayout(self):
        for w in self.grid_frame.winfo_children():
            w.grid_forget()
        n = len(self.tiles)
        cols = 1 if n <= 1 else (2 if n <= 4 else 3)
        rows = max(1, (n + cols - 1) // cols)
        for r in range(3):
            self.grid_frame.grid_rowconfigure(r, weight=1 if r < rows else 0)
        for c in range(3):
            self.grid_frame.grid_columnconfigure(c, weight=1 if c < cols else 0)
        for idx, tile in enumerate(self.tiles.values()):
            r, c = divmod(idx, cols)
            tile.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)

    def copy_invite(self):
        if not self.net:
            return
        text = f"Server: {self.host} | Code: {self.net.code} | PIN: {self.net.pin}"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.copy_btn.configure(text="Copied")
        self.after(1500, lambda: self.copy_btn.configure(text="Copy invite"))

    def toggle_mic(self):
        if not self.net:
            return
        self.net.set_mic(not self.net.mic_on)
        on = self.net.mic_on
        self.mic_btn.configure(
            text="Mute" if on else "Unmute", fg_color=RAISED if on else DANGER
        )
        if self.net.id in self.tiles:
            self.tiles[self.net.id].set_state(on, self.net.cam_on)

    def toggle_cam(self):
        if not self.net:
            return
        self.net.set_cam(not self.net.cam_on)
        on = self.net.cam_on
        self.cam_btn.configure(
            text="Stop video" if on else "Start video",
            fg_color=RAISED if on else DANGER,
        )
        if self.net.id in self.tiles:
            self.tiles[self.net.id].set_state(self.net.mic_on, on)

    def poll_events(self):
        if not self.net or not self.net.running:
            return
        while True:
            try:
                ev = self.net.events.get_nowait()
            except Exception:
                break
            kind = ev[0]
            if kind == "peer_joined":
                _, pid, name, mic, cam = ev
                self.add_tile(pid, name, False, mic, cam)
            elif kind == "peer_left":
                self.remove_tile(ev[1])
            elif kind == "peer_state":
                _, pid, mic, cam = ev
                if pid in self.tiles:
                    self.tiles[pid].set_state(mic, cam)
            elif kind == "video":
                _, pid, img = ev
                if pid in self.tiles:
                    self.tiles[pid].update_frame(img)
            elif kind == "local_video":
                if self.net.id in self.tiles:
                    self.tiles[self.net.id].update_frame(ev[1])
            elif kind == "closed":
                self.on_leave(ev[1])
                return
        self.after(30, self.poll_events)

    def refresh_stats(self):
        if not self.net or not self.net.running:
            return
        now = time.time()
        dt = max(0.2, now - self.last_stat_t)
        up = int(((self.net.tx - self.last_tx) * 8) / (dt * 1000))
        down = int(((self.net.rx - self.last_rx) * 8) / (dt * 1000))
        self.last_tx = self.net.tx
        self.last_rx = self.net.rx
        self.last_stat_t = now
        self.stats_lbl.configure(
            text=f"Ping {self.net.rtt} ms · Up {up} kbps · Down {down} kbps"
        )
        self.after(1000, self.refresh_stats)