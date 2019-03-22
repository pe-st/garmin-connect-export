from unittest import TestCase
from gcexport import resolve_path


class Tests(TestCase):
    def test_resolve_path_1(self):
        actual = resolve_path("root", "sub/{YYYY}", "2018-03-08 12:23:22")
        self.assertEqual("root/sub/2018", actual)

        actual = resolve_path("root", "sub/{MM}", "2018-03-08 12:23:22")
        self.assertEqual("root/sub/03", actual)

        actual = resolve_path("root", "sub/{YYYY}/{MM}", "2018-03-08 12:23:22")
        self.assertEqual("root/sub/2018/03", actual)

        actual = resolve_path("root", "sub/{yyyy}", "2018-03-08 12:23:22")
        self.assertEqual("root/sub/{yyyy}", actual)

        actual = resolve_path("root", "sub/{YYYYMM}", "2018-03-08 12:23:22")
        self.assertEqual("root/sub/{YYYYMM}", actual)

        actual = resolve_path("root", "sub/all", "2018-03-08 12:23:22")
        self.assertEqual("root/sub/all", actual)
