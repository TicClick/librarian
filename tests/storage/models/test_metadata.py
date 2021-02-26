class TestMetadata:
    def test__basic(self, storage):
        m = storage.metadata
        assert m.load() == {}
        assert m.load_field("blah") is None

        for data_piece in (1, 2.3, "blah", {"nested": {"dict": "ionary"}}, ["test"], [["test"]]):
            m.save_field("blah", data_piece)
            assert m.load() == {"blah": data_piece}
            assert m.load_field("blah") == data_piece

        m.save({})
        assert m.load() == {}
        m.save({1: 2, 3: 4})
        assert m.load() == {1: 2, 3: 4}
