from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TracesUrl")


@_attrs_define
class TracesUrl:
    """
    Attributes:
        url (str): Absolute URL into the Langfuse instance, filtered by
            `environment=<run_label>`. In v1 Langfuse runs on its own
            loopback origin (`http://127.0.0.1:3010`); user logs in once
            with the seeded `LANGFUSE_INIT_USER_*` credentials and the
            browser keeps the 30-day NextAuth session.
        run_label (str):
    """

    url: str
    run_label: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        url = self.url

        run_label = self.run_label

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "url": url,
                "run_label": run_label,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        url = d.pop("url")

        run_label = d.pop("run_label")

        traces_url = cls(
            url=url,
            run_label=run_label,
        )

        traces_url.additional_properties = d
        return traces_url

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
