"""
tobi_core.py - Tobi's brain for the phone app.
Memory (SQLite) + API key storage + providers (Groq, Claude) + router.
No Kivy in here, so it can also be tested on a laptop.
"""

import json
import os
import sqlite3
import time

import requests

# ---------- 1. STORAGE LOCATION ----------
# main.py calls set_data_dir(app.user_data_dir) when the app starts.
# On Android that is a private folder the app is always allowed to write to.
DATA_DIR = "."


def set_data_dir(path):
    global DATA_DIR
    DATA_DIR = path
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db()


def _db_path():
    return os.path.join(DATA_DIR, "tobi_memory.db")


def _keys_path():
    return os.path.join(DATA_DIR, "keys.json")


# ---------- 2. API KEYS ----------
# One file, one place to save, one place to read. This is what prevents
# the "no api key found" problem: saving and loading use the same code.
def load_keys():
    try:
        with open(_keys_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_key(provider, key):
    keys = load_keys()
    keys[provider] = key.strip()  # strip() removes stray spaces/newlines from pasting
    with open(_keys_path(), "w", encoding="utf-8") as f:
        json.dump(keys, f)


def get_key(provider):
    return load_keys().get(provider, "").strip()


def has_key(provider):
    return bool(get_key(provider))


# ---------- 3. PROVIDERS AND MODELS ----------
# To add a provider later: add an entry here and a call_<name> function below.
PROVIDERS = {
    "groq": {
        "label": "Groq",
        "models": [
            ("GPT-OSS 20B (fast)", "openai/gpt-oss-20b"),
            ("GPT-OSS 120B (deep)", "openai/gpt-oss-120b"),
        ],
        "fast": "openai/gpt-oss-20b",
        "deep": "openai/gpt-oss-120b",
    },
    "gemini": {
        "label": "Gemini",
        "models": [
            ("2.5 Flash-Lite (fast)", "gemini-2.5-flash-lite"),
            ("2.5 Flash (deep)", "gemini-2.5-flash"),
        ],
        "fast": "gemini-2.5-flash-lite",
        "deep": "gemini-2.5-flash",
    },
    "claude": {
        "label": "Claude",
        "models": [
            ("Haiku 5.5 (fast)", "claude-haiku-5-5"),
            ("Sonnet 5.5 (deep)", "claude-sonnet-5-5"),
        ],
        "fast": "claude-haiku-5-5",
        "deep": "claude-sonnet-5-5",
    },
}

SYSTEM_PROMPTS = {
    "chat": "You are Tobi, a friendly JARVIS-style assistant. Be natural and helpful.",
    "robot": (
        "You are Tobi's robot controller. Reply with ONE short line. "
        "If the user wants movement, answer in the form: CMD:<F|B|L|R|S>"
    ),
    "helper": "You are Tobi in helper mode. Briefly say which action you would take.",
}


class NoKeyError(Exception):
    """Raised when no provider has an API key saved yet."""


# ---------- 4. MEMORY ----------
def init_db():
    with sqlite3.connect(_db_path()) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                task_mode TEXT,
                model TEXT
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                fact TEXT NOT NULL
            )"""
        )


def save_message(role, content, task_mode, model):
    with sqlite3.connect(_db_path()) as db:
        db.execute(
            "INSERT INTO messages (ts, role, content, task_mode, model) VALUES (?, ?, ?, ?, ?)",
            (time.time(), role, content, task_mode, model),
        )


def get_recent(n=10):
    with sqlite3.connect(_db_path()) as db:
        rows = db.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    rows.reverse()
    return [{"role": r, "content": c} for r, c in rows]


def save_fact(fact):
    with sqlite3.connect(_db_path()) as db:
        # Skip duplicates so /remember twice doesn't store it twice.
        exists = db.execute("SELECT 1 FROM facts WHERE fact = ?", (fact,)).fetchone()
        if not exists:
            db.execute("INSERT INTO facts (ts, fact) VALUES (?, ?)", (time.time(), fact))


def get_facts():
    with sqlite3.connect(_db_path()) as db:
        rows = db.execute("SELECT fact FROM facts ORDER BY id").fetchall()
    return [r[0] for r in rows]


def search_old(user_message, skip_recent=10, limit=4):
    """Older user messages that share keywords with the new message."""
    words = [w.strip("?.,!").lower() for w in user_message.split()]
    words = [w for w in words if len(w) > 3]
    if not words:
        return []

    with sqlite3.connect(_db_path()) as db:
        cutoff = db.execute(
            "SELECT id FROM messages ORDER BY id DESC LIMIT 1 OFFSET ?",
            (skip_recent - 1,),
        ).fetchone()
        cutoff_id = cutoff[0] if cutoff else 0
        rows = db.execute(
            "SELECT content FROM messages WHERE id < ? AND role = 'user'", (cutoff_id,)
        ).fetchall()

    scored = []
    for (content,) in rows:
        score = sum(1 for w in words if w in content.lower())
        if score > 0:
            scored.append((score, content))
    scored.sort(reverse=True)
    return [c for _, c in scored[:limit]]


def build_messages(user_message, task_mode):
    """System prompt + facts + relevant old messages + recent history + new message."""
    system = SYSTEM_PROMPTS[task_mode]

    facts = get_facts()
    if facts:
        system += "\n\nThings you know about the user:\n- " + "\n- ".join(facts)

    old = search_old(user_message)
    if old:
        system += "\n\nPossibly relevant things the user said earlier:\n- " + "\n- ".join(old)

    messages = [{"role": "system", "content": system}]
    messages += get_recent(10)
    messages.append({"role": "user", "content": user_message})
    return messages


# ---------- 5. PROVIDER CALLS ----------
def call_groq(key, model, messages):
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": messages},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"].strip()


def call_gemini(key, model, messages):
    # Gemini offers an OpenAI-compatible endpoint, so it looks just like Groq.
    resp = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": messages},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"].strip()


def _claude_format(messages):
    """Claude wants the system prompt separate, and alternating user/assistant turns."""
    system = ""
    turns = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        elif turns and turns[-1]["role"] == m["role"]:
            turns[-1]["content"] += "\n" + m["content"]  # merge same-role neighbours
        else:
            turns.append({"role": m["role"], "content": m["content"]})
    while turns and turns[0]["role"] != "user":
        turns.pop(0)  # must start with a user message
    return system, turns


def call_claude(key, model, messages):
    system, turns = _claude_format(messages)
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": model, "max_tokens": 1024, "system": system, "messages": turns},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Claude {resp.status_code}: {resp.text[:300]}")
    return resp.json()["content"][0]["text"].strip()


CALLERS = {"groq": call_groq, "gemini": call_gemini, "claude": call_claude}


# ---------- 6. ROUTER ----------
def candidates(choice):
    """Ordered list of (provider, model) to try. Only providers with a saved key."""
    order = []
    if choice["kind"] == "model":
        order.append((choice["provider"], choice["model"]))
        speed = "fast"
    else:
        speed = choice["speed"]
    for pid, p in PROVIDERS.items():
        pair = (pid, p[speed])
        if pair not in order:
            order.append(pair)
    return [(pid, m) for pid, m in order if has_key(pid)]


def get_reply(user_message, task_mode, choice):
    """Returns (reply_text, model_used). Tries the choice first, then other providers."""
    tries = candidates(choice)
    if not tries:
        raise NoKeyError("No API key saved yet. Open the Keys box and add one.")

    messages = build_messages(user_message, task_mode)
    last_error = None
    for pid, model in tries:
        try:
            reply = CALLERS[pid](get_key(pid), model, messages)
            save_message("user", user_message, task_mode, "user")
            save_message("assistant", reply, task_mode, model)
            return reply, model
        except Exception as e:  # network down, bad key, rate limit...
            last_error = e
    raise RuntimeError(str(last_error))
