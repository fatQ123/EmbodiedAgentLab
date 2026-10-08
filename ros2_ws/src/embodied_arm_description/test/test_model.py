"""Independent model oracles; SI units, no GUI and no numerical dependencies."""

import importlib.util
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest


PACKAGE = Path(__file__).resolve().parents[1]
TOL = 1e-12
BOXES = {
    'base_link': ((0.12, 0.12, 0.04), (0.0, 0.0, -0.04), 1.0),
    'link1': ((0.4, 0.05, 0.04), (0.2, 0.0, 0.0), 1.0),
    'link2': ((0.3, 0.04, 0.03), (0.15, 0.0, 0.0), 0.75),
}
CHAIN = (
    ('joint1', 'revolute', 'base_link', 'link1', (0.0, 0.0, 0.0)),
    ('joint2', 'revolute', 'link1', 'link2', (0.4, 0.0, 0.0)),
    ('tool0_fixed', 'fixed', 'link2', 'tool0', (0.3, 0.0, 0.0)),
)


def vector(element, attribute):
    assert element is not None, f'missing {attribute} element'
    values = tuple(float(item) for item in element.attrib[attribute].split())
    assert len(values) == 3
    assert all(math.isfinite(item) for item in values)
    return values


def origin(element, expected):
    assert vector(element, 'xyz') == pytest.approx(expected, abs=TOL, rel=0)
    assert vector(element, 'rpy') == pytest.approx((0, 0, 0), abs=TOL, rel=0)


@pytest.fixture(scope='module')
def model():
    # Missing xacro is an error, never a skipped or passing model check.
    import xacro
    document = xacro.process_file(str(PACKAGE / 'urdf/two_link_arm.urdf.xacro'))
    root = ET.fromstring(document.toxml())
    assert root.tag == 'robot'
    assert not any('xacro' in element.tag for element in root.iter())
    return root


def test_unique_tree_and_stage_scope(model):
    links = model.findall('link')
    joints = model.findall('joint')
    assert len(links) == 4
    assert {item.attrib['name'] for item in links} == {'base_link', 'link1', 'link2', 'tool0'}
    assert len(joints) == 3
    assert {item.attrib['name'] for item in joints} == {row[0] for row in CHAIN}
    parents = {item.find('parent').attrib['link'] for item in joints}
    children = [item.find('child').attrib['link'] for item in joints]
    assert len(set(children)) == len(children)
    assert parents - set(children) == {'base_link'}
    assert set(children) == {'link1', 'link2', 'tool0'}
    assert not any(model.iter('gazebo'))
    assert not any(model.iter('ros2_control'))
    assert not any(model.iter('transmission'))


@pytest.mark.parametrize('name,kind,parent,child,offset', CHAIN)
def test_joint_contract(model, name, kind, parent, child, offset):
    joint = model.find(f"joint[@name='{name}']")
    assert joint.attrib['type'] == kind
    assert joint.find('parent').attrib['link'] == parent
    assert joint.find('child').attrib['link'] == child
    origin(joint.find('origin'), offset)
    if kind == 'fixed':
        assert joint.find('limit') is None
        return
    assert vector(joint.find('axis'), 'xyz') == pytest.approx((0, 0, 1), abs=TOL, rel=0)
    limit = joint.find('limit')
    actual = {key: float(limit.attrib[key]) for key in ('lower', 'upper', 'effort', 'velocity')}
    assert actual == pytest.approx(
        {'lower': -math.pi / 2, 'upper': math.pi / 2, 'effort': 10, 'velocity': 1},
        abs=TOL, rel=0)


