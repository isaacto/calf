import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='calf',
    version='0.3',
    python_requires='~=3.5',
    author='Isaac To',
    author_email='isaac.to@gmail.com',
    description='Command Argument Loading Functions',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/isaacto/calf',
    packages=setuptools.find_packages(),
    entry_points={
        "console_scripts": [
            "calf=calf.__main__:main",
        ]
    },
    package_data={'calf': ['py.typed']},
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: Software Development :: Libraries',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
