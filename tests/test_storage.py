import pytest
from app import storage

@pytest.fixture
def init_db(tmp_path):
    db_path = tmp_path / 'test.db'
    storage.init(db_path)
    return db_path

def test_ensure_and_get_user(init_db):
    storage.ensure_user(1, 'alice')
    user = storage.get_user(1)
    assert user['tg_id'] == 1
    assert user['username'] == 'alice'


def test_ensure_user_updates_username(init_db):
    storage.ensure_user(1, 'alice')
    storage.ensure_user(1, 'bob')
    user = storage.get_user(1)
    assert user['username'] == 'bob'


def test_set_user_field_and_get(init_db):
    storage.ensure_user(2, 'charlie')
    storage.set_user_field(2, 'banned', 1)
    user = storage.get_user(2)
    assert user['banned'] == 1


def test_get_user_missing(init_db):
    assert storage.get_user(999) is None
