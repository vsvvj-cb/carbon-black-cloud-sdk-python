"""Tests for the Job object of the CBC SDK"""

import pytest
import logging
import io
import os
from tempfile import mkstemp
from cbc_sdk.platform import Job
from cbc_sdk.rest_api import CBCloudAPI
from tests.unit.fixtures.CBCSDKMock import CBCSDKMock
from tests.unit.fixtures.platform.mock_jobs import (FIND_ALL_JOBS_RESP, JOB_DETAILS_1, JOB_DETAILS_2, PROGRESS_1,
                                                    PROGRESS_2)


logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG, filename='log.txt')


@pytest.fixture(scope="function")
def cb():
    """Create CBCloudAPI singleton"""
    return CBCloudAPI(url="https://example.com",
                      org_key="test",
                      token="abcd/1234",
                      ssl_verify=False)


@pytest.fixture(scope="function")
def cbcsdk_mock(monkeypatch, cb):
    """Mocks CBC SDK for unit tests"""
    return CBCSDKMock(monkeypatch, cb)


def new_tempfile():
    """Create a temporary file and return the name of it."""
    rc = mkstemp()
    os.close(rc[0])
    return rc[1]


def file_contents(filename):
    """Return a string containing the contents of the file."""
    with io.open(filename, "r", encoding="utf-8") as f:
        return f.read()


# ==================================== UNIT TESTS BELOW ====================================

def test_get_jobs(cbcsdk_mock):
    """Tests getting the list of all jobs."""
    cbcsdk_mock.mock_request('GET', '/jobs/v1/orgs/test/jobs', FIND_ALL_JOBS_RESP)
    api = cbcsdk_mock.api
    query = api.select(Job)
    assert query._count() == 2
    list_jobs = list(query)
    assert len(list_jobs) == 2
    assert list_jobs[0].id == 12345
    assert list_jobs[0].status == 'COMPLETED'
    assert list_jobs[0].progress['num_total'] == 18
    assert list_jobs[0].progress['num_completed'] == 18
    assert list_jobs[1].id == 23456
    assert list_jobs[1].status == 'CREATED'
    assert list_jobs[1].progress['num_total'] == 34
    assert list_jobs[1].progress['num_completed'] == 16


def test_get_jobs_async(cbcsdk_mock):
    """Tests getting the list of all jobs in an asynchronous fashion."""
    cbcsdk_mock.mock_request('GET', '/jobs/v1/orgs/test/jobs', FIND_ALL_JOBS_RESP)
    api = cbcsdk_mock.api
    future = api.select(Job).execute_async()
    list_jobs = future.result()
    assert len(list_jobs) == 2
    assert list_jobs[0].id == 12345
    assert list_jobs[0].status == 'COMPLETED'
    assert list_jobs[0].progress['num_total'] == 18
    assert list_jobs[0].progress['num_completed'] == 18
    assert list_jobs[1].id == 23456
    assert list_jobs[1].status == 'CREATED'
    assert list_jobs[1].progress['num_total'] == 34
    assert list_jobs[1].progress['num_completed'] == 16


@pytest.mark.parametrize("jobid, total, completed, msg, load_return, progress_return", [
    (12345, 18, 18, None, JOB_DETAILS_1, PROGRESS_1),
    (23456, 34, 16, 'Foo', JOB_DETAILS_2, PROGRESS_2)
])
def test_load_job_and_get_progress(cbcsdk_mock, jobid, total, completed, msg, load_return, progress_return):
    """Tests loading a job by ID and getting its progress indicators."""
    cbcsdk_mock.mock_request('GET', f'/jobs/v1/orgs/test/jobs/{jobid}', load_return)
    cbcsdk_mock.mock_request('GET', f'/jobs/v1/orgs/test/jobs/{jobid}/progress', progress_return)
    api = cbcsdk_mock.api
    job = api.select(Job, jobid)
    my_total, my_completed, my_message = job.get_progress()
    assert my_total == total
    assert my_completed == completed
    assert my_message == msg


def test_job_output_export_string(cbcsdk_mock):
    """Tests exporting the results of a job as a string."""
    cbcsdk_mock.mock_request('GET', '/jobs/v1/orgs/test/jobs/12345', JOB_DETAILS_1)
    cbcsdk_mock.mock_request('STREAM:GET', '/jobs/v1/orgs/test/jobs/12345/download',
                             CBCSDKMock.StubResponse("ThisIsFine", 200, "ThisIsFine", False))
    api = cbcsdk_mock.api
    job = api.select(Job, 12345)
    output = job.get_output_as_string()
    assert output == "ThisIsFine"


def test_job_output_export_file(cbcsdk_mock):
    """Tests exporting the results of a job as a file."""
    cbcsdk_mock.mock_request('GET', '/jobs/v1/orgs/test/jobs/12345', JOB_DETAILS_1)
    cbcsdk_mock.mock_request('STREAM:GET', '/jobs/v1/orgs/test/jobs/12345/download',
                             CBCSDKMock.StubResponse("ThisIsFine", 200, "ThisIsFine", False))
    api = cbcsdk_mock.api
    job = api.select(Job, 12345)
    tempfile = new_tempfile()
    try:
        job.get_output_as_file(tempfile)
        assert file_contents(tempfile) == "ThisIsFine"
    finally:
        os.remove(tempfile)


def test_job_output_export_lines(cbcsdk_mock):
    """Tests exporting the results of a query as a list of lines."""
    cbcsdk_mock.mock_request('GET', '/jobs/v1/orgs/test/jobs/12345', JOB_DETAILS_1)
    data = "AAA\r\nBBB\r\nCCC"
    cbcsdk_mock.mock_request('ITERATE:GET', '/jobs/v1/orgs/test/jobs/12345/download',
                             CBCSDKMock.StubResponse(data, 200, data, False))
    api = cbcsdk_mock.api
    job = api.select(Job, 12345)
    output = list(job.get_output_as_lines())
    assert output == ["AAA", "BBB", "CCC"]