def assert_inertia(link, center, mass, diagonal):
    inertial = link.find('inertial')
    assert len(link.findall('inertial')) == 1
    origin(inertial.find('origin'), center)
    assert float(inertial.find('mass').attrib['value']) == pytest.approx(mass, abs=TOL, rel=0)
    entries = {key: float(inertial.find('inertia').attrib[key])
               for key in ('ixx', 'ixy', 'ixz', 'iyy', 'iyz', 'izz')}
    assert all(math.isfinite(value) for value in entries.values())
    xx, yy, zz = (entries[key] for key in ('ixx', 'iyy', 'izz'))
    xy, xz, yz = (entries[key] for key in ('ixy', 'ixz', 'iyz'))
    # Sylvester's criterion for the symmetric inertia tensor.
    assert xx > 0
    assert xx * yy - xy * xy > 0
    determinant = xx * yy * zz + 2 * xy * xz * yz - xx * yz**2 - yy * xz**2 - zz * xy**2
    assert determinant > 0
    assert (xx, yy, zz) == pytest.approx(diagonal, abs=TOL, rel=0)
    assert (xy, xz, yz) == pytest.approx((0, 0, 0), abs=TOL, rel=0)
    assert xx + yy >= zz and yy + zz >= xx and zz + xx >= yy


@pytest.mark.parametrize('name', tuple(BOXES))
def test_uniform_boxes_geometry_com_and_inertia(model, name):
    dimensions, center, mass = BOXES[name]
    link = model.find(f"link[@name='{name}']")
    for tag in ('visual', 'collision'):
        assert len(link.findall(tag)) == 1
        element = link.find(tag)
        origin(element.find('origin'), center)
        geometry = element.find('geometry')
        assert len(geometry) == 1 and geometry[0].tag == 'box'
        assert vector(geometry[0], 'size') == pytest.approx(dimensions, abs=TOL, rel=0)
    x, y, z = dimensions
    # Uniform-solid COM inertia, independently derived from dimensional constants.
    expected = (mass * (y*y + z*z) / 12, mass * (x*x + z*z) / 12,
                mass * (x*x + y*y) / 12)
    assert_inertia(link, center, mass, expected)


def test_uniform_tool_sphere(model):
    link = model.find("link[@name='tool0']")
    for tag in ('visual', 'collision'):
        assert len(link.findall(tag)) == 1
        element = link.find(tag)
        origin(element.find('origin'), (0, 0, 0))
        geometry = element.find('geometry')
        assert len(geometry) == 1 and geometry[0].tag == 'sphere'
        assert float(geometry[0].attrib['radius']) == pytest.approx(0.015, abs=TOL, rel=0)
    sphere_inertia = 2 * 0.05 * 0.015**2 / 5
    assert_inertia(link, (0, 0, 0), 0.05, (sphere_inertia,) * 3)


def multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def transform(translation=(0, 0, 0), rpy=(0, 0, 0)):
    roll, pitch, yaw = rpy
    cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch),
                              math.sin(pitch), math.cos(yaw), math.sin(yaw))
    x, y, z = translation
    return [[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr, x],
            [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr, y],
            [-sp, cp*sr, cp*cr, z], [0, 0, 0, 1]]


def urdf_fk(model, angles):
    result = transform()
    for name, kind, _, _, _ in CHAIN:
        joint = model.find(f"joint[@name='{name}']")
        pose = joint.find('origin')
        result = multiply(result, transform(vector(pose, 'xyz'), vector(pose, 'rpy')))
        if kind != 'fixed':
            axis = vector(joint.find('axis'), 'xyz')
            norm = math.sqrt(sum(value * value for value in axis))
            x, y, z = (value / norm for value in axis)
            c, s, t = math.cos(angles[name]), math.sin(angles[name]), 1-math.cos(angles[name])
            rotation = [[t*x*x+c, t*x*y-s*z, t*x*z+s*y, 0],
                        [t*x*y+s*z, t*y*y+c, t*y*z-s*x, 0],
                        [t*x*z-s*y, t*y*z+s*x, t*z*z+c, 0], [0, 0, 0, 1]]
            result = multiply(result, rotation)
    return result


@pytest.mark.parametrize('q1,q2', [
    (0, 0), (math.pi/2, 0), (-math.pi/2, 0), (0, math.pi/2), (0, -math.pi/2),
    (math.pi/2, math.pi/2), (-math.pi/2, -math.pi/2),
    (math.pi/2, -math.pi/2), (-math.pi/2, math.pi/2),
    (math.pi/4, -math.pi/6), (-math.pi/3, math.pi/4),
])
def test_chain_fk_against_independent_planar_formula(model, q1, q2):
    actual = urdf_fk(model, {'joint1': q1, 'joint2': q2})
    theta = q1 + q2
    expected = transform((0.4*math.cos(q1) + 0.3*math.cos(theta),
                          0.4*math.sin(q1) + 0.3*math.sin(theta), 0), (0, 0, theta))
    for row, wanted in zip(actual, expected):
        assert row == pytest.approx(wanted, abs=TOL, rel=0)


