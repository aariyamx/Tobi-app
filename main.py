"""
main.py - Tobi phone app (Kivy). Buildozer looks for a file with exactly this name.
Layout: three small expandable boxes (Mode, Model, Keys) on top, chat below.
"""

import threading

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import tobi_core as core

Window.softinput_mode = "below_target"  # keyboard pushes the input up, not over it
ROW = dp(44)
GAP = dp(4)


# ---------- EXPANDABLE BOX ----------
class ExpandableBox(BoxLayout):
    """A header button. Tap it and the body slides open to show its rows."""

    def __init__(self, title, value="", **kw):
        super().__init__(orientation="vertical", size_hint_y=None, **kw)
        self.title = title
        self.value = value
        self.is_open = False

        self.header = Button(size_hint_y=None, height=ROW, font_size=sp(15))
        self.header.bind(on_release=lambda *_: self.toggle())
        self.body = BoxLayout(
            orientation="vertical", size_hint_y=None, height=0, opacity=0, spacing=GAP
        )
        self.add_widget(self.header)
        # The body is only attached while the box is open (see toggle). A collapsed
        # body has height 0 but its children still overflow and would invisibly
        # cover the headers, swallowing every tap.

        # The box's own height always equals header + body, so the layout
        # around it moves smoothly while the body animates.
        self.bind(minimum_height=self.setter("height"))
        self.refresh()

    def refresh(self):
        arrow = "v" if self.is_open else ">"
        self.header.text = f"{arrow}  {self.title}: {self.value}"

    def set_value(self, value):
        self.value = value
        self.refresh()

    def add_row(self, widget):
        self.body.add_widget(widget)

    def toggle(self):
        self.is_open = not self.is_open
        Animation.cancel_all(self.body)
        if self.is_open:
            n = len(self.body.children)
            target = n * ROW + max(0, n - 1) * GAP
            if self.body.parent is None:
                self.add_widget(self.body)
            Animation(height=target, opacity=1, d=0.2).start(self.body)
        else:
            anim = Animation(height=0, opacity=0, d=0.2)
            anim.bind(on_complete=lambda *_: self._detach_body())
            anim.start(self.body)
        self.refresh()

    def _detach_body(self):
        # Only detach if the user didn't re-open the box in the meantime.
        if not self.is_open and self.body.parent is not None:
            self.remove_widget(self.body)

    def close(self):
        if self.is_open:
            self.toggle()


def option_button(text, on_pick):
    b = Button(text=text, size_hint_y=None, height=ROW, font_size=sp(14),
               background_color=(0.25, 0.25, 0.3, 1))
    b.bind(on_release=lambda *_: on_pick())
    return b


