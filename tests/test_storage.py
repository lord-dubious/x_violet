from xviolet.storage import InteractionStore

def test_interaction_store(tmp_path):
    path = tmp_path / "interactions.json"
    store = InteractionStore(path)
    assert store.data == {"interacted_tweets": []}
    store.add_interaction("123")
    assert store.has_interacted("123")
    store.remove_interaction("123")
    assert not store.has_interacted("123")
    store.add_interaction("456")
    store.clear()
    assert store.data["interacted_tweets"] == []
    # Test persistence
    store.add_interaction("789")
    store2 = InteractionStore(path)
    assert store2.has_interacted("789")