@pytest.fixture(scope='module')
def probe():
    path = PACKAGE.parents[2] / 'scripts/verify_week04_description.py'
    spec = importlib.util.spec_from_file_location('description_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('sample', [
    {'names': ['joint1', 'joint2'], 'positions': [0.1, 0]},
    {'names': ['joint1', 'joint2'], 'positions': [0, float('nan')]},
    {'names': ['joint1', 'joint1'], 'positions': [0, 0]},
    {'names': ['joint1', 'joint2'], 'positions': [0]},
    {'names': ['joint1', 'joint2', 'extra'], 'positions': [0, 0, 0]},
])
def test_observer_rejects_invalid_joint_samples(probe, sample):
    assert probe.joint_errors(sample)


def test_observer_accepts_permuted_joint_order(probe):
    assert not probe.joint_errors({'names': ['joint2', 'joint1'], 'positions': [0, 0]})


@pytest.mark.parametrize('translation,quaternion', [
    ([0.71, 0, 0], [0, 0, 0, 1]),
    ([0.7, 0, 0], [0, 0, 0, 2]),
    ([0.7, 0, 0], [0, 0, 1, 0]),
    ([float('nan'), 0, 0], [0, 0, 0, 1]),
])
def test_observer_rejects_incorrect_tf(probe, translation, quaternion):
    assert probe.transform_errors(translation, quaternion, [0.7, 0, 0])


def test_observer_accepts_equivalent_quaternion_sign(probe):
    assert not probe.transform_errors([0.7, 0, 0], [0, 0, 0, -1], [0.7, 0, 0])


@pytest.mark.parametrize('text', [
    '<robot>', '<robot/>', '<launch/>',
    '<robot><link name="base_link"/><joint name="joint1"/></robot>',
])
def test_observer_rejects_malformed_or_incomplete_description(probe, text):
    assert probe.description_errors(text)


@pytest.mark.parametrize('endpoints', [
    [],
    [{'node_name': 'wrong', 'node_namespace': '/', 'topic_type': 'sensor_msgs/msg/JointState'}],
    [{'node_name': 'joint_state_publisher', 'node_namespace': '/other',
      'topic_type': 'sensor_msgs/msg/JointState'}],
    [{'node_name': 'joint_state_publisher', 'node_namespace': '/',
      'topic_type': 'std_msgs/msg/String'}],
    [{'node_name': 'joint_state_publisher', 'node_namespace': '/',
      'topic_type': 'sensor_msgs/msg/JointState'}] * 2,
])
def test_observer_rejects_missing_wrong_or_duplicate_publishers(probe, endpoints):
    assert probe.publisher_errors(endpoints, 'joint_state_publisher', 'sensor_msgs/msg/JointState')


def test_observer_accepts_single_expected_publisher(probe):
    endpoint = {'node_name': 'joint_state_publisher', 'node_namespace': '/',
                'topic_type': 'sensor_msgs/msg/JointState'}
    assert not probe.publisher_errors([endpoint], 'joint_state_publisher', 'sensor_msgs/msg/JointState')


@pytest.mark.parametrize('timeout', ['nan', 'inf', '0', '121'])
def test_observer_refuses_invalid_deadline_without_starting_ros(probe, tmp_path, timeout):
    output = tmp_path / 'never-written.json'
    with pytest.raises(SystemExit) as error:
        probe.main(['--output', str(output), '--timeout', timeout])
    assert error.value.code == 2
    assert not output.exists()


def test_observer_preserves_existing_evidence(probe, tmp_path):
    output = tmp_path / 'existing.json'
    output.write_text('earlier failure evidence\n')
    with pytest.raises(SystemExit) as error:
        probe.main(['--output', str(output)])
    assert error.value.code == 2
    assert output.read_text() == 'earlier failure evidence\n'


