import asyncio
import pytest

@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test to run asynchronously")

@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    marker = pyfuncitem.get_closest_marker("asyncio")
    if marker is not None:
        loop = pyfuncitem.funcargs.get('event_loop')
        if loop is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        funcargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
        loop.run_until_complete(pyfuncitem.obj(**funcargs))
        return True
