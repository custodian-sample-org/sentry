from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from itertools import groupby
from typing import (
    Any,
    Mapping,
    MutableMapping,
    MutableSequence,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from sentry.sentry_metrics.configuration import UseCaseKey
from sentry.utils.services import Service


class FetchType(Enum):
    CACHE_HIT = "c"
    HARDCODED = "h"
    DB_READ = "d"
    FIRST_SEEN = "f"
    RATE_LIMITED = "r"


class FetchTypeExt(NamedTuple):
    is_global: bool


UseCaseId = str
OrgId = int


KR = TypeVar("KR", bound="KeyResult")
UR = TypeVar("UR", bound="UseCaseKeyResult")


class Metadata(NamedTuple):
    id: Optional[int]
    fetch_type: FetchType
    fetch_type_ext: Optional[FetchTypeExt] = None


@dataclass(frozen=True)
class KeyResult:
    org_id: OrgId
    string: str
    id: Optional[int]

    @classmethod
    def from_string(cls: Type[KR], key: str, id: int) -> KR:
        org_id, string = key.split(":", 1)
        return cls(int(org_id), string, id)


@dataclass(frozen=True)
class UseCaseKeyResult:
    use_case_id: UseCaseId
    org_id: OrgId
    string: str
    id: Optional[int]

    @classmethod
    def from_string(cls: Type[UR], key: str, id: int) -> UR:
        use_case_id, org_id, string = key.split(":", 1)
        return cls(use_case_id, int(org_id), string, id)


class KeyCollection:
    """
    A KeyCollection is a way of keeping track of a group of keys
    used to fetch ids, whose results are stored in KeyResults.

    A key is a org_id, string pair, either represented as a
    tuple e.g (1, "a"), or a string "1:a".

    Initial mapping is org_id's to sets of strings:
        { 1: {"a", "b", "c"}, 2: {"e", "f"} }
    """

    def __init__(self, mapping: Mapping[OrgId, Set[str]]):
        self.mapping = mapping
        self.size = self._size()

    def __eq__(self, value: Any) -> bool:
        return (
            isinstance(value, self.__class__)
            and self.size == value.size
            and self.mapping == value.mapping
        )

    def _size(self) -> int:
        total_size = 0
        for org_id in self.mapping.keys():
            total_size += len(self.mapping[org_id])
        return total_size

    def as_tuples(self) -> Sequence[Tuple[int, str]]:
        """
        Returns all the keys, each key represented as tuple -> (1, "a")
        """
        key_pairs: MutableSequence[Tuple[int, str]] = []
        for org_id in self.mapping:
            key_pairs.extend([(org_id, string) for string in self.mapping[org_id]])

        return key_pairs

    def as_strings(self) -> Sequence[str]:
        """
        Returns all the keys, each key represented as string -> "1:a"
        """
        keys: MutableSequence[str] = []
        for org_id in self.mapping:
            keys.extend([f"{org_id}:{string}" for string in self.mapping[org_id]])

        return keys


class UseCaseKeyCollection:
    """
    A UseCaseKeyCollection is a way of keeping track of a group
    of keys used to fetch ids, whose results are stored in UseCaseKeyResults.

    A key is a use_case_id, org_id, string pair, either represented as a
    tuple e.g ("performance", 1, "a"), or a string "performance:1:a".

    Initial mapping is org_id's to sets of strings:
        {"performance": { 1: {"a", "b", "c"}, 2: {"e", "f"} }}
    """

    def __init__(self, mapping: Mapping[UseCaseId, Union[Mapping[OrgId, Set[str]], KeyCollection]]):
        self.mapping = {
            use_case_id: keys if isinstance(keys, KeyCollection) else KeyCollection(keys)
            for use_case_id, keys in mapping.items()
        }
        self.size = self._size()

    def __eq__(self, __value: object) -> bool:
        return (
            isinstance(__value, self.__class__)
            and self.size == __value.size
            and self.mapping == __value.mapping
        )

    def _size(self) -> int:
        return sum(key_collection.size for key_collection in self.mapping.values())

    def as_tuples(self) -> Sequence[Tuple[UseCaseId, OrgId, str]]:
        return [
            (use_case_id, org_id, s)
            for use_case_id, key_collection in self.mapping.items()
            for org_id, s in key_collection.as_tuples()
        ]

    def as_strings(self) -> Sequence[str]:
        return [
            f"{use_case_id}:{s}"
            for use_case_id, key_collection in self.mapping.items()
            for s in key_collection.as_strings()
        ]


class KeyResults:
    def __init__(self) -> None:
        self.results: MutableMapping[OrgId, MutableMapping[str, Optional[int]]] = defaultdict(dict)
        self.meta: MutableMapping[OrgId, MutableMapping[str, Metadata]] = defaultdict(dict)

    def __eq__(self, __value: object) -> bool:
        return (
            isinstance(__value, self.__class__)
            and self.results == __value.results
            and self.meta == __value.meta
        )

    def add_key_result(
        self,
        key_result: KeyResult,
        fetch_type: Optional[FetchType] = None,
        fetch_type_ext: Optional[FetchTypeExt] = None,
    ) -> None:
        self.results[key_result.org_id].update({key_result.string: key_result.id})
        if fetch_type:
            self.meta[key_result.org_id][key_result.string] = Metadata(
                id=key_result.id, fetch_type=fetch_type, fetch_type_ext=fetch_type_ext
            )

    def add_key_results(
        self,
        key_results: Sequence[KeyResult],
        fetch_type: Optional[FetchType] = None,
        fetch_type_ext: Optional[FetchTypeExt] = None,
    ) -> None:
        for key_result in key_results:
            self.results[key_result.org_id].update({key_result.string: key_result.id})
            if fetch_type:
                self.meta[key_result.org_id][key_result.string] = Metadata(
                    id=key_result.id, fetch_type=fetch_type, fetch_type_ext=fetch_type_ext
                )

    def get_mapped_results(self) -> Mapping[OrgId, Mapping[str, Optional[int]]]:
        """
        Only return results that have org_ids with string/int mappings.
        """
        mapped_results = {k: v for k, v in self.results.items() if len(v) > 0}
        return mapped_results

    def get_unmapped_keys(self, keys: KeyCollection) -> KeyCollection:
        """
        Takes a KeyCollection and compares it to the results. Returns
        a new KeyCollection for any keys that don't have corresponding
        ids in results.
        """
        unmapped_org_strings: MutableMapping[OrgId, Set[str]] = defaultdict(set)
        for org_id, strings in keys.mapping.items():
            for string in strings:
                if not self.results[org_id].get(string):
                    unmapped_org_strings[org_id].add(string)

        return KeyCollection(unmapped_org_strings)

    def get_mapped_key_strings_to_ints(self) -> MutableMapping[str, int]:
        """
        Return the results, but formatted as the following:
            {
                "1:a": 10,
                "1:b": 11,
                "1:c", 12,
                "2:e": 13
            }
        This is for when we use indexer_cache.set_many()
        """
        cache_key_results: MutableMapping[str, int] = {}
        for org_id, result_dict in self.results.items():
            for string, id in result_dict.items():
                key = f"{org_id}:{string}"
                if id is not None:
                    cache_key_results[key] = id

        return cache_key_results

    def get_fetch_metadata(
        self,
    ) -> Mapping[OrgId, Mapping[str, Metadata]]:
        return self.meta

    def merge(self, other: "KeyResults") -> "KeyResults":
        new_results: "KeyResults" = KeyResults()

        for org_id, strings in [*other.results.items(), *self.results.items()]:
            new_results.results[org_id].update(strings)

        for org_id, org_meta in self.meta.items():
            new_results.meta[org_id].update(org_meta)

        for org_id, org_meta in other.meta.items():
            new_results.meta[org_id].update(org_meta)

        return new_results

    # For brevity, allow callers to address the mapping directly
    def __getitem__(self, org_id: OrgId) -> Mapping[str, Optional[int]]:
        return self.results[org_id]


class UseCaseKeyResults:
    """
    A UseCaseKeyResults the use case ID aware version of KeyResults.

    It stores mapping of strings and their indexed ID, keyed by use case ID and org ID
    E.g
        {"performance": { 1: {"a": 1, "b": 2}, 2: {"f": 7} }}
    """

    def __init__(self) -> None:
        self.results: MutableMapping[UseCaseId, KeyResults] = defaultdict(lambda: KeyResults())

    def __eq__(self, __value: object) -> bool:
        return isinstance(__value, self.__class__) and self.results == __value.results

    def add_use_case_key_result(
        self,
        use_case_key_result: UseCaseKeyResult,
        fetch_type: Optional[FetchType] = None,
        fetch_type_ext: Optional[FetchTypeExt] = None,
    ) -> None:
        self.results[use_case_key_result.use_case_id].add_key_result(
            KeyResult(
                use_case_key_result.org_id, use_case_key_result.string, use_case_key_result.id
            ),
            fetch_type,
            fetch_type_ext,
        )

    def add_use_case_key_results(
        self,
        use_case_key_results: Sequence[UseCaseKeyResult],
        fetch_type: Optional[FetchType] = None,
        fetch_type_ext: Optional[FetchTypeExt] = None,
    ) -> None:
        for use_case, grouped_use_case_key_results in groupby(
            use_case_key_results, lambda use_case_key_result: use_case_key_result.use_case_id
        ):
            self.results[use_case].add_key_results(
                [
                    KeyResult(
                        use_case_key_result.org_id,
                        use_case_key_result.string,
                        use_case_key_result.id,
                    )
                    for use_case_key_result in grouped_use_case_key_results
                ],
                fetch_type,
                fetch_type_ext,
            )

    def get_mapped_results(self) -> Mapping[UseCaseId, Mapping[OrgId, Mapping[str, Optional[int]]]]:
        """
        Only return results that string/int mappings, keyed by use case ID, then org ID.
        """
        return {
            use_case_id: mapped_result
            for use_case_id, key_results in self.results.items()
            if (mapped_result := key_results.get_mapped_results())
        }

    def get_unmapped_use_case_keys(
        self, use_case_key_collection: UseCaseKeyCollection
    ) -> UseCaseKeyCollection:
        """
        Takes a UseCaseKeyCollection and compares it to the results. Returns
        a new UseCaseKeyCollection for any keys that don't have corresponding
        ids in results.
        """
        return UseCaseKeyCollection(
            {
                use_case_id: unmapped_result
                for use_case_id, key_collection in use_case_key_collection.mapping.items()
                if (
                    unmapped_result := self.results[use_case_id].get_unmapped_keys(key_collection)
                ).size
                > 0
            }
        )

    def get_mapped_strings_to_ints(self) -> MutableMapping[str, int]:
        """
        Return the results, but formatted as the following:
            {
                "use_case_1:1:a": 10,
                "use_case_1:1:b": 11,
                "use_case_1:1:c", 12,
                "use_case_1:2:e": 13
            }
        This is for when we use indexer_cache.set_many()
        """
        return {
            f"{use_case_id}:{string}": id
            for use_case_id, key_results in self.results.items()
            for string, id in key_results.get_mapped_key_strings_to_ints().items()
        }

    def get_fetch_metadata(
        self,
    ) -> Mapping[UseCaseId, Mapping[OrgId, Mapping[str, Metadata]]]:
        return {
            use_case_id: key_results.get_fetch_metadata()
            for use_case_id, key_results in self.results.items()
            if key_results.get_fetch_metadata()
        }

    def merge(self, other: "UseCaseKeyResults") -> "UseCaseKeyResults":
        def merge_use_case(use_case_id: UseCaseId) -> KeyResults:
            if use_case_id in self.results and use_case_id in other.results:
                return self.results[use_case_id].merge(other.results[use_case_id])
            if use_case_id in self.results:
                return self.results[use_case_id]
            return other.results[use_case_id]

        new_results = UseCaseKeyResults()

        new_results.results = {
            use_case_id: merge_use_case(use_case_id)
            for use_case_id in set(self.results.keys()) | set(other.results.keys())
        }

        return new_results

    def __getitem__(self, use_case_id: UseCaseId) -> KeyResults:
        return self.results[use_case_id]


class StringIndexer(Service):
    """
    Provides integer IDs for metric names, tag keys and tag values
    and the corresponding reverse lookup.

    Check `sentry.snuba.metrics` for convenience functions.
    """

    __all__ = (
        "record",
        "resolve",
        "reverse_resolve",
        "bulk_record",
        "resolve_shared_org",
        "reverse_shared_org_resolve",
    )

    def bulk_record(
        self, use_case_id: UseCaseKey, org_strings: Mapping[int, Set[str]]
    ) -> KeyResults:
        """
        Takes in a mapping with org_ids to sets of strings.

        Ultimately returns a mapping of those org_ids to a
        string -> id mapping, for each string in the set.

        There are three steps to getting the ids for strings:
            0. ids from static strings (StaticStringIndexer)
            1. ids from cache (CachingIndexer)
            2. ids from existing db records (postgres/spanner)
            3. ids that have been rate limited (postgres/spanner)
            4. ids from newly created db records (postgres/spanner)

        Each step will start off with a KeyCollection and KeyResults:
            keys = KeyCollection(mapping)
            key_results = KeyResults()

        Then the work to get the ids (either from cache, db, etc)
            .... # work to add results to KeyResults()

        Those results will be added to `mapped_results` which can
        be retrieved
            key_results.get_mapped_results()

        Remaining unmapped keys get turned into a new
        KeyCollection for the next step:
            new_keys = key_results.get_unmapped_keys(mapping)

        When the last step is reached or a step resolves all the remaining
        unmapped keys the key_results objects are merged and returned:
            e.g. return cache_key_results.merge(db_read_key_results)
        """
        raise NotImplementedError()

    def record(self, use_case_id: UseCaseKey, org_id: int, string: str) -> Optional[int]:
        """Store a string and return the integer ID generated for it

        With every call to this method, the lifetime of the entry will be
        prolonged.
        """
        raise NotImplementedError()

    def resolve(self, use_case_id: UseCaseKey, org_id: int, string: str) -> Optional[int]:
        """Lookup the integer ID for a string.

        Does not affect the lifetime of the entry.

        Callers should not rely on the default use_case_id -- it exists only
        as a temporary workaround.

        Returns None if the entry cannot be found.
        """
        raise NotImplementedError()

    def reverse_resolve(self, use_case_id: UseCaseKey, org_id: int, id: int) -> Optional[str]:
        """Lookup the stored string for a given integer ID.

        Callers should not rely on the default use_case_id -- it exists only
        as a temporary workaround.

        Returns None if the entry cannot be found.
        """
        raise NotImplementedError()

    def resolve_shared_org(self, string: str) -> Optional[int]:
        """
        Look up the index for a shared (cross organisation) string.

        Typically, this function will only lookup strings that are statically defined but
        regardless of the mechanism these are strings that are not organisation or use-case specific.
        """
        raise NotImplementedError()

    def reverse_shared_org_resolve(self, id: int) -> Optional[str]:
        """Lookup the stored string given integer for a shared (cross organisation) ID.

        Returns None if the entry cannot be found.
        """
        raise NotImplementedError()