@pytest.mark.parametrize('error,status,code', [
    (KeyboardInterrupt(), 'interrupted', 130),
    (ImportError('missing test dependency'), 'environment_blocked', 2),
    (RuntimeError('test observer failure'), 'observer_error', 2),
])
def test_observer_records_distinct_exception_outcomes(probe, monkeypatch, tmp_path, error, status, code):
    import json

    def interrupted_observation(args, report):
        # Exercise outcome handling without creating any ROS node or process.
        report['joint_samples'] = [{'names': ['joint1', 'joint2'], 'positions': [0, 0]}]
        raise error

    monkeypatch.setattr(probe, 'observe', interrupted_observation)
    output = tmp_path / 'exception-report.json'
    assert probe.main(['--output', str(output)]) == code
    report = json.loads(output.read_text())
    assert report['status'] == status
    assert report['exit_code'] == code
    assert report['joint_samples'] == [{'names': ['joint1', 'joint2'], 'positions': [0, 0]}]
    assert report['manual_rviz_acceptance'] == 'pending_manual_acceptance'


@pytest.mark.parametrize('gui,rviz', [(False, False), (False, True), (True, False), (True, True)])
def test_launch_selection_without_executing_nodes(monkeypatch, gui, rviz):
    from launch import Action, LaunchContext
    from launch.actions import DeclareLaunchArgument
    from launch.utilities import perform_substitutions

    path = PACKAGE / 'launch/display.launch.py'
    spec = importlib.util.spec_from_file_location('display_launch_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class CapturedNode(Action):
        def __init__(self, **kwargs):
            # Capture public constructor arguments, never execute a ROS action,
            # subprocess, FindPackageShare resolution or Xacro Command.
            super().__init__(condition=kwargs.get('condition'))
            self.declaration = kwargs

    monkeypatch.setattr(module, 'Node', CapturedNode)
    description = module.generate_launch_description()
    context = LaunchContext()
    arguments = [item for item in description.entities if isinstance(item, DeclareLaunchArgument)]
    assert {item.name for item in arguments} == {'gui', 'rviz'}
    for argument in arguments:
        assert perform_substitutions(context, argument.default_value) == 'false'
        assert set(argument.choices) == {'true', 'false'}
    context.launch_configurations.update(gui=str(gui).lower(), rviz=str(rviz).lower())
    declared_nodes = [item for item in description.entities if isinstance(item, CapturedNode)]
    assert len(declared_nodes) == 4
    active = [item.declaration for item in declared_nodes
              if item.condition is None or item.condition.evaluate(context)]
    publisher = 'joint_state_publisher_gui' if gui else 'joint_state_publisher'
    expected = {'robot_state_publisher', publisher} | ({'rviz2'} if rviz else set())
    assert {item['executable'] for item in active} == expected
    assert len(active) == 2 + int(rviz)
    assert {item['name'] for item in active} == expected
    for item in active:
        parameters = {key: value for group in item['parameters'] for key, value in group.items()}
        assert parameters['use_sim_time'] is False
        if item['executable'] == publisher:
            assert parameters['rate'] == 20
            assert parameters['zeros.joint1'] == 0.0
            assert parameters['zeros.joint2'] == 0.0
        if item['executable'] == 'robot_state_publisher':
            assert parameters['robot_description'].value_type is str


def test_rviz_fixed_frame_displays_and_description_qos():
    import yaml
    configuration = yaml.safe_load((PACKAGE / 'rviz/two_link_arm.rviz').read_text())
    manager = configuration['Visualization Manager']
    assert manager['Global Options']['Fixed Frame'] == 'base_link'
    displays = manager['Displays']
    for name in ('Grid', 'RobotModel', 'TF'):
        matches = [item for item in displays if item['Class'] == f'rviz_default_plugins/{name}']
        assert len(matches) == 1
        assert matches[0]['Enabled'] is True
    robot = next(item for item in displays if item['Class'] == 'rviz_default_plugins/RobotModel')
    assert robot['Visual Enabled'] is True
    assert robot['Description Source'] == 'Topic'
    assert robot['Description Topic'] == {
        'Depth': 1, 'Durability Policy': 'Transient Local', 'History Policy': 'Keep Last',
        'Reliability Policy': 'Reliable', 'Value': '/robot_description',
    }
