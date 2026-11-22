# CSCE 4350 Project 1 — Simple Key-Value Store

**Student:** Anil Shrestha  
**EUID:** `amm0813`  
**Course:** CSCE 4350.401 — Fundamentals of Database Systems

This project implements a persistent command-line key-value database in Python.
It uses an append-only `data.db` log and replays that log at startup. The
in-memory top-level index is a custom linked list; no built-in dictionary/map is
used for database indexing.

## Run

```bash
python3 kvstore.py
```

The default database file is `data.db`. A different file can be supplied for
isolated black-box runs:

```bash
python3 kvstore.py /tmp/gradebot-data.db
```

Commands can be piped without manual input:

```bash
printf 'SET course CSCE4350\nGET course\nEXIT\n' | python3 kvstore.py
```

## Supported commands

`SET`, `GET`, `DEL`, `EXISTS`, `MSET`, `MGET`, `EXPIRE`, `TTL`, `RANGE`,
`BEGIN`, `COMMIT`, `ABORT`, `HSET`, `HGET`, `HGETALL`, `LPUSH`, `RPUSH`,
`LRANGE`, `INCR`, `DECR`, `FLUSHDB`, and `EXIT`.

Missing values print an empty response; missing-key TTL prints `-2`; a key without an
expiration prints `-1`. Values containing spaces should be quoted, for example
`SET greeting "hello world"`.

Transactions are read-your-writes: commands inside `BEGIN` are applied in
memory and reported as `QUEUED`; `COMMIT` appends them to disk, while `ABORT`
reloads the last durable state.

## Tests and lint

```bash
python3 -m pip install -r requirements-dev.txt
pytest -q
ruff check .
```

GitHub Actions runs both checks on every push and pull request.

## Final tag

After the black-box run and screenshot are complete:

```bash
git add .
git commit -m "Complete CSCE 4350 key-value store"
git tag project
```

The file `gradebot_screenshot.png` must be the actual Gradebot rubric output
with the student's identifying information visible.
