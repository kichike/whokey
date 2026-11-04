"""Синхронизация: два устройства пишут в один файл, а облако иногда мешает. Пароль нельзя потерять."""

import json
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sync  # noqa: E402
import vault as V  # noqa: E402
from vault import FileBusy, PasswordChangedElsewhere, Vault  # noqa: E402

PASSWORD = "Зелёный-Кит-Летит-2026!"


def names(vault):
    return sorted(e["site"] for e in vault.entries)


def passwords(vault):
    return {e["password"] for e in vault.entries}


class Devices(unittest.TestCase):
    """A и B — два компьютера: два открытых Vault над одним файлом (его возит облако)."""

    @classmethod
    def setUpClass(cls):
        folder = Path(tempfile.mkdtemp())
        cls.template = folder / "template.dat"
        vault = Vault.create(cls.template, PASSWORD)  # Argon2 медленный — создаём один раз
        cls.key = vault.key

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.path = self.folder / "vault.dat"
        self.path.write_bytes(self.template.read_bytes())
        self.a, self.b = self.device(), self.device()

    def device(self):
        return Vault.open_with_key(self.path, self.key)

    def test_additions_on_both_devices_are_kept(self):
        self.a.add("почта", "a", "pw-a")
        self.b.add("банк", "b", "pw-b")  # B не видел запись A
        self.assertEqual(names(self.b), ["банк", "почта"])
        self.a.sync()
        self.assertEqual(names(self.a), ["банк", "почта"])
        self.assertEqual(names(self.device()), ["банк", "почта"])

    def test_edits_of_different_entries_are_merged(self):
        self.a.add("почта", "a", "1")
        self.a.add("банк", "b", "2")
        self.b.sync()
        self.a.update(0, password="новый-а")
        self.b.update(1, password="новый-б")
        self.a.sync()
        self.assertEqual(passwords(self.a), {"новый-а", "новый-б"})
        self.assertEqual(len(self.a.entries), 2)

    def test_plain_later_edit_makes_no_conflict(self):
        self.a.add("почта", "a", "1")
        self.b.sync()
        self.a.update(0, password="2")
        self.b.sync()
        self.b.update(0, password="3")
        self.a.sync()
        self.assertEqual([e["password"] for e in self.a.entries], ["3"])

    def test_conflict_keeps_both_passwords_and_appears_once(self):
        self.a.add("почта", "a", "1")
        self.b.sync()
        self.a.update(0, password="с-устройства-а")
        self.b.update(0, password="с-устройства-б")  # независимая правка той же записи
        self.assertEqual(passwords(self.b), {"с-устройства-а", "с-устройства-б"})
        self.assertEqual(len(self.b.entries), 2)
        self.assertEqual(sum("⚠" in e["site"] for e in self.b.entries), 1)
        self.a.sync()
        self.assertEqual(passwords(self.a), passwords(self.b))
        self.assertEqual(len(self.a.entries), 2)  # копия не размножается
        self.a.update(0, note="дальше")
        self.b.sync()
        self.assertEqual(len(self.b.entries), 2)

    def test_deleted_conflict_copy_does_not_return(self):
        self.a.add("почта", "a", "1")
        self.b.sync()
        self.a.update(0, password="а")
        self.b.update(0, password="б")
        self.a.sync()
        copy = [e for e in self.a.entries if "⚠" in e["site"]][0]
        self.a.delete_id(copy["id"])
        self.b.sync()
        self.assertEqual(len(self.b.entries), 1)
        self.b.update(0, note="ещё")
        self.a.sync()
        self.assertEqual(len(self.a.entries), 1)

    def test_deletion_reaches_other_device_and_stays(self):
        self.a.add("почта", "a", "1")
        self.b.sync()
        self.a.delete(0)
        self.b.add("другое", "x", "2")  # у B запись ещё есть, и B сохраняет
        self.assertEqual(names(self.b), ["другое"])
        self.a.sync()
        self.assertEqual(names(self.a), ["другое"])
        self.assertEqual(names(self.device()), ["другое"])

    def test_edit_unseen_by_the_deleter_survives(self):
        self.a.add("почта", "a", "1")
        self.b.sync()
        self.a.delete(0)
        self.b.update(0, password="важная-правка")  # B не знал об удалении
        self.assertEqual(passwords(self.b), {"важная-правка"})
        self.a.sync()
        self.assertEqual(passwords(self.a), {"важная-правка"})

    def test_deleting_does_not_remove_an_edit_the_person_never_saw(self):
        self.a.add("почта", "a", "1")
        self.b.sync()
        self.a.update(0, password="свежая-правка")
        self.b.delete(0)  # B удаляет версию «1», о свежей правке не зная
        self.assertEqual(passwords(self.b), {"свежая-правка"})
        self.a.sync()
        self.assertEqual(passwords(self.a), {"свежая-правка"})

    def test_failed_save_changes_nothing(self):
        self.a.add("почта", "a", "1")
        self.b.add("банк", "b", "2")
        with mock.patch.object(V, "_write_file", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(V.SaveError):
                self.a.update(0, password="новый")
            with self.assertRaises(V.SaveError):
                self.a.delete(0)
        self.assertEqual(passwords(self.a), {"1"})
        self.a.sync()  # чужая запись не потеряна: файл будет прочитан снова
        self.assertEqual(passwords(self.a), {"1", "2"})

    def test_edit_of_entry_deleted_elsewhere_during_dialog_brings_it_back(self):
        self.a.add("почта", "a", "1")
        entry = dict(self.a.entries[0])
        self.b.sync()
        self.b.delete(0)
        self.a.sync()
        self.assertEqual(self.a.entries, [])
        self.a.update_id(entry["id"], base=entry, password="правка-из-окна")
        self.b.sync()
        self.assertEqual(passwords(self.b), {"правка-из-окна"})

    def test_edit_by_id_survives_reordering_in_an_open_dialog(self):
        self.a.add("первая", "a", "1")
        self.a.add("вторая", "b", "2")
        self.b.sync()
        second = self.a.entries[1]["id"]
        self.b.delete(0)  # пока на A открыто окно правки, номера записей сдвинулись
        self.a.sync()
        self.a.update_id(second, password="новый")
        self.assertEqual([(e["site"], e["password"]) for e in self.a.entries], [("вторая", "новый")])

    def test_password_changed_elsewhere_never_overwrites(self):
        self.a.add("почта", "a", "1")
        self.b.sync()
        self.a.change_password("Новый-Длинный-Пароль-2026!")
        changed = self.path.read_bytes()
        with self.assertRaises(PasswordChangedElsewhere):
            self.b.add("своё", "b", "2")
        with self.assertRaises(PasswordChangedElsewhere):
            self.b.sync()
        self.assertEqual(self.path.read_bytes(), changed)
        self.assertEqual(names(Vault.open(self.path, "Новый-Длинный-Пароль-2026!")), ["почта"])

    def test_change_password_keeps_changes_from_other_device(self):
        self.a.add("с-а", "a", "1")
        self.b.change_password("Новый-Длинный-Пароль-2026!")
        self.assertEqual(names(Vault.open(self.path, "Новый-Длинный-Пароль-2026!")), ["с-а"])

    def test_half_synced_file_is_not_overwritten(self):
        self.a.add("почта", "a", "1")
        self.path.write_text("{ облако ещё докачивает")
        with self.assertRaises(FileBusy):
            self.a.add("ещё", "b", "2")
        with self.assertRaises(FileBusy):
            self.a.sync()
        self.assertEqual(self.path.read_text(), "{ облако ещё докачивает")

    def test_missing_file_keeps_memory_and_comes_back(self):
        self.a.add("почта", "a", "1")
        self.path.unlink()
        self.assertFalse(self.a.sync())
        self.assertEqual(names(self.a), ["почта"])
        self.a.add("ещё", "b", "2")
        self.assertEqual(names(self.device()), ["ещё", "почта"])

    def test_cloud_overwriting_with_other_version_is_repaired(self):
        self.a.add("общая", "a", "1")
        self.b.sync()
        old = self.path.read_bytes()
        self.a.add("с-а", "a", "2")
        self.path.write_bytes(old)  # облако молча оставило старую версию
        self.assertFalse(self.a.sync())  # у A ничего не изменилось...
        self.assertEqual(names(self.device()), ["общая", "с-а"])  # ...а в файле запись снова есть

    def test_sync_does_not_rewrite_without_need(self):
        self.a.add("почта", "a", "1")
        self.b.sync()
        before = self.path.read_bytes()
        self.assertFalse(self.b.sync())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.a.sync())
        self.assertEqual(self.path.read_bytes(), before)

    def test_file_changed_is_cheap_and_correct(self):
        self.a.add("почта", "a", "1")
        self.assertFalse(self.a.file_changed())
        self.b.add("банк", "b", "2")
        self.assertTrue(self.a.file_changed())
        self.a.sync()
        self.assertFalse(self.a.file_changed())

    def test_revoked_extension_stays_revoked(self):
        self.a.set_bridge_keys(["расширение"])
        self.b.sync()
        self.assertEqual(self.b.bridge_keys, ["расширение"])
        time.sleep(0.002)
        self.a.set_bridge_keys([])  # отключили на A
        self.b.add("запись", "b", "1")  # B со старым списком сохраняет
        self.assertEqual(self.device().bridge_keys, [])

    def test_old_copy_cannot_bring_back_revoked_extension_or_deleted_entry(self):
        self.a.add("удалю", "a", "1")
        self.a.set_bridge_keys(["расширение"])
        old = self.path.read_bytes()
        self.a.delete(0)
        time.sleep(0.002)
        self.a.set_bridge_keys([])
        self.path.write_bytes(old)  # кто-то подложил старую копию файла
        self.a.sync()
        self.assertEqual(self.a.bridge_keys, [])
        self.assertEqual(self.a.entries, [])
        self.assertEqual(self.device().bridge_keys, [])

    def test_access_log_merges_and_cleared_stays_cleared(self):
        self.a.log_access("site-a", "a")
        self.b.log_access("site-b", "b")
        self.a.sync()
        self.assertEqual({i["site"] for i in self.a.access_log}, {"site-a", "site-b"})
        self.a.clear_access_log()
        self.b.sync()
        self.assertEqual(self.b.access_log, [])

    def test_cloud_conflict_copy_is_merged_and_foreign_is_ignored(self):
        self.a.add("общая", "a", "1")
        self.b.sync()
        self.b.add("в-копии", "b", "2")
        copy = self.folder / "vault (MacBook's conflicted copy 2026-11-04).dat"
        copy.write_bytes(self.path.read_bytes())
        self.path.write_bytes(self.template.read_bytes())
        other = self.folder / "vault 2.dat"
        Vault.create(other, "Совсем-Другой-Пароль-2026!")
        for unrelated in ("vaults.dat", "WhoKey.dat", ".vault.dat.bak", "vault.txt"):
            (self.folder / unrelated).write_text("x")
        self.assertEqual(self.device().conflict_copies(), [other, copy] if str(other) < str(copy) else [copy, other])
        vault = self.device()
        self.assertTrue(vault.merge_copy(copy))
        self.assertFalse(vault.merge_copy(other))
        self.assertIn("в-копии", names(self.device()))
        self.assertTrue(other.exists() and copy.exists())  # удаляет файлы только окно WhoKey, спросив человека

    def test_old_format_file_gets_same_ids_on_both_devices(self):
        from cryptography.fernet import Fernet
        import base64
        header = json.loads(self.path.read_text())
        old = [{"site": "почта", "login": "a", "password": "1", "note": "", "created": "2025-01-01 10:00", "updated": "2025-02-02 10:00"},
               {"site": "почта", "login": "a", "password": "2", "note": "", "created": "2025-01-01 10:00", "updated": "2025-02-02 10:00"}]
        header["data"] = Fernet(self.key).encrypt(json.dumps({"entries": old}).encode()).decode()
        self.assertTrue(base64.b64decode(header["salt"]))
        self.path.write_text(json.dumps(header))
        one, two = self.device(), self.device()
        self.assertEqual([e["id"] for e in one.entries], [e["id"] for e in two.entries])
        self.assertEqual(len({e["id"] for e in one.entries}), 2)
        one.update(0, note="правка")
        two.add("новая", "b", "3")
        self.assertEqual(passwords(two), {"1", "2", "3"})
        self.assertEqual(len(two.entries), 3)  # ничего не задвоилось

    def test_hostile_sync_fields_are_rejected(self):
        from cryptography.fernet import Fernet
        header = json.loads(self.path.read_text())
        for content in ({"entries": [], "deleted": []}, {"entries": [], "deleted": {"x": {"at": "s", "seen": []}}},
                        {"entries": [], "bridge_keys_at": "1"},
                        {"entries": [{"site": "s", "login": "", "password": "", "note": "", "created": "", "updated": "",
                                      "id": 5, "modified": 1, "prevs": []}]}):
            header["data"] = Fernet(self.key).encrypt(json.dumps(content).encode()).decode()
            self.path.write_text(json.dumps(header))
            with self.assertRaises(V.VaultError):
                self.device()

    def test_random_work_on_three_devices_converges_and_keeps_latest_passwords(self):
        """Случайные правки на трёх устройствах с редкой синхронизацией."""
        for seed in range(12):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                self.path.write_bytes(self.template.read_bytes())
                devices = [self.device() for _ in range(3)]
                counter = 0
                live = {}  # id -> последний пароль, который кто-то записал и никто не удалял
                for _ in range(60):
                    device = rng.choice(devices)
                    action = rng.random()
                    counter += 1
                    if action < 0.35 or not device.entries:
                        device.add(f"s{counter}", "l", f"p{counter}")
                        live[device.entries[-1]["id"]] = f"p{counter}"
                    elif action < 0.65:
                        entry = rng.choice(device.entries)
                        device.update_id(entry["id"], password=f"p{counter}")
                        live[entry["id"]] = f"p{counter}"
                    elif action < 0.75:
                        entry = rng.choice(device.entries)
                        device.delete_id(entry["id"])
                        live.pop(entry["id"], None)
                    else:
                        device.sync()
                for _ in range(3):
                    for device in devices:
                        device.sync()
                states = [{e["id"]: (e["password"], e["modified"]) for e in d.entries} for d in devices]
                self.assertEqual(states[0], states[1])
                self.assertEqual(states[1], states[2])
                self.assertEqual(len({e["id"] for e in devices[0].entries}), len(devices[0].entries))
                # последний записанный пароль каждой неудалённой записи где-то уцелел
                self.assertLessEqual(set(live.values()), passwords(devices[0]))

    def test_every_write_goes_through_merge(self):
        """Ни одна правка не пишет файл, не посмотрев сначала, что в нём."""
        self.a.add("x", "a", "1")
        actions = [lambda: self.a.add("y", "b", "2"), lambda: self.a.update(0, note="n"), lambda: self.a.delete(0),
                   lambda: self.a.log_access("s", "l"), self.a.clear_access_log, lambda: self.a.set_bridge_keys(["k"]),
                   lambda: self.a.add_many([{"site": "z", "login": "", "password": "3", "note": "", "url": ""}])]
        for action in actions:
            with mock.patch.object(self.a, "_pull", wraps=self.a._pull) as pull:
                action()
            pull.assert_called_once()


