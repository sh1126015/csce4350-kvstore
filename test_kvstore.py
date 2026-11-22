import subprocess
import sys
import time
from pathlib import Path

from kvstore import KVStore


def test_set_get_and_overwrite(tmp_path: Path) -> None:
    db = KVStore(str(tmp_path / "data.db"))
    assert db.execute("SET name Anil") == ["OK"]
    assert db.execute("GET name") == ["Anil"]
    db.execute("SET name Shrestha")
    assert db.execute("GET name") == ["Shrestha"]


def test_persistence_delete_and_exists(tmp_path: Path) -> None:
    path = tmp_path / "data.db"
    db = KVStore(str(path))
    db.execute("SET answer 42")
    assert path.exists() and path.stat().st_size > 0
    assert KVStore(str(path)).execute("GET answer") == ["42"]
    assert db.execute("EXISTS answer") == ["1"]
    assert db.execute("DEL answer") == ["1"]
    assert db.execute("EXISTS answer") == ["0"]


def test_multi_range_and_ttl(tmp_path: Path) -> None:
    db = KVStore(str(tmp_path / "data.db"))
    db.execute("MSET apple red banana yellow carrot orange")
    assert db.execute("MGET apple missing banana") == ["red", "", "yellow"]
    assert db.execute("RANGE banana carrot") == ["banana", "carrot", "END"]
    assert db.execute("EXPIRE apple 1") == ["1"]
    assert int(db.execute("TTL apple")[0]) in (0, 1)
    time.sleep(1.1)
    assert db.execute("GET apple") == [""]


def test_transactions_hashes_lists_counters_flush(tmp_path: Path) -> None:
    path = tmp_path / "data.db"
    db = KVStore(str(path))
    assert db.execute("HSET user name Anil") == ["1"]
    assert db.execute("HGET user name") == ["Anil"]
    assert db.execute("HGETALL user") == ["name", "Anil"]
    db.execute("LPUSH colors red")
    db.execute("RPUSH colors blue")
    assert db.execute("LRANGE colors 0 -1") == ["red", "blue"]
    assert db.execute("INCR count") == ["1"]
    assert db.execute("DECR count") == ["0"]
    assert db.execute("FLUSHDB") == ["OK"]
    assert db.execute("GET count") == [""]

    program = str(Path(__file__).with_name("kvstore.py"))
    subprocess.run(
        [sys.executable, program, str(path)],
        input="BEGIN\nSET temporary value\nGET temporary\nABORT\nEXIT\n",
        text=True,
        capture_output=True,
        check=True,
    )
    assert KVStore(str(path)).execute("GET temporary") == [""]


def test_cli_restart(tmp_path: Path) -> None:
    path = tmp_path / "data.db"
    program = str(Path(__file__).with_name("kvstore.py"))
    first = subprocess.run(
        [sys.executable, program, str(path)],
        input="SET x persisted\nEXIT\n",
        text=True,
        capture_output=True,
        check=True,
    )
    assert first.stdout.strip() == "OK"
    second = subprocess.run(
        [sys.executable, program, str(path)],
        input="GET x\nEXIT\n",
        text=True,
        capture_output=True,
        check=True,
    )
    assert second.stdout.strip() == "persisted"
