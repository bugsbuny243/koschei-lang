import pytest
from koschei.immutable_collections_v1 import (
    CollectionBudgetError, CollectionBudgetV1, KList, KMap,
)

B = CollectionBudgetV1(max_items=4, max_work=8)

def test_klist_is_immutable_and_bounded():
    a = KList.from_iterable([1,2], budget=B)
    b = a.push(3, budget=B)
    assert tuple(a) == (1,2)
    assert tuple(b) == (1,2,3)
    with pytest.raises(CollectionBudgetError):
        KList.from_iterable(range(5), budget=B)

def test_list_map_filter_fold_are_work_bounded():
    a = KList.from_iterable([1,2,3], budget=B)
    assert tuple(a.map(lambda x:x*2,budget=B)) == (2,4,6)
    assert tuple(a.filter(lambda x:x%2,budget=B)) == (1,3)
    assert a.fold(0,lambda acc,x:acc+x,budget=B) == 6
    tiny = CollectionBudgetV1(max_items=4,max_work=2)
    with pytest.raises(CollectionBudgetError):
        a.map(lambda x:x,budget=tiny)

def test_take_drop_concat_are_deterministic():
    a = KList.from_iterable([1,2,3], budget=B)
    assert tuple(a.take(2)) == (1,2)
    assert tuple(a.drop(2)) == (3,)
    assert tuple(a.concat(KList((4,)),budget=B)) == (1,2,3,4)

def test_kmap_updates_without_mutating_source():
    a = KMap.from_mapping({"a":1,"b":2},budget=B)
    b = a.set("a",9,budget=B)
    c = b.remove("b")
    assert a.get("a") == 1
    assert b.get("a") == 9
    assert c.contains("b") is False
    assert tuple(c.keys()) == ("a",)

def test_map_entry_budget_fails_closed():
    a = KMap.from_mapping({"a":1,"b":2,"c":3,"d":4},budget=B)
    with pytest.raises(CollectionBudgetError):
        a.set("e",5,budget=B)
