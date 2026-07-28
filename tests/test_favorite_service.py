from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.favorite_service import FavoriteService


class TestFavoriteService:
    def test_list_favorited_symbols(self):
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = ["sh.600000", "sz.000001"]
        result = FavoriteService(db).list_favorited_symbols()
        assert result == {"sh.600000", "sz.000001"}

    def test_toggle_adds_when_missing(self):
        db = MagicMock()
        # is_favorited -> None, then add path: get StockFavorite None, get StockMaster exists
        stock = SimpleNamespace(symbol="sh.600000")
        db.get.side_effect = [None, None, stock]
        favorited = FavoriteService(db).toggle("sh.600000")
        assert favorited is True
        db.add.assert_called_once()
        db.commit.assert_called()

    def test_toggle_removes_when_present(self):
        fav = SimpleNamespace(symbol="sh.600000")
        db = MagicMock()
        db.get.side_effect = [fav, fav]
        favorited = FavoriteService(db).toggle("sh.600000")
        assert favorited is False
        db.delete.assert_called_once_with(fav)
        db.commit.assert_called()

    def test_add_unknown_symbol_raises(self):
        db = MagicMock()
        db.get.side_effect = [None, None]
        with pytest.raises(ValueError, match="股票不存在"):
            FavoriteService(db).add("xx.999999")
