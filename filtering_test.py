# Standard library imports
import json
import tempfile
import unittest
from os import path
from os import remove

# Local application/library specific imports
import filtering
from filtering import DOWNLOADED_IDS_FILE_NAME
from filtering import KEY_IDS

DIR = tempfile.gettempdir()


class TestExcludeFile(unittest.TestCase):
    @property
    def file_under_test(self):
        return path.join(DIR, "exclude.json")

    @property
    def non_existing_file(self):
        return path.join(DIR, "non_existing_exclude.json")

    @property
    def dir(self):
        return DIR

    def setUp(self):
        if path.exists(self.file_under_test):
            remove(self.file_under_test)

        if path.exists(self.non_existing_file):
            remove(self.non_existing_file)

    def test_read_exclude(self):
        self.assertIsNone(filtering.read_exclude(self.non_existing_file))

        with open(self.file_under_test, 'w') as f:
            json.dump(dict(ids=["1001", "1002", "1010", "1003"]), f)

        ids = filtering.read_exclude(self.file_under_test)

        self.assertEqual(len(ids), 4)

        self.assertIn("1001", ids)
        self.assertIn("1002", ids)
        self.assertIn("1003", ids)
        self.assertIn("1010", ids)


class TestDownloadStats(unittest.TestCase):
    @property
    def file_under_test(self):
        return path.join(DIR, DOWNLOADED_IDS_FILE_NAME)

    @property
    def dir(self):
        return DIR

    def setUp(self):
        if path.exists(self.file_under_test):
            remove(self.file_under_test)

    def test_new_file(self):
        filtering.update_download_stats('1000', self.dir)

        with open(self.file_under_test, 'r') as actual_file:
            actual = json.load(actual_file)

            self.assertEqual(actual[KEY_IDS][0], '1000')

    def test_1000_items(self):
        r = range(1, 1000)

        for i in r:
            filtering.update_download_stats(str(i), self.dir)

        with open(self.file_under_test, 'r') as actual_file:
            actual = json.load(actual_file)

            self.assertEqual(len(actual[KEY_IDS]), len(r))

    def test_new_item(self):
        filtering.update_download_stats('1000', self.dir)
        filtering.update_download_stats('1010', self.dir)

        with open(self.file_under_test, 'r') as actual_file:
            actual = json.load(actual_file)

            self.assertEqual(actual[KEY_IDS][0], '1000')
            self.assertEqual(actual[KEY_IDS][1], '1010')

    def test_corrupted_file(self):
        with open(self.file_under_test, 'w') as corrupted_file:
            corrupted_file.write("HUGO")

        filtering.update_download_stats('1000', self.dir)

        with open(self.file_under_test, 'r') as actual_file:
            actual = json.load(actual_file)

            self.assertEqual(actual[KEY_IDS][0], '1000')

    def test_sort(self):
        filtering.update_download_stats('1010', self.dir)
        filtering.update_download_stats('1000', self.dir)
        filtering.update_download_stats('1005', self.dir)

        with open(self.file_under_test, 'r') as actual_file:
            actual = json.load(actual_file)

            self.assertEqual(actual[KEY_IDS][0], '1000')
            self.assertEqual(actual[KEY_IDS][1], '1005')
            self.assertEqual(actual[KEY_IDS][2], '1010')


if __name__ == '__main__':
    unittest.main()
