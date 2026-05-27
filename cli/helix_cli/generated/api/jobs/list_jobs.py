from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.job import Job
from ...models.job_status import JobStatus
from ...models.job_type import JobType
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    program: str | Unset = UNSET,
    version: str | Unset = UNSET,
    dataset: str | Unset = UNSET,
    split: str | Unset = UNSET,
    status: JobStatus | Unset = UNSET,
    type_: JobType | Unset = UNSET,
    limit: int | Unset = 100,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["program"] = program

    params["version"] = version

    params["dataset"] = dataset

    params["split"] = split

    json_status: str | Unset = UNSET
    if not isinstance(status, Unset):
        json_status = status.value

    params["status"] = json_status

    json_type_: str | Unset = UNSET
    if not isinstance(type_, Unset):
        json_type_ = type_.value

    params["type"] = json_type_

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/jobs",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> list[Job] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = Job.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[list[Job]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    program: str | Unset = UNSET,
    version: str | Unset = UNSET,
    dataset: str | Unset = UNSET,
    split: str | Unset = UNSET,
    status: JobStatus | Unset = UNSET,
    type_: JobType | Unset = UNSET,
    limit: int | Unset = 100,
) -> Response[list[Job]]:
    """List jobs with filters

    Args:
        program (str | Unset):
        version (str | Unset):
        dataset (str | Unset):
        split (str | Unset):
        status (JobStatus | Unset):
        type_ (JobType | Unset):
        limit (int | Unset):  Default: 100.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Job]]
    """

    kwargs = _get_kwargs(
        program=program,
        version=version,
        dataset=dataset,
        split=split,
        status=status,
        type_=type_,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    program: str | Unset = UNSET,
    version: str | Unset = UNSET,
    dataset: str | Unset = UNSET,
    split: str | Unset = UNSET,
    status: JobStatus | Unset = UNSET,
    type_: JobType | Unset = UNSET,
    limit: int | Unset = 100,
) -> list[Job] | None:
    """List jobs with filters

    Args:
        program (str | Unset):
        version (str | Unset):
        dataset (str | Unset):
        split (str | Unset):
        status (JobStatus | Unset):
        type_ (JobType | Unset):
        limit (int | Unset):  Default: 100.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Job]
    """

    return sync_detailed(
        client=client,
        program=program,
        version=version,
        dataset=dataset,
        split=split,
        status=status,
        type_=type_,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    program: str | Unset = UNSET,
    version: str | Unset = UNSET,
    dataset: str | Unset = UNSET,
    split: str | Unset = UNSET,
    status: JobStatus | Unset = UNSET,
    type_: JobType | Unset = UNSET,
    limit: int | Unset = 100,
) -> Response[list[Job]]:
    """List jobs with filters

    Args:
        program (str | Unset):
        version (str | Unset):
        dataset (str | Unset):
        split (str | Unset):
        status (JobStatus | Unset):
        type_ (JobType | Unset):
        limit (int | Unset):  Default: 100.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[list[Job]]
    """

    kwargs = _get_kwargs(
        program=program,
        version=version,
        dataset=dataset,
        split=split,
        status=status,
        type_=type_,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    program: str | Unset = UNSET,
    version: str | Unset = UNSET,
    dataset: str | Unset = UNSET,
    split: str | Unset = UNSET,
    status: JobStatus | Unset = UNSET,
    type_: JobType | Unset = UNSET,
    limit: int | Unset = 100,
) -> list[Job] | None:
    """List jobs with filters

    Args:
        program (str | Unset):
        version (str | Unset):
        dataset (str | Unset):
        split (str | Unset):
        status (JobStatus | Unset):
        type_ (JobType | Unset):
        limit (int | Unset):  Default: 100.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        list[Job]
    """

    return (
        await asyncio_detailed(
            client=client,
            program=program,
            version=version,
            dataset=dataset,
            split=split,
            status=status,
            type_=type_,
            limit=limit,
        )
    ).parsed
