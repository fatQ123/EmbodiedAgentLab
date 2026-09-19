import pytest
from rclpy.context import Context


@pytest.fixture
def ros_context():
    context = Context()
    context.init(args=[], domain_id=172)
    yield context
    context.try_shutdown()
