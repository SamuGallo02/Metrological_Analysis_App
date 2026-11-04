import unittest

from corpse.functions.training.server_data import group_datasets_by_species


def item(path, classes, date="2026-11-03"):
    return {"path": path, "classes": classes, "date": date}


class GroupDatasetsTest(unittest.TestCase):
    def names(self, groups):
        return [(species, [i["path"] for i in items]) for species, items in groups]

    def test_a_dataset_is_listed_under_each_of_its_species(self):
        groups = group_datasets_by_species([item("multi", ["Zeus faber", "Apogon imberbis"]),
                                            item("solo", ["Apogon imberbis"])])
        self.assertEqual(self.names(groups), [("Apogon imberbis", ["multi", "solo"]), ("Zeus faber", ["multi"])])

    def test_datasets_without_species_go_last_under_an_empty_name(self):
        groups = group_datasets_by_species([item("vuoto", []), item("solo", ["Apogon imberbis"])])
        self.assertEqual(self.names(groups), [("Apogon imberbis", ["solo"]), ("", ["vuoto"])])

    def test_inside_a_species_the_older_dataset_comes_first(self):
        groups = group_datasets_by_species([item("nuovo", ["Zeus faber"], "2026-11-03"),
                                            item("vecchio", ["Zeus faber"], "2026-10-01")])
        self.assertEqual(self.names(groups), [("Zeus faber", ["vecchio", "nuovo"])])