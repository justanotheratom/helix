from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.artifact import Artifact
from ...types import UNSET, Response, Unset


def _get_kwargs(
    job_id: UUID,
    *,
    kind: str | Unset = UNSET,
    prefix: str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["kind"] = kind

    params["prefix"] = prefix

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/jobs/{job_id}/artifacts".format(
            job_id=quote(str(job_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> list[Artifact] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = Artifact.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[list[Artifact]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    kind: str | Unset = UNSET,
    prefix: str | Unset = UNSET,
) -> Response[list[Artifact]]:
    """
    Args:
        job_id (UUID):
        kind (str | Unset):
        prefix (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Artifact]]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        kind=kind,
        prefix=prefix,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    kind: str | Unset = UNSET,
    prefix: str | Unset = UNSET,
) -> list[Artifact] | None:
    """
    Args:
        job_id (UUID):
        kind (str | Unset):
        prefix (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Artifact]
    """

    return sync_detailed(
        job_id=job_id,
        client=client,
        kind=kind,
        prefix=prefix,
    ).parsed


async def asyncio_detailed(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    kind: str | Unset = UNSET,
    prefix: str | Unset = UNSET,
) -> Response[list[Artifact]]:
    """
    Args:
        job_id (UUID):
        kind (str | Unset):
        prefix (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Artifact]]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        kind=kind,
        prefix=prefix,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    job_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    kind: str | Unset = UNSET,
    prefix: str | Unset = UNSET,
) -> list[Artifact] | None:
    """
    Args:
        job_id (UUID):
        kind (str | Unset):
        prefix (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Artifact]
    """

    return (
        await asyncio_detailed(
            job_id=job_id,
            client=client,
            kind=kind,
            prefix=prefix,
        )
    ).parsed
