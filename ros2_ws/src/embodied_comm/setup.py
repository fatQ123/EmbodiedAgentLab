from glob import glob

from setuptools import find_packages, setup

setup(
    name='embodied_comm',
    version='0.3.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/embodied_comm']),
        ('share/embodied_comm', ['package.xml', 'LICENSE']),
        ('share/embodied_comm/launch', glob('launch/*.launch.py')),
        ('share/embodied_comm/config', glob('config/*.rviz')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='fatQ123',
    maintainer_email='fatQ123@users.noreply.github.com',
    description='第 3 周长任务、坐标变换、监控与故障诊断实验',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': [
        'sensor_simulator = embodied_comm.sensor_simulator:main',
        'task_executor = embodied_comm.task_executor:main',
        'status_monitor = embodied_comm.status_monitor:main',
        'inspection_demo = embodied_comm.inspection_demo:main',
        'service_timeout_demo = embodied_comm.service_timeout_demo:main',
        'week03_day6_evidence = embodied_comm.evidence_recorder:main',
        'spatial_health_monitor = embodied_comm.spatial_health_monitor:main',
        'workcell_visualizer = embodied_comm.workcell_visualizer:main',
    ]},
)
