"""Locate the single audited native data-json/v1 source in checkouts and wheels."""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from . import data_language_v1 as _data_language

_RESOURCE = Path("share/koschei/native/datajson/json.go")


def _source_path() -> Path:
    checkout = Path(__file__).resolve().parents[1] / "native" / "datajson" / "json.go"
    if checkout.is_file():
        return checkout

    try:
        installed = Path(distribution("koschei-lang").locate_file(_RESOURCE))
    except PackageNotFoundError as error:
        raise RuntimeError(
            "koschei-lang distribution metadata is unavailable; native Data ABI refused"
        ) from error
    if not installed.is_file():
        raise RuntimeError(
            "the installed koschei-lang package is missing the audited "
            "native/datajson/json.go source; native Data ABI refused"
        )
    return installed


def _go_data_runtime() -> str:
    try:
        source = _source_path().read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(
            "the audited native data-json/v1 source could not be read"
        ) from error

    body = re.sub(
        r"\A// Package datajson.*?\npackage datajson\n\nimport \(\n.*?\n\)\n\n",
        "",
        source,
        count=1,
        flags=re.DOTALL,
    )
    if body == source:
        raise RuntimeError("native data-json/v1 source shape changed; embedding refused")

    wrappers = r'''
type KsData struct {
	Value any
}

func ksDataParse(raw any) any {
	text, ok := raw.(string)
	if !ok {
		return ksErrorf("KS3608 [byte 0]: parse_json() expects String")
	}
	value, err := Decode(text, DefaultLimits)
	if err != nil {
		return ksErrorf(err.Error())
	}
	return &KsData{Value: value}
}

func ksDataEncode(raw any) any {
	data, ok := raw.(*KsData)
	if !ok {
		return ksErrorf("KS3608 [byte 0]: encode_json() expects Data")
	}
	text, err := Encode(data.Value, DefaultLimits)
	if err != nil {
		return ksErrorf(err.Error())
	}
	return text
}
'''
    return body + "\n" + wrappers


def install_packaged_native_source() -> None:
    _data_language._go_data_runtime = _go_data_runtime
