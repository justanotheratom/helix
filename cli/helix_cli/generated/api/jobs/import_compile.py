from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error import Error
from ...models.import_compile_submission import ImportCompileSubmission
from ...models.job_submission_result import JobSubmissionResult
from ...types import Response


def _get_kwargs(
    *,
    body: ImportCompileSubmission,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/jobs/import-compile",
    }

    _kwargs["files"] = body.to_multipart()

    headers["Content-Type"] = "multipart/form-data; boundary=+++"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | JobSubmissionResult | None:
    if response.status_code == 200:
        response_200 = JobSubmissionResult.from_dict(response.json())

        return response_200

    if response.status_code == 201:
        response_201 = JobSubmissionResult.from_dict(response.json())

        return response_201

    if response.status_code == 400:
        response_400 = Error.from_dict(response.json())

        return response_400

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Error | JobSubmissionResult]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ImportCompileSubmission,
) -> Response[Error | JobSubmissionResult]:
    """Import a legacy local results directory as an ad-hoc compile job

     Accepts a tarball of a results-dir tree (as produced by the old
    launcher). Creates a `succeeded` compile job row with
    baked_sha=null, emitted_run_number parsed from the directory
    name, and uploads every file (except evals/** and helix/**)
    as an artifact. Idempotent on (program_version, emitted_run_number).

    Args:
        body (ImportCompileSubmission):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | JobSubmissionResult]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: ImportCompileSubmission,
) -> Error | JobSubmissionResult | None:
    """Import a legacy local results directory as an ad-hoc compile job

     Accepts a tarball of a results-dir tree (as produced by the old
    launcher). Creates a `succeeded` compile job row with
    baked_sha=null, emitted_run_number parsed from the directory
    name, and uploads every file (except evals/** and helix/**)
    as an artifact. Idempotent on (program_version, emitted_run_number).

    Args:
        body (ImportCompileSubmission):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | JobSubmissionResult
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ImportCompileSubmission,
) -> Response[Error | JobSubmissionResult]:
    """Import a legacy local results directory as an ad-hoc compile job

     Accepts a tarball of a results-dir tree (as produced by the old
    launcher). Creates a `succeeded` compile job row with
    baked_sha=null, emitted_run_number parsed from the directory
    name, and uploads every file (except evals/** and helix/**)
    as an artifact. Idempotent on (program_version, emitted_run_number).

    Args:
        body (ImportCompileSubmission):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | JobSubmissionResult]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ImportCompileSubmission,
) -> Error | JobSubmissionResult | None:
    """Import a legacy local results directory as an ad-hoc compile job

     Accepts a tarball of a results-dir tree (as produced by the old
    launcher). Creates a `succeeded` compile job row with
    baked_sha=null, emitted_run_number parsed from the directory
    name, and uploads every file (except evals/** and helix/**)
    as an artifact. Idempotent on (program_version, emitted_run_number).

    Args:
        body (ImportCompileSubmission):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | JobSubmissionResult
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
