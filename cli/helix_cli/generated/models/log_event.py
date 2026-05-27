from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.log_event_stream import LogEventStream

T = TypeVar("T", bound="LogEvent")


@_attrs_define
class LogEvent:
    """
    Attributes:
        seq (int): Monotonic per-job sequence
        ts (datetime.datetime):
        stream (LogEventStream):
        line (str):
    """

    seq: int
    ts: datetime.datetime
    stream: LogEventStream
    line: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        seq = self.seq

        ts = self.ts.isoformat()

        stream = self.stream.value

        line = self.line

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "seq": seq,
                "ts": ts,
                "stream": stream,
                "line": line,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        seq = d.pop("seq")

        ts = isoparse(d.pop("ts"))

        stream = LogEventStream(d.pop("stream"))

        line = d.pop("line")

        log_event = cls(
            seq=seq,
            ts=ts,
            stream=stream,
            line=line,
        )

        log_event.additional_properties = d
        return log_event

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
