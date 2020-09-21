# *******************************************************
# Copyright (c) VMware, Inc. 2020. All Rights Reserved.
# SPDX-License-Identifier: MIT
# *******************************************************
# *
# * DISCLAIMER. THIS PROGRAM IS PROVIDED TO YOU "AS IS" WITHOUT
# * WARRANTIES OR CONDITIONS OF ANY KIND, WHETHER ORAL OR WRITTEN,
# * EXPRESS OR IMPLIED. THE AUTHOR SPECIFICALLY DISCLAIMS ANY IMPLIED
# * WARRANTIES OR CONDITIONS OF MERCHANTABILITY, SATISFACTORY QUALITY,
# * NON-INFRINGEMENT AND FITNESS FOR A PARTICULAR PURPOSE.

"""Tests for the connection object and related code."""

import pytest
import requests
import ssl
from cbc_sdk.connection import MAX_RETRIES, try_json, Connection
from cbc_sdk.credentials import Credentials
from cbc_sdk.errors import (ApiError, ClientError, ConnectionError, ObjectNotFoundError, QuerySyntaxError, ServerError,
                            TimeoutError, UnauthorizedError)
from tests.unit.fixtures.stubresponse import StubResponse
from mox import Func, IgnoreArg


def test_try_json(mox):
    resp_data = {'Something': 'Going On'}
    resp1 = StubResponse(resp_data)
    resp2 = StubResponse(resp_data)
    mox.StubOutWithMock(resp2, 'json')
    resp2.json().AndRaise(ValueError)
    mox.ReplayAll()
    rc1 = try_json(resp1)
    assert rc1 == resp_data
    rc2 = try_json(resp2)
    assert rc2 == {}
    mox.VerifyAll()


@pytest.mark.parametrize("cdata, msg_prefix", [
    ({}, "Server URL must be a URL"),
    ({'url': 'ftp://example.org'}, "Server URL must be a URL"),
    ({'url': 'https://example.com'}, "No API token provided")
])
def test_initial_connection_error(cdata, msg_prefix):
    creds = Credentials(cdata)
    with pytest.raises(ConnectionError) as excinfo:
        Connection(creds)
    assert excinfo.value.message.startswith(msg_prefix)


@pytest.mark.parametrize("adapter_raises, msg_prefix", [
    (ssl.SSLError, "This version of Python and OpenSSL do not support TLSv1.2"),
    (ValueError, "Unknown error establishing cbapi session")
])
def test_session_adapter_creation_failure(mox, adapter_raises, msg_prefix):
    creds = Credentials({'url': 'https://example.com', 'token': 'ABCDEFGH'})
    import cbc_sdk.connection
    mox.StubOutWithMock(cbc_sdk.connection, 'CbAPISessionAdapter', use_mock_anything=True)
    cbc_sdk.connection.CbAPISessionAdapter(force_tls_1_2=False, max_retries=IgnoreArg(), verify_hostname=True)\
        .AndRaise(adapter_raises)
    mox.ReplayAll()
    with pytest.raises(ApiError) as excinfo:
        Connection(creds)
    assert excinfo.value.message.startswith(msg_prefix)
    mox.VerifyAll()


def test_session_cert_file_and_proxies():
    creds = Credentials({'url': 'https://example.com', 'token': 'ABCDEFGH', 'ssl_cert_file': 'blort',
                         'proxy': 'foobie.bletch.com'})
    conn = Connection(creds)
    assert conn.ssl_verify == 'blort'
    assert conn.proxies['http'] == 'foobie.bletch.com'
    assert conn.proxies['https'] == 'foobie.bletch.com'


def test_session_ignore_system_proxy():
    creds = Credentials({'url': 'https://example.com', 'token': 'ABCDEFGH', 'ignore_system_proxy': True})
    conn = Connection(creds)
    assert conn.proxies['http'] == ''
    assert conn.proxies['https'] == ''
    assert conn.proxies['no'] == 'pass'


