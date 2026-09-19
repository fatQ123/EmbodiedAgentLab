from glob import glob

from setuptools import find_packages, setup

setup(
    name='embodied_comm',
    version='0.2.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/embodied_comm']),
        ('share/embodied_comm', ['package.xml', 'LICENSE']),
        ('share/embodied_comm/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='fatQ123',
    maintainer_email='fatQ123@users.noreply.github.com',
    description='第 2 周独立模拟传感器通信实验',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': [
        'sensor_simulator = embodied_comm.sensor_simulator:main',
        'task_executor = embodied_comm.task_executor:main',
        'status_monitor = embodied_comm.status_monitor:main',
    ]},
)
