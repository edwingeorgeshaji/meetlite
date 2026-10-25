import queue
import threading
import customtkinter as ctk
import net
import ui


class MeetLiteApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("MeetLite")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.configure(fg_color=ui.BG)
        self.client = None
        self.connect_q = queue.Queue()
        self.home = ui.HomeScreen(self, self.start_create, self.start_join)
        self.meeting = ui.MeetingScreen(self, self.leave_meeting)
        self.home.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(50, self.poll_connect)

    def start_create(self, host, name):
        self.home.set_busy(True, "Connecting…", False)
        threading.Thread(
            target=self.connect_worker,
            args=(host, name, None, None),
            daemon=True,
        ).start()

    def start_join(self, host, name, code, pin):
        self.home.set_busy(True, "Connecting…", False)
        threading.Thread(
            target=self.connect_worker,
            args=(host, name, code, pin),
            daemon=True,
        ).start()

    def connect_worker(self, host, name, code, pin):
        client = net.Net()
        try:
            reply = client.connect(host, name, code, pin)
            self.connect_q.put(("ok", client, host, reply))
        except RuntimeError as exc:
            client.close()
            self.connect_q.put(("err", str(exc)))
        except Exception:
            client.close()
            self.connect_q.put(("err", f"Cannot reach server at {host}"))

    def poll_connect(self):
        try:
            item = self.connect_q.get_nowait()
        except queue.Empty:
            self.after(50, self.poll_connect)
            return
        if item[0] == "ok":
            _, client, host, reply = item
            self.client = client
            self.home.set_busy(False, "", False)
            self.home.pack_forget()
            self.meeting.pack(fill="both", expand=True)
            self.client.start_media()
            self.meeting.attach(self.client, host, reply)
        else:
            self.home.set_busy(False, item[1], True)
        self.after(50, self.poll_connect)

    def leave_meeting(self, reason=None):
        if self.client:
            self.client.close()
            self.client = None
        self.meeting.pack_forget()
        self.home.pack(fill="both", expand=True)
        if reason:
            self.home.set_busy(False, reason, True)
        else:
            self.home.set_busy(False, "", False)

    def on_close(self):
        if self.client:
            self.client.close()
            self.client = None
        self.destroy()


if __name__ == "__main__":
    app = MeetLiteApp()
    app.mainloop()