class MergeRules(unittest.TestCase):
    def entry(self, id_, modified, prevs=(), password="p"):
        return {"id": id_, "modified": modified, "prevs": list(prevs), "site": "s", "login": "l", "password": password,
                "note": "", "created": "2026-01-01 10:00", "updated": "2026-01-01 10:00"}

    def test_merge_is_order_independent(self):
        a, b = self.entry("x", 2, [1], "из-а"), self.entry("x", 3, [1], "из-б")
        one, _ = sync.merge_entries([a], {}, [b], {})
        two, _ = sync.merge_entries([b], {}, [a], {})
        key = lambda e: e["id"]  # noqa: E731
        self.assertEqual(sorted(one, key=key), sorted(two, key=key))

    def test_merge_is_repeatable(self):
        a, b = self.entry("x", 2, [1], "а"), self.entry("x", 3, [1], "б")
        first, marks = sync.merge_entries([a], {}, [b], {})
        again, _ = sync.merge_entries(first, marks, [b], {})
        self.assertTrue(sync.same_entries(first, again))

    def test_old_tombstones_are_forgotten(self):
        old = {"gone": {"at": sync.now_ms() - sync.TOMBSTONE_MS - 1000, "seen": [1]}}
        self.assertEqual(sync.merge_entries([], old, [], {})[1], {})


if __name__ == "__main__":
    unittest.main()
