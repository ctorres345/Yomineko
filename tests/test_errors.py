import pytest

from yomineko.core.encodings.tbl import TableError
from yomineko.core.rom.base import RomError
from yomineko.core.roundtrip import LengthChanged
from yomineko.errors import YominekoError
from yomineko.extract import ProfileMismatch
from yomineko.profile.loader import ProfileError


@pytest.mark.parametrize(
    "error", [RomError, ProfileError, ProfileMismatch, TableError, LengthChanged]
)
def test_every_expected_failure_is_a_yomineko_error(error):
    """The CLI shows YominekoError messages without a traceback; anything else is a bug."""
    assert issubclass(error, YominekoError)


def test_errors_that_were_value_errors_still_are():
    assert issubclass(TableError, ValueError)
    assert issubclass(LengthChanged, ValueError)
