from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error import Error
from ...models.snapshot_ref import SnapshotRef
from ...types import UNSET, Response


def _get_kwargs(
    *,
    repo_id: str,
    digest: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["repo_id"] = repo_id

    params["digest"] = digest

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/snapshots/resolve",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | SnapshotRef | None:
    if response.status_code == 200:
        response_200 = SnapshotRef.from_dict(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = Error.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Error | SnapshotRef]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    repo_id: str,
    digest: str,
) -> Response[Error | SnapshotRef]:
    """Return an existing snapshot manifest for (repo_id, digest), else 404

    Args:
        repo_id (str):
        digest (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | SnapshotRef]
    """

    kwargs = _get_kwargs(
        repo_id=repo_id,
        digest=digest,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    repo_id: str,
    digest: str,
) -> Error | SnapshotRef | None:
    """Return an existing snapshot manifest for (repo_id, digest), else 404

    Args:
        repo_id (str):
        digest (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | SnapshotRef
    """

    return sync_detailed(
        client=client,
        repo_id=repo_id,
        digest=digest,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    repo_id: str,
    digest: str,
) -> Response[Error | SnapshotRef]:
    """Return an existing snapshot manifest for (repo_id, digest), else 404

    Args:
        repo_id (str):
        digest (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | SnapshotRef]
    """

    kwargs = _get_kwargs(
        repo_id=repo_id,
        digest=digest,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    repo_id: str,
    digest: str,
) -> Error | SnapshotRef | None:
    """Return an existing snapshot manifest for (repo_id, digest), else 404

    Args:
        repo_id (str):
        digest (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | SnapshotRef
    """

    return (
        await asyncio_detailed(
            client=client,
            repo_id=repo_id,
            digest=digest,
        )
    ).parsed
