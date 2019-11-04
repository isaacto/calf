import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='calf',
    version='0.1.5',
    author='Isaac To',
    author_email='isaac.to@gmail.com',
    description='Command Argument Loading Functions',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/isaacto/calf',
    packages=setuptools.find_packages(),
    package_data={'calf': ['py.typed']},
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development :: Libraries',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
