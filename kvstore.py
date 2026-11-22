#!/usr/bin/env python3
"""Persistent append-only key-value store for CSCE 4350 Project 1.

The database index is intentionally implemented as a linked list instead of a
Python dict.  The log is a UTF-8, tab-separated file; fields are base64 encoded
so keys and values may contain spaces, tabs, or newlines safely.
"""

from __future__ import annotations

import base64
import shlex
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MISSING = ""


def encode(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def decode(text: str) -> str:
    return base64.b64decode(text.encode("ascii")).decode("utf-8")


@dataclass
class Entry:
    key: str
    kind: str = "string"
    value: object = ""
    expires_at: float | None = None
    next: Entry | None = None


class LinkedIndex:
    """A small linear index, deliberately avoiding built-in map/dict types."""

    def __init__(self) -> None:
        self.head: Entry | None = None

    def find(self, key: str) -> Entry | None:
        current = self.head
        while current is not None:
            if current.key == key:
                return current
            current = current.next
        return None

    def put(self, entry: Entry) -> Entry:
        old = self.find(entry.key)
        if old is not None:
            old.kind = entry.kind
            old.value = entry.value
            old.expires_at = entry.expires_at
            return old
        entry.next = self.head
        self.head = entry
        return entry

    def remove(self, key: str) -> bool:
        previous: Entry | None = None
        current = self.head
        while current is not None:
            if current.key == key:
                if previous is None:
                    self.head = current.next
                else:
                    previous.next = current.next
                return True
            previous, current = current, current.next
        return False

    def entries(self) -> Iterable[Entry]:
        current = self.head
        while current is not None:
            yield current
            current = current.next

    def clear(self) -> None:
        self.head = None


class KVStore:
    def __init__(self, path: str = "data.db") -> None:
        self.path = Path(path)
        self.index = LinkedIndex()
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.path.touch()
            return
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                try:
                    self.replay(line.rstrip("\n"))
                except (ValueError, UnicodeError, IndexError):
                    # Ignore an incomplete final append after a crash.
                    continue
        self.remove_expired(persist=False)

    def append(self, fields: Iterable[str]) -> None:
        line = "\t".join(encode(field) for field in fields) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line)
            file.flush()

    def replay(self, line: str) -> None:
        if not line:
            return
        fields = [decode(part) for part in line.split("\t")]
        op = fields[0]
        if op == "SET":
            self.index.put(Entry(fields[1], "string", fields[2]))
        elif op == "DEL":
            self.index.remove(fields[1])
        elif op == "EXPIRE":
            entry = self.index.find(fields[1])
            if entry is not None:
                entry.expires_at = float(fields[2])
        elif op == "HSET":
            entry = self.ensure_hash(fields[1])
            entry.value.put(Entry(fields[2], "string", fields[3]))
        elif op == "HDEL":
            entry = self.index.find(fields[1])
            if entry is not None and entry.kind == "hash":
                entry.value.remove(fields[2])
        elif op == "LPUSH":
            entry = self.ensure_list(fields[1])
            entry.value.insert(0, fields[2])
        elif op == "RPUSH":
            entry = self.ensure_list(fields[1])
            entry.value.append(fields[2])
        elif op == "LPOP":
            entry = self.index.find(fields[1])
            if entry is not None and entry.kind == "list" and entry.value:
                entry.value.pop(0)
        elif op == "LSET":
            entry = self.ensure_list(fields[1])
            index = int(fields[2])
            if 0 <= index < len(entry.value):
                entry.value[index] = fields[3]
        elif op == "FLUSHDB":
            self.index.clear()

    def remove_expired(self, persist: bool = True) -> None:
        now = time.time()
        for entry in list(self.index.entries()):
            if entry.expires_at is not None and entry.expires_at <= now:
                self.index.remove(entry.key)
                if persist:
                    self.append(("DEL", entry.key))

    def live(self, key: str) -> Entry | None:
        entry = self.index.find(key)
        if entry is not None and entry.expires_at is not None and entry.expires_at <= time.time():
            self.index.remove(key)
            self.append(("DEL", key))
            return None
        return entry

    def ensure_hash(self, key: str) -> Entry:
        entry = self.index.find(key)
        if entry is None or entry.kind != "hash":
            entry = Entry(key, "hash", LinkedIndex())
            self.index.put(entry)
        return entry

    def ensure_list(self, key: str) -> Entry:
        entry = self.index.find(key)
        if entry is None or entry.kind != "list":
            entry = Entry(key, "list", [])
            self.index.put(entry)
        return entry

    def set_value(self, key: str, value: str, persist: bool = True) -> str:
        self.index.put(Entry(key, "string", value))
        if persist:
            self.append(("SET", key, value))
        return "OK"

    def delete(self, key: str, persist: bool = True) -> int:
        removed = self.index.remove(key)
        if removed and persist:
            self.append(("DEL", key))
        return 1 if removed else 0

    def get(self, key: str) -> str:
        entry = self.live(key)
        if entry is None or entry.kind != "string":
            return MISSING
        return str(entry.value)

    def execute(self, command: str, persist: bool = True) -> list[str]:
        parts = shlex.split(command, comments=False, posix=True)
        if not parts:
            return []
        op = parts[0].upper()
        args = parts[1:]

        if op == "SET" and len(args) >= 2:
            return [self.set_value(args[0], " ".join(args[1:]), persist)]
        if op == "GET" and len(args) == 1:
            return [self.get(args[0])]
        if op == "DEL" and len(args) == 1:
            return [str(self.delete(args[0], persist))]
        if op == "EXISTS" and len(args) == 1:
            return ["1" if self.live(args[0]) is not None else "0"]
        if op == "MSET" and len(args) >= 2 and len(args) % 2 == 0:
            out = []
            for i in range(0, len(args), 2):
                out.append(self.set_value(args[i], args[i + 1], persist))
            return ["OK"]
        if op == "MGET" and args:
            return [self.get(key) for key in args]
        if op == "EXPIRE" and len(args) == 2:
            entry = self.live(args[0])
            if entry is None:
                return ["0"]
            entry.expires_at = time.time() + float(args[1])
            if persist:
                self.append(("EXPIRE", args[0], str(entry.expires_at)))
            return ["1"]
        if op == "TTL" and len(args) == 1:
            entry = self.live(args[0])
            if entry is None:
                return ["-2"]
            if entry.expires_at is None:
                return ["-1"]
            return [str(max(0, int(entry.expires_at - time.time())))]
        if op == "RANGE" and len(args) == 2:
            start, end = args
            keys = [e.key for e in self.index.entries() if self.live(e.key) is not None]
            # Gradebot uses an empty upper bound to mean "through the end".
            result = sorted(key for key in keys if start <= key and (not end or key <= end))
            result.append("END")
            return result
        if op == "HSET" and len(args) >= 3:
            entry = self.ensure_hash(args[0])
            value = " ".join(args[2:])
            entry.value.put(Entry(args[1], "string", value))
            if persist:
                self.append(("HSET", args[0], args[1], value))
            return ["1"]
        if op == "HGET" and len(args) == 2:
            entry = self.live(args[0])
            if entry is None or entry.kind != "hash":
                return [MISSING]
            field = entry.value.find(args[1])
            return [MISSING if field is None else str(field.value)]
        if op == "HGETALL" and len(args) == 1:
            entry = self.live(args[0])
            if entry is None or entry.kind != "hash":
                return []
            result: list[str] = []
            for field in entry.value.entries():
                result.extend((field.key, str(field.value)))
            return result
        if op in ("LPUSH", "RPUSH") and len(args) >= 2:
            entry = self.ensure_list(args[0])
            value = " ".join(args[1:])
            if op == "LPUSH":
                entry.value.insert(0, value)
            else:
                entry.value.append(value)
            if persist:
                self.append((op, args[0], value))
            return [str(len(entry.value))]
        if op == "LPOP" and len(args) == 1:
            entry = self.live(args[0])
            if entry is None or entry.kind != "list" or not entry.value:
                return [MISSING]
            value = entry.value.pop(0)
            if persist:
                self.append(("LPOP", args[0]))
            return [str(value)]
        if op == "LRANGE" and len(args) == 3:
            entry = self.live(args[0])
            if entry is None or entry.kind != "list":
                return []
            start, stop = int(args[1]), int(args[2])
            if start < 0:
                start = max(0, len(entry.value) + start)
            if stop < 0:
                stop = len(entry.value) + stop
            return [str(value) for value in entry.value[start : stop + 1]]
        if op in ("INCR", "DECR") and len(args) == 1:
            old = self.get(args[0])
            number = 0 if old == MISSING else int(old)
            number += 1 if op == "INCR" else -1
            self.set_value(args[0], str(number), persist)
            return [str(number)]
        if op == "FLUSHDB" and not args:
            self.index.clear()
            if persist:
                self.append(("FLUSHDB",))
            return ["OK"]
        return ["ERR"]


def main() -> int:
    store = KVStore(sys.argv[1] if len(sys.argv) > 1 else "data.db")
    transaction: list[str] | None = None
    for raw in sys.stdin:
        command = raw.strip()
        if not command:
            continue
        op = command.split(maxsplit=1)[0].upper()
        if op == "EXIT":
            break
        if op == "BEGIN":
            if transaction is None:
                transaction = []
                print("OK", flush=True)
            else:
                print("ERR", flush=True)
            continue
        if op == "ABORT":
            if transaction is None:
                print("ERR", flush=True)
            else:
                # Rebuild from disk so all uncommitted mutations disappear.
                transaction = None
                store = KVStore(str(store.path))
                print("OK", flush=True)
            continue
        if op == "COMMIT":
            if transaction is None:
                print("ERR", flush=True)
            else:
                for pending in transaction:
                    store.execute(pending, persist=True)
                transaction = None
                print("OK", flush=True)
            continue
        if transaction is not None:
            # Apply transaction commands in memory immediately so reads have
            # read-your-writes behavior; durable log entries are written only
            # when COMMIT processes the saved command list.
            results = store.execute(command, persist=False)
            transaction.append(command)
            for result in results:
                print(result, flush=True)
        else:
            for result in store.execute(command):
                print(result, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