@pytest.mark.parametrize("exception_raised, exception_caught, prefix", [
    (requests.Timeout, TimeoutError, None),
    (requests.ConnectionError, ConnectionError, "Received a network connection error from"),
    (ValueError, ApiError, "Unknown exception when connecting to server:")
])
def test_http_request_exception_cases(mox, exception_raised, exception_caught, prefix):
    creds = Credentials({'url': 'https://example.com', 'token': 'ABCDEFGH'})
    conn = Connection(creds)
    mox.StubOutWithMock(conn.session, 'request')
    conn.session.request('GET', 'https://example.com/path', headers=IgnoreArg(), verify=True, proxies=conn.proxies,
                         timeout=conn._timeout).AndRaise(exception_raised)
    mox.ReplayAll()
    with pytest.raises(exception_caught) as excinfo:
        conn.http_request('get', '/path')
    if prefix:
        assert excinfo.value.message.startswith(prefix)
    mox.VerifyAll()


@pytest.mark.parametrize("response, exception_caught, prefix", [
    (StubResponse({}, 502, "Alpha Error"), ServerError, "Alpha Error"),
    (StubResponse({}, 404, "Bravo Error"), ObjectNotFoundError, "Bravo Error"),
    (StubResponse({}, 401, "Charlie Error"), UnauthorizedError, "Charlie Error"),
    (StubResponse({'reason': 'query_malformed_syntax'}, 400, "Delta Error"), QuerySyntaxError, "Delta Error"),
    (StubResponse({}, 400, "Echo Error"), ClientError, "Echo Error")
])
def test_http_request_error_code_cases(mox, response, exception_caught, prefix):
    creds = Credentials({'url': 'https://example.com', 'token': 'ABCDEFGH'})
    conn = Connection(creds)
    mox.StubOutWithMock(conn.session, 'request')
    conn.session.request('GET', 'https://example.com/path', headers=IgnoreArg(), verify=True, proxies=conn.proxies,
                         timeout=conn._timeout).AndReturn(response)
    mox.ReplayAll()
    with pytest.raises(exception_caught) as excinfo:
        conn.http_request('get', '/path')
    assert excinfo.value.message.startswith(prefix)
    mox.VerifyAll()


def test_http_request_happy_path(mox):
    def validate_headers(hdrs):
        assert hdrs['X-Auth-Token'] == 'ABCDEFGH'
        assert hdrs['User-Agent'].startswith("CBC_SDK/")
        assert hdrs['X-Test'] == 'yes'
        return True

    creds = Credentials({'url': 'https://example.com', 'token': 'ABCDEFGH'})
    conn = Connection(creds)
    mox.StubOutWithMock(conn.session, 'request')
    conn.session.request('GET', 'https://example.com/path', headers=Func(validate_headers), verify=True,
                         proxies=conn.proxies, timeout=conn._timeout).AndReturn(StubResponse({'ok': True}))
    mox.ReplayAll()
    resp = conn.http_request('get', '/path', headers={'X-Test': 'yes'})
    assert resp.json()['ok']
    mox.VerifyAll()


def test_request_helper_methods(mox):
    creds = Credentials({'url': 'https://example.com', 'token': 'ABCDEFGH'})
    conn = Connection(creds)
    mox.StubOutWithMock(conn.session, 'request')
    conn.session.request('GET', 'https://example.com/getpath', headers=IgnoreArg(), verify=True,
                         proxies=conn.proxies, timeout=conn._timeout).AndReturn(StubResponse({'get': True}))
    conn.session.request('POST', 'https://example.com/postpath', headers=IgnoreArg(), verify=True,
                         proxies=conn.proxies, timeout=conn._timeout).AndReturn(StubResponse({'post': True}))
    conn.session.request('PUT', 'https://example.com/putpath', headers=IgnoreArg(), verify=True,
                         proxies=conn.proxies, timeout=conn._timeout).AndReturn(StubResponse({'put': True}))
    conn.session.request('DELETE', 'https://example.com/delpath', headers=IgnoreArg(), verify=True,
                         proxies=conn.proxies, timeout=conn._timeout).AndReturn(StubResponse({'delete': True}))
    mox.ReplayAll()
    resp = conn.get('/getpath')
    assert resp.json()['get']
    resp = conn.post('/postpath')
    assert resp.json()['post']
    resp = conn.put('/putpath')
    assert resp.json()['put']
    resp = conn.delete('/delpath')
    assert resp.json()['delete']
    mox.VerifyAll()
