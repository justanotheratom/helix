from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.gc_report import GcReport
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    grace_hours: int | Unset = 24,
    dry_run: bool | Unset = True,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["grace_hours"] = grace_hours

    params["dry_run"] = dry_run

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/gc",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GcReport | None:
    if response.status_code == 200:
        response_200 = GcReport.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[GcReport]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    grace_hours: int | Unset = 24,
    dry_run: bool | Unset = True,
) -> Response[GcReport]:
    """Reclaim storage — unreferenced snapshots/blobs + orphan bundles

    Args:
        grace_hours (int | Unset):  Default: 24.
        dry_run (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GcReport]
    """

    kwargs = _get_kwargs(
        grace_hours=grace_hours,
        dry_run=dry_run,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    grace_hours: int | Unset = 24,
    dry_run: bool | Unset = True,
) -> GcReport | None:
    """Reclaim storage — unreferenced snapshots/blobs + orphan bundles

    Args:
        grace_hours (int | Unset):  Default: 24.
        dry_run (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GcReport
    """

    return sync_detailed(
        client=client,
        grace_hours=grace_hours,
        dry_run=dry_run,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    grace_hours: int | Unset = 24,
    dry_run: bool | Unset = True,
) -> Response[GcReport]:
    """Reclaim storage — unreferenced snapshots/blobs + orphan bundles

    Args:
        grace_hours (int | Unset):  Default: 24.
        dry_run (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GcReport]
    """

    kwargs = _get_kwargs(
        grace_hours=grace_hours,
        dry_run=dry_run,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    grace_hours: int | Unset = 24,
    dry_run: bool | Unset = True,
) -> GcReport | None:
    """Reclaim storage — unreferenced snapshots/blobs + orphan bundles

    Args:
        grace_hours (int | Unset):  Default: 24.
        dry_run (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GcReport
    """

    return (
        await asyncio_detailed(
            client=client,
            grace_hours=grace_hours,
            dry_run=dry_run,
        )
    ).parsed