# ---------- THE APP ----------
class TobiApp(App):
    def build(self):
        core.set_data_dir(self.user_data_dir)  # private storage folder on the phone

        self.task_mode = "chat"
        self.choice = {"kind": "auto", "speed": "fast"}
        self.busy = False

        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))
        root.add_widget(self.build_boxes())
        root.add_widget(self.build_chat())
        root.add_widget(self.build_input_row())

        self.say("Tobi: Hi! Open the Keys box and add an API key to begin.")
        return root

    # ----- the three boxes -----
    def build_boxes(self):
        holder = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
        holder.bind(minimum_height=holder.setter("height"))

        # Mode box
        self.mode_box = ExpandableBox("Mode", self.task_mode)
        for m in core.SYSTEM_PROMPTS:
            self.mode_box.add_row(option_button(m, lambda m=m: self.pick_mode(m)))

        # Model box: two Auto options, then every model of every provider
        self.model_box = ExpandableBox("Model", "Auto - Fast")
        options = [
            ("Auto - Fast", {"kind": "auto", "speed": "fast"}),
            ("Auto - Deep", {"kind": "auto", "speed": "deep"}),
        ]
        for pid, p in core.PROVIDERS.items():
            for label, model_id in p["models"]:
                options.append(
                    (f"{p['label']}: {label}",
                     {"kind": "model", "provider": pid, "model": model_id})
                )
        for label, choice in options:
            self.model_box.add_row(
                option_button(label, lambda l=label, c=choice: self.pick_model(l, c))
            )

        # Keys box: one input + Save button per provider
        self.keys_box = ExpandableBox("Keys", self.keys_summary())
        for pid, p in core.PROVIDERS.items():
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=ROW, spacing=GAP)
            ti = TextInput(hint_text=self.key_hint(pid), password=True, multiline=False,
                           font_size=sp(14))
            save = Button(text="Save", size_hint_x=None, width=dp(70))
            save.bind(on_release=lambda *_, pid=pid, ti=ti: self.save_key(pid, ti))
            row.add_widget(ti)
            row.add_widget(save)
            self.keys_box.add_row(row)

        for box in (self.mode_box, self.model_box, self.keys_box):
            holder.add_widget(box)
        return holder

    def key_hint(self, pid):
        label = core.PROVIDERS[pid]["label"]
        return f"{label} key (saved)" if core.has_key(pid) else f"Paste {label} key"

    def keys_summary(self):
        saved = sum(1 for pid in core.PROVIDERS if core.has_key(pid))
        return f"{saved}/{len(core.PROVIDERS)} saved"

    # ----- chat area -----
    def build_chat(self):
        self.scroll = ScrollView()
        self.log = Label(text="", size_hint_y=None, halign="left", valign="top",
                         font_size=sp(15))
        # Wrap text to the width, and grow the label to fit the text.
        self.log.bind(width=lambda *_: setattr(self.log, "text_size", (self.log.width, None)))
        self.log.bind(texture_size=lambda *_: setattr(self.log, "height", self.log.texture_size[1]))
        self.scroll.add_widget(self.log)
        return self.scroll

    def build_input_row(self):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=ROW, spacing=GAP)
        self.input = TextInput(hint_text="Talk to Tobi...", multiline=False, font_size=sp(15))
        self.input.bind(on_text_validate=lambda *_: self.send())
        self.send_btn = Button(text="Send", size_hint_x=None, width=dp(80))
        self.send_btn.bind(on_release=lambda *_: self.send())
        row.add_widget(self.input)
        row.add_widget(self.send_btn)
        return row

    # ----- actions -----
    def pick_mode(self, mode):
        self.task_mode = mode
        self.mode_box.set_value(mode)
        self.mode_box.close()

    def pick_model(self, label, choice):
        self.choice = choice
        self.model_box.set_value(label)
        self.model_box.close()

    def save_key(self, pid, ti):
        key = ti.text.strip()
        if not key:
            return
        core.save_key(pid, key)
        ti.text = ""
        ti.hint_text = self.key_hint(pid)
        self.keys_box.set_value(self.keys_summary())
        self.say(f"System: {core.PROVIDERS[pid]['label']} key saved.")

    def say(self, text):
        self.log.text += text + "\n\n"
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.1)

    def send(self):
        text = self.input.text.strip()
        if not text or self.busy:
            return
        self.input.text = ""

        # Small built-in commands
        if text.startswith("/remember "):
            core.save_fact(text[len("/remember "):])
            self.say("System: Saved to memory.")
            return
        if text == "/facts":
            self.say("Facts:\n" + ("\n".join(core.get_facts()) or "none yet"))
            return

        self.say("You: " + text)
        self.busy = True
        self.send_btn.text = "..."
        # Network calls must NOT run on the UI thread, or the app freezes.
        threading.Thread(target=self.worker, args=(text,), daemon=True).start()

    def worker(self, text):
        try:
            reply, model = core.get_reply(text, self.task_mode, self.choice)
            msg = f"Tobi ({model}): {reply}"
        except core.NoKeyError as e:
            msg = f"System: {e}"
        except Exception as e:
            msg = f"System: Error - {e}"
        # Go back to the UI thread to touch widgets.
        Clock.schedule_once(lambda dt: self.finish(msg))

    def finish(self, msg):
        self.say(msg)
        self.busy = False
        self.send_btn.text = "Send"


if __name__ == "__main__":
    TobiApp().run()